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


class TestNutzung(unittest.TestCase):
    """Grenzen je Modell. Braucht kein PyTorch."""

    def setUp(self):
        import tempfile
        from datetime import datetime, timezone
        self.tmp = tempfile.TemporaryDirectory()
        self.jetzt = datetime(2026, 11, 20, tzinfo=timezone.utc)
        self.pfad = Path(self.tmp.name) / "nutzung.json"
        self.kunde = {"id": "k1", "name": "Anna", "rolle": "kunde", "abo": "start"}
        self.chef = {"id": "i1", "name": "Ben", "rolle": "inhaber", "abo": "start"}

    def tearDown(self):
        self.tmp.cleanup()

    def nutzung(self):
        from bengx_ki.konto import Nutzung
        return Nutzung(self.pfad, uhr=lambda: self.jetzt)

    def test_staerkere_modelle_kosten_mehr(self):
        from bengx_ki.konto import kosten
        self.assertEqual([kosten("analyse", m) for m in ("mini", "standard", "max")], [1, 3, 10])
        self.assertEqual(kosten("strategie", "max"), 50)

    def test_limit_stoppt_nur_dieses_modell(self):
        from bengx_ki.konto import Grenze
        n = self.nutzung()
        for _ in range(10):                      # Start: Standard 30 Tokens = 10 Analysen
            n.abbuchen(self.kunde, "standard", "analyse")
        with self.assertRaises(Grenze) as fehler:
            n.abbuchen(self.kunde, "standard", "analyse")
        self.assertIn("01.12.2026", str(fehler.exception))
        n.abbuchen(self.kunde, "mini", "analyse")  # Mini läuft weiter
        s = n.stand(self.kunde)["modelle"]
        self.assertEqual((s["standard"]["rest"], s["mini"]["verbraucht"]), (0, 1))

    def test_gesperrtes_modell(self):
        from bengx_ki.konto import Grenze
        with self.assertRaises(Grenze):
            self.nutzung().abbuchen(self.kunde, "max", "analyse")   # Max nicht in Start

    def test_inhaber_ohne_grenzen_aber_gezaehlt(self):
        n = self.nutzung()
        for _ in range(200):
            n.abbuchen(self.chef, "max", "strategie")
        s = n.stand(self.chef)
        self.assertTrue(s["unbegrenzt"])
        self.assertEqual((s["modelle"]["max"]["limit"], s["modelle"]["max"]["verbraucht"]),
                         (None, 10000))

    def test_neuer_monat_gibt_frei_und_erstattung(self):
        from datetime import datetime, timezone
        n = self.nutzung()
        n.abbuchen(self.kunde, "mini", "strategie")
        n.erstatten(self.kunde, "mini", "strategie", "kaputt")
        self.assertEqual(n.stand(self.kunde)["modelle"]["mini"]["verbraucht"], 0)
        n.abbuchen(self.kunde, "mini", "strategie")
        self.jetzt = datetime(2026, 12, 2, tzinfo=timezone.utc)
        s = self.nutzung().stand(self.kunde)          # auch nach Neustart
        self.assertEqual(s["modelle"]["mini"]["verbraucht"], 0)
        self.assertEqual(s["auffuellung"], "2027-01-01")

    def test_abo_wechsel_hebt_grenze(self):
        n = self.nutzung()
        self.assertTrue(n.stand(self.kunde)["modelle"]["max"]["gesperrt"])
        self.kunde["abo"] = "pro"
        self.assertEqual(n.stand(self.kunde)["modelle"]["max"]["rest"], 200)


