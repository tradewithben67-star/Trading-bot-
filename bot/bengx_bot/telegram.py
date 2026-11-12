"""Telegram-Anbindung.

Der Bot hängt an derselben Maschine wie der Handelsbot und liest dessen
Protokoll, Zustand und Aufgaben. Er beantwortet Befehle immer; freies
Schreiben nur, wenn das Anthropic-SDK und ein Schlüssel vorhanden sind.

Gesprochen wird über die Bot-API von Telegram, per langem Abruf (getUpdates).
Dafür braucht die Maschine keine öffentliche Adresse — sie fragt nur nach
draußen. Reines Standard-Python.

Zugangsdaten kommen aus der Umgebung, nie aus dem Repository:

    TELEGRAM_TOKEN     von @BotFather
    TELEGRAM_CHAT_ID   die eigene Chat-Kennung; nur sie wird bedient
    ANTHROPIC_API_KEY  nur für freies Schreiben
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
from .assistant import Assistant, AssistantSettings
from .cli import rules_for
from .coder import Coder, CoderSettings
from .config import Config
from .gruppen import GruppenSettings, Verteiler
from .llm import LLMSettings

API = "https://api.telegram.org"


class Umgezogen(ConnectionError):
    """Die Gruppe wurde zur Supergruppe und hat dabei eine neue Kennung.

    Telegram vergibt beim Umwandeln einer einfachen Gruppe in eine
    Supergruppe eine neue Chat-Kennung — das passiert still, sobald man
    einen öffentlichen Link vergibt oder viele Mitglieder hinzufügt. Ab
    dann gehen alle Nachrichten an die alte Kennung ins Leere. Statt
    eines unverständlichen 400er sagt dieser Fehler, was zu tun ist.
    """

    def __init__(self, alt: str, neu: str) -> None:
        self.alt, self.neu = str(alt), str(neu)
        super().__init__(
            f"Die Gruppe {alt} ist jetzt eine Supergruppe und heißt {neu}. "
            f"Trag {neu} in bot/.env ein und starte den Bot neu — "
            "bis dahin kommt dort nichts an.")
LIMIT = 3900          # Telegram bricht bei 4096 Zeichen ab


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
HILFE = """Schreib einfach normal, ich mache den Rest. Zum Beispiel:

„wie läuft es gerade“
„wie waren die signale heute“
„zeig mir die letzten fünf trades“
„was sind die regeln vom swing bot“
„mach den bot aus“
„long 4012, stop 4004, ziel 4029, 1h sweep und 1m bos“
„lade den max in den inner circle“
„das letzte signal ist im ziel“

Bilder kannst du auch schicken — Chart oder Fehlermeldung, ich schau es mir an.

