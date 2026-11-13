"""Tests für die MT5-Brücke und die Marktnamen."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bengx_bot import maerkte
from bengx_bot.mt5bruecke import (Bruecke, BrueckeSettings, FakeMT5, Konto,
                                  Position)


def pos(ticket, symbol="XAUUSD", seite="long", entry=4012.0, sl=4004.0,
        tp=4029.0, volumen=0.1, geoeffnet=1_700_000_000.0):
    return Position(ticket, symbol, seite, entry, sl, tp, volumen, geoeffnet)


def konto(nummer=5001, echt=False):
    return Konto(nummer, "Ben", "Tradequo", "EUR", echt)


def bauen(ordner, positionen=(), fenster=90, mit_konto=None):
    quelle = FakeMT5(list(positionen), mit_konto)
    b = Bruecke(quelle, BrueckeSettings(
        zusammen_sekunden=fenster,
        state_file=str(Path(ordner) / "mt5.json")))
    return b, quelle


class TestMaerkte(unittest.TestCase):
    def test_anhaengsel_fallen_weg(self):
        for roh in ("XAUUSD", "XAUUSD.r", "XAUUSD_i", "XAUUSD#", "xauusd.m"):
            self.assertEqual(maerkte.bereinigen(roh), "XAUUSD", roh)

    def test_anzeigenamen(self):
        self.assertEqual(maerkte.anzeigename("XAUUSD.r"), "GOLD")
        self.assertEqual(maerkte.anzeigename("BTCUSD"), "BTCUSD")
        self.assertEqual(maerkte.anzeigename("GER40"), "DAX")

    def test_unbekanntes_symbol_bleibt_wie_es_ist(self):
        # Lieber der Brokername als ein erfundener.
        self.assertEqual(maerkte.anzeigename("XYZ123"), "XYZ")

    def test_pipgroessen(self):
        self.assertEqual(maerkte.pipgroesse("XAUUSD"), 0.1)
        self.assertEqual(maerkte.pipgroesse("EURUSD"), 0.0001)
        self.assertEqual(maerkte.pipgroesse("USDJPY"), 0.01)
        self.assertIsNone(maerkte.pipgroesse("BTCUSD"))

    def test_nachkommastellen(self):
        self.assertEqual(maerkte.nachkommastellen("XAUUSD"), 2)
        self.assertEqual(maerkte.nachkommastellen("EURUSD"), 5)
        self.assertEqual(maerkte.nachkommastellen("USDJPY"), 3)


class TestNeueTrades(unittest.TestCase):
    def test_erster_lauf_meldet_nichts(self):
        with tempfile.TemporaryDirectory() as d:
            b, _ = bauen(d, [pos(1), pos(2)])
            self.assertEqual(b.gleichstand(), 2)
            self.assertEqual(b.neue(), [])

    def test_neue_position_wird_gemeldet(self):
        with tempfile.TemporaryDirectory() as d:
            b, quelle = bauen(d, [pos(1)])
            b.gleichstand()
            quelle.dazu(pos(2, entry=4015.0))
            raus = b.neue()
            self.assertEqual(len(raus), 1)
            self.assertEqual(raus[0]["pair"], "GOLD")
            self.assertEqual(raus[0]["side"], "long")
            self.assertEqual(raus[0]["tickets"], [2])

    def test_nicht_zweimal_melden(self):
        with tempfile.TemporaryDirectory() as d:
            b, quelle = bauen(d, [])
            quelle.dazu(pos(1))
            self.assertEqual(len(b.neue()), 1)
            self.assertEqual(b.neue(), [])

    def test_geschlossene_position_meldet_nichts_neues(self):
        with tempfile.TemporaryDirectory() as d:
            b, quelle = bauen(d, [])
            quelle.dazu(pos(1))
            b.neue()
            quelle.weg(1)
            self.assertEqual(b.neue(), [])

    def test_ueberlebt_neustart(self):
        with tempfile.TemporaryDirectory() as d:
            b, quelle = bauen(d, [pos(1)])
            b.neue()
            zweite, _ = bauen(d, [pos(1)])
            self.assertEqual(zweite.neue(), [])


class TestTeilziele(unittest.TestCase):
    def test_drei_positionen_werden_ein_signal(self):
        with tempfile.TemporaryDirectory() as d:
            b, quelle = bauen(d, [])
            quelle.dazu(
                pos(1, tp=4029.0, geoeffnet=1000.0),
                pos(2, tp=4045.0, geoeffnet=1010.0),
                pos(3, tp=4060.0, geoeffnet=1020.0))
            raus = b.neue()
            self.assertEqual(len(raus), 1)
            self.assertEqual(raus[0]["ziele"], [4029.0, 4045.0, 4060.0])
            self.assertAlmostEqual(raus[0]["volumen"], 0.3)
            self.assertEqual(raus[0]["tickets"], [1, 2, 3])

    def test_bei_short_liegt_das_naechste_ziel_unten(self):
        with tempfile.TemporaryDirectory() as d:
            b, quelle = bauen(d, [])
            quelle.dazu(
                pos(1, seite="short", entry=4030.0, sl=4040.0, tp=4010.0, geoeffnet=1000.0),
                pos(2, seite="short", entry=4030.0, sl=4040.0, tp=3990.0, geoeffnet=1005.0))
            self.assertEqual(b.neue()[0]["ziele"], [4010.0, 3990.0])

    def test_zu_weit_auseinander_sind_zwei_signale(self):
        with tempfile.TemporaryDirectory() as d:
            b, quelle = bauen(d, [], fenster=90)
            quelle.dazu(pos(1, geoeffnet=1000.0), pos(2, geoeffnet=2000.0))
            self.assertEqual(len(b.neue()), 2)

    def test_andere_richtung_wird_nicht_zusammengefasst(self):
        with tempfile.TemporaryDirectory() as d:
            b, quelle = bauen(d, [])
            quelle.dazu(pos(1, geoeffnet=1000.0),
                        pos(2, seite="short", sl=4020.0, tp=3990.0, geoeffnet=1005.0))
            self.assertEqual(len(b.neue()), 2)

    def test_anderes_symbol_wird_nicht_zusammengefasst(self):
        with tempfile.TemporaryDirectory() as d:
            b, quelle = bauen(d, [])
            quelle.dazu(pos(1, geoeffnet=1000.0),
                        pos(2, symbol="BTCUSD", entry=60000.0, sl=59000.0,
                            tp=62000.0, geoeffnet=1005.0))
            raus = b.neue()
            self.assertEqual(len(raus), 2)
            self.assertEqual({r["pair"] for r in raus}, {"GOLD", "BTCUSD"})

    def test_einstieg_ist_nach_volumen_gewichtet(self):
        with tempfile.TemporaryDirectory() as d:
            b, quelle = bauen(d, [])
            quelle.dazu(pos(1, entry=4000.0, volumen=0.3, geoeffnet=1000.0),
                        pos(2, entry=4010.0, volumen=0.1, geoeffnet=1005.0))
            self.assertAlmostEqual(b.neue()[0]["entry"], 4002.5)

    def test_vergessen_macht_das_melden_rueckgaengig(self):
        with tempfile.TemporaryDirectory() as d:
            b, quelle = bauen(d, [])
            quelle.dazu(pos(1))
            b.neue()
            b.vergessen([1])
            self.assertEqual(len(b.neue()), 1)


if __name__ == "__main__":
    unittest.main()


class TestKonto(unittest.TestCase):
    """Der Bot sucht sich kein Konto aus — er liest das, was im Terminal
    angemeldet ist. Deshalb muss er sagen koennen, welches das ist, und
    merken, wenn ein anderes auftaucht."""

    def test_lesbar_fuer_menschen(self):
        self.assertEqual(str(konto()), "Konto 5001 · Tradequo · Demo")
        self.assertEqual(str(konto(77, echt=True)),
                         "Konto 77 · Tradequo · Echtgeld")

    def test_quelle_ohne_konto_stoert_nicht(self):
        with tempfile.TemporaryDirectory() as d:
            b, _ = bauen(d, [pos(1)])
            self.assertIsNone(b.konto())
            self.assertEqual(b.gleichstand(), 1)

    def test_erster_lauf_meldet_keinen_wechsel(self):
        with tempfile.TemporaryDirectory() as d:
            b, quelle = bauen(d, mit_konto=konto(5001))
            b.gleichstand()
            quelle.dazu(pos(1))
            self.assertEqual(len(b.neue()), 1)
            self.assertIsNone(b.gewechselt)

    def test_anderes_konto_wird_nicht_zu_signalen(self):
        with tempfile.TemporaryDirectory() as d:
            b, quelle = bauen(d, [pos(1)], mit_konto=konto(5001))
            b.gleichstand()

            # Ben meldet sich auf dem Echtgeldkonto an. Dort laufen
            # bereits drei Positionen — die sind kein frisches Signal.
            quelle._konto = konto(9002, echt=True)
            quelle.liste = [pos(10), pos(11, seite="short"), pos(12)]
            self.assertEqual(b.neue(), [])
            self.assertEqual(b.gewechselt, (5001, 9002))

            # Was er danach stellt, schon.
            quelle.dazu(pos(13, symbol="BTCUSD", geoeffnet=1_700_009_999.0))
            frisch = b.neue()
            self.assertEqual(len(frisch), 1)
            self.assertEqual(frisch[0]["pair"], "BTCUSD")

    def test_kontonummer_ueberlebt_den_neustart(self):
        with tempfile.TemporaryDirectory() as d:
            b, quelle = bauen(d, [pos(1)], mit_konto=konto(5001))
            b.gleichstand()

            zweite = Bruecke(FakeMT5([pos(1), pos(2)], konto(9002)),
                             BrueckeSettings(state_file=str(Path(d) / "mt5.json")))
            self.assertEqual(zweite.neue(), [])
            self.assertEqual(zweite.gewechselt, (5001, 9002))
