"""Die Oberfläche: ein kleiner Webserver mit Anmeldung.

    python -m bengx_ki oberflaeche --csv data/xauusd_h1.csv
    python -m bengx_ki oberflaeche --csv data/xauusd_h1.csv --offen   # auch fürs Netz

Ohne `--offen` hört er nur auf 127.0.0.1, also nur auf dem eigenen Rechner.
Mit `--offen` ist er im ganzen Netz erreichbar. Fürs Internet gehört davor
ein Server mit HTTPS (z. B. Caddy oder nginx), sonst gehen Passwörter
unverschlüsselt über die Leitung.

Beim ersten Start gibt es noch keinen Nutzer: wer die Seite dann öffnet, legt
den Inhaber an. Danach legt nur der Inhaber weitere Nutzer an.

Schnittstelle (alles JSON, alles außer Anmeldung nur angemeldet):

    GET  /api/ich                   wer bin ich, muss eingerichtet werden?
    POST /api/einrichten            {"name", "passwort"} — nur solange es keinen Nutzer gibt
    POST /api/anmelden              {"name", "passwort"}
    POST /api/abmelden
    GET  /api/stand                 Überblick für den angemeldeten Nutzer
    GET  /api/verlauf[?bereich=…]   eigener Verlauf; der Inhaber sieht alle
    GET  /api/verlauf/<id>
    GET  /api/nutzung               Kontingente je Modell, Buchungen
    GET  /api/modelle               die drei Modelle und ihr Stand
    POST /api/analyse               {"modell", "schwelle"}
    POST /api/indikatoren
    POST /api/strategie             {"modell"}
    GET  /api/chat?bereich=…        Gespräch in einem Bereich, mit Karten
    POST /api/chat                  {"bereich", "text"} — Antwort der KI (Claude + eigene Werkzeuge)
    POST /api/chat/neu              {"bereich"} — Gespräch neu beginnen
    GET  /api/indikatoren/eigene    eigene Indikatoren, Vorlagen, Hilfe
    POST /api/indikatoren/eigene    {"name", "formel", "anzeige"}
    POST /api/indikatoren/eigene/loeschen {"id"}
    POST /api/indikatoren/pruefen   {"formel"} — ausrechnen, ohne zu speichern
  nur Inhaber:
    GET  /api/training     POST /api/training      {"modell", "epochen"}
    GET  /api/nutzer       POST /api/nutzer        {"name", "passwort", "abo"}
    GET  /api/nutzer/<id>  Kontingente, Buchungen und Verlauf eines Nutzers
    POST /api/nutzer/abo   {"id", "abo"}
    POST /api/nutzer/passwort {"id", "passwort"}
    POST /api/nutzer/loeschen {"id"}
"""

from __future__ import annotations

import json
import threading
import time
import traceback
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import dienste, eigene
from .chat import BEREICHE, Chat
from .auswertung import kennzahlen
from .gehirn import Bauplan
from .konto import Grenze, Nutzung, kosten
from .modelle import MODELLE, STANDARD, pruefe
from .nutzer import Nutzerliste, Sitzungen
from .training import Einstellungen, speichern, trainieren, wahrscheinlichkeiten
from .verlauf import Verlauf

SEITE = Path(__file__).with_name("oberflaeche.html")
KEKS = "bengx_sitzung"


class Verboten(Exception):
    pass


class NichtAngemeldet(Exception):
    pass


class Training:
    """Ein Training im Hintergrund, damit die Oberfläche bedienbar bleibt."""

    def __init__(self) -> None:
        self.status = "bereit"          # bereit, laeuft, fertig, fehler
        self.modell: str | None = None
        self.zeilen: list[str] = []
        self.start = 0.0
        self.ende = 0.0
        self._sperre = threading.Lock()

    def info(self) -> dict:
        with self._sperre:
            return {"status": self.status, "modell": self.modell,
                    "zeilen": self.zeilen[-400:], "start": self.start, "ende": self.ende}

    def melden(self, text: str) -> None:
        with self._sperre:
            self.zeilen.append(text)

    def beginnen(self, modell: str) -> bool:
        with self._sperre:
            if self.status == "laeuft":
                return False
            self.status, self.modell, self.zeilen = "laeuft", modell, []
            self.start, self.ende = time.time(), 0.0
            return True

    def beenden(self, status: str) -> None:
        with self._sperre:
            self.status, self.ende = status, time.time()


