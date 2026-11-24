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
    def test_loeschen_und_aufbewahrung(self):
        import json
        import tempfile
        from bengx_ki.verlauf import Verlauf
        with tempfile.TemporaryDirectory() as tmp:
            v = Verlauf(Path(tmp) / "v.jsonl")
            v.eintragen("analyse", "A", {"kurz": "a"}, nutzer={"id": "x", "name": "X"})
            v.eintragen("analyse", "B", {"kurz": "b"}, nutzer={"id": "y", "name": "Y"})
            alt = {"id": "alt", "zeit": "2020-01-01T00:00:00+00:00", "bereich": "analyse", "titel": "Alt",
                   "nutzer": "y", "daten": {}}
            with v.pfad.open("a") as fh:
                fh.write(json.dumps(alt) + "\n")
            self.assertEqual(v.bereinigen(365), 1)
            self.assertEqual(v.nutzer_loeschen("x"), 1)
            self.assertEqual([e["titel"] for e in v.liste()], ["B"])


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


def json_text(d):
    import json
    return json.dumps(d, ensure_ascii=False)


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

    def einrichten(self, zustimmen=True):
        _, _, chef = self.rufen("/api/einrichten", {"name": "Ben", "passwort": "geheim123"})
        self.rufen("/api/nutzer", {"name": "Anna", "passwort": "passwort9", "abo": "start"}, chef)
        _, _, kunde = self.rufen("/api/anmelden", {"name": "Anna", "passwort": "passwort9"})
        if zustimmen:
            self.rufen("/api/zustimmung", {"art": "nutzung", "volljaehrig": True,
                                           "nutzungsbedingungen": True, "datenschutz": True}, kunde)
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

    def test_ohne_zustimmung_nur_zustimmen_export_loeschen(self):
        import json
        _, kunde = self.einrichten(zustimmen=False)
        self.assertTrue(self.rufen("/api/ich", keks=kunde)[1]["zustimmung_noetig"])
        status, d, _ = self.rufen("/api/indikatoren", {}, kunde)
        self.assertEqual((status, d.get("zustimmung")), (403, True))
        self.assertEqual(self.rufen("/api/konto/export", keks=kunde)[0], 200)
        # Halbe Zustimmung reicht nicht, Kinder sind ausgeschlossen.
        status, _, _ = self.rufen("/api/zustimmung", {"art": "nutzung", "volljaehrig": False,
                                                      "nutzungsbedingungen": True, "datenschutz": True}, kunde)
        self.assertEqual(status, 400)
        self.rufen("/api/zustimmung", {"art": "nutzung", "volljaehrig": True,
                                       "nutzungsbedingungen": True, "datenschutz": True}, kunde)
        ich = self.rufen("/api/ich", keks=kunde)[1]
        self.assertFalse(ich["zustimmung_noetig"])
        self.assertIn("zeit", ich["nutzer"]["zustimmungen"]["nutzung"])
        self.assertEqual(self.rufen("/api/indikatoren", {}, kunde)[0], 200)
        json.dumps(ich)

    def test_rechtliches_oeffentlich_betreiber_nur_inhaber(self):
        for seite in ("impressum", "datenschutz", "nutzungsbedingungen", "widerruf", "cookies"):
            status, d, _ = self.rufen(f"/api/rechtliches?seite={seite}")
            self.assertEqual(status, 200)
            self.assertTrue(d["bloecke"])
        self.assertFalse(self.rufen("/api/rechtliches?seite=impressum")[1]["vollstaendig"])
        chef, kunde = self.einrichten()
        self.assertEqual(self.rufen("/api/betreiber", keks=kunde)[0], 403)
        self.rufen("/api/betreiber", {"name": "Ben Muster", "anschrift": "Musterweg 1, 12345 Musterstadt",
                                      "email": "kontakt@example.org"}, chef)
        d = self.rufen("/api/rechtliches?seite=impressum")[1]
        self.assertTrue(d["vollstaendig"])
        self.assertIn("Musterweg 1", json_text(d))
        self.assertEqual(self.rufen("/api/betreiber", {"email": "keine-mail"}, chef)[0], 400)

    def test_export_und_konto_loeschen_entfernt_alles(self):
        chef, kunde = self.einrichten()
        self.rufen("/api/indikatoren", {}, kunde)
        self.rufen("/api/indikatoren/eigene", {"name": "EMA 9", "formel": "ema(close, 9)", "anzeige": "chart"}, kunde)
        status, d, _ = self.rufen("/api/konto/export", keks=kunde)
        self.assertEqual((status, len(d["verlauf"]), d["eigene_indikatoren"][0]["name"]), (200, 1, "EMA 9"))
        self.assertNotIn("hash", d["konto"])
        self.assertEqual(self.rufen("/api/konto/loeschen", {"passwort": "falsch"}, kunde)[0], 400)
        self.assertEqual(self.rufen("/api/konto/loeschen", {"passwort": "passwort9"}, kunde)[0], 200)
        self.assertEqual(self.rufen("/api/stand", keks=kunde)[0], 401)
        self.assertEqual(len(self.rufen("/api/verlauf", keks=chef)[1]), 0)
        self.assertEqual(self.rufen("/api/konto/loeschen", {"passwort": "geheim123"}, chef)[0], 400)

    def test_passwort_aendern_und_sicherheits_header(self):
        import urllib.request
        _, kunde = self.einrichten()
        self.assertEqual(self.rufen("/api/konto/passwort", {"alt": "falsch", "neu": "neuesPasswort"}, kunde)[0], 400)
        self.assertEqual(self.rufen("/api/konto/passwort", {"alt": "passwort9", "neu": "neuesPasswort"}, kunde)[0], 200)
        self.assertEqual(self.rufen("/api/anmelden", {"name": "Anna", "passwort": "neuesPasswort"})[0], 200)
        with urllib.request.urlopen(self.basis + "/") as r:
            self.assertIn("default-src 'self'", r.headers["Content-Security-Policy"])
            self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")

    def test_abmelden(self):
        chef, _ = self.einrichten()
        self.rufen("/api/abmelden", {}, chef)
        self.assertEqual(self.rufen("/api/stand", keks=chef)[0], 401)