class TestNutzer(unittest.TestCase):
    def test_erster_ist_inhaber_passwort_gehasht(self):
        import tempfile
        from bengx_ki.nutzer import Nutzerliste
        with tempfile.TemporaryDirectory() as tmp:
            liste = Nutzerliste(Path(tmp) / "n.json")
            ben = liste.anlegen("Ben", "geheim123")
            anna = liste.anlegen("Anna", "passwort9", "pro")
            self.assertEqual((ben["rolle"], anna["rolle"]), ("inhaber", "kunde"))
            self.assertNotIn("geheim123", (Path(tmp) / "n.json").read_text())
            self.assertEqual(liste.pruefen("anna", "passwort9")["id"], anna["id"])
            self.assertIsNone(liste.pruefen("Anna", "falsch"))
            self.assertIsNone(liste.pruefen("Niemand", "x"))
            with self.assertRaises(ValueError):
                liste.anlegen("anna", "nochmal123")          # Name schon vergeben
            with self.assertRaises(ValueError):
                liste.anlegen("Kurz", "1234")                # Passwort zu kurz
            with self.assertRaises(ValueError):
                liste.loeschen(ben["id"])                    # Inhaber bleibt


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
        self.app = App(Quelle(None, nur_lernprobe=True), Path(self.tmp.name))
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_fuer(self.app))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.basis = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def rufen(self, pfad, body=None, keks=None):
        import json
        import urllib.error
        import urllib.request
        daten = None if body is None else json.dumps(body).encode()
        kopf = {"Content-Type": "application/json"}
        if keks:
            kopf["Cookie"] = keks
        req = urllib.request.Request(self.basis + pfad, data=daten, headers=kopf)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read() or b"null") if pfad != "/" else None, \
                    (r.headers.get("Set-Cookie") or "").split(";")[0]
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null"), ""

    def einrichten(self):
        _, _, chef = self.rufen("/api/einrichten", {"name": "Ben", "passwort": "geheim123"})
        self.rufen("/api/nutzer", {"name": "Anna", "passwort": "passwort9", "abo": "start"}, chef)
        _, _, kunde = self.rufen("/api/anmelden", {"name": "Anna", "passwort": "passwort9"})
        return chef, kunde

    def test_ohne_anmeldung_nichts(self):
        self.assertEqual(self.rufen("/")[0], 200)
        status, d, _ = self.rufen("/api/ich")
        self.assertTrue(d["einrichten"])
        self.assertEqual(self.rufen("/api/stand")[0], 401)
        self.assertEqual(self.rufen("/api/indikatoren", {})[0], 401)

    def test_einrichten_nur_einmal(self):
        chef, _ = self.einrichten()
        status, _, _ = self.rufen("/api/einrichten", {"name": "Eve", "passwort": "boese1234"})
        self.assertEqual(status, 403)
        self.assertEqual(self.rufen("/api/ich", keks=chef)[1]["nutzer"]["rolle"], "inhaber")

    def test_falsches_passwort_und_bremse(self):
        self.einrichten()
        for _ in range(5):
            self.assertEqual(self.rufen("/api/anmelden", {"name": "Anna", "passwort": "x"})[0], 400)
        status, _, _ = self.rufen("/api/anmelden", {"name": "Anna", "passwort": "passwort9"})
        self.assertEqual(status, 409)                       # erst nach einer Minute wieder

    def test_kunde_darf_nicht_verwalten_und_nicht_trainieren(self):
        _, kunde = self.einrichten()
        self.assertEqual(self.rufen("/api/nutzer", keks=kunde)[0], 403)
        self.assertEqual(self.rufen("/api/training", {"modell": "mini"}, kunde)[0], 403)
        self.assertEqual(self.rufen("/api/nutzer", {"name": "X", "passwort": "12345678"}, kunde)[0], 403)

    def test_nur_json_posts(self):
        import urllib.error
        import urllib.request
        req = urllib.request.Request(self.basis + "/api/anmelden", data=b"name=a",
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        self.assertEqual(e.exception.code, 400)

    def test_indikatoren_frei_und_verlauf_getrennt(self):
        chef, kunde = self.einrichten()
        self.assertEqual(self.rufen("/api/indikatoren", {}, kunde)[0], 200)
        self.assertEqual(self.rufen("/api/indikatoren", {}, chef)[0], 200)
        eigene = self.rufen("/api/verlauf", keks=kunde)[1]
        alle = self.rufen("/api/verlauf", keks=chef)[1]
        self.assertEqual((len(eigene), len(alle)), (1, 2))
        fremd = next(e for e in alle if e["nutzer_name"] == "Ben")
        self.assertEqual(self.rufen(f"/api/verlauf/{fremd['id']}", keks=kunde)[0], 404)

    def test_grenze_429_und_inhaber_frei(self):
        from bengx_ki import lernprobe
        from bengx_ki.gehirn import Bauplan
        from bengx_ki.training import Einstellungen, speichern, trainieren
        chef, kunde = self.einrichten()
        # ohne Modell: Fehler, aber nichts verbraucht
        self.assertEqual(self.rufen("/api/analyse", {"modell": "standard"}, kunde)[0], 400)
        paket = trainieren(lernprobe.kerzen(1200, zufall=2),
                           Bauplan(fenster=16, breite=16, koepfe=2, schichten=1),
                           Einstellungen(epochen=1), melden=lambda s: None)
        for m in ("standard", "max"):
            speichern(paket, self.app.modelle[m].pfad)
        self.assertEqual(self.rufen("/api/analyse", {"modell": "max"}, kunde)[0], 429)
        for _ in range(10):
            self.assertEqual(self.rufen("/api/analyse", {"modell": "standard"}, kunde)[0], 200)
        status, d, _ = self.rufen("/api/analyse", {"modell": "standard"}, kunde)
        self.assertEqual(status, 429)
        self.assertIn("Limit", d["fehler"])
        for _ in range(12):
            self.assertEqual(self.rufen("/api/analyse", {"modell": "max"}, chef)[0], 200)

    def test_nutzung_pro_nutzer_nur_fuer_inhaber(self):
        chef, kunde = self.einrichten()
        self.rufen("/api/indikatoren", {}, kunde)
        anna = next(u for u in self.rufen("/api/nutzer", keks=chef)[1] if u["name"] == "Anna")
        status, d, _ = self.rufen(f"/api/nutzer/{anna['id']}", keks=chef)
        self.assertEqual(status, 200)
        self.assertEqual((d["nutzer"]["name"], len(d["verlauf"])), ("Anna", 1))
        self.assertTrue(d["stand"]["modelle"]["max"]["gesperrt"])
        self.assertNotIn("hash", d["nutzer"])
        self.assertEqual(self.rufen(f"/api/nutzer/{anna['id']}", keks=kunde)[0], 403)
        self.assertEqual(self.rufen("/api/nutzer/gibtsnicht", keks=chef)[0], 404)

    def test_abmelden(self):
        chef, _ = self.einrichten()
        self.rufen("/api/abmelden", {}, chef)
        self.assertEqual(self.rufen("/api/stand", keks=chef)[0], 401)


if __name__ == "__main__":
    unittest.main()