class App:
    def __init__(self, quelle: dienste.Quelle, ordner: str | Path,
                 modellordner: str | Path | None = None, epochen: int = 30) -> None:
        ordner = Path(ordner)
        self.quelle = quelle
        self.modelle = dienste.Modelle(modellordner or ordner / "modelle")
        self.nutzer = Nutzerliste(ordner / "nutzer.json")
        self.nutzung = Nutzung(ordner / "nutzung.json")
        self.verlauf = Verlauf(ordner / "verlauf.jsonl")
        self.sitzungen = Sitzungen()
        self.training = Training()
        self.eigene = eigene.Ablage(ordner / "indikatoren.json")
        self.chat = Chat(self, ordner / "chats")
        self.epochen = epochen

    # -- bezahlte Aktionen ---------------------------------------------

    def _bezahlt(self, n: dict, modell: str, aktion: str, titel: str, arbeit) -> dict:
        k = self.nutzung.abbuchen(n, modell, aktion)
        try:
            daten = arbeit()
        except Exception as exc:
            self.nutzung.erstatten(n, modell, aktion, str(exc)[:80])
            raise
        return self.verlauf.eintragen(aktion, titel, daten, k, nutzer=n, modell=modell)

    def analyse(self, n: dict, body: dict) -> dict:
        modell = pruefe(str(body.get("modell", STANDARD)))
        schwelle = float(body.get("schwelle", 0.5))
        if not 0.34 <= schwelle <= 0.95:
            raise ValueError("Schwelle muss zwischen 34 % und 95 % liegen.")
        # Erst prüfen, ob alles da ist — wofür nichts geschieht, wird nichts verbraucht.
        gehirn, paket = self.modelle[modell].holen()
        kerzen = self.quelle.kerzen()
        return self._bezahlt(n, modell, "analyse", f"KI-Analyse · {MODELLE[modell]['name']}",
                             lambda: dienste.analyse(kerzen, gehirn, paket, schwelle))

    def indikatoren(self, n: dict, body: dict) -> dict:
        kerzen = self.quelle.kerzen()
        daten = dienste.indikatoren(kerzen)
        daten["chart"] = dienste.chartdaten(kerzen)
        daten["eigene"] = self.eigene_auswerten(n, kerzen)
        return self.verlauf.eintragen("indikatoren", "Indikatoren", daten, 0, nutzer=n)

    # -- eigene Indikatoren (frei) ---------------------------------------

    def eigene_auswerten(self, n: dict, kerzen=None) -> list[dict]:
        kerzen = kerzen or self.quelle.kerzen()
        raus = []
        for i in self.eigene.liste(n["id"]):
            try:
                raus.append({**i, **eigene.auswerten(kerzen, i["formel"])})
            except ValueError as exc:
                raus.append({**i, "fehler": str(exc)})
        return raus

    def formel_pruefen(self, body: dict) -> dict:
        kerzen = self.quelle.kerzen()
        return {"formel": str(body.get("formel", "")),
                **eigene.auswerten(kerzen, str(body.get("formel", ""))),
                "chart": dienste.chartdaten(kerzen)}

    def eigene_speichern(self, n: dict, body: dict) -> dict:
        formel = str(body.get("formel", ""))
        eigene.auswerten(self.quelle.kerzen(), formel)      # nur Gültiges speichern
        return self.eigene.speichern(n["id"], str(body.get("name", "")), formel,
                                     str(body.get("anzeige", "chart")))

    # -- Chat -------------------------------------------------------------

    def anhaenge_aufloesen(self, n: dict, nachrichten: list[dict]) -> list[dict]:
        """Hängt an Chat-Antworten die vollen Daten der Karten (Analyse, Test, Indikator)."""
        raus = []
        for m in nachrichten:
            fertig = []
            for a in m.get("anhaenge", []):
                if a["art"] == "verlauf":
                    e = self.verlauf.holen(a["id"])
                    if e and (n["rolle"] == "inhaber" or e.get("nutzer") == n["id"]):
                        fertig.append({"art": "verlauf", "eintrag": e})
                elif a["art"] == "formel":
                    try:
                        fertig.append({**a, "auswertung": self.formel_pruefen({"formel": a["formel"]})})
                    except ValueError:
                        pass
            raus.append({**m, "anhaenge": fertig})
        return raus

    def chat_stand(self, n: dict, bereich: str) -> dict:
        if bereich not in BEREICHE:
            raise ValueError("Unbekannter Bereich.")
        bereit, grund = self.chat.bereit()
        return {"bereich": bereich, "bereit": bereit, "grund": grund,
                "kontingent": self.nutzung.stand(n)["chat"],
                "nachrichten": self.anhaenge_aufloesen(n, self.chat.verlauf(n, bereich))}

    def chat_senden(self, n: dict, body: dict) -> dict:
        bereich = str(body.get("bereich", "allgemein"))
        antwort = self.chat.senden(n, bereich, str(body.get("text", "")))
        return {"antwort": self.anhaenge_aufloesen(n, [antwort])[0],
                "kontingent": self.nutzung.stand(n)["chat"]}

    def strategie(self, n: dict, body: dict) -> dict:
        modell = pruefe(str(body.get("modell", STANDARD)))
        gehirn, paket = self.modelle[modell].holen()
        kerzen = self.quelle.kerzen()
        return self._bezahlt(n, modell, "strategie", f"Strategie-Test · {MODELLE[modell]['name']}",
                             lambda: dienste.strategie(kerzen, gehirn, paket))

    # -- nur Inhaber ----------------------------------------------------

    def training_starten(self, n: dict, body: dict) -> dict:
        modell = pruefe(str(body.get("modell", STANDARD)))
        epochen = int(body.get("epochen", self.epochen))
        if not 1 <= epochen <= 200:
            raise ValueError("Epochen zwischen 1 und 200.")
        kerzen = self.quelle.kerzen()
        if not self.training.beginnen(modell):
            raise RuntimeError("Es läuft schon ein Training.")
        threading.Thread(target=self._trainieren, args=(n, modell, kerzen, epochen),
                         daemon=True).start()
        return self.training.info()

    def _trainieren(self, n: dict, modell: str, kerzen, epochen: int) -> None:
        t = self.training
        name = MODELLE[modell]["name"]
        try:
            t.melden(f"{name}: {len(kerzen)} Kerzen aus {self.quelle.name}")
            paket = trainieren(kerzen, Bauplan(**MODELLE[modell]["plan"]),
                               Einstellungen(epochen=epochen), melden=t.melden)
            daten, test = paket["_daten"], paket["_test"]
            p = wahrscheinlichkeiten(paket["_gehirn"], daten.tabelle, test)
            ergebnis = kennzahlen(test, daten.ausgang, p)
            paket["ergebnis"] = ergebnis
            paket["modell"] = modell
            speichern(paket, self.modelle[modell].pfad)
            t.melden(f"Test: {ergebnis['treffer']:.1%} richtig, Raten {ergebnis['raten']:.1%}")
            t.melden(f"Gespeichert: {self.modelle[modell].pfad}")
            ergebnis |= {"kurz": f"Treffer {ergebnis['treffer']:.0%} gegen "
                                 f"{ergebnis['raten']:.0%} Raten",
                         "protokoll": t.info()["zeilen"], "ab": paket["test_ab"]}
            self.verlauf.eintragen("training", f"Training · {name}", ergebnis, 0,
                                   nutzer=n, modell=modell)
            t.beenden("fertig")
        except Exception as exc:
            t.melden(f"Fehler: {exc}")
            self.verlauf.eintragen("training", f"Training · {name} fehlgeschlagen",
                                   {"kurz": str(exc)[:120], "protokoll": t.info()["zeilen"]},
                                   nutzer=n, modell=modell)
            t.beenden("fehler")

    def nutzer_detail(self, nid: str) -> dict | None:
        """Alles über einen Nutzer: Kontingente, Buchungen, Verlauf."""
        n = self.nutzer.holen(nid)
        if n is None:
            return None
        return {"nutzer": n, "stand": self.nutzung.stand(n),
                "buchungen": self.nutzung.buchungen(nid),
                "verlauf": self.verlauf.liste(anzahl=200, nutzer=nid),
                "zaehler": self.verlauf.zaehlen(nid)}

    def nutzer_liste(self) -> list[dict]:
        raus = []
        for n in self.nutzer.liste():
            s = self.nutzung.stand(n)
            raus.append(n | {"abo_name": s["abo_name"], "modelle": s["modelle"], "chat": s["chat"],
                             "aktionen": sum(self.verlauf.zaehlen(n["id"]).values())})
        return raus

    def nutzer_anlegen(self, body: dict) -> dict:
        return self.nutzer.anlegen(str(body.get("name", "")), str(body.get("passwort", "")),
                                   str(body.get("abo", "start")))

    def nutzer_loeschen(self, body: dict) -> dict:
        nid = str(body.get("id", ""))
        self.nutzer.loeschen(nid)
        self.sitzungen.alle_beenden(nid)
        self.nutzung.vergessen(nid)
        self.eigene.vergessen(nid)
        return {"ok": True}

    def nutzer_passwort(self, body: dict) -> dict:
        nid = str(body.get("id", ""))
        n = self.nutzer.passwort_setzen(nid, str(body.get("passwort", "")))
        self.sitzungen.alle_beenden(nid)
        return n

    # -- lesen ----------------------------------------------------------

    def stand(self, n: dict) -> dict:
        wer = None if n["rolle"] == "inhaber" else n["id"]
        return {
            "nutzung": self.nutzung.stand(n),
            "modelle": self.modelle.info(),
            "quelle": self.quelle.info(),
            "letzte_analyse": self.verlauf.letzter("analyse", n["id"]),
            "letzte_indikatoren": self.verlauf.letzter("indikatoren", n["id"]),
            "zaehler": self.verlauf.zaehlen(wer),
            "training": self.training.info()["status"],
            "neueste": self.verlauf.liste(anzahl=6, nutzer=wer),
            "nutzerzahl": len(self.nutzer.liste()) if not wer else None,
            "chat": dict(zip(("bereit", "grund"), self.chat.bereit())),
        }


