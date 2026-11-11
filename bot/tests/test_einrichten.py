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
