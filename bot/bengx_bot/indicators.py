"""Indikatoren, gerechnet auf Listen. Jede Funktion gibt eine Liste mit der
Länge der Eingabe zurück; Werte, die noch nicht definiert sind, sind None.

Bewusst ohne numpy: der Bot soll auf jedem Rechner mit Python 3.11 laufen.
"""

from __future__ import annotations

from typing import Sequence


def sma(values: Sequence[float], period: int) -> list[float | None]:
    """Einfacher gleitender Durchschnitt."""
    if period < 1:
        raise ValueError("period muss mindestens 1 sein")
    out: list[float | None] = [None] * len(values)
    total = 0.0
    for i, v in enumerate(values):
        total += v
        if i >= period:
            total -= values[i - period]
        if i >= period - 1:
            out[i] = total / period
    return out


def ema(values: Sequence[float], period: int) -> list[float | None]:
    """Exponentiell geglätteter Durchschnitt, gestartet auf dem SMA."""
    if period < 1:
        raise ValueError("period muss mindestens 1 sein")
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    k = 2.0 / (period + 1.0)
    prev = sum(values[:period]) / period
    out[period - 1] = prev
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1.0 - k)
        out[i] = prev
    return out


def wilder(values: Sequence[float | None], period: int) -> list[float | None]:
    """Wilders Glättung (RMA). None-Werte am Anfang werden übersprungen."""
    out: list[float | None] = [None] * len(values)
    buf: list[float] = []
    prev: float | None = None
    for i, v in enumerate(values):
        if v is None:
            continue
        if prev is None:
            buf.append(float(v))
            if len(buf) == period:
                prev = sum(buf) / period
                out[i] = prev
        else:
            prev = (prev * (period - 1) + float(v)) / period
            out[i] = prev
    return out


def true_range(highs: Sequence[float], lows: Sequence[float],
               closes: Sequence[float]) -> list[float | None]:
    """True Range: die größte der drei Spannen inklusive Kurslücke."""
    out: list[float | None] = [None] * len(highs)
    for i in range(len(highs)):
        if i == 0:
            out[i] = highs[i] - lows[i]
            continue
        prev_close = closes[i - 1]
        out[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - prev_close),
            abs(lows[i] - prev_close),
        )
    return out


def atr(highs: Sequence[float], lows: Sequence[float],
        closes: Sequence[float], period: int = 14) -> list[float | None]:
    """Average True Range nach Wilder — das Maß für die Volatilität."""
    return wilder(true_range(highs, lows, closes), period)


def rsi(closes: Sequence[float], period: int = 14) -> list[float | None]:
    """Relative Strength Index nach Wilder."""
    gains: list[float | None] = [None] * len(closes)
    losses: list[float | None] = [None] * len(closes)
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains[i] = max(diff, 0.0)
        losses[i] = max(-diff, 0.0)
    avg_gain = wilder(gains, period)
    avg_loss = wilder(losses, period)
    out: list[float | None] = [None] * len(closes)
    for i in range(len(closes)):
        g, l = avg_gain[i], avg_loss[i]
        if g is None or l is None:
            continue
        if l == 0:
            out[i] = 100.0
        else:
            rs = g / l
            out[i] = 100.0 - (100.0 / (1.0 + rs))
    return out


def adx(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float],
        period: int = 14) -> list[float | None]:
    """ADX nach Wilder — wie klar der Markt gerade gerichtet ist.

    Niedrige Werte heißen Seitwärts; dort soll der Bot nicht ausbrechen.
    """
    n = len(highs)
    plus_dm: list[float | None] = [None] * n
    minus_dm: list[float | None] = [None] * n
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm[i] = up if (up > down and up > 0) else 0.0
        minus_dm[i] = down if (down > up and down > 0) else 0.0

    tr = true_range(highs, lows, closes)
    tr[0] = None  # ohne Vorkerze ist die erste Spanne nicht vergleichbar
    atr_s = wilder(tr, period)
    plus_s = wilder(plus_dm, period)
    minus_s = wilder(minus_dm, period)

    dx: list[float | None] = [None] * n
    for i in range(n):
        a, p, m = atr_s[i], plus_s[i], minus_s[i]
        if a is None or p is None or m is None or a == 0:
            continue
        pdi = 100.0 * p / a
        mdi = 100.0 * m / a
        denom = pdi + mdi
        dx[i] = 0.0 if denom == 0 else 100.0 * abs(pdi - mdi) / denom
    return wilder(dx, period)


def donchian(highs: Sequence[float], lows: Sequence[float],
             period: int) -> tuple[list[float | None], list[float | None]]:
    """Höchstes Hoch und tiefstes Tief der *vorangegangenen* `period` Kerzen.

    Die laufende Kerze bleibt bewusst außen vor: sonst wäre der Ausbruch
    schon im Kanal enthalten und das Signal würde sich selbst bestätigen.
    """
    n = len(highs)
    upper: list[float | None] = [None] * n
    lower: list[float | None] = [None] * n
    for i in range(n):
        if i < period:
            continue
        window_h = highs[i - period:i]
        window_l = lows[i - period:i]
        upper[i] = max(window_h)
        lower[i] = min(window_l)
    return upper, lower


def slope(values: Sequence[float | None], lookback: int) -> list[float | None]:
    """Veränderung eines Werts gegenüber `lookback` Kerzen davor."""
    out: list[float | None] = [None] * len(values)
    for i in range(len(values)):
        j = i - lookback
        if j < 0:
            continue
        a, b = values[i], values[j]
        if a is None or b is None:
            continue
        out[i] = a - b
    return out
