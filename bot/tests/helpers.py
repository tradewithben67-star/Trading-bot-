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



def rows_to_candles(rows, start: datetime = START, minutes: int = 1):
    """Aus (open, high, low, close)-Zeilen Kerzen bauen."""
    out = []
    ts = start
    for o, h, l, c in rows:
        out.append(candle(ts, o, h, l, c))
        ts += timedelta(minutes=minutes)
    return out


def m1_hour(start_price: float, end_price: float, low: float | None = None,
            high: float | None = None, wick: float = 0.5):
    """60 Minutenkerzen von `start_price` nach `end_price`.

    `low`/`high` setzen in der Mitte der Stunde einen Ausschlag — so lässt sich
    ein Stundentief oder ein Sweep genau platzieren.
    """
    rows = []
    step = (end_price - start_price) / 60.0
    p = start_price
    for k in range(60):
        o, c = p, p + step
        h = max(o, c) + wick
        l = min(o, c) - wick
        if low is not None and k == 30:
            l = min(l, low)
        if high is not None and k == 30:
            h = max(h, high)
        rows.append((round(o, 2), round(h, 2), round(l, 2), round(c, 2)))
        p = c
    return rows


def sweep_scenario(entry_phase: list | None = None):
    """Ein vollständiges Swing-Setup auf der Long-Seite.

    Fünf Stunden bauen ein Stundentief bei 1990 auf, die sechste holt es sich
    (Tief 1985) und schließt darüber — der Sweep. Die siebte Stunde liefert
    Fortsetzungskerze, Lücke und Pullback.
    """
    rows = []
    rows += m1_hour(2000, 1999, low=1998)      # Stunde 0
    rows += m1_hour(1999, 1998, low=1996)      # Stunde 1
    rows += m1_hour(1998, 1997, low=1990)      # Stunde 2 — das Swing-Tief
    rows += m1_hour(1997, 1996, low=1995)      # Stunde 3
    rows += m1_hour(1996, 1995, low=1997)      # Stunde 4 (Tief über 1990)
    rows += m1_hour(1995, 2002, low=1985)      # Stunde 5 — Sweep und Rückschluss
    rows += entry_phase if entry_phase is not None else long_entry_phase()
    return rows_to_candles(rows)


def long_entry_phase():
    """Stunde 6: ruhig, dann Fortsetzung, dann Lücke, dann Pullback."""
    rows = []
    p = 2002.0
    for _ in range(10):                        # Minuten 0–9: ruhig
        rows.append((p, p + 0.3, p - 0.3, p + 0.1))
        p += 0.1
    for _ in range(5):                         # Minuten 10–14: Fortsetzung
        rows.append((p, p + 1.5, p - 0.1, p + 1.4))
        p += 1.4
    rows.append((p, p + 0.3, p - 0.2, p + 0.2)); p += 0.2        # 15
    top16 = p + 0.3                                             # Hoch der 16. Minute
    rows.append((p, top16, p - 0.2, p + 0.2)); p += 0.2         # 16
    rows.append((p, p + 4.0, p, p + 3.8)); p += 3.8              # 17 — reißt die Lücke
    rows.append((p, p + 0.5, top16 + 2.5, p + 0.2)); p += 0.2    # 18 — Tief über Hoch 16
    gap_low, gap_high = top16, top16 + 2.5
    mid = gap_high - 0.5 * (gap_high - gap_low)
    # Der Pullback reicht bis an die ferne Kante: so greift jedes Einstiegslevel.
    rows.append((p, p + 0.2, gap_low, mid + 0.3))                # 19 — Pullback in die Lücke
    p = mid + 0.3
    for _ in range(40):
        rows.append((p, p + 0.4, p - 0.4, p + 0.1))
        p += 0.1
    return [(round(a, 2), round(b, 2), round(c, 2), round(d, 2)) for a, b, c, d in rows]


def ifvg_entry_phase():
    """Stunde 6 in einer Fassung, die eine invertierte Lücke erzeugt.

    Nach der Fortsetzung reißt ein kurzer Rutsch eine bärische Lücke; die
    nächste Kerze schließt darüber. Damit dreht die Lücke ihre Bedeutung.
    """
    rows = []
    p = 2002.0
    for _ in range(10):                                   # ruhig
        rows.append((p, p + 0.3, p - 0.3, p + 0.1)); p += 0.1
    for _ in range(5):                                    # Fortsetzung
        rows.append((p, p + 1.5, p - 0.1, p + 1.4)); p += 1.4
    a_low = p - 0.5
    rows.append((p, p + 0.5, a_low, p))                   # A
    rows.append((p, p + 0.1, p - 4.0, p - 3.8))           # B — Rutsch
    p -= 3.8
    rows.append((p, a_low - 2.5, p - 0.7, p - 0.2))       # C — Hoch unter Tief A
    p -= 0.2
    rows.append((p, p + 2.0, p - 0.2, p + 1.8)); p += 1.8  # D
    rows.append((p, a_low + 1.0, p - 0.3, a_low + 0.7))    # E — Schluss über der Lücke
    p = a_low + 0.7
    for _ in range(40):
        rows.append((p, p + 0.4, p - 0.4, p + 0.1)); p += 0.1
    return [(round(a, 2), round(b, 2), round(c, 2), round(d, 2)) for a, b, c, d in rows]