@unittest.skipUnless(HAT_TORCH and importlib.util.find_spec("anthropic") is not None,
                     "PyTorch oder anthropic nicht installiert")
class TestChat(unittest.TestCase):
    """Der Chat gegen einen Schein-Server, der Claude spielt — echtes SDK, keine Kosten."""

    def setUp(self):
        import json
        import tempfile
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        import anthropic
        from bengx_ki import lernprobe
        from bengx_ki.chat import Chat
        from bengx_ki.dienste import Quelle
        from bengx_ki.gehirn import Bauplan
        from bengx_ki.server import App
        from bengx_ki.training import Einstellungen, speichern, trainieren

        self.anfragen = []
        self.antworten = []
        test = self

        class Claude(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                roh = self.rfile.read(int(self.headers["Content-Length"]))
                test.anfragen.append({"body": json.loads(roh), "beta": self.headers.get("anthropic-beta")})
                antwort = json.dumps(test.antworten.pop(0)).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(antwort)))
                self.end_headers()
                self.wfile.write(antwort)

        self.claude = ThreadingHTTPServer(("127.0.0.1", 0), Claude)
        threading.Thread(target=self.claude.serve_forever, daemon=True).start()
        self.tmp = tempfile.TemporaryDirectory()
        self.app = App(Quelle(None, nur_lernprobe=True), Path(self.tmp.name))
        client = anthropic.Anthropic(api_key="test", max_retries=0,
                                     base_url=f"http://127.0.0.1:{self.claude.server_port}")
        self.app.chat = Chat(self.app, Path(self.tmp.name) / "chats", client=client)
        paket = trainieren(lernprobe.kerzen(1200, zufall=2),
                           Bauplan(fenster=16, breite=16, koepfe=2, schichten=1),
                           Einstellungen(epochen=1), melden=lambda s: None)
        for m in ("standard", "max"):
            speichern(paket, self.app.modelle[m].pfad)
        self.chef = self.app.nutzer.anlegen("Ben", "geheim123")
        self.anna = self.app.nutzer.anlegen("Anna", "passwort9", "start")
        for n in (self.chef, self.anna):
            self.app.nutzer.zustimmen(n["id"], "chat", "1")
        self.chef, self.anna = self.app.nutzer.holen(self.chef["id"]), self.app.nutzer.holen(self.anna["id"])

    def tearDown(self):
        self.claude.shutdown()
        self.claude.server_close()
        self.tmp.cleanup()

    @staticmethod
    def nachricht(inhalt, stop):
        return {"id": "msg_test", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
                "content": inhalt, "stop_reason": stop, "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 10}}

    def test_werkzeug_runde_mit_analyse(self):
        import json
        self.antworten = [
            self.nachricht([{"type": "text", "text": "Ich schaue nach."},
                            {"type": "tool_use", "id": "toolu_1", "name": "ki_analyse",
                             "input": {"modell": "standard", "schwelle": 0.5}}], "tool_use"),
            self.nachricht([{"type": "text", "text": "Die KI sieht leicht steigende Kurse."}], "end_turn"),
        ]
        antwort = self.app.chat_senden(self.anna, {"bereich": "analyse", "text": "Warum dieses Setup?"})
        self.assertIn("leicht steigende", antwort["antwort"]["text"])
        karte = antwort["antwort"]["anhaenge"][0]["eintrag"]
        self.assertEqual(karte["bereich"], "analyse")
        self.assertIn("gruende", karte["daten"])
        self.assertIn("chart", karte["daten"])
        # Die Anfrage an Claude: richtiges Modell, Werkzeuge, Kontextzeile, Rückfall-Beta.
        erste = self.anfragen[0]
        self.assertEqual(erste["body"]["model"], "claude-opus-5-5")
        self.assertIn("server-side-fallback-2026-07-01", erste["beta"])
        self.assertTrue(erste["body"]["messages"][0]["content"].startswith("[Seite: Analyse"))
        self.assertNotIn("Anna", json_text(erste["body"]))        # Name geht nicht an Anthropic
        ergebnis = self.anfragen[1]["body"]["messages"][-1]["content"][0]
        self.assertEqual(ergebnis["tool_use_id"], "toolu_1")
        self.assertIn("gruende", json.loads(ergebnis["content"]))
        # Verbraucht: eine Chat-Nachricht und 3 Tokens Standard.
        s = self.app.nutzung.stand(self.anna)
        self.assertEqual((s["chat"]["verbraucht"], s["modelle"]["standard"]["verbraucht"]), (1, 3))
        # Der Faden bleibt: die nächste Anfrage enthält das ganze Gespräch.
        self.antworten = [self.nachricht([{"type": "text", "text": "Gern."}], "end_turn")]
        self.app.chat_senden(self.anna, {"bereich": "analyse", "text": "Danke"})
        self.assertEqual(len(self.anfragen[-1]["body"]["messages"]), 5)

    def test_grenze_im_werkzeug_wird_gemeldet(self):
        self.antworten = [
            self.nachricht([{"type": "tool_use", "id": "toolu_2", "name": "ki_analyse",
                             "input": {"modell": "max", "schwelle": 0.5}}], "tool_use"),
            self.nachricht([{"type": "text", "text": "Max ist nicht in deinem Abo."}], "end_turn"),
        ]
        self.app.chat_senden(self.anna, {"bereich": "allgemein", "text": "Analysiere mit Max"})
        ergebnis = self.anfragen[1]["body"]["messages"][-1]["content"][0]
        self.assertTrue(ergebnis["is_error"])
        self.assertIn("nicht enthalten", ergebnis["content"])

    def test_indikator_per_chat_speichern(self):
        self.antworten = [
            self.nachricht([{"type": "tool_use", "id": "toolu_3", "name": "indikator_speichern",
                             "input": {"name": "RSI 21", "formel": "rsi(close, 21)", "anzeige": "unten"}}], "tool_use"),
            self.nachricht([{"type": "text", "text": "Gespeichert."}], "end_turn"),
        ]
        a = self.app.chat_senden(self.anna, {"bereich": "indikatoren", "text": "Bau mir einen RSI 21"})
        self.assertEqual(self.app.eigene.liste(self.anna["id"])[0]["formel"], "rsi(close, 21)")
        self.assertIn("werte", a["antwort"]["anhaenge"][0]["auswertung"])

    def test_ohne_chat_hinweis_kein_chat(self):
        from bengx_ki.server import ChatHinweisFehlt
        neu = self.app.nutzer.anlegen("Neu", "passwort9", "pro")
        with self.assertRaises(ChatHinweisFehlt):
            self.app.chat_senden(neu, {"bereich": "allgemein", "text": "Hallo"})
        self.assertEqual(self.anfragen, [])

    def test_chat_limit_und_erstattung_bei_fehler(self):
        from bengx_ki.konto import Grenze
        self.antworten = []          # der Schein-Server hat nichts → Fehler
        with self.assertRaises(Exception):
            self.app.chat_senden(self.anna, {"bereich": "allgemein", "text": "Hallo"})
        self.assertEqual(self.app.nutzung.stand(self.anna)["chat"]["verbraucht"], 0)
        for _ in range(30):
            self.app.nutzung.chat_abbuchen(self.anna)
        with self.assertRaises(Grenze):
            self.app.chat_senden(self.anna, {"bereich": "allgemein", "text": "Hallo"})
        self.antworten = [self.nachricht([{"type": "text", "text": "Hallo Ben"}], "end_turn")]
        self.assertEqual(self.app.chat_senden(self.chef, {"bereich": "allgemein", "text": "Hallo"})["antwort"]["text"], "Hallo Ben")


if __name__ == "__main__":
    unittest.main()
