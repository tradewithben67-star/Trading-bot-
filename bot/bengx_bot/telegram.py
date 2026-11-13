"""Telegram-Anbindung.

Der Bot tut genau drei Dinge, und die richtig:

1. Signale in die Gruppen stellen — VIP alle, der Inner Circle eins je
   Sitzung (London und New York).
2. Das Ergebnis als Antwort unter das Signal hängen.
3. Einmal am Tag einen Rückblick in beide Gruppen schicken.

Dazu Einladungslinks für VIP und der Not-Aus für den Handelsbot.

Kein Sprachmodell. Früher ging jede Nachricht an Gemini, das daraus
Werkzeugaufrufe machte — bei jedem Werkzeug eine eigene Anfrage. Auf dem
kostenlosen Kontingent war das aussichtslos; am Ende kam nur noch
„You exceeded your current quota“ zurück. Ein Signal ist aber kein
Verständnisproblem, sondern eine Richtung und drei Zahlen. Die liest
`lesen.py` fest. Das ist schneller, kostet nichts und tut immer dasselbe.

Gesprochen wird über die Bot-API von Telegram, per langem Abruf
(getUpdates). Dafür braucht die Maschine keine öffentliche Adresse — sie
fragt nur nach draußen. Reines Standard-Python.

Zugangsdaten kommen aus der Umgebung, nie aus dem Repository:

    TELEGRAM_TOKEN     von @BotFather
    TELEGRAM_CHAT_ID   die eigene Chat-Kennung; nur sie wird bedient
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence

from . import report
from .cli import rules_for
from .config import Config
from .gruppen import GruppenSettings, Verteiler, de
from .lesen import ergebnis_lesen, ja_gesagt, signal_lesen

API = "https://api.telegram.org"
LIMIT = 3900          # Telegram bricht bei 4096 Zeichen ab

DOPPELT = (
    "Es läuft noch ein zweiter Bot mit demselben Token.\n"
    "Telegram lässt immer nur einen gleichzeitig zu.\n\n"
    "Schließ alle anderen schwarzen Fenster — auch die aus einer "
    "älteren Entpackung — und starte dann neu. Solange zwei laufen, "
    "nimmt der eine dem anderen die Nachrichten weg.")


class Umgezogen(ConnectionError):
    """Die Gruppe wurde zur Supergruppe und hat dabei eine neue Kennung.

    Telegram vergibt beim Umwandeln einer einfachen Gruppe in eine
    Supergruppe eine neue Chat-Kennung — das passiert still, sobald man
    einen öffentlichen Link vergibt oder die Berechtigungen ändert. Ab
    dann gehen alle Nachrichten an die alte Kennung ins Leere. Statt
    eines unverständlichen 400er sagt dieser Fehler, was zu tun ist.
    """

    def __init__(self, alt: str, neu: str) -> None:
        self.alt, self.neu = str(alt), str(neu)
        super().__init__(
            f"Die Gruppe {alt} ist jetzt eine Supergruppe und heißt {neu}. "
            f"Trag {neu} in bot/.env ein und starte den Bot neu — "
            "bis dahin kommt dort nichts an.")


@dataclass
class TelegramSettings:
    token: str = ""
    chat_id: str = ""
    poll_timeout: int = 50

    @staticmethod
    def from_env(env: dict[str, str] | None = None) -> "TelegramSettings":
        e = env if env is not None else os.environ
        return TelegramSettings(
            token=e.get("TELEGRAM_TOKEN", "").strip(),
            chat_id=str(e.get("TELEGRAM_CHAT_ID", "")).strip(),
            poll_timeout=int(e.get("TELEGRAM_POLL_TIMEOUT", "50") or 50),
        )


def load_env_file(path: str | Path) -> dict[str, str]:
    """Liest eine einfache KEY=WERT-Datei. Nichts davon gehört ins Repository."""
    p = Path(path)
    out: dict[str, str] = {}
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


# ---- Verbindung ----------------------------------------------------------
class Transport(Protocol):
    def call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    def download(self, file_path: str) -> bytes: ...


@dataclass
class HttpTransport:
    token: str
    timeout: float = 70.0

    def call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{API}/bot{self.token}/{method}", data=data,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as answer:
                return json.loads(answer.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            roh = exc.read().decode("utf-8", "replace")
            neu = _umgezogen_nach(roh)
            if neu:
                raise Umgezogen(payload.get("chat_id", "?"), neu) from exc
            # Telegrams eigener Text dazu ist englisch und sagt einem
            # Menschen nichts. Das hier ist die häufigste Ursache.
            if exc.code == 409:
                raise ConnectionError(DOPPELT) from exc
            raise ConnectionError(
                f"Telegram antwortet {exc.code}: {roh[:300]}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ConnectionError(f"Telegram nicht erreichbar: {exc}") from exc

    def download(self, file_path: str) -> bytes:
        url = f"{API}/file/bot{self.token}/{file_path}"
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as answer:
                return answer.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ConnectionError(f"Datei nicht abrufbar: {exc}") from exc


class FakeTransport:
    """Für Tests: merkt sich alles und liefert vorbereitete Antworten."""

    def __init__(self, updates: Sequence[dict[str, Any]] = (),
                 files: dict[str, bytes] | None = None) -> None:
        self.updates = list(updates)
        self.files = files or {}
        self.sent: list[dict[str, Any]] = []
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.links = 0

    def call(self, method, payload):
        self.calls.append((method, payload))
        if method == "getUpdates":
            batch, self.updates = self.updates, []
            return {"ok": True, "result": batch}
        if method == "sendMessage":
            self.sent.append(payload)
            return {"ok": True, "result": {"message_id": len(self.sent)}}
        if method == "getFile":
            return {"ok": True, "result": {"file_path": "fotos/" + payload["file_id"]}}
        if method == "createChatInviteLink":
            self.links += 1
            return {"ok": True, "result": {
                "invite_link": f"https://t.me/+probe{self.links}"}}
        if method in ("banChatMember", "unbanChatMember"):
            return {"ok": True, "result": True}
        return {"ok": True, "result": {}}

    def download(self, file_path):
        return self.files.get(file_path.split("/")[-1], b"")


# ---- Der Bot --------------------------------------------------------------
HILFE = """So gibst du ein Signal durch — einfach tippen:

   long 4012, stop 4004, ziel 4029, 1h sweep und 1m bos

