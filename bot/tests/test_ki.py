"""Tests für die KI. Ohne PyTorch werden sie übersprungen — der Bot selbst braucht es nicht."""

import importlib.util
import unittest

HAT_TORCH = importlib.util.find_spec("torch") is not None


@unittest.skipUnless(HAT_TORCH, "PyTorch nicht installiert")
class TestMerkmale(unittest.TestCase):
    def setUp(self):
        from bengx_ki import lernprobe
        self.kerzen = lernprobe.kerzen(800, zufall=5)

    def test_merkmale_schauen_nicht_in_die_zukunft(self):
        from bengx_ki.merkmale import merkmale
        ganz = merkmale(self.kerzen)
        gekuerzt = merkmale(self.kerzen[:500])
        # Die Zeile für Kerze 400 darf sich nicht ändern, wenn spätere Kerzen fehlen.
        self.assertEqual(ganz[400], gekuerzt[400])

    def test_etikett_trifft_ziel_oder_stop(self):
        from bengx_ki.merkmale import HOCH, RUNTER, ausgaenge
        for a in ausgaenge(self.kerzen, 24, 1.5):
            if a is None:
                continue
            if a.klasse == HOCH:
                self.assertEqual((a.r_long, a.r_short), (1.0, -1.0))
            if a.klasse == RUNTER:
                self.assertEqual((a.r_long, a.r_short), (-1.0, 1.0))
            self.assertTrue(1 <= a.dauer <= 24)


@unittest.skipUnless(HAT_TORCH, "PyTorch nicht installiert")
class TestGehirn(unittest.TestCase):
    def test_spaetere_kerzen_aendern_frueheres_nicht(self):
        import torch
        from bengx_ki.gehirn import Aufmerksamkeit, Bauplan
        torch.manual_seed(0)
        plan = Bauplan(fenster=8, breite=16, koepfe=2, vergessen=0.0)
        att = Aufmerksamkeit(plan).eval()
        x = torch.randn(1, 8, 16)
        y = x.clone()
        y[0, 5:] += 10.0                   # nur die letzten Kerzen verändern
        self.assertTrue(torch.allclose(att(x)[0, :5], att(y)[0, :5], atol=1e-6))

    def test_ausgabe_form(self):
        import torch
        from bengx_ki.gehirn import Bauplan, Gehirn
        g = Gehirn(Bauplan(fenster=16, breite=16, koepfe=2, schichten=1))
        self.assertEqual(g(torch.randn(3, 16, 12)).shape, (3, 3))


@unittest.skipUnless(HAT_TORCH, "PyTorch nicht installiert")
class TestTraining(unittest.TestCase):
    def test_lernen_speichern_laden(self):
        import tempfile
        from pathlib import Path

        import torch
        from bengx_ki import lernprobe
        from bengx_ki.gehirn import Bauplan
        from bengx_ki.training import (Einstellungen, daten_fuer, laden, speichern,
                                       trainieren, wahrscheinlichkeiten)

        kerzen = lernprobe.kerzen(1200, zufall=2)
        plan = Bauplan(fenster=16, breite=16, koepfe=2, schichten=1)
        paket = trainieren(kerzen, plan, Einstellungen(epochen=1), melden=lambda s: None)
        # Der Test-Teil ist das jüngste Stück der Daten, nicht zufällig verstreut.
        stellen = paket["_daten"].stellen
        self.assertEqual(paket["_test"], stellen[len(stellen) - len(paket["_test"]):])

        with tempfile.TemporaryDirectory() as tmp:
            pfad = speichern(paket, Path(tmp) / "m.pt")
            gehirn, geladen = laden(pfad)
            daten = daten_fuer(kerzen, geladen)
            p1 = wahrscheinlichkeiten(paket["_gehirn"], paket["_daten"].tabelle, daten.stellen[:20])
            p2 = wahrscheinlichkeiten(gehirn, daten.tabelle, daten.stellen[:20])
            self.assertTrue(torch.allclose(p1, p2, atol=1e-5))
            self.assertTrue(torch.allclose(p2.sum(dim=1), torch.ones(20), atol=1e-5))


if __name__ == "__main__":
    unittest.main()
