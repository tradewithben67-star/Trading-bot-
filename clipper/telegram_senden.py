#!/usr/bin/env python3
"""Schickt alle fertigen Clips aus ausgabe/ per Telegram-Bot an dich.

Braucht TELEGRAM_BOT_TOKEN und TELEGRAM_CHAT_ID. Fehlt eins davon,
macht das Skript nichts (die Clips liegen dann nur im GitHub-Release).
"""
import json
import os
import sys
from pathlib import Path

import requests

ausgabe = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "ausgabe")
token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
if not (token and chat):
    print("Telegram nicht eingerichtet, ueberspringe.")
    sys.exit(0)

liste = json.loads((ausgabe / "liste.json").read_text()) if (ausgabe / "liste.json").exists() else []
for c in liste:
    video = ausgabe / c["datei"]
    text = video.with_suffix(".txt").read_text(encoding="utf-8")[:1000]
    with video.open("rb") as f:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendVideo",
                          data={"chat_id": chat, "caption": text, "supports_streaming": "true"},
                          files={"video": (video.name, f, "video/mp4")}, timeout=300)
    print(video.name, "->", r.status_code, "" if r.ok else r.text[:200])
