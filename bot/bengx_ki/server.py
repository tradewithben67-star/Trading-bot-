"""Die Oberfläche: ein kleiner Webserver auf dem eigenen Rechner.

    python -m bengx_ki oberflaeche --csv data/xauusd_h1.csv

Er hört nur auf 127.0.0.1, ist also von außen nicht erreichbar. Eine Anmeldung
gibt es deshalb noch nicht. Bevor die Oberfläche für Abonnenten ins Netz geht,
braucht es Anmeldung und ein Konto je Nutzer.

Schnittstelle (alles JSON):

    GET  /api/stand                 Überblick: Tokens, Modell, Daten, letzte Analyse
    GET  /api/verlauf[?bereich=…]   Historie, neueste zuerst
    GET  /api/verlauf/<id>          ein Eintrag mit allen Details
    GET  /api/konto                 Tokens, Abos, Buchungen
    GET  /api/training              Stand eines laufenden Trainings
    POST /api/analyse               kostet Tokens
    POST /api/indikatoren           kostet Tokens
    POST /api/strategie             kostet Tokens
    POST /api/training              startet ein Training, kostet Tokens
    POST /api/konto/aufladen        {"menge": 500}
    POST /api/konto/abo             {"abo": "pro"}
"""

from __future__ import annotations

import json
import threading
import time
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import dienste
from .auswertung import kennzahlen
from .gehirn import Bauplan
from .konto import KOSTEN, Konto, ZuWenigTokens
from .training import Einstellungen, speichern, trainieren, wahrscheinlichkeiten
from .verlauf import Verlauf

SEITE = Path(__file__).with_name("oberflaeche.html")


class Training:
    """Ein Training im Hintergrund, damit die Oberfläche weiter bedienbar bleibt."""

    def __init__(self) -> None:
        self.status = "bereit"          # bereit, laeuft, fertig, fehler
        self.zeilen: list[str] = []
        self.start = 0.0
        self.ende = 0.0
        self._sperre = threading.Lock()

    def info(self) -> dict:
        with self._sperre:
            return {"status": self.status, "zeilen": self.zeilen[-400:],
                    "start": self.start, "ende": self.ende}

    def melden(self, text: str) -> None:
        with self._sperre:
            self.zeilen.append(text)

    def beginnen(self) -> bool:
        with self._sperre:
            if self.status == "laeuft":
                return False
            self.status, self.zeilen = "laeuft", []
            self.start, self.ende = time.time(), 0.0
            return True

    def beenden(self, status: str) -> None:
        with self._sperre:
            self.status, self.ende = status, time.time()


class App:
    def __init__(self, quelle: dienste.Quelle, modell: str | Path, ordner: str | Path,
                 epochen: int = 30) -> None:
        ordner = Path(ordner)
        self.quelle = quelle
        self.modell = dienste.Modellablage(modell)
        self.konto = Konto(ordner / "konto.json")
        self.verlauf = Verlauf(ordner / "verlauf.jsonl")
        self.training = Training()
        self.epochen = epochen

    # -- bezahlte Aktionen ---------------------------------------------

    def _bezahlt(self, aktion: str, bereich: str, titel: str, arbeit) -> dict:
        self.konto.abbuchen(aktion)
        try:
            daten = arbeit()
        except Exception as exc:
            self.konto.erstatten(aktion, str(exc)[:80])
            raise
        return self.verlauf.eintragen(bereich, titel, daten, KOSTEN[aktion])

    def analyse(self, body: dict) -> dict:
        schwelle = float(body.get("schwelle", 0.5))
        if not 0.34 <= schwelle <= 0.95:
            raise ValueError("Schwelle muss zwischen 34 % und 95 % liegen.")

        # Erst prüfen, ob alles da ist — wofür nichts geschieht, wird nicht abgebucht.
        gehirn, paket = self.modell.holen()
        kerzen = self.quelle.kerzen()
        return self._bezahlt("analyse", "analyse", "KI-Analyse",
                             lambda: dienste.analyse(kerzen, gehirn, paket, schwelle))

    def indikatoren(self, body: dict) -> dict:
        kerzen = self.quelle.kerzen()
        return self._bezahlt("indikatoren", "indikatoren", "Indikatoren",
                             lambda: dienste.indikatoren(kerzen))

    def strategie(self, body: dict) -> dict:
        gehirn, paket = self.modell.holen()
        kerzen = self.quelle.kerzen()
        return self._bezahlt("strategie", "strategie", "Strategie-Test",
                             lambda: dienste.strategie(kerzen, gehirn, paket))

    def training_starten(self, body: dict) -> dict:
        kerzen = self.quelle.kerzen()      # Fehler hier kosten nichts
        if not self.training.beginnen():
            raise RuntimeError("Es läuft schon ein Training.")
        try:
            self.konto.abbuchen("training")
        except ZuWenigTokens:
            self.training.beenden("bereit")
            raise
        epochen = int(body.get("epochen", self.epochen))
        threading.Thread(target=self._trainieren, args=(kerzen, epochen),
                         daemon=True).start()
        return self.training.info()

    def _trainieren(self, kerzen, epochen: int) -> None:
        t = self.training
        try:
            t.melden(f"{len(kerzen)} Kerzen aus {self.quelle.name}")
            paket = trainieren(kerzen, Bauplan(), Einstellungen(epochen=epochen),
                               melden=t.melden)
            daten, test = paket["_daten"], paket["_test"]
            p = wahrscheinlichkeiten(paket["_gehirn"], daten.tabelle, test)
            ergebnis = kennzahlen(test, daten.ausgang, p)
            paket["ergebnis"] = ergebnis
            speichern(paket, self.modell.pfad)
            t.melden(f"Test: {ergebnis['treffer']:.1%} richtig, Raten {ergebnis['raten']:.1%}")
            t.melden(f"Gespeichert: {self.modell.pfad}")
            ergebnis["kurz"] = (f"Treffer {ergebnis['treffer']:.0%} gegen "
                                f"{ergebnis['raten']:.0%} Raten")
            ergebnis["protokoll"] = t.info()["zeilen"]
            ergebnis["ab"] = paket["test_ab"]
            self.verlauf.eintragen("training", "Training", ergebnis, KOSTEN["training"])
            t.beenden("fertig")
        except Exception as exc:
            t.melden(f"Fehler: {exc}")
            self.konto.erstatten("training", str(exc)[:80])
            self.verlauf.eintragen("training", "Training fehlgeschlagen",
                                   {"kurz": str(exc)[:120], "protokoll": t.info()["zeilen"]})
            t.beenden("fehler")

    # -- lesen ----------------------------------------------------------

    def stand(self) -> dict:
        letzte = self.verlauf.letzter("analyse")
        return {
            "konto": self.konto.stand(),
            "modell": self.modell.info(),
            "quelle": self.quelle.info(),
            "letzte_analyse": letzte,
            "letzte_indikatoren": self.verlauf.letzter("indikatoren"),
            "zaehler": self.verlauf.zaehlen(),
            "training": self.training.info()["status"],
            "neueste": self.verlauf.liste(anzahl=6),
        }


