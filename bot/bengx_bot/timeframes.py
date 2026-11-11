"""Mehrere Zeitrahmen aus einer Kerzenreihe, dazu die Bausteine des
Swing-Modells: Swing-Punkte, Liquiditäts-Sweeps und Fair-Value-Gaps.

Alles ohne Blick in die Zukunft. Jeder Baustein trägt ein `known_ts`: den
Zeitpunkt, ab dem er wirklich bekannt war. Ein Swing-Hoch etwa steht erst
fest, wenn `lookback` Kerzen danach gelaufen sind — vorher weiß niemand, ob
es ein Hoch war.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Sequence

from .model import Candle, Side


# ---- Zeitrahmen ---------------------------------------------------------
def resample(candles: Sequence[Candle], minutes: int,
             source_minutes: int = 1, drop_incomplete: bool = True) -> list[Candle]:
    """Fasst Kerzen zu einem größeren Zeitrahmen zusammen.

    Die Eimer liegen auf vollen Vielfachen seit Mitternacht UTC, damit eine
    Stundenkerze wirklich um xx:00 beginnt. Ein angebrochener letzter Eimer
    wird weggelassen: im Live-Betrieb wäre das eine Kerze, die noch läuft.
    """
    if minutes < source_minutes:
        raise ValueError("Der Zielzeitrahmen muss größer sein als der Quellzeitrahmen")
    if minutes % source_minutes:
        raise ValueError("Der Zielzeitrahmen muss ein Vielfaches der Quelle sein")

    span = minutes * 60
    buckets: list[tuple[Candle, int]] = []
    key: int | None = None

    for candle in candles:
        k = int(candle.ts.timestamp()) // span
        if k != key:
            key = k
            buckets.append((Candle(
                ts=datetime.fromtimestamp(k * span, tz=timezone.utc),
                open=candle.open, high=candle.high, low=candle.low,
                close=candle.close, volume=candle.volume), 1))
        else:
            prev, count = buckets[-1]
            buckets[-1] = (Candle(
                ts=prev.ts, open=prev.open,
                high=max(prev.high, candle.high),
                low=min(prev.low, candle.low),
                close=candle.close,
                volume=prev.volume + candle.volume), count + 1)

    if drop_incomplete and buckets and buckets[-1][1] < minutes // source_minutes:
        buckets.pop()
    return [c for c, _ in buckets]


def close_time(candle: Candle, minutes: int) -> datetime:
    """Wann diese Kerze fertig war — ab da darf man sie benutzen."""
    return candle.ts + timedelta(minutes=minutes)


# ---- Swing-Punkte --------------------------------------------------------
@dataclass(frozen=True, slots=True)
class SwingPoint:
    index: int
    ts: datetime
    price: float
    kind: str            # "high" oder "low"
    known_ts: datetime   # ab wann der Punkt bestätigt war


def swing_points(candles: Sequence[Candle], lookback: int,
                 minutes: int) -> list[SwingPoint]:
    """Fraktale Hochs und Tiefs: `lookback` Kerzen links und rechts niedriger
    bzw. höher. Bestätigt ist ein Punkt erst `lookback` Kerzen später."""
    if lookback < 1:
        raise ValueError("lookback muss mindestens 1 sein")
    out: list[SwingPoint] = []
    n = len(candles)
    for j in range(lookback, n - lookback):
        window = candles[j - lookback:j + lookback + 1]
        mid = candles[j]
        if mid.high == max(w.high for w in window) and \
                all(w.high < mid.high for w in window if w is not mid):
            out.append(SwingPoint(j, mid.ts, mid.high, "high",
                                  close_time(candles[j + lookback], minutes)))
        if mid.low == min(w.low for w in window) and \
                all(w.low > mid.low for w in window if w is not mid):
            out.append(SwingPoint(j, mid.ts, mid.low, "low",
                                  close_time(candles[j + lookback], minutes)))
    out.sort(key=lambda s: s.known_ts)
    return out


# ---- Liquiditäts-Sweep ----------------------------------------------------
@dataclass(frozen=True, slots=True)
class Sweep:
    ts: datetime         # Öffnung der Kerze, die gesweept hat
    known_ts: datetime   # Schluss dieser Kerze
    side: Side           # Richtung, die danach erwartet wird
    level: float         # der abgeräumte Swing-Punkt
    extreme: float       # das Extrem der Sweep-Kerze
    close: float


def liquidity_sweeps(candles: Sequence[Candle], points: Sequence[SwingPoint],
                     minutes: int) -> list[Sweep]:
    """Eine Kerze holt sich die Liquidität hinter dem jüngsten offenen
    Swing-Punkt und schließt wieder zurück im Bereich.

    Unter ein altes Tief stechen und darüber schließen heißt: die Verkäufer
    wurden abgeholt, der Weg nach oben ist frei — daher Side.LONG.

    Geprüft wird nur gegen den **jüngsten noch nicht abgeräumten** Punkt je
    Seite. Gegen jedes alte Hoch zu prüfen würde fast jede Kerze zu einem
    Sweep machen; gemeint ist die Liquidität, die gerade oben drauf liegt.
    """
    out: list[Sweep] = []
    taken: set[tuple[int, str]] = set()

    def newest(kind: str, before: int, ts: datetime) -> SwingPoint | None:
        found = None
        for p in points:
            if p.kind != kind or p.index >= before or p.known_ts > ts:
                continue
            if (p.index, p.kind) in taken:
                continue
            if found is None or p.index > found.index:
                found = p
        return found

    for i, c in enumerate(candles):
        done = close_time(c, minutes)
        low_point = newest("low", i, c.ts)
        high_point = newest("high", i, c.ts)

        long_hit = low_point is not None and c.low < low_point.price <= c.close
        short_hit = high_point is not None and c.high > high_point.price >= c.close

        if long_hit and short_hit:
            # Beide Seiten in einer Kerze: die tiefere Durchdringung zählt.
            long_hit = (low_point.price - c.low) >= (c.high - high_point.price)
            short_hit = not long_hit

        if long_hit:
            taken.add((low_point.index, "low"))
            out.append(Sweep(c.ts, done, Side.LONG, low_point.price, c.low, c.close))
        elif short_hit:
            taken.add((high_point.index, "high"))
            out.append(Sweep(c.ts, done, Side.SHORT, high_point.price, c.high, c.close))

    out.sort(key=lambda s: s.known_ts)
    return out


# ---- Fair Value Gap -------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Gap:
    side: Side           # LONG = bullische Lücke, SHORT = bärische
    low: float
    high: float
    index: int           # Index der dritten Kerze
    ts: datetime
    known_ts: datetime

    @property
    def size(self) -> float:
        return self.high - self.low

    def contains(self, price: float) -> bool:
        return self.low <= price <= self.high

    def level(self, fraction: float) -> float:
        """0 = die zuerst berührte Kante, 1 = die gegenüberliegende."""
        if self.side is Side.LONG:
            return self.high - fraction * self.size
        return self.low + fraction * self.size


def fair_value_gaps(candles: Sequence[Candle], minutes: int,
                    min_size: float = 0.0) -> list[Gap]:
    """Drei Kerzen, bei denen die mittlere eine Lücke reißt.

    Bullisch: das Tief der dritten Kerze liegt über dem Hoch der ersten.
    Dazwischen wurde kein Handel gemacht — diese Zone zieht den Kurs an.
    """
    out: list[Gap] = []
    for i in range(2, len(candles)):
        a, c = candles[i - 2], candles[i]
        if c.low > a.high and (c.low - a.high) >= min_size:
            out.append(Gap(Side.LONG, a.high, c.low, i, c.ts, close_time(c, minutes)))
        elif a.low > c.high and (a.low - c.high) >= min_size:
            out.append(Gap(Side.SHORT, c.high, a.low, i, c.ts, close_time(c, minutes)))
    return out
