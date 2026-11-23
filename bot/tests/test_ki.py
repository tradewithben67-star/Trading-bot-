"""Tests für die KI. Ohne PyTorch werden sie übersprungen — der Bot selbst braucht es nicht."""

import importlib.util
import unittest
from pathlib import Path

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


class TestKonto(unittest.TestCase):
    """Tokens brauchen kein PyTorch."""

    def setUp(self):
        import tempfile
        from datetime import datetime, timezone
        self.tmp = tempfile.TemporaryDirectory()
        self.jetzt = datetime(2026, 11, 20, tzinfo=timezone.utc)
        self.pfad = Path(self.tmp.name) / "konto.json"

    def tearDown(self):
        self.tmp.cleanup()

    def konto(self):
        from bengx_ki.konto import Konto
        return Konto(self.pfad, uhr=lambda: self.jetzt)

    def test_start_mit_monatsguthaben(self):
        s = self.konto().stand()
        self.assertEqual((s["abo"], s["abo_rest"], s["extra"]), ("start", 200, 0))
        self.assertEqual(s["auffuellung"], "2026-12-01")

    def test_erst_abo_dann_extra(self):
        k = self.konto()
        k.aufladen(10)
        for _ in range(4):
            k.abbuchen("training")           # 4 × 50 = 200, leert das Abo
        k.abbuchen("analyse")                # 5 kommen aus dem Extra
        s = k.stand()
        self.assertEqual((s["abo_rest"], s["extra"]), (0, 5))

    def test_zu_wenig(self):
        from bengx_ki.konto import ZuWenigTokens
        k = self.konto()
        for _ in range(4):
            k.abbuchen("training")
        with self.assertRaises(ZuWenigTokens):
            k.abbuchen("strategie")
        self.assertEqual(k.stand()["gesamt"], 0)

    def test_neuer_monat_fuellt_auf_extra_bleibt(self):
        from datetime import datetime, timezone
        k = self.konto()
        k.aufladen(7)
        k.abbuchen("training")
        self.jetzt = datetime(2026, 12, 2, tzinfo=timezone.utc)
        s = self.konto().stand()             # auch nach Neustart
        self.assertEqual((s["abo_rest"], s["extra"]), (200, 7))
        self.assertEqual(s["auffuellung"], "2027-01-01")

    def test_abo_wechsel_und_buchungen(self):
        k = self.konto()
        k.abo_wechseln("pro")
        self.assertEqual(k.stand()["abo_rest"], 2000)
        with self.assertRaises(ValueError):
            k.abo_wechseln("gibtsnicht")
        with self.assertRaises(ValueError):
            k.aufladen(-5)
        arten = [b["art"] for b in k.buchungen()]
        self.assertEqual(arten, ["abo", "monat"])


class TestVerlauf(unittest.TestCase):
    def test_eintragen_lesen_filtern(self):
        import tempfile
        from bengx_ki.verlauf import Verlauf
        with tempfile.TemporaryDirectory() as tmp:
            v = Verlauf(Path(tmp) / "v.jsonl")
            a = v.eintragen("analyse", "A", {"kurz": "eins", "gross": [1] * 100}, 5)
            v.eintragen("indikatoren", "I", {"kurz": "zwei"}, 1)
            with v.pfad.open("a") as fh:
                fh.write('{"halb')                     # abgebrochene Zeile
            liste = v.liste()
            self.assertEqual([e["titel"] for e in liste], ["I", "A"])
            self.assertNotIn("daten", liste[0])
            self.assertEqual(v.liste("analyse")[0]["kurz"], "eins")
            self.assertEqual(v.holen(a["id"])["daten"]["gross"], [1] * 100)
            self.assertEqual(v.zaehlen(), {"analyse": 1, "indikatoren": 1})


@unittest.skipUnless(HAT_TORCH, "PyTorch nicht installiert")
class TestServer(unittest.TestCase):
    def setUp(self):
        import tempfile
        import threading
        from http.server import ThreadingHTTPServer
        from bengx_ki.dienste import Quelle
        from bengx_ki.server import App, handler_fuer
        self.tmp = tempfile.TemporaryDirectory()
        ordner = Path(self.tmp.name)
        self.app = App(Quelle(None, nur_lernprobe=True), ordner / "m.pt", ordner)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_fuer(self.app))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.basis = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def rufen(self, pfad, body=None):
        import json
        import urllib.error
        import urllib.request
        daten = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.basis + pfad, data=daten,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def test_seite_und_stand(self):
        import json
        status, html = self.rufen("/")
        self.assertEqual(status, 200)
        self.assertIn("BENGX", html)
        status, roh = self.rufen("/api/stand")
        d = json.loads(roh)
        self.assertEqual(d["konto"]["gesamt"], 200)
        self.assertFalse(d["modell"]["vorhanden"])

    def test_indikatoren_kosten_und_verlauf(self):
        import json
        status, roh = self.rufen("/api/indikatoren", {})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(roh)["tokens"], 1)
        self.assertEqual(self.app.konto.stand()["gesamt"], 199)
        self.assertEqual(len(json.loads(self.rufen("/api/verlauf")[1])), 1)

    def test_ohne_modell_wird_nichts_abgebucht(self):
        status, _ = self.rufen("/api/analyse", {})
        self.assertEqual(status, 400)
        self.assertEqual(self.app.konto.stand()["gesamt"], 200)

    def test_ohne_tokens_402(self):
        for _ in range(4):
            self.app.konto.abbuchen("training")
        status, _ = self.rufen("/api/indikatoren", {})
        self.assertEqual(status, 402)


if __name__ == "__main__":
    unittest.main()