def handler_fuer(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = "BENGX-KI"

        def log_message(self, *args) -> None:   # leise
            pass

        def _json(self, daten, status: int = 200) -> None:
            roh = json.dumps(daten, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(roh)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(roh)

        def _fehler(self, exc: Exception) -> None:
            if isinstance(exc, ZuWenigTokens):
                self._json({"fehler": str(exc), "tokens": True}, HTTPStatus.PAYMENT_REQUIRED)
            elif isinstance(exc, (FileNotFoundError, ValueError)):
                self._json({"fehler": str(exc)}, HTTPStatus.BAD_REQUEST)
            elif isinstance(exc, RuntimeError):
                self._json({"fehler": str(exc)}, HTTPStatus.CONFLICT)
            else:
                traceback.print_exc()
                self._json({"fehler": f"Interner Fehler: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

        def do_GET(self) -> None:
            url = urlparse(self.path)
            pfad = url.path
            try:
                if pfad in ("/", "/index.html"):
                    roh = SEITE.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(roh)))
                    self.end_headers()
                    self.wfile.write(roh)
                elif pfad == "/api/stand":
                    self._json(app.stand())
                elif pfad == "/api/verlauf":
                    bereich = parse_qs(url.query).get("bereich", [None])[0]
                    self._json(app.verlauf.liste(bereich or None))
                elif pfad.startswith("/api/verlauf/"):
                    e = app.verlauf.holen(pfad.rsplit("/", 1)[1])
                    self._json(e or {"fehler": "Nicht gefunden"}, 200 if e else 404)
                elif pfad == "/api/konto":
                    self._json({"stand": app.konto.stand(),
                                "buchungen": app.konto.buchungen()})
                elif pfad == "/api/training":
                    self._json(app.training.info())
                elif pfad == "/api/modell":
                    self._json(app.modell.info())
                else:
                    self._json({"fehler": "Nicht gefunden"}, 404)
            except Exception as exc:
                self._fehler(exc)

        def do_POST(self) -> None:
            try:
                laenge = int(self.headers.get("Content-Length") or 0)
                if laenge > 100_000:
                    raise ValueError("Anfrage zu groß.")
                body = json.loads(self.rfile.read(laenge) or b"{}") if laenge else {}
                if not isinstance(body, dict):
                    raise ValueError("Erwartet wird ein JSON-Objekt.")
                ziel = {
                    "/api/analyse": app.analyse,
                    "/api/indikatoren": app.indikatoren,
                    "/api/strategie": app.strategie,
                    "/api/training": app.training_starten,
                    "/api/konto/aufladen": lambda b: app.konto.aufladen(
                        int(b.get("menge", 0)), "Aufgeladen (Inhaber)"),
                    "/api/konto/abo": lambda b: app.konto.abo_wechseln(str(b.get("abo", ""))),
                }.get(urlparse(self.path).path)
                if ziel is None:
                    self._json({"fehler": "Nicht gefunden"}, 404)
                    return
                self._json(ziel(body))
            except json.JSONDecodeError:
                self._json({"fehler": "Ungültiges JSON."}, 400)
            except Exception as exc:
                self._fehler(exc)

    return Handler


def starten(app: App, port: int = 8765, browser: bool = True) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), handler_fuer(app))
    adresse = f"http://127.0.0.1:{server.server_port}/"
    print(f"BENGX KI läuft: {adresse}")
    print(f"Daten: {app.quelle.name}")
    print("Beenden mit Strg+C.")
    if browser:
        import webbrowser
        threading.Timer(0.6, webbrowser.open, args=(adresse,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBeendet.")
    finally:
        server.server_close()
