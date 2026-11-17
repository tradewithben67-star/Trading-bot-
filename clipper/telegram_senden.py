#!/usr/bin/env python3
"""Schickt alle fertigen Clips aus ausgabe/ per Telegram-Bot an dich.

Braucht nur TELEGRAM_BOT_TOKEN. Die Chat-ID wird so gefunden:
  1. TELEGRAM_CHAT_ID, falls gesetzt
  2. sonst die gespeicherte Datei (Pfad als 2. Argument)
  3. sonst der Chat der letzten Nachricht an den Bot (du schreibst ihm einmal /start)
Gefundene IDs werden in der Datei gespeichert.

Aufruf: telegram_senden.py <ausgabe-ordner> <chat-id-datei>
"""
import json
import os
import sys
import time
from pathlib import Path

import requests

ausgabe = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "ausgabe")
chat_datei = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent / "state" / "telegram_chat.txt"
token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
if not token:
    print("Telegram nicht eingerichtet (TELEGRAM_BOT_TOKEN fehlt), ueberspringe.")
    sys.exit(0)
api = f"https://api.telegram.org/bot{token}"


def chat_id_finden() -> str | None:
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


cid = chat_id_finden()
if not cid:
    print("Chat-ID unbekannt: Oeffne genau den oben genannten Bot in Telegram und schreibe /start.")
    sys.exit(0)

liste = json.loads((ausgabe / "liste.json").read_text()) if (ausgabe / "liste.json").exists() else []
for c in liste:
    video = ausgabe / c["datei"]
    text = video.with_suffix(".txt").read_text(encoding="utf-8")[:1000]
    for versuch in range(3):
        with video.open("rb") as f:
            if video.suffix == ".mp4":
                r = requests.post(f"{api}/sendVideo", timeout=300,
                                  data={"chat_id": cid, "caption": text, "supports_streaming": "true",
                                        "width": c.get("breite", 1080), "height": c.get("hoehe", 1920)},
                                  files={"video": (video.name, f, "video/mp4")})
            else:  # MOV/WebM als Datei, damit Telegram nichts umwandelt
                r = requests.post(f"{api}/sendDocument", timeout=300,
                                  data={"chat_id": cid, "caption": text},
                                  files={"document": (video.name, f)})
        if r.status_code != 429:
            break
        # Telegram bremst: so lange warten, wie es sagt
        warten = r.json().get("parameters", {}).get("retry_after", 5)
        print(f"{video.name}: Telegram bremst, warte {warten}s")
        time.sleep(warten + 1)
    print(video.name, "->", r.status_code, "" if r.ok else r.text[:200])
    time.sleep(1.5)
