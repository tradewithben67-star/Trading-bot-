"""Tests für den Nachrichtenleser — er ersetzt das Modell."""

from __future__ import annotations

import unittest

from bengx_bot.lesen import ergebnis_lesen, ja_gesagt, signal_lesen


class TestSignalLesen(unittest.TestCase):
    def test_bens_normale_schreibweise(self):
        r = signal_lesen("long 4012, stop 4004, ziel 4029, 1h sweep und 1m bos")
        self.assertEqual(r["side"], "long")
        self.assertAlmostEqual(r["entry"], 4012)
        self.assertAlmostEqual(r["sl"], 4004)
        self.assertAlmostEqual(r["tp"], 4029)
        self.assertEqual(r["note"], "1h sweep und 1m bos")

    def test_ohne_beschriftung_der_reihe_nach(self):
        r = signal_lesen("short 4021 4028 4008")
        self.assertEqual(r["side"], "short")
        self.assertAlmostEqual(r["entry"], 4021)
        self.assertAlmostEqual(r["sl"], 4028)
        self.assertAlmostEqual(r["tp"], 4008)

    def test_deutsche_und_englische_zahlen(self):
        a = signal_lesen("long 4.012,40 stop 4.004,10 ziel 4.029,00")
        b = signal_lesen("long 4012.40 stop 4004.10 ziel 4029.00")
        self.assertAlmostEqual(a["entry"], 4012.40)
        self.assertAlmostEqual(b["entry"], 4012.40)
        self.assertAlmostEqual(a["sl"], 4004.10)

    def test_andere_woerter(self):
        for text, seite in (("buy 4012 sl 4004 tp 4029", "long"),
                            ("sell 4021 sl 4028 tp 4008", "short"),
                            ("kaufen 4012 stop 4004 ziel 4029", "long"),
                            ("verkaufen 4021 stop 4028 ziel 4008", "short")):
            self.assertEqual(signal_lesen(text)["side"], seite, text)

    def test_reihenfolge_der_marken_egal(self):
        r = signal_lesen("short ziel 4008 einstieg 4021 stop 4028")
        self.assertAlmostEqual(r["entry"], 4021)
        self.assertAlmostEqual(r["sl"], 4028)
        self.assertAlmostEqual(r["tp"], 4008)

    def test_begruendung_mit_zahlen_darin(self):
        # "1h" und "5m" sind keine Kurse.
        r = signal_lesen("long 4012 stop 4004 ziel 4029 nach 1h sweep")
        self.assertAlmostEqual(r["entry"], 4012)
        self.assertAlmostEqual(r["tp"], 4029)

    def test_was_kein_signal_ist(self):
        for text in ("wie läuft es", "hallo", "long", "stop 4004",
                     "long 4012 stop 4004", "", "4012 4004 4029"):
            self.assertIsNone(signal_lesen(text), text)


class TestErgebnisLesen(unittest.TestCase):
    def test_ohne_kennung(self):
        self.assertEqual(ergebnis_lesen("ziel"), ("", "gewonnen"))
        self.assertEqual(ergebnis_lesen("stop"), ("", "verloren"))
        self.assertEqual(ergebnis_lesen("be"), ("", "be"))

    def test_mit_kennung(self):
        self.assertEqual(ergebnis_lesen("sig-0003 ziel"), ("sig-0003", "gewonnen"))
        self.assertEqual(ergebnis_lesen("sig3 stop"), ("sig-0003", "verloren"))

    def test_ganze_saetze(self):
        self.assertEqual(ergebnis_lesen("das letzte ist im ziel")[1], "gewonnen")
        self.assertEqual(ergebnis_lesen("wurde ausgestoppt")[1], "verloren")
        self.assertEqual(ergebnis_lesen("ausgeglichen raus")[1], "be")

    def test_nichts_davon(self):
        for text in ("hallo", "", "wie läuft es"):
            self.assertIsNone(ergebnis_lesen(text), text)


class TestJaNein(unittest.TestCase):
    def test_ja(self):
        for w in ("ja", "J", "ok", "passt", "raus", "schicken", "los"):
            self.assertIs(ja_gesagt(w), True, w)

    def test_nein(self):
        for w in ("nein", "n", "nee", "abbrechen", "verwerfen"):
            self.assertIs(ja_gesagt(w), False, w)

    def test_weder_noch(self):
        for w in ("vielleicht", "", "long 4012"):
            self.assertIsNone(ja_gesagt(w), w)


if __name__ == "__main__":
    unittest.main()