def handler_fuer(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = "BENGX-KI"

        def log_message(self, *args) -> None:   # leise
            pass

        # -- Antworten --------------------------------------------------

        def _json(self, daten, status: int = 200, keks: str | None = None) -> None:
            roh = json.dumps(daten, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(roh)))
            self.send_header("Cache-Control", "no-store")
            if keks is not None:
                alter = app.sitzungen.DAUER if keks else 0
                self.send_header("Set-Cookie", f"{KEKS}={keks}; Path=/; HttpOnly; "
                                               f"SameSite=Strict; Max-Age={alter}")
            self.end_headers()
            self.wfile.write(roh)

        def _fehler(self, exc: Exception) -> None:
            if isinstance(exc, NichtAngemeldet):
                self._json({"fehler": "Bitte anmelden.", "anmelden": True}, HTTPStatus.UNAUTHORIZED)
            elif isinstance(exc, Verboten):
                self._json({"fehler": str(exc) or "Nur für den Inhaber."}, HTTPStatus.FORBIDDEN)
            elif isinstance(exc, Grenze):
                self._json({"fehler": str(exc), "grenze": True, "modell": exc.modell},
                           HTTPStatus.TOO_MANY_REQUESTS)
            elif isinstance(exc, (FileNotFoundError, ValueError)):
                self._json({"fehler": str(exc)}, HTTPStatus.BAD_REQUEST)
            elif isinstance(exc, RuntimeError):
                self._json({"fehler": str(exc)}, HTTPStatus.CONFLICT)
            else:
                traceback.print_exc()
                self._json({"fehler": f"Interner Fehler: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

        # -- Wer fragt? ---------------------------------------------------

        def _token(self) -> str | None:
            k = SimpleCookie(self.headers.get("Cookie") or "")
            return k[KEKS].value if KEKS in k else None

        def _nutzer(self) -> dict | None:
            nid = app.sitzungen.wer(self._token())
            return app.nutzer.holen(nid) if nid else None

        def _angemeldet(self) -> dict:
            n = self._nutzer()
            if n is None:
                raise NichtAngemeldet()
            return n

        def _inhaber(self) -> dict:
            n = self._angemeldet()
            if n["rolle"] != "inhaber":
                raise Verboten("Nur für den Inhaber.")
            return n

        # -- GET ----------------------------------------------------------

        def do_GET(self) -> None:
            url = urlparse(self.path)
            pfad = url.path
            try:
                if pfad in ("/", "/index.html"):
                    roh = SEITE.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(roh)))
                    self.send_header("X-Frame-Options", "DENY")
                    self.end_headers()
                    self.wfile.write(roh)
                elif pfad == "/api/ich":
                    self._json({"nutzer": self._nutzer(), "einrichten": app.nutzer.leer()})
                elif pfad == "/api/stand":
                    self._json(app.stand(self._angemeldet()))
                elif pfad == "/api/verlauf":
                    n = self._angemeldet()
                    bereich = parse_qs(url.query).get("bereich", [None])[0]
                    wer = None if n["rolle"] == "inhaber" else n["id"]
                    self._json(app.verlauf.liste(bereich or None, nutzer=wer))
                elif pfad.startswith("/api/verlauf/"):
                    n = self._angemeldet()
                    e = app.verlauf.holen(pfad.rsplit("/", 1)[1])
                    if e and n["rolle"] != "inhaber" and e.get("nutzer") != n["id"]:
                        e = None                      # fremde Einträge gibt es nicht
                    self._json(e or {"fehler": "Nicht gefunden"}, 200 if e else 404)
                elif pfad == "/api/nutzung":
                    n = self._angemeldet()
                    self._json({"stand": app.nutzung.stand(n),
                                "buchungen": app.nutzung.buchungen(n["id"])})
                elif pfad == "/api/chat":
                    n = self._angemeldet()
                    bereich = parse_qs(url.query).get("bereich", ["allgemein"])[0]
                    self._json(app.chat_stand(n, bereich))
                elif pfad == "/api/indikatoren/eigene":
                    n = self._angemeldet()
                    self._json({"liste": app.eigene_auswerten(n), "vorlagen": eigene.VORLAGEN,
                                "hilfe": eigene.HILFE})
                elif pfad == "/api/modelle":
                    self._angemeldet()
                    self._json(app.modelle.info())
                elif pfad == "/api/training":
                    self._inhaber()
                    self._json(app.training.info())
                elif pfad == "/api/nutzer":
                    self._inhaber()
                    self._json(app.nutzer_liste())
                elif pfad.startswith("/api/nutzer/"):
                    self._inhaber()
                    d = app.nutzer_detail(pfad.rsplit("/", 1)[1])
                    self._json(d or {"fehler": "Nicht gefunden"}, 200 if d else 404)
                else:
                    self._json({"fehler": "Nicht gefunden"}, 404)
            except Exception as exc:
                self._fehler(exc)

        # -- POST ---------------------------------------------------------

        def do_POST(self) -> None:
            try:
                # Nur JSON: ein fremdes Formular kann das ohne Erlaubnis nicht schicken.
                if not (self.headers.get("Content-Type") or "").startswith("application/json"):
                    raise ValueError("Erwartet wird JSON.")
                laenge = int(self.headers.get("Content-Length") or 0)
                if laenge > 100_000:
                    raise ValueError("Anfrage zu groß.")
                body = json.loads(self.rfile.read(laenge) or b"{}") if laenge else {}
                if not isinstance(body, dict):
                    raise ValueError("Erwartet wird ein JSON-Objekt.")
                pfad = urlparse(self.path).path

                if pfad == "/api/einrichten":
                    if not app.nutzer.leer():
                        raise Verboten("Es gibt schon einen Inhaber.")
                    if self.client_address[0] not in ("127.0.0.1", "::1"):
                        raise Verboten("Den Inhaber nur am eigenen Rechner anlegen.")
                    n = app.nutzer.anlegen(str(body.get("name", "")), str(body.get("passwort", "")))
                    self._json({"nutzer": n}, keks=app.sitzungen.neu(n["id"]))
                elif pfad == "/api/anmelden":
                    name = str(body.get("name", ""))
                    if app.sitzungen.gesperrt(name):
                        raise RuntimeError("Zu viele Fehlversuche. Bitte eine Minute warten.")
                    n = app.nutzer.pruefen(name, str(body.get("passwort", "")))
                    if n is None:
                        app.sitzungen.fehlversuch(name)
                        raise ValueError("Name oder Passwort stimmt nicht.")
                    app.sitzungen.erfolg(name)
                    self._json({"nutzer": n}, keks=app.sitzungen.neu(n["id"]))
                elif pfad == "/api/abmelden":
                    app.sitzungen.beenden(self._token())
                    self._json({"ok": True}, keks="")
                elif pfad in ("/api/analyse", "/api/indikatoren", "/api/strategie"):
                    n = self._angemeldet()
                    ziel = {"/api/analyse": app.analyse, "/api/indikatoren": app.indikatoren,
                            "/api/strategie": app.strategie}[pfad]
                    self._json(ziel(n, body))
                elif pfad == "/api/chat":
                    self._json(app.chat_senden(self._angemeldet(), body))
                elif pfad == "/api/chat/neu":
                    n = self._angemeldet()
                    app.chat.neu(n, str(body.get("bereich", "allgemein")))
                    self._json({"ok": True})
                elif pfad == "/api/indikatoren/pruefen":
                    self._angemeldet()
                    self._json(app.formel_pruefen(body))
                elif pfad == "/api/indikatoren/eigene":
                    self._json(app.eigene_speichern(self._angemeldet(), body))
                elif pfad == "/api/indikatoren/eigene/loeschen":
                    n = self._angemeldet()
                    app.eigene.loeschen(n["id"], str(body.get("id", "")))
                    self._json({"ok": True})
                elif pfad == "/api/training":
                    self._json(app.training_starten(self._inhaber(), body))
                elif pfad == "/api/nutzer":
                    self._inhaber()
                    self._json(app.nutzer_anlegen(body))
                elif pfad == "/api/nutzer/abo":
                    self._inhaber()
                    self._json(app.nutzer.abo_setzen(str(body.get("id", "")), str(body.get("abo", ""))))
                elif pfad == "/api/nutzer/passwort":
                    self._inhaber()
                    self._json(app.nutzer_passwort(body))
                elif pfad == "/api/nutzer/loeschen":
                    self._inhaber()
                    self._json(app.nutzer_loeschen(body))
                else:
                    self._json({"fehler": "Nicht gefunden"}, 404)
            except json.JSONDecodeError:
                self._json({"fehler": "Ungültiges JSON."}, 400)
            except Exception as exc:
                self._fehler(exc)

    return Handler


def starten(app: App, port: int = 8765, browser: bool = True, offen: bool = False) -> None:
    host = "0.0.0.0" if offen else "127.0.0.1"
    server = ThreadingHTTPServer((host, port), handler_fuer(app))
    adresse = f"http://127.0.0.1:{server.server_port}/"
    print(f"BENGX KI läuft: {adresse}")
    if offen:
        print("Offen fürs Netz. Fürs Internet nur hinter HTTPS betreiben!")
    print(f"Daten: {app.quelle.name}")
    if app.nutzer.leer():
        print("Noch kein Nutzer: beim ersten Öffnen legst du den Inhaber an.")
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


__all__ = ["App", "starten", "handler_fuer", "kosten"]