Falls ich mal nicht antworte, gehen diese Befehle immer:
/stand /signale /regeln /gruppen /einladung /aufgabe /aufgaben /aus /an /neu"""


class TelegramBot:
    def __init__(self, config: Config, settings: TelegramSettings,
                 transport: Transport, assistant: Assistant | None = None,
                 coder: Coder | None = None,
                 verteiler: Verteiler | None = None) -> None:
        self.cfg = config
        self.tg = settings
        self.net = transport
        self.coder = coder
        self.verteiler = verteiler
        self.ai = assistant or Assistant(
            AssistantSettings(LLMSettings()), config=config, coder=coder,
            verteiler=verteiler)
        self.offset = 0

    # ---- Zugang ---------------------------------------------------------
    def allowed(self, chat_id: str) -> bool:
        return bool(self.tg.chat_id) and str(chat_id) == str(self.tg.chat_id)

    # ---- Eine Nachricht --------------------------------------------------
    def handle(self, update: dict[str, Any]) -> list[str]:
        message = update.get("message") or update.get("edited_message") or {}
        chat = message.get("chat") or {}
        chat_id = str(chat.get("id", ""))
        if not chat_id:
            return []

        if not self.allowed(chat_id):
            # In einer Gruppe schweigt er. Der Bot sitzt in VIP und im
            # Inner Circle; dort auf jede fremde Nachricht "nicht
            # freigegeben" zu antworten, waere Laerm vor zahlenden Leuten
            # und verraet ausserdem, dass er mithoert.
            if chat.get("type") in ("group", "supergroup", "channel"):
                return []
            if not self.tg.chat_id:
                return ["Noch keine Chat-Kennung hinterlegt.\n\n"
                        f"Deine lautet: {chat_id}\n\n"
                        "Trag sie als TELEGRAM_CHAT_ID ein und starte mich neu. "
                        "Bis dahin antworte ich nichts weiter."]
            return ["Dieser Chat ist nicht freigegeben."]

        text = (message.get("text") or message.get("caption") or "").strip()
        bilder = self._images(message)

        if text.startswith("/"):
            return self._command(text)
        if not text and not bilder:
            return ["Damit kann ich nichts anfangen. /hilfe zeigt, was geht."]

        self.typing(chat_id)
        lage = report.build(self.cfg).text()
        melden = lambda nachricht: self.send(chat_id, nachricht)
        return [self.ai.answer(text, lage, bilder, melden=melden)]

    def _command(self, text: str) -> list[str]:
        teile = text.split()
        befehl = teile[0].split("@")[0].lower()
        rest = " ".join(teile[1:]).strip()

        if befehl in ("/start", "/hilfe", "/help"):
            return [HILFE]

        if befehl == "/stand":
            return [report.build(self.cfg).text()]

        if befehl == "/signale":
            zeitraum = (rest or "heute").lower()
            if zeitraum not in ("heute", "woche", "monat", "alles"):
                return ["Zeitraum: heute, woche, monat oder alles."]
            return [report.signale_text(self.cfg, zeitraum)]

        if befehl == "/regeln":
            name = (rest or self.cfg.bot.name).lower()
            try:
                return [rules_for(self.cfg, name)]
            except ValueError as exc:
                return [str(exc)]

        if befehl == "/aufgabe":
            if not rest:
                return ["So: /aufgabe Der Bot schreibt seit gestern keine Signale."]
            nummer = report.aufgabe_anlegen(self.cfg, rest)
            return [f"Notiert als Aufgabe {nummer}. Claude Code arbeitet sie ab."]

        if befehl == "/aufgaben":
            liste = report.aufgaben_lesen(self.cfg)
            offen = [a for a in liste if a.get("status") != "erledigt"]
            if not offen:
                return ["Keine offenen Aufgaben."]
            zeilen = [f"{i + 1}. {a.get('text', '')}" for i, a in enumerate(offen)]
            return ["Offene Aufgaben:\n" + "\n".join(zeilen)]

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

        if befehl == "/gruppen":
            if self.verteiler is None:
                return ["Die Gruppen sind hier nicht eingerichtet."]
            return [self.verteiler.stand_text()]

        if befehl == "/einladung":
            if self.verteiler is None:
                return ["Die Gruppen sind hier nicht eingerichtet."]
            teile_r = rest.split()
            if not teile_r:
                return ["So: /einladung inner Max — oder /einladung vip"]
            try:
                return [self.verteiler.einladung(
                    teile_r[0], " ".join(teile_r[1:]))]
            except (ValueError, RuntimeError) as exc:
                return [str(exc)]

        if befehl == "/neu":
            self.ai.reset()
            return ["Gesprächsfaden vergessen."]

        return [f"Den Befehl {befehl} kenne ich nicht. /hilfe zeigt die Liste."]

    # ---- Bilder ----------------------------------------------------------
    def _images(self, message: dict[str, Any]) -> list[tuple[str, bytes]]:
        fotos = message.get("photo") or []
        if not fotos:
            return []
        groesstes = max(fotos, key=lambda f: f.get("file_size") or f.get("width") or 0)
        try:
            antwort = self.net.call("getFile", {"file_id": groesstes["file_id"]})
            pfad = (antwort.get("result") or {}).get("file_path")
            if not pfad:
                return []
            daten = self.net.download(pfad)
        except (ConnectionError, KeyError):
            return []
        if not daten:
            return []
        art = "image/png" if daten[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
        return [(art, daten)]

    # ---- Betrieb ----------------------------------------------------------
    def typing(self, chat_id: str) -> None:
        """Zeigt „schreibt …“ an. Mit Werkzeugen dauert eine Antwort länger,
        da soll Ben nicht ins Leere schauen."""
        try:
            self.net.call("sendChatAction", {"chat_id": chat_id, "action": "typing"})
        except ConnectionError:
            pass

    def send(self, chat_id: str, text: str) -> None:
        for stueck in _split(text):
            self.net.call("sendMessage", {
                "chat_id": chat_id, "text": stueck,
                "disable_web_page_preview": True,
            })

    def poll_once(self) -> int:
        # Der VIP-Verzug braucht keinen eigenen Faden: bei jedem Durchgang
        # wird nachgesehen, was inzwischen dran ist.
        if self.verteiler is not None:
            try:
                self.verteiler.faellige_senden()
            except (ConnectionError, OSError) as exc:
                print(f"Wartende Signale nicht verschickt: {exc}", flush=True)

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
                # einer Zeile im Fenster, statt die Schleife zu reissen.
                print(f"Nachricht aus {chat_id} nicht verarbeitet: {exc}",
                      flush=True)
                try:
                    self.send(chat_id, f"Da ist etwas schiefgegangen: {exc}")
                except Exception:
                    pass
        return len(updates)

    def run(self) -> None:
        print(f"Telegram-Bot läuft. Bot: {self.cfg.bot.name}, "
              f"Assistent: {self.ai.anbieter if self.ai.ready() else 'aus'}",
              flush=True)
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
