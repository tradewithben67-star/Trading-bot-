"""Hilfen für die Tests: Kerzen bauen, ohne jedes Mal alles auszuschreiben."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bengx_bot.model import Candle  # noqa: E402

START = datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)   # Montag, 08:00 UTC


def candle(ts: datetime, o: float, h: float, l: float, c: float) -> Candle:
    return Candle(ts=ts, open=o, high=h, low=l, close=c, volume=1000.0)


def series(closes, start: datetime = START, minutes: int = 60, spread: float = 1.0):
    """Baut aus Schlusskursen eine saubere Kerzenreihe."""
    out = []
    ts = start
    prev = closes[0]
    for c in closes:
        o = prev
        h = max(o, c) + spread
        l = min(o, c) - spread
        out.append(candle(ts, o, h, l, c))
        prev = c
        ts += timedelta(minutes=minutes)
    return out


def trending(n: int = 400, start_price: float = 2000.0, step: float = 4.0,
             wobble: float = 0.5, start: datetime = START):
    """Steigende Kerzen, deren Schluss über den Dochten der Vorkerzen liegt.

    Der Schritt muss größer sein als der Docht, sonst gibt es keinen Ausbruch —
    ein gleichmäßiges Dahinkriechen löst das Regelwerk zu Recht nicht aus.
    """
    closes = []
    price = start_price
    for i in range(n):
        price += step + (wobble if i % 2 else -wobble)
        closes.append(round(price, 2))
    return series(closes, start=start, spread=1.0)


def choppy(n: int = 400, price: float = 2000.0, span: float = 6.0,
           seed: int = 42, start: datetime = START):
    """Seitwärtsphase mit unruhigen, aber richtungslosen Kerzen.

    Wichtig: Hochs und Tiefs müssen schwanken. Eine Reihe mit exakt gleichen
    Hochs und Tiefs hat dauerhaft null Richtungsbewegung in eine Seite — der
    ADX wird dann rechnerisch 100, obwohl sich nichts bewegt. Echte Märkte
    sehen so nicht aus, Testdaten sollten es auch nicht.
    """
    import random

    rng = random.Random(seed)
    out = []
    ts = start
    prev = price
    for _ in range(n):
        o = prev
        c = price + rng.uniform(-span / 2, span / 2)
        h_ = max(o, c) + abs(rng.gauss(0, span / 3))
        l_ = min(o, c) - abs(rng.gauss(0, span / 3))
        out.append(candle(ts, round(o, 2), round(h_, 2), round(l_, 2), round(c, 2)))
        prev = c
        ts += timedelta(minutes=60)
    return out

