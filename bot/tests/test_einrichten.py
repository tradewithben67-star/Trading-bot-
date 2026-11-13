"""Tests für das Einrichtungsprogramm — nur die Teile ohne Netz."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("einrichten", WURZEL / "einrichten.py")
einrichten = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(einrichten)


class TestMaskieren(unittest.TestCase):
    def test_lange_geheimnisse_zeigen_nur_die_raender(self):
        self.assertEqual(einrichten.maskieren("123456789:AAHgeheim"), "1234…heim")

    def test_kurze_werden_ganz_verdeckt(self):
        self.assertEqual(einrichten.maskieren("kurz"), "****")
        self.assertEqual(einrichten.maskieren(""), "")


class TestLesen(unittest.TestCase):
    def test_werte_kommentare_und_leerzeilen(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text('# Kommentar\nA="eins"\n\nB=zwei\nKAPUTT\n', encoding="utf-8")
            werte = einrichten.lesen(p)
            self.assertEqual(werte, {"A": "eins", "B": "zwei"})

    def test_fehlende_datei(self):
        self.assertEqual(einrichten.lesen(Path("/gibt/es/nicht")), {})


class TestZusammenfuehren(unittest.TestCase):
    VORLAGE = "# Hinweis\nTELEGRAM_TOKEN=\nTELEGRAM_CHAT_ID=\n\n# BENGX_CODER=1\n"

    def test_werte_landen_an_ihrer_stelle(self):
        text = einrichten.zusammenfuehren(
            self.VORLAGE, {"TELEGRAM_TOKEN": "abc:1", "TELEGRAM_CHAT_ID": "42"})
        self.assertIn("TELEGRAM_TOKEN=abc:1", text)
        self.assertIn("TELEGRAM_CHAT_ID=42", text)

    def test_kommentare_bleiben_stehen(self):
        text = einrichten.zusammenfuehren(self.VORLAGE, {"TELEGRAM_TOKEN": "x:1"})
        self.assertIn("# Hinweis", text)
        self.assertIn("# BENGX_CODER=1", text)

    def test_unbekannte_werte_kommen_ans_ende(self):
        text = einrichten.zusammenfuehren(self.VORLAGE, {"BENGX_CODER": "1"})
        self.assertTrue(text.rstrip().endswith("BENGX_CODER=1"))

    def test_auskommentiertes_wird_nicht_ueberschrieben(self):
        text = einrichten.zusammenfuehren(self.VORLAGE, {"BENGX_CODER": "1"})
        self.assertEqual(text.count("BENGX_CODER"), 2)   # Kommentar plus Wert

    def test_datei_endet_mit_genau_einem_umbruch(self):
        text = einrichten.zusammenfuehren(self.VORLAGE, {"TELEGRAM_TOKEN": "x:1"})
        self.assertTrue(text.endswith("\n"))
        self.assertFalse(text.endswith("\n\n"))

    def test_runde_reise_durch_lesen(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text(einrichten.zusammenfuehren(
                self.VORLAGE, {"TELEGRAM_TOKEN": "abc:1", "TELEGRAM_CHAT_ID": "42",
                               "BENGX_CODER": "1"}), encoding="utf-8")
            werte = einrichten.lesen(p)
            self.assertEqual(werte["TELEGRAM_TOKEN"], "abc:1")
            self.assertEqual(werte["TELEGRAM_CHAT_ID"], "42")
            self.assertEqual(werte["BENGX_CODER"], "1")


class TestChatKennung(unittest.TestCase):
    def test_aus_einer_nachricht(self):
        self.assertEqual(
            einrichten.chat_aus_updates(
                {"result": [{"message": {"chat": {"id": 42, "first_name": "Ben"}}}]}),
            ("42", "Ben"))

    def test_aus_einer_bearbeiteten_nachricht(self):
        self.assertEqual(
            einrichten.chat_aus_updates(
                {"result": [{"edited_message": {"chat": {"id": 7,
                                                         "username": "ben"}}}]}),
            ("7", "ben"))

    def test_ohne_namen(self):
        self.assertEqual(
            einrichten.chat_aus_updates({"result": [{"message": {"chat": {"id": 9}}}]}),
            ("9", ""))

    def test_leere_antwort(self):
        self.assertIsNone(einrichten.chat_aus_updates({"result": []}))
        self.assertIsNone(einrichten.chat_aus_updates({}))

    def test_update_ohne_chat(self):
        self.assertIsNone(einrichten.chat_aus_updates(
            {"result": [{"my_chat_member": {}}]}))


if __name__ == "__main__":
    unittest.main()


class TestTokenErkennen(unittest.TestCase):
    def test_echte_form(self):
        self.assertTrue(einrichten.sieht_aus_wie_token(
            "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"))

    def test_falsche_formen(self):
        for text in ("", "kein-token", "abc:def", "123456789:kurz",
                     "123456789 :AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw",
                     "x" * 300):
            self.assertFalse(einrichten.sieht_aus_wie_token(text), text)

    def test_leerzeichen_aussen_stoeren_nicht(self):
        self.assertTrue(einrichten.sieht_aus_wie_token(
            "  123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw  "))


class TestZwischenablage(unittest.TestCase):
    def test_gibt_leer_zurueck_wenn_nichts_geht(self):
        import subprocess
        echt = subprocess.run
        subprocess.run = lambda *a, **k: (_ for _ in ()).throw(OSError("nope"))
        try:
            self.assertEqual(einrichten.zwischenablage(), "")
        finally:
            subprocess.run = echt

    def test_liest_die_ausgabe(self):
        import subprocess
        from types import SimpleNamespace
        echt = subprocess.run
        subprocess.run = lambda *a, **k: SimpleNamespace(
            returncode=0, stdout="  geheim  \n", stderr="")
        try:
            self.assertEqual(einrichten.zwischenablage(), "geheim")
        finally:
            subprocess.run = echt


class TestAlteEinstellungenFinden(unittest.TestCase):
    """Beim Umstieg auf eine neue Fassung soll nichts neu eingetippt werden."""

    def test_findet_nachbarordner(self):
        with tempfile.TemporaryDirectory() as d:
            wurzel = Path(d)
            alt = wurzel / "Trading-bot--alt" / "bot"
            neu = wurzel / "Trading-bot--neu" / "bot"
            alt.mkdir(parents=True)
            neu.mkdir(parents=True)
            (alt / ".env").write_text("TELEGRAM_TOKEN=1:abc\n", encoding="utf-8")
            gefunden = einrichten.alte_einstellungen(neu)
            self.assertEqual([p.parent.parent.name for p in gefunden],
                             ["Trading-bot--alt"])

    def test_findet_sich_nicht_selbst(self):
        with tempfile.TemporaryDirectory() as d:
            hier = Path(d) / "Trading-bot-" / "bot"
            hier.mkdir(parents=True)
            (hier / ".env").write_text("TELEGRAM_TOKEN=1:abc\n", encoding="utf-8")
            self.assertEqual(einrichten.alte_einstellungen(hier), [])

    def test_ohne_nachbarn_leer(self):
        with tempfile.TemporaryDirectory() as d:
            hier = Path(d) / "nur" / "bot"
            hier.mkdir(parents=True)
            self.assertEqual(einrichten.alte_einstellungen(hier), [])

    def test_neueste_zuerst(self):
        import os as _os
        import time as _time
        with tempfile.TemporaryDirectory() as d:
            wurzel = Path(d)
            neu = wurzel / "c" / "bot"
            neu.mkdir(parents=True)
            for name, alter in (("a", 100), ("b", 0)):
                ordner = wurzel / name / "bot"
                ordner.mkdir(parents=True)
                datei = ordner / ".env"
                datei.write_text("TELEGRAM_TOKEN=1:abc\n", encoding="utf-8")
                _os.utime(datei, (_time.time() - alter, _time.time() - alter))
            gefunden = einrichten.alte_einstellungen(neu)
            self.assertEqual(gefunden[0].parent.parent.name, "b")


class TestGruppenErkennen(unittest.TestCase):
    """Gruppen sollen sich selbst melden, statt dass Ben Kennungen sucht."""

    def test_findet_gruppen_ohne_doppelte(self):
        antwort = {"result": [
            {"message": {"chat": {"id": -1001, "type": "supergroup", "title": "Inner Circle"}}},
            {"message": {"chat": {"id": -1002, "type": "group", "title": "VIP"}}},
            {"message": {"chat": {"id": -1001, "type": "supergroup", "title": "Inner Circle"}}},
        ]}
        self.assertEqual(einrichten.gruppen_aus_updates(antwort),
                         [("-1001", "Inner Circle"), ("-1002", "VIP")])

    def test_einzelchats_sind_keine_gruppen(self):
        antwort = {"result": [
            {"message": {"chat": {"id": 42, "type": "private", "first_name": "Ben"}}}]}
        self.assertEqual(einrichten.gruppen_aus_updates(antwort), [])

    def test_ohne_titel_steht_die_kennung_da(self):
        antwort = {"result": [{"message": {"chat": {"id": -7, "type": "group"}}}]}
        self.assertEqual(einrichten.gruppen_aus_updates(antwort), [("-7", "-7")])

    def test_gruppe_wird_nicht_zur_persoenlichen_kennung(self):
        # Haengt der Bot schon in einer Gruppe und diese schreibt zuerst,
        # kam sonst deren Kennung als TELEGRAM_CHAT_ID heraus — danach haette
        # der Bot nur noch die Gruppe bedient statt Ben.
        antwort = {"result": [
            {"message": {"chat": {"id": -1001, "type": "supergroup", "title": "VIP"}}},
            {"message": {"chat": {"id": 42, "type": "private", "first_name": "Ben"}}},
        ]}
        self.assertEqual(einrichten.chat_aus_updates(antwort), ("42", "Ben"))

    def test_leeres_ergebnis(self):
        self.assertEqual(einrichten.gruppen_aus_updates({}), [])
        self.assertEqual(einrichten.gruppen_aus_updates({"result": []}), [])


class TestZweiterBot(unittest.TestCase):
    """409 heisst: ein zweiter Bot hoert schon zu. Das muss gesagt werden,
    statt 90 Sekunden ins Leere zu warten."""

    def test_409_wird_zu_einer_eigenen_meldung(self):
        import urllib.error, io
        def kaputt(*a, **k):
            raise urllib.error.HTTPError("u", 409, "Conflict", {}, io.BytesIO(b"{}"))
        alt = einrichten.urllib.request.urlopen
        einrichten.urllib.request.urlopen = kaputt
        try:
            with self.assertRaises(einrichten.LaeuftSchon):
                einrichten.telegram("t", "getUpdates")
        finally:
            einrichten.urllib.request.urlopen = alt

    def test_andere_fehler_bleiben_wie_sie_sind(self):
        import urllib.error, io
        def kaputt(*a, **k):
            raise urllib.error.HTTPError("u", 401, "Unauthorized", {}, io.BytesIO(b"{}"))
        alt = einrichten.urllib.request.urlopen
        einrichten.urllib.request.urlopen = kaputt
        try:
            with self.assertRaises(urllib.error.HTTPError):
                einrichten.telegram("t", "getUpdates")
        finally:
            einrichten.urllib.request.urlopen = alt

    def test_gruppensuche_bricht_ab_statt_zu_warten(self):
        import urllib.error, io, time
        def kaputt(*a, **k):
            raise urllib.error.HTTPError("u", 409, "Conflict", {}, io.BytesIO(b"{}"))
        alt = einrichten.urllib.request.urlopen
        einrichten.urllib.request.urlopen = kaputt
        t0 = time.time()
        try:
            self.assertEqual(einrichten.gruppen_suchen("t", sekunden=90), [])
        finally:
            einrichten.urllib.request.urlopen = alt
        self.assertLess(time.time() - t0, 5, "haette sofort abbrechen muessen")


class TestNachtrag(unittest.TestCase):
    """Neue Einstellungen muessen auch den erreichen, der laengst
    eingerichtet hat.

    Genau hier ist es schiefgegangen: nach „Übernehmen?" ging die
    Einrichtung sofort raus, die MetaTrader-Frage kam nie, und im
    Fenster stand dann „MetaTrader: aus".
    """

    def _lauf(self, inhalt: str, antworten: list[bool]):
        with tempfile.TemporaryDirectory() as d:
            env = Path(d) / ".env"
            if inhalt:
                env.write_text(inhalt, encoding="utf-8")
            alt_env, alt_vorlage = einrichten.ENV, einrichten.VORLAGE
            alt_ja, alt_pakete = einrichten.ja, einrichten.pakete_nachziehen
            gefragt: list[str] = []
            einrichten.ENV = env
            einrichten.VORLAGE = Path(d) / "gibt-es-nicht"
            einrichten.pakete_nachziehen = lambda werte: None

            def ja(text, standard=False):
                gefragt.append(text)
                return antworten.pop(0) if antworten else standard

            einrichten.ja = ja
            try:
                werte = einrichten.lesen(env)
                geaendert = einrichten.nachtrag(werte)
                return geaendert, einrichten.lesen(env), gefragt
            finally:
                einrichten.ENV, einrichten.VORLAGE = alt_env, alt_vorlage
                einrichten.ja, einrichten.pakete_nachziehen = alt_ja, alt_pakete

    def test_fragt_nach_metatrader_wenn_es_fehlt(self):
        geaendert, werte, gefragt = self._lauf(
            "TELEGRAM_TOKEN=1:abc\n", [True, False])
        self.assertTrue(geaendert)
        self.assertEqual(werte["MT5"], "1")
        self.assertEqual(werte["MT5_OHNE_RUECKFRAGE"], "0")
        self.assertEqual(werte["TELEGRAM_TOKEN"], "1:abc")
        self.assertTrue(any("Einschalten" in t for t in gefragt))

    def test_nein_schreibt_null_und_fragt_nicht_weiter(self):
        geaendert, werte, gefragt = self._lauf(
            "TELEGRAM_TOKEN=1:abc\n", [False])
        self.assertTrue(geaendert)
        self.assertEqual(werte["MT5"], "0")
        self.assertNotIn("MT5_OHNE_RUECKFRAGE", werte)
        self.assertEqual(len(gefragt), 1)

    def test_schweigt_wenn_schon_beantwortet(self):
        geaendert, werte, gefragt = self._lauf(
            "TELEGRAM_TOKEN=1:abc\nMT5=0\n", [True])
        self.assertFalse(geaendert)
        self.assertEqual(gefragt, [])
        self.assertEqual(werte["MT5"], "0")