Ich zeige dir, wie es in beiden Gruppen aussieht, und frage nach.
Dann „ja“ oder „nein“.

Ergebnis melden, wenn der Trade zu ist:

   ziel        das neueste offene Signal ist im Ziel
   stop        ausgestoppt
   be          ausgeglichen raus
   sig-3 ziel  ein bestimmtes Signal

Befehle:

/stand       Zahlen des Handelsbots
/gruppen     was eingerichtet ist und was heute noch frei ist
/signale     die letzten Signale
/rueckblick  den Tagesrückblick jetzt schicken
/einladung vip Max     Einladungslink, gilt einmal
/regeln      das Regelwerk eines Bots
/aus /an     Not-Aus für den Handelsbot
/hilfe       diese Liste"""


class TelegramBot:
    def __init__(self, config: Config, settings: TelegramSettings,
                 transport: Transport,
                 verteiler: Verteiler | None = None,
                 bruecke: Any = None) -> None:
        self.cfg = config
        self.tg = settings
        self.net = transport
        self.verteiler = verteiler
        self.bruecke = bruecke
        self.offset = 0

    # ---- Zugang ---------------------------------------------------------
    def allowed(self, chat_id: str) -> bool:
        return bool(self.tg.chat_id) and str(chat_id) == str(self.tg.chat_id)

    def _v(self) -> Verteiler:
        if self.verteiler is None:
            raise RuntimeError(
                "Die Gruppen sind nicht eingerichtet. Trag "
                "TELEGRAM_VIP_CHAT_ID und TELEGRAM_INNER_CHAT_ID in "
                "bot/.env ein — oder lass LOSGEHTS.bat noch einmal laufen.")
        return self.verteiler

    # ---- Eine Nachricht --------------------------------------------------
    def handle(self, update: dict[str, Any]) -> list[str]:
        message = update.get("message") or update.get("edited_message") or {}
        chat = message.get("chat") or {}
        chat_id = str(chat.get("id", ""))
        if not chat_id:
            return []

        if not self.allowed(chat_id):
            # In einer Gruppe schweigt er. Der Bot sitzt in VIP und im
            # Inner Circle; dort auf jede fremde Nachricht zu antworten
            # wäre Lärm vor zahlenden Leuten und verriete außerdem, dass
            # er mithört.
            if chat.get("type") in ("group", "supergroup", "channel"):
                return []
            if not self.tg.chat_id:
                return ["Noch keine Chat-Kennung hinterlegt.\n\n"
                        f"Deine lautet: {chat_id}\n\n"
                        "Trag sie als TELEGRAM_CHAT_ID ein und starte mich neu. "
                        "Bis dahin antworte ich nichts weiter."]
            return ["Dieser Chat ist nicht freigegeben."]

        text = (message.get("text") or message.get("caption") or "").strip()
        if not text:
            return ["Damit kann ich nichts anfangen. /hilfe zeigt, was geht."]
        if text.startswith("/"):
            return self._befehl(text)
        return self._freitext(text)

    # ---- Freier Text: Signal, Ergebnis, Ja/Nein --------------------------
    def _freitext(self, text: str) -> list[str]:
        # 1. Liegt ein Entwurf bereit, zählt nur Ja oder Nein.
        if self.verteiler is not None and self.verteiler.entwurf_liegt():
            antwort = ja_gesagt(text)
            if antwort is True:
                return [self._freigeben()]
            if antwort is False:
                return [self._v().entwurf_verwerfen()]
            return ["Ein Entwurf liegt noch bereit. „ja“ schickt ihn raus, "
                    "„nein“ wirft ihn weg."]

        # 2. Sieht es wie ein Signal aus?
        signal = signal_lesen(text)
        if signal:
            return [self._entwurf(signal)]

        # 3. Oder wie ein Ergebnis?
        gelesen = ergebnis_lesen(text)
        if gelesen:
            return [self._ergebnis(*gelesen)]

        return ["Das war weder ein Signal noch ein Ergebnis.\n\n" + HILFE]

    def _entwurf(self, signal: dict[str, Any]) -> str:
        try:
            raus = self._v().entwurf(signal)
        except (ValueError, RuntimeError) as exc:
            return str(exc)
        teile = ["So würde es rausgehen:", ""]
        for name, text in raus["vorschau"].items():
            teile += [f"── {name} ──", text, ""]
        darf, grund = self._v().frei_moeglich()
        if not darf:
            teile.append(f"(Der Inner Circle bekommt es nicht: {grund}.)")
            teile.append("")
        teile.append("Schicken? „ja“ oder „nein“.")
        return "\n".join(teile)

    def _freigeben(self) -> str:
        try:
            raus = self._v().freigeben()
        except (ValueError, RuntimeError) as exc:
            return str(exc)
        return self._bilanz(raus)

    def _ergebnis(self, kennung: str, lage: str) -> str:
        v = self._v()
        if not kennung:
            offen = [s for s in v.letzte(20) if s.get("status", "offen") == "offen"]
            if not offen:
                return ("Kein offenes Signal da. Mit „sig-3 ziel“ kannst du "
                        "ein bestimmtes nachtragen.")
            kennung = offen[0]["id"]
        try:
            raus = v.ergebnis_senden(kennung, lage)
        except (ValueError, RuntimeError) as exc:
            return str(exc)
        return (f"{raus['id']}: {lage}, {raus['pips']:+.0f} Pips. "
                f"Steht in {', '.join(raus['gruppen'])}.")

    # ---- Befehle ---------------------------------------------------------
    def _befehl(self, text: str) -> list[str]:
        teile = text.split()
        befehl = teile[0].split("@")[0].lower()
        rest = " ".join(teile[1:]).strip()

        if befehl in ("/start", "/hilfe", "/help"):
            return [HILFE]

        if befehl == "/stand":
            return [report.build(self.cfg).text()]

        if befehl == "/signale":
            if self.verteiler is None:
                return [report.signale_text(self.cfg, (rest or "heute").lower())]
            return [self._v().stand_text(10)]

        if befehl == "/gruppen":
            return [self._v().stand_text()] if self.verteiler else [
                "Die Gruppen sind hier nicht eingerichtet."]

        if befehl in ("/rueckblick", "/rückblick", "/recap"):
            try:
                raus = self._v().rueckblick_senden()
            except RuntimeError as exc:
                return [str(exc)]
            return [f"Rückblick für {raus['tag']} verschickt an "
                    f"{', '.join(raus['gruppen'])} ({raus['signale']} Signale)."]

        if befehl == "/einladung":
            woerter = rest.split()
            if not woerter:
                return ["So: /einladung vip Max"]
            try:
                return [self._v().einladung(woerter[0], " ".join(woerter[1:]))]
            except (ValueError, RuntimeError) as exc:
                return [str(exc)]

        if befehl == "/regeln":
            name = (rest or self.cfg.bot.name).lower()
            try:
                return [rules_for(self.cfg, name)]
            except ValueError as exc:
                return [str(exc)]

        if befehl == "/aus":
            p = Path(self.cfg.live.killswitch_file)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("aus über Telegram\n", encoding="utf-8")
            return ["Not-Aus gesetzt. Beim nächsten Durchlauf wird alles "
                    "geschlossen und nichts Neues eröffnet. Lösen mit /an."]

        if befehl == "/an":
            p = Path(self.cfg.live.killswitch_file)
            if p.exists():
                p.unlink()
                return ["Not-Aus gelöst. Der Bot darf wieder handeln."]
            return ["Der Not-Aus war nicht gesetzt."]

        return [f"Den Befehl {befehl} kenne ich nicht. /hilfe zeigt die Liste."]

    # ---- Betrieb ----------------------------------------------------------
    def send(self, chat_id: str, text: str) -> None:
        for stueck in _split(text):
            self.net.call("sendMessage", {
                "chat_id": chat_id, "text": stueck,
                "disable_web_page_preview": True,
            })

    def neue_trades(self) -> None:
        """Schaut in MetaTrader, ob Ben einen Trade gestellt hat."""
        if self.bruecke is None or self.verteiler is None or not self.tg.chat_id:
            return
        try:
            neue = self.bruecke.neue()
        except Exception as exc:                  # MT5 darf nichts reissen
            print(f"MetaTrader nicht gelesen: {exc}", flush=True)
            return
        for roh in neue:
            self._gemeldeter_trade(roh)

    def _gemeldeter_trade(self, roh: dict[str, Any]) -> None:
        fehlt = [was for was, wert in (("Stop", roh.get("sl")),
                                       ("Ziel", roh.get("tp"))) if not wert]
        if fehlt:
            # Ein Signal ohne Stop gehört nicht in eine Gruppe.
            self.send(self.tg.chat_id,
                      f"Neuer Trade in {roh['pair']} erkannt, aber "
                      f"{' und '.join(fehlt)} fehlt in MetaTrader. "
                      "Trag es dort nach und melde das Signal von Hand.")
            return
        if self.bruecke.settings.ohne_rueckfrage:
            try:
                raus = self.verteiler.signal_senden(dict(roh))
            except (ValueError, RuntimeError) as exc:
                self.send(self.tg.chat_id, f"Trade nicht verschickt: {exc}")
                return
            self.send(self.tg.chat_id, "Automatisch raus.\n" + self._bilanz(raus))
            return
        try:
            self.verteiler.entwurf(dict(roh))
        except (ValueError, RuntimeError) as exc:
            self.send(self.tg.chat_id, f"Trade nicht übernommen: {exc}")
            return
        teile = [f"Neuer Trade in {roh['pair']} — so würde er rausgehen:", ""]
        for name, text in self.verteiler.entwurf_vorschau().items():
            teile += [f"── {name} ──", text, ""]
        teile.append("Schicken? „ja“ oder „nein“.")
        self.send(self.tg.chat_id, "\n".join(teile))

    def _bilanz(self, raus: dict[str, Any]) -> str:
        zeilen = [f"Raus als {raus['id']}."]
        if raus["sofort"]:
            zeilen.append("An: " + ", ".join(raus["sofort"]))
        if raus["wartet"]:
            zeilen.append("Folgt: " + ", ".join(raus["wartet"]))
        if raus["ausgelassen"]:
            zeilen.append("Nicht an: " + ", ".join(raus["ausgelassen"]))
        return "\n".join(zeilen)

    def nebenbei(self) -> None:
        """Was ohne Zutun passiert: Trades, wartende Signale, Rückblick."""
        self.neue_trades()
        if self.verteiler is None:
            return
        try:
            self.verteiler.faellige_senden()
            if self.verteiler.rueckblick_faellig():
                raus = self.verteiler.rueckblick_senden()
                print(f"Rückblick für {raus['tag']} verschickt "
                      f"({raus['signale']} Signale).", flush=True)
                if self.tg.chat_id:
                    self.send(self.tg.chat_id,
                              f"Tagesrückblick ist raus: {raus['signale']} "
                              f"Signale, an {', '.join(raus['gruppen'])}.")
        except (ConnectionError, OSError) as exc:
            print(f"Nebenbei nicht erledigt: {exc}", flush=True)

    def poll_once(self) -> int:
        self.nebenbei()
        antwort = self.net.call("getUpdates", {
            "offset": self.offset, "timeout": self.tg.poll_timeout,
            "allowed_updates": ["message", "edited_message"],
        })
        updates = antwort.get("result") or []
        for update in updates:
            self.offset = max(self.offset, int(update.get("update_id", 0)) + 1)
            message = update.get("message") or update.get("edited_message") or {}
            chat_id = str((message.get("chat") or {}).get("id", ""))
            if not chat_id:
                continue
            try:
                for text in self.handle(update):
                    self.send(chat_id, text)
            except Exception as exc:                      # nie an einer Nachricht sterben
                # Auch die Entschuldigung kann scheitern — etwa wenn der
                # Chat gar nicht mehr erreichbar ist. Dann bleibt es bei
                # einer Zeile im Fenster, statt die Schleife zu reißen.
                print(f"Nachricht aus {chat_id} nicht verarbeitet: {exc}",
                      flush=True)
                try:
                    self.send(chat_id, f"Da ist etwas schiefgegangen: {exc}")
                except Exception:
                    pass
        return len(updates)

    def run(self) -> None:
        print(f"Telegram-Bot läuft. Handelsbot: {self.cfg.bot.name}", flush=True)
        while True:
            try:
                self.poll_once()
            except ConnectionError as exc:
                print(f"Verbindung weg ({exc}) — neuer Versuch in 15 s", flush=True)
                time.sleep(15)


def _umgezogen_nach(body: str) -> str:
    """Liest die neue Kennung aus einer Telegram-Fehlerantwort, falls da."""
    try:
        daten = json.loads(body)
    except ValueError:
        return ""
    neu = (daten.get("parameters") or {}).get("migrate_to_chat_id")
    return str(neu) if neu else ""


def _split(text: str) -> list[str]:
    if len(text) <= LIMIT:
        return [text]
    teile, rest = [], text
    while len(rest) > LIMIT:
        schnitt = rest.rfind("\n", 0, LIMIT)
        if schnitt < LIMIT // 2:
            schnitt = LIMIT
        teile.append(rest[:schnitt])
        rest = rest[schnitt:].lstrip("\n")
    if rest:
        teile.append(rest)
    return teile
