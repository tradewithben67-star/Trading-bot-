"""Liest Bens Nachrichten, ohne ein Modell zu fragen.

Früher ging jede Nachricht an Gemini, das daraus Werkzeugaufrufe machte.
Das kostete bei jedem Werkzeug eine eigene Anfrage — auf dem kostenlosen
Kontingent (15 pro Minute) war das aussichtslos, und am Ende kam nur noch
„You exceeded your current quota" zurück.

Ein Signal ist aber kein Verständnisproblem. Es sind eine Richtung und
drei Zahlen. Das hier liest sie fest und tut immer dasselbe — ohne Netz,
ohne Kosten, ohne Warten, und prüfbar.
"""

from __future__ import annotations

import re
from typing import Any

# long/short in den Schreibweisen, die Ben wirklich benutzt
LONG = ("long", "buy", "kaufen", "lang")
SHORT = ("short", "sell", "verkaufen", "kurz")

# Wörter, hinter denen eine bestimmte Zahl steht
MARKEN = {
    "sl": ("stop", "sl", "stoploss", "stop-loss"),
    "tp": ("ziel", "tp", "target", "take", "takeprofit", "take-profit"),
    "entry": ("einstieg", "entry", "bei", "ab"),
}

ERGEBNIS = {
    "gewonnen": ("ziel", "tp", "gewonnen", "getroffen", "im ziel", "läuft ins ziel"),
    "verloren": ("stop", "sl", "verloren", "ausgestoppt", "rausgeflogen"),
    "be": ("be", "ausgeglichen", "breakeven", "break-even", "null"),
}


def _zahl(text: str) -> float | None:
    """„4.012,40" und „4012.40" ergeben beide 4012.40."""
    roh = text.strip()
    if not roh:
        return None
    # Deutsche Schreibweise: Punkt trennt Tausender, Komma die Stelle.
    if "," in roh:
        roh = roh.replace(".", "").replace(",", ".")
    try:
        return float(roh)
    except ValueError:
        return None


def _zahlen_mit_ort(text: str) -> list[tuple[int, int, float]]:
    """Alle Zahlen im Text, mit Anfang und Ende."""
    raus = []
    for treffer in re.finditer(r"\d[\d.,]*", text):
        wert = _zahl(treffer.group(0).rstrip(".,"))
        if wert is not None:
            raus.append((treffer.start(), treffer.end(), wert))
    return raus


def signal_lesen(text: str) -> dict[str, Any] | None:
    """Macht aus „long 4012, stop 4004, ziel 4029, 1h sweep" ein Signal.

    Gibt None zurück, wenn die Nachricht offensichtlich keins ist — dann
    soll der Bot nicht raten, sondern nachfragen.
    """
    if not text:
        return None
    klein = text.lower()

    seite = None
    for wort in LONG:
        if re.search(rf"\b{wort}\b", klein):
            seite = "long"
            break
    if seite is None:
        for wort in SHORT:
            if re.search(rf"\b{wort}\b", klein):
                seite = "short"
                break
    if seite is None:
        return None

    zahlen = _zahlen_mit_ort(klein)
    if len(zahlen) < 3:
        return None

    gefunden: dict[str, float] = {}
    belegt: dict[str, int] = {}
    for feld, woerter in MARKEN.items():
        for wort in woerter:
            for marke in re.finditer(rf"\b{wort}\b", klein):
                # Die erste Zahl NACH dem Wort gehört dazu.
                for i, (ort, _, wert) in enumerate(zahlen):
                    if ort > marke.end() and i not in belegt.values():
                        gefunden[feld] = wert
                        belegt[feld] = i
                        break
                if feld in gefunden:
                    break
            if feld in gefunden:
                break

    # Was nicht beschriftet war, kommt der Reihe nach: Einstieg, Stop, Ziel.
    offen = [i for i in range(len(zahlen)) if i not in belegt.values()]
    for feld in ("entry", "sl", "tp"):
        if feld not in gefunden and offen:
            i = offen.pop(0)
            gefunden[feld] = zahlen[i][2]
            belegt[feld] = i

    if not {"entry", "sl", "tp"} <= set(gefunden):
        return None

    # Die Begründung beginnt nach dem letzten KURS — nicht nach der letzten
    # Ziffer. Sonst frisst "1h sweep und 1m bos" sich selbst auf, weil das
    # "1" in "1m" als Zahl zählt.
    ende = max(zahlen[i][1] for i in belegt.values())
    begruendung = text[ende:].strip(" ,;.-")

    return {
        "side": seite,
        "entry": gefunden["entry"],
        "sl": gefunden["sl"],
        "tp": gefunden["tp"],
        "note": begruendung,
    }


def ergebnis_lesen(text: str) -> tuple[str, str] | None:
    """Erkennt „sig-0003 ziel" oder einfach „stop".

    Gibt (Kennung oder leer, Ergebnis) zurück.
    """
    if not text:
        return None
    klein = text.lower().strip()

    kennung = ""
    treffer = re.search(r"\bsig-?(\d{1,6})\b", klein)
    if treffer:
        kennung = f"sig-{int(treffer.group(1)):04d}"
        klein = klein[:treffer.start()] + klein[treffer.end():]

    for lage, woerter in ERGEBNIS.items():
        for wort in woerter:
            if re.search(rf"\b{re.escape(wort)}\b", klein):
                return kennung, lage
    return None


def ja_gesagt(text: str) -> bool | None:
    """True bei Ja, False bei Nein, None wenn es weder noch ist."""
    klein = (text or "").lower().strip(" .!?")
    if klein in ("ja", "j", "jo", "jep", "yes", "y", "ok", "okay", "passt",
                 "raus", "senden", "schick", "schicken", "los"):
        return True
    if klein in ("nein", "n", "no", "nee", "stop", "abbrechen", "verwerfen",
                 "doch nicht", "lass", "nicht"):
        return False
    return None
