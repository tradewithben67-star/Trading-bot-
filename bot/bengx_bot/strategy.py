"""Das Regelwerk des Dauerläufers.

Die Idee in einem Satz: In einem klar gerichteten Markt den Ausbruch aus der
jüngsten Spanne mitnehmen, mit einem Stop, der sich an der Volatilität misst —
und in allen anderen Lagen nichts tun.

Fünf Bedingungen müssen gleichzeitig erfüllt sein, sonst gibt es kein Signal:

1. Trend      — Kurs über dem EMA(200) und der EMA steigt (umgekehrt für Short).
2. Stärke     — ADX(14) über der Schwelle; in der Seitwärtsphase bleibt der Bot draußen.
3. Volatilität— ATR(14) innerhalb eines Korridors; weder totes Wasser noch Panik.
4. Handelszeit— nur zwischen Londoner Eröffnung und New Yorker Nachmittag,
                freitags früher Schluss.
5. Ausbruch   — die Kerze schließt über dem höchsten Hoch der letzten 20 Kerzen
                (für Short: unter dem tiefsten Tief).

Jede Bedingung hat einen Grund. Der Trendfilter hält von Gegenbewegungen fern,
der ADX von der Seitwärtsphase, der Volatilitätskorridor von Kerzen, in denen
ein ATR-Stop entweder unsinnig eng oder unsinnig weit liegt, die Handelszeit
von der dünnen asiatischen Nacht, und der Ausbruch ist das eigentliche Signal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from . import indicators as ind
from .config import Config
from .model import Candle, Side, Signal


@dataclass(frozen=True, slots=True)
class Context:
    """Alle Indikatorreihen, einmal über die ganze Kerzenreihe gerechnet."""

    ema: list[float | None]
    ema_slope: list[float | None]
    atr: list[float | None]
    adx: list[float | None]
    donchian_up: list[float | None]
    donchian_dn: list[float | None]

    def ready(self, i: int) -> bool:
        return all(series[i] is not None for series in (
            self.ema, self.ema_slope, self.atr, self.adx,
            self.donchian_up, self.donchian_dn,
        ))


class Dauerlaeufer:
    """Der Bot aus dem Bereich X der Seite."""

    name = "Dauerläufer"

    def __init__(self, config: Config) -> None:
        self.cfg = config
        self.p = config.strategy
        self.pip = config.market.pip

    # ---- Vorbereitung -------------------------------------------------
    def prepare(self, candles: Sequence[Candle]) -> Context:
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        closes = [c.close for c in candles]
        p = self.p
        ema = ind.ema(closes, p.trend_ema)
        up, dn = ind.donchian(highs, lows, p.breakout)
        return Context(
            ema=ema,
            ema_slope=ind.slope(ema, p.trend_slope_bars),
            atr=ind.atr(highs, lows, closes, p.atr_period),
            adx=ind.adx(highs, lows, closes, p.adx_period),
            donchian_up=up,
            donchian_dn=dn,
        )

    def warmup_bars(self) -> int:
        p = self.p
        return max(p.trend_ema + p.trend_slope_bars, p.breakout, p.adx_period * 3) + 5

    # ---- Einzelne Regeln ----------------------------------------------
    def in_session(self, candle: Candle) -> bool:
        """Handelszeit: London bis New York, freitags früher Schluss."""
        p = self.p
        ts = candle.ts
        if ts.weekday() >= 5:            # Samstag, Sonntag
            return False
        if not (p.session_start_hour <= ts.hour < p.session_end_hour):
            return False
        if ts.weekday() == 4 and ts.hour >= p.friday_cutoff_hour:
            return False
        return True

    def trend_bias(self, ctx: Context, i: int, close: float) -> Side | None:
        """Richtung, die der übergeordnete Trend zulässt."""
        ema, slope = ctx.ema[i], ctx.ema_slope[i]
        if ema is None or slope is None:
            return None
        if close > ema and slope > 0:
            return Side.LONG
        if close < ema and slope < 0:
            return Side.SHORT
        return None

    def volatility_ok(self, ctx: Context, i: int) -> bool:
        a = ctx.atr[i]
        if a is None:
            return False
        pips = a / self.pip
        return self.p.min_atr_pips <= pips <= self.p.max_atr_pips

    def strength_ok(self, ctx: Context, i: int) -> bool:
        a = ctx.adx[i]
        return a is not None and a >= self.p.adx_min

    def breakout_side(self, ctx: Context, candle: Candle, i: int) -> Side | None:
        """Schlusskurs außerhalb der Spanne der Vorkerzen."""
        up, dn = ctx.donchian_up[i], ctx.donchian_dn[i]
        if up is None or dn is None:
            return None
        if candle.close > up:
            return Side.LONG
        if candle.close < dn:
            return Side.SHORT
        return None

    # ---- Signal ---------------------------------------------------------
    def evaluate(self, candles: Sequence[Candle], ctx: Context, i: int) -> Signal | None:
        """Prüft die abgeschlossene Kerze `i` und gibt höchstens ein Signal zurück."""
        if i < 1 or i >= len(candles) or not ctx.ready(i):
            return None

        candle = candles[i]
        if not self.in_session(candle):
            return None
        if not self.strength_ok(ctx, i):
            return None
        if not self.volatility_ok(ctx, i):
            return None

        bias = self.trend_bias(ctx, i, candle.close)
        if bias is None:
            return None

        breakout = self.breakout_side(ctx, candle, i)
        if breakout is None or breakout is not bias:
            return None

        atr_now = float(ctx.atr[i])
        adx_now = float(ctx.adx[i])
        entry = candle.close
        distance = self.p.stop_atr * atr_now
        stop = entry - distance * bias.sign
        target = entry + distance * self.p.partial_r * bias.sign

        reason = (
            f"Ausbruch über {self.p.breakout} Kerzen im Trend; "
            f"ADX {adx_now:.0f}, ATR {atr_now / self.pip:.0f} Pips"
            if bias is Side.LONG else
            f"Ausbruch unter {self.p.breakout} Kerzen im Trend; "
            f"ADX {adx_now:.0f}, ATR {atr_now / self.pip:.0f} Pips"
        )
        return Signal(
            ts=candle.ts,
            side=bias,
            entry=entry,
            stop=stop,
            target=target,
            atr=atr_now,
            adx=adx_now,
            reason=reason,
        )
