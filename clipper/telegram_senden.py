#!/usr/bin/env python3
"""Schickt alle fertigen Clips aus einem Ordner per Telegram (fuer Handbetrieb).

Die Clip-Fabrik selbst schickt jeden Clip direkt nach dem Schneiden; dieses
Skript braucht man nur, um einen Ordner nachtraeglich zu verschicken.

Aufruf: telegram_senden.py <ausgabe-ordner> <chat-id-datei>
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import telegram_versand as telegram  # noqa: E402

ausgabe = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "ausgabe")
chat_datei = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent / "state" / "telegram_chat.txt"

tg = telegram.verbinden(chat_datei)
if not tg:
    sys.exit(0)
liste = json.loads((ausgabe / "liste.json").read_text()) if (ausgabe / "liste.json").exists() else []
for c in liste:
    video = ausgabe / c["datei"]
    tg.senden(video, video.with_suffix(".txt").read_text(encoding="utf-8"))
