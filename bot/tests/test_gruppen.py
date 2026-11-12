"""Tests für den Signal-Bot: zwei Stufen, Verzug, Ergebnisse, Einladungen."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bengx_bot.gruppen import (GruppenSettings, Verteiler, crv, de, pips,
                               pruefen, text_ergebnis, text_signal)
from bengx_bot.telegram import FakeTransport


class Uhr:
    """Eine Uhr, die nur vorgeht, wenn der Test es sagt.

    Die Vorgabe ist ein Werktag um 11:00 Ortszeit — mitten in der
    London-Sitzung, damit ein Gratis-Signal durchgeht.
    """

    def __init__(self, start: float | None = None, stunde: int = 11,
                 minute: int = 0) -> None:
        if start is None:
            from datetime import datetime
            start = datetime(2026, 3, 10, stunde, minute).timestamp()
        self.jetzt = start

    def __call__(self) -> float:
        return self.jetzt

    def weiter(self, sekunden: float) -> None:
        self.jetzt += sekunden


SIGNAL = {"side": "long", "entry": 4012.40, "sl": 4004.10, "tp": 4029.00,
          "note": "1H-Sweep, 5M-Fortsetzung, 1M-BOS."}


def bauen(ordner: str, inner: str = "-100", vip: str = "-200",
          verzug: int = 20, london: str = "09:00-15:30",
          newyork: str = "15:30-23:00",
          uhr: Uhr | None = None) -> tuple[Verteiler, FakeTransport, Uhr]:
    takt = uhr or Uhr()
    netz = FakeTransport()
    v = Verteiler(
        GruppenSettings(inner_chat_id=inner, vip_chat_id=vip,
                        inner_verzug_min=verzug,
                        frei_london=london, frei_newyork=newyork,
                        state_file=str(Path(ordner) / "gruppen.json")),
        netz, pip=0.1, uhr=takt)
    return v, netz, takt


class TestZahlen(unittest.TestCase):
    def test_deutsche_schreibweise(self):
        self.assertEqual(de(4012.4), "4.012,40")
        self.assertEqual(de(2.5, 1), "2,5")
        self.assertEqual(de(-67.5), "-67,50")

    def test_pips_bei_gold(self):
        # Gold: ein Pip sind 0,10 USD.
        self.assertAlmostEqual(pips(4012.40, 4004.10, 0.1), 83.0, places=3)

    def test_crv(self):
        self.assertAlmostEqual(crv(4012.40, 4004.10, 4029.00), 2.0, places=2)
        self.assertIsNone(crv(100.0, 100.0, 110.0))


class TestPruefen(unittest.TestCase):
    def test_nimmt_sauberes_signal(self):
        raus = pruefen(SIGNAL)
        self.assertEqual(raus["side"], "long")
        self.assertEqual(raus["pair"], "XAU/USD")
        self.assertAlmostEqual(raus["entry"], 4012.40)

    def test_deutsche_woerter_und_komma(self):
        raus = pruefen({"side": "verkaufen", "entry": "4012,40",
                        "sl": "4020,00", "tp": "3995,00"})
        self.assertEqual(raus["side"], "short")
        self.assertAlmostEqual(raus["entry"], 4012.40)

    def test_stop_auf_falscher_seite_bei_long(self):
        falsch = dict(SIGNAL, sl=4020.0)
        with self.assertRaises(ValueError) as fehler:
            pruefen(falsch)
        self.assertIn("Stop unter", str(fehler.exception))

    def test_stop_auf_falscher_seite_bei_short(self):
        falsch = {"side": "short", "entry": 4012.4, "sl": 4000.0, "tp": 3990.0}
        with self.assertRaises(ValueError) as fehler:
            pruefen(falsch)
        self.assertIn("Stop über", str(fehler.exception))

    def test_fehlende_und_kaputte_felder(self):
        with self.assertRaises(ValueError):
            pruefen({"side": "long", "entry": 4012.4, "sl": 4004.1})
        with self.assertRaises(ValueError):
            pruefen(dict(SIGNAL, tp="weiß nicht"))
        with self.assertRaises(ValueError):
            pruefen(dict(SIGNAL, side="seitwärts"))


class TestText(unittest.TestCase):
    def test_vip_bekommt_begruendung_und_crv(self):
        t = text_signal(pruefen(SIGNAL), True, 0.1)
        self.assertIn("1H-Sweep", t)
        self.assertIn("CRV", t)
        self.assertIn("83 Pips", t)

    def test_inner_circle_bekommt_weder_begruendung_noch_crv(self):
        t = text_signal(pruefen(SIGNAL), False, 0.1)
        self.assertNotIn("1H-Sweep", t)
        self.assertNotIn("CRV", t)
        self.assertIn("4.012,40", t)

    def test_beide_tragen_den_hinweis(self):
        for ausfuehrlich in (True, False):
            self.assertIn("Keine Anlageberatung",
                          text_signal(pruefen(SIGNAL), ausfuehrlich, 0.1))

    def test_ergebnis(self):
        t = text_ergebnis(pruefen(SIGNAL), "gewonnen", 166.0)
        self.assertIn("Ziel erreicht", t)
        self.assertIn("+166 Pips", t)
        self.assertNotIn("Pips", text_ergebnis(pruefen(SIGNAL), "be", 0.0))


class TestVerteilen(unittest.TestCase):
    def test_vip_sofort_inner_wartet(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, netz, _ = bauen(ordner)
            raus = v.signal_senden(SIGNAL)
            self.assertEqual(raus["sofort"], ["VIP"])
            self.assertEqual(len(netz.sent), 1)
            self.assertEqual(netz.sent[0]["chat_id"], "-200")
            self.assertIn("Inner Circle in 20 min", raus["wartet"][0])

    def test_inner_geht_erst_nach_ablauf_raus(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, netz, takt = bauen(ordner)
            v.signal_senden(SIGNAL)
            takt.weiter(18 * 60)
            self.assertEqual(v.faellige_senden(), 0)
            self.assertEqual(len(netz.sent), 1)
            takt.weiter(4 * 60)
            self.assertEqual(v.faellige_senden(), 1)
            self.assertEqual(netz.sent[1]["chat_id"], "-100")
            # und nicht ein zweites Mal
            self.assertEqual(v.faellige_senden(), 0)

    def test_wartendes_ueberlebt_den_neustart(self):
        with tempfile.TemporaryDirectory() as ordner:
            takt = Uhr()
            v, netz, _ = bauen(ordner, uhr=takt)
            v.signal_senden(SIGNAL)
            # Neuer Verteiler auf derselben Datei — als wäre der Rechner
            # zwischendurch neu gestartet worden.
            takt.weiter(22 * 60)
            zweiter, netz2, _ = bauen(ordner, uhr=takt)
            self.assertEqual(zweiter.faellige_senden(), 1)
            self.assertEqual(netz2.sent[0]["chat_id"], "-100")

    def test_eigene_kennung_wird_vergeben(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, _, _ = bauen(ordner)
            a = v.signal_senden(SIGNAL)["id"]
            b = v.signal_senden(SIGNAL)["id"]
            self.assertNotEqual(a, b)
            self.assertTrue(a.startswith("sig-"))

    def test_ohne_gruppe_klare_ansage(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, _, _ = bauen(ordner, inner="", vip="")
            self.assertEqual(v.gruppen(), [])
            with self.assertRaises(RuntimeError) as fehler:
                v.signal_senden(SIGNAL)
            self.assertIn("TELEGRAM_INNER_CHAT_ID", str(fehler.exception))

    def test_kaputtes_signal_geht_nirgends_hin(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, netz, _ = bauen(ordner)
            with self.assertRaises(ValueError):
                v.signal_senden(dict(SIGNAL, sl=4020.0))
            self.assertEqual(netz.sent, [])


class TestErgebnis(unittest.TestCase):
    def test_haengt_unter_der_richtigen_nachricht(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, netz, takt = bauen(ordner)
            kennung = v.signal_senden(SIGNAL)["id"]
            takt.weiter(22 * 60)
            v.faellige_senden()
            inner_id = netz.sent[0] and 1
            netz.sent.clear()
            raus = v.ergebnis_senden(kennung, "gewonnen")
            self.assertEqual(raus["gruppen"], ["VIP", "Inner Circle"])
            self.assertEqual(netz.sent[0]["reply_to_message_id"], 1)
            self.assertEqual(netz.sent[1]["reply_to_message_id"], 2)
            self.assertEqual(inner_id, 1)

    def test_pips_werden_aus_ziel_und_stop_gerechnet(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, _, _ = bauen(ordner)
            kennung = v.signal_senden(SIGNAL)["id"]
            self.assertAlmostEqual(
                v.ergebnis_senden(kennung, "gewonnen")["pips"], 166.0, places=0)
            zweites = v.signal_senden(SIGNAL)["id"]
            self.assertAlmostEqual(
                v.ergebnis_senden(zweites, "verloren")["pips"], -83.0, places=0)

    def test_ergebnis_vor_ablauf_zieht_das_signal_nach(self):
        # Sonst stünde in der VIP-Gruppe das Ergebnis vor dem Signal.
        with tempfile.TemporaryDirectory() as ordner:
            v, netz, _ = bauen(ordner)
            kennung = v.signal_senden(SIGNAL)["id"]
            netz.sent.clear()
            v.ergebnis_senden(kennung, "gewonnen")
            an_inner = [n for n in netz.sent if n["chat_id"] == "-100"]
            self.assertEqual(len(an_inner), 2)
            self.assertIn("Einstieg", an_inner[0]["text"])      # erst das Signal
            self.assertIn("Ziel erreicht", an_inner[1]["text"])  # dann das Ergebnis
            self.assertEqual(v.faellige_senden(), 0)           # nichts bleibt übrig

    def test_unbekanntes_signal_und_falscher_status(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, _, _ = bauen(ordner)
            kennung = v.signal_senden(SIGNAL)["id"]
            with self.assertRaises(ValueError):
                v.ergebnis_senden("gibtsnicht", "gewonnen")
            with self.assertRaises(ValueError):
                v.ergebnis_senden(kennung, "naja")


class TestMitglieder(unittest.TestCase):
    def test_einladung_gilt_einmal_und_laeuft_ab(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, netz, takt = bauen(ordner)
            link = v.einladung("inner", "Max", 12)
            self.assertTrue(link.startswith("https://t.me/+"))
            methode, nutzlast = netz.calls[-1]
            self.assertEqual(methode, "createChatInviteLink")
            self.assertEqual(nutzlast["member_limit"], 1)
            self.assertEqual(nutzlast["name"], "Max")
            self.assertEqual(nutzlast["expire_date"], int(takt.jetzt) + 12 * 3600)

    def test_einladung_fuer_unbekannte_gruppe(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, _, _ = bauen(ordner)
            with self.assertRaises(ValueError) as fehler:
                v.einladung("platin")
            self.assertIn("inner", str(fehler.exception))

    def test_ohne_recht_sagt_der_fehler_was_zu_tun_ist(self):
        class Stumm(FakeTransport):
            def call(self, method, payload):
                if method == "createChatInviteLink":
                    return {"ok": False, "result": {}}
                return super().call(method, payload)

        with tempfile.TemporaryDirectory() as ordner:
            v = Verteiler(
                GruppenSettings(inner_chat_id="-100",
                                state_file=str(Path(ordner) / "g.json")),
                Stumm(), uhr=Uhr())
            with self.assertRaises(RuntimeError) as fehler:
                v.einladung("inner")
            self.assertIn("Administrator", str(fehler.exception))

    def test_entfernen_sperrt_nicht_dauerhaft(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, netz, _ = bauen(ordner)
            v.entfernen("vip", "4711")
            methoden = [m for m, _ in netz.calls]
            self.assertEqual(methoden, ["banChatMember", "unbanChatMember"])
            self.assertTrue(netz.calls[1][1]["only_if_banned"])

    def test_entfernen_braucht_eine_zahl(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, _, _ = bauen(ordner)
            with self.assertRaises(ValueError):
                v.entfernen("vip", "@maxmustermann")


class TestAuskunft(unittest.TestCase):
    def test_uebersicht_nennt_beide_stufen(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, _, _ = bauen(ordner)
            text = v.uebersicht()
            self.assertIn("VIP: sofort, mit Begründung", text)
            self.assertIn("Inner Circle: nach 20 min, knapp", text)
            self.assertIn("noch offen: London, New York", text)

    def test_uebersicht_zeigt_wartende(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, _, _ = bauen(ordner)
            v.signal_senden(SIGNAL)
            self.assertIn("Wartend: 1", v.uebersicht())

    def test_letzte_signale_neueste_zuerst(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, _, takt = bauen(ordner)
            erstes = v.signal_senden(SIGNAL)["id"]
            takt.weiter(90)
            zweites = v.signal_senden(SIGNAL)["id"]
            liste = v.letzte(5)
            self.assertEqual([s["id"] for s in liste], [zweites, erstes])


class TestEinstellungen(unittest.TestCase):
    def test_aus_der_umgebung(self):
        s = GruppenSettings.from_env({
            "TELEGRAM_INNER_CHAT_ID": " -100 ",
            "TELEGRAM_VIP_CHAT_ID": "-200",
            "TELEGRAM_INNER_VERZUG": "15",
            "TELEGRAM_FREI_LONDON": "08:00-14:00"})
        self.assertEqual(s.inner_chat_id, "-100")
        self.assertEqual(s.inner_verzug_min, 15)
        self.assertEqual(s.frei_london, "08:00-14:00")
        self.assertEqual(s.frei_newyork, "15:30-23:00")

    def test_ohne_angabe_kein_verzug(self):
        # Die zwei Gratis-Signale sollen mithandelbar sein. Mit Vorsprung
        # waere der Einstieg weg, bevor sie ihn sehen.
        self.assertEqual(GruppenSettings.from_env({}).inner_verzug_min, 0)

    def test_unsinnige_werte_werden_gefangen(self):
        self.assertEqual(
            GruppenSettings.from_env({"TELEGRAM_INNER_VERZUG": "abc"}).inner_verzug_min, 0)
        self.assertEqual(
            GruppenSettings.from_env({"TELEGRAM_INNER_VERZUG": "9999"}).inner_verzug_min, 240)
        self.assertEqual(
            GruppenSettings.from_env({"TELEGRAM_INNER_VERZUG": "-3"}).inner_verzug_min, 0)
        self.assertEqual(
            GruppenSettings.from_env({"TELEGRAM_FREI_LONDON": ""}).frei_london,
            "09:00-15:30")


if __name__ == "__main__":
    unittest.main()


class TestEntwurf(unittest.TestCase):
    """Ein Signal geht an zahlende Leute — die Rückfrage muss im Ablauf stecken."""

    def test_entwurf_verschickt_noch_nichts(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, netz, _ = bauen(ordner)
            raus = v.entwurf(SIGNAL)
            self.assertEqual(netz.sent, [])
            self.assertIn("Inner Circle", raus["vorschau"])
            self.assertIn("1H-Sweep", raus["vorschau"]["VIP"])
            self.assertNotIn("1H-Sweep", raus["vorschau"]["Inner Circle"])

    def test_freigeben_verschickt_den_entwurf(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, netz, _ = bauen(ordner)
            v.entwurf(SIGNAL)
            raus = v.freigeben()
            self.assertEqual(raus["sofort"], ["VIP"])
            self.assertEqual(len(netz.sent), 1)

    def test_ohne_entwurf_geht_nichts_raus(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, netz, _ = bauen(ordner)
            with self.assertRaises(ValueError):
                v.freigeben()
            self.assertEqual(netz.sent, [])

    def test_zweimal_freigeben_schickt_nicht_doppelt(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, netz, _ = bauen(ordner)
            v.entwurf(SIGNAL)
            v.freigeben()
            with self.assertRaises(ValueError):
                v.freigeben()
            self.assertEqual(len(netz.sent), 1)

    def test_alter_entwurf_wird_nicht_mehr_verschickt(self):
        # Ein Einstieg von vor einer Stunde ist kein Einstieg mehr.
        with tempfile.TemporaryDirectory() as ordner:
            v, netz, takt = bauen(ordner)
            v.entwurf(SIGNAL)
            takt.weiter(2 * 3600)
            with self.assertRaises(ValueError) as fehler:
                v.freigeben()
            self.assertIn("zu alt", str(fehler.exception))
            self.assertEqual(netz.sent, [])

    def test_entwurf_ueberlebt_neustart(self):
        with tempfile.TemporaryDirectory() as ordner:
            takt = Uhr()
            v, _, _ = bauen(ordner, uhr=takt)
            v.entwurf(SIGNAL)
            zweiter, netz2, _ = bauen(ordner, uhr=takt)
            zweiter.freigeben()
            self.assertEqual(len(netz2.sent), 1)

    def test_verwerfen(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, netz, _ = bauen(ordner)
            v.entwurf(SIGNAL)
            self.assertIn("verworfen", v.entwurf_verwerfen())
            with self.assertRaises(ValueError):
                v.freigeben()
            self.assertEqual(netz.sent, [])

    def test_kaputter_entwurf_wird_gar_nicht_erst_angelegt(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, _, _ = bauen(ordner)
            with self.assertRaises(ValueError):
                v.entwurf(dict(SIGNAL, sl=4020.0))
            with self.assertRaises(ValueError):
                v.freigeben()


class TestSitzungen(unittest.TestCase):
    """Eins in London, eins in New York — mehr nicht."""

    def test_zweites_in_derselben_sitzung_geht_nur_an_vip(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, netz, takt = bauen(ordner, verzug=0, uhr=Uhr(stunde=10))
            self.assertEqual(v.signal_senden(SIGNAL)["ausgelassen"], [])
            takt.weiter(90 * 60)                      # 11:30, noch London
            raus = v.signal_senden(SIGNAL)
            self.assertEqual(raus["sofort"], ["VIP"])
            self.assertIn("London-Signal von heute ist schon raus",
                          raus["ausgelassen"][0])
            self.assertEqual(len([n for n in netz.sent if n["chat_id"] == "-100"]), 1)

    def test_new_york_hat_ein_eigenes_kontingent(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, netz, takt = bauen(ordner, verzug=0, uhr=Uhr(stunde=10))
            v.signal_senden(SIGNAL)                   # London
            takt.weiter(7 * 3600)                     # 17:00, New York
            self.assertEqual(v.signal_senden(SIGNAL)["ausgelassen"], [])
            self.assertEqual(len([n for n in netz.sent if n["chat_id"] == "-100"]), 2)

    def test_nachts_geht_nichts_an_den_inner_circle(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, netz, _ = bauen(ordner, verzug=0, uhr=Uhr(stunde=3))
            raus = v.signal_senden(SIGNAL)
            self.assertEqual(raus["sofort"], ["VIP"])
            self.assertIn("ausserhalb der Sitzungen", raus["ausgelassen"][0])
            self.assertEqual([n["chat_id"] for n in netz.sent], ["-200"])

    def test_fenster_erkennen(self):
        with tempfile.TemporaryDirectory() as ordner:
            for stunde, minute, erwartet in (
                    (8, 59, None), (9, 0, "london"), (15, 29, "london"),
                    (15, 30, "newyork"), (22, 59, "newyork"), (23, 0, None)):
                v, _, _ = bauen(ordner, uhr=Uhr(stunde=stunde, minute=minute))
                wo = v.fenster_jetzt()
                self.assertEqual(wo[0] if wo else None, erwartet,
                                 f"{stunde:02d}:{minute:02d}")

    def test_naechster_tag_fuellt_beide_wieder_auf(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, _, takt = bauen(ordner, verzug=0, uhr=Uhr(stunde=10))
            v.signal_senden(SIGNAL)
            self.assertIn("New York", v.uebersicht())
            takt.weiter(24 * 3600)
            self.assertEqual(v.signal_senden(SIGNAL)["ausgelassen"], [])

    def test_kontingent_ueberlebt_neustart(self):
        with tempfile.TemporaryDirectory() as ordner:
            takt = Uhr(stunde=10)
            v, _, _ = bauen(ordner, verzug=0, uhr=takt)
            v.signal_senden(SIGNAL)
            zweiter, netz2, _ = bauen(ordner, verzug=0, uhr=takt)
            self.assertIn("schon raus", zweiter.signal_senden(SIGNAL)["ausgelassen"][0])

    def test_gratis_signal_wirbt_fuer_vip(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, netz, _ = bauen(ordner, verzug=0)
            v.signal_senden(SIGNAL)
            an_inner = [n for n in netz.sent if n["chat_id"] == "-100"][0]["text"]
            an_vip = [n for n in netz.sent if n["chat_id"] == "-200"][0]["text"]
            self.assertIn("laufen in VIP", an_inner)
            self.assertNotIn("laufen in VIP", an_vip)

    def test_ergebnis_geht_nicht_an_wer_das_signal_nie_bekam(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, netz, _ = bauen(ordner, verzug=0, uhr=Uhr(stunde=3))
            kennung = v.signal_senden(SIGNAL)["id"]
            netz.sent.clear()
            raus = v.ergebnis_senden(kennung, "gewonnen")
            self.assertEqual(raus["gruppen"], ["VIP"])
            self.assertEqual([n["chat_id"] for n in netz.sent], ["-200"])

    def test_uebersicht_nennt_die_offenen_sitzungen(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, _, takt = bauen(ordner, verzug=0, uhr=Uhr(stunde=10))
            self.assertIn("noch offen: London, New York", v.uebersicht())
            v.signal_senden(SIGNAL)
            self.assertIn("noch offen: New York", v.uebersicht())
            takt.weiter(7 * 3600)
            v.signal_senden(SIGNAL)
            self.assertIn("beide Sitzungen für heute raus", v.uebersicht())


class TestOhneVerzug(unittest.TestCase):
    """So, wie es ab jetzt vorgesehen ist: beide Gruppen gleichzeitig."""

    def test_beide_bekommen_es_sofort(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, netz, _ = bauen(ordner, verzug=0)
            raus = v.signal_senden(SIGNAL)
            self.assertEqual(raus["sofort"], ["VIP", "Inner Circle"])
            self.assertEqual(raus["wartet"], [])
            self.assertEqual(sorted(n["chat_id"] for n in netz.sent), ["-100", "-200"])

    def test_der_unterschied_ist_die_menge_nicht_die_zeit(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, netz, takt = bauen(ordner, verzug=0, uhr=Uhr(stunde=10))
            for _ in range(3):
                v.signal_senden(SIGNAL)
                takt.weiter(30 * 60)
            vip = [n for n in netz.sent if n["chat_id"] == "-200"]
            inner = [n for n in netz.sent if n["chat_id"] == "-100"]
            self.assertEqual(len(vip), 3)
            self.assertEqual(len(inner), 1)
            self.assertIn("CRV", vip[0]["text"])
            self.assertNotIn("CRV", inner[0]["text"])
            self.assertIn("handel sie mit", inner[0]["text"])

    def test_ergebnis_haengt_in_beiden_unter_dem_signal(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, netz, _ = bauen(ordner, verzug=0)
            kennung = v.signal_senden(SIGNAL)["id"]
            netz.sent.clear()
            v.ergebnis_senden(kennung, "gewonnen")
            self.assertEqual(len(netz.sent), 2)
            for n in netz.sent:
                self.assertTrue(n.get("reply_to_message_id"))


class TestRueckblick(unittest.TestCase):
    def test_zaehlt_was_heute_lief(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, netz, takt = bauen(ordner, verzug=0, uhr=Uhr(stunde=10))
            a = v.signal_senden(SIGNAL)["id"]
            v.ergebnis_senden(a, "gewonnen")
            takt.weiter(7 * 3600)
            b = v.signal_senden(SIGNAL)["id"]
            v.ergebnis_senden(b, "verloren")
            text = v.rueckblick_text(v._tag(), True)
            self.assertIn("2 Signale", text)
            self.assertIn("1 im Ziel", text)
            self.assertIn("1 am Stop", text)
            self.assertIn("+83 Pips", text)      # +166 und -83

    def test_ohne_signal_eine_eigene_zeile(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, _, _ = bauen(ordner)
            self.assertIn("kein Signal", v.rueckblick_text(v._tag(), True))

    def test_inner_circle_sagt_wie_viele_dort_ankamen(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, _, takt = bauen(ordner, verzug=0, uhr=Uhr(stunde=10))
            v.signal_senden(SIGNAL)            # London -> auch Inner Circle
            takt.weiter(60 * 60)
            v.signal_senden(SIGNAL)            # zweites London -> nur VIP
            kurz = v.rueckblick_text(v._tag(), False)
            self.assertIn("2 Signale", kurz)
            self.assertIn("davon hier: 1", kurz)
            # In VIP steht der Zusatz nicht, dort kam alles an.
            self.assertNotIn("davon hier", v.rueckblick_text(v._tag(), True))

    def test_faellig_erst_ab_der_zeit_und_nur_einmal(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, _, takt = bauen(ordner, verzug=0, uhr=Uhr(stunde=10))
            v.settings.rueckblick_um = "23:15"
            self.assertFalse(v.rueckblick_faellig())
            takt.weiter(13 * 3600 + 20 * 60)      # 23:20
            self.assertTrue(v.rueckblick_faellig())
            v.rueckblick_senden()
            self.assertFalse(v.rueckblick_faellig())

    def test_abgeschaltet_wenn_keine_zeit_gesetzt(self):
        with tempfile.TemporaryDirectory() as ordner:
            v, _, takt = bauen(ordner, uhr=Uhr(stunde=23, minute=50))
            v.settings.rueckblick_um = ""
            self.assertFalse(v.rueckblick_faellig())
