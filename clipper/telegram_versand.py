"""Telegram-Versand fuer die Clip-Fabrik.

Braucht nur TELEGRAM_BOT_TOKEN. Die Chat-ID wird so gefunden:
  1. TELEGRAM_CHAT_ID, falls gesetzt
  2. sonst die gespeicherte Datei
  3. sonst der Chat der letzten Nachricht an den Bot (du schreibst ihm einmal /start)
Gefundene IDs werden in der Datei gespeichert.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import requests


class Telegram:
    def __init__(self, token: str, chat_id: str):
        self.api = f"https://api.telegram.org/bot{token}"
        self.chat_id = chat_id

    def senden(self, video: Path, text: str) -> bool:
        r = None
        for _ in range(3):
            with video.open("rb") as f:
                r = requests.post(f"{self.api}/sendVideo", timeout=300,
                                  data={"chat_id": self.chat_id, "caption": text[:1000],
                                        "supports_streaming": "true",
                                        "width": 1080, "height": 1920},
                                  files={"video": (video.name, f, "video/mp4")})
            if r.status_code != 429:
                break
            # Telegram bremst: so lange warten, wie es sagt
            warten = r.json().get("parameters", {}).get("retry_after", 5)
            print(f"  Telegram bremst, warte {warten}s", flush=True)
            time.sleep(warten + 1)
        print(f"  Telegram: {video.name} -> {r.status_code}" + ("" if r.ok else f" {r.text[:200]}"),
              flush=True)
        time.sleep(1.5)
        return r.ok


def _chat_id_finden(api: str, chat_datei: Path) -> str | None:
    cid = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if cid:
        return cid
    if chat_datei.exists() and chat_datei.read_text().strip():
        return chat_datei.read_text().strip()
    ich = requests.get(f"{api}/getMe", timeout=30).json()
    if not ich.get("ok"):
        print(f"Telegram lehnt den Token ab ({ich.get('error_code')}: {ich.get('description')}). "
              "Token in GitHub pruefen: neu von @BotFather kopieren, ohne Leerzeichen.")
        return None
    print(f"Bot: @{ich['result'].get('username')}")
    r = requests.get(f"{api}/getUpdates", timeout=30).json()
    if not r.get("ok") and r.get("error_code") == 409:
        # Webhook gesetzt -> blockiert getUpdates. Entfernen und erneut versuchen.
        requests.post(f"{api}/deleteWebhook", timeout=30)
        r = requests.get(f"{api}/getUpdates", timeout=30).json()
    if not r.get("ok"):
        print(f"getUpdates fehlgeschlagen ({r.get('error_code')}: {r.get('description')})")
        return None
    print(f"{len(r.get('result', []))} Nachricht(en) an den Bot gefunden.")
    for upd in reversed(r.get("result", [])):
        nachricht = upd.get("message") or upd.get("edited_message") or {}
        chat = nachricht.get("chat", {})
        if chat.get("id"):
            cid = str(chat["id"])
            chat_datei.parent.mkdir(parents=True, exist_ok=True)
            chat_datei.write_text(cid)
            requests.post(f"{api}/sendMessage", timeout=30, data={
                "chat_id": cid,
                "text": "✅ Verbunden! Ab jetzt bekommst du hier jeden neuen Clip."})
            print("Chat-ID gefunden und gespeichert.")
            return cid
    return None


def verbinden(chat_datei: Path) -> Telegram | None:
    """Liefert einen Telegram-Sender oder None (nicht eingerichtet / Chat unbekannt)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("Telegram nicht eingerichtet (TELEGRAM_BOT_TOKEN fehlt).")
        return None
    try:
        cid = _chat_id_finden(f"https://api.telegram.org/bot{token}", chat_datei)
    except Exception as e:
        print(f"Telegram nicht erreichbar: {e}")
        return None
    if not cid:
        print("Chat-ID unbekannt: Oeffne genau den oben genannten Bot in Telegram und schreibe /start.")
        return None
    return Telegram(token, cid)
