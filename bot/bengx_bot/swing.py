"""Der Swing-Bot.

Das Modell in vier Schritten, jeder auf seinem Zeitrahmen:

1. **1h — Liquidität abgeräumt.** Eine Stundenkerze sticht unter das jüngste
   offene Swing-Tief und schließt wieder darüber. Die Stops der Käufer wurden
   abgeholt; wir erwarten die Bewegung nach oben. (Short spiegelbildlich.)

2. **5m — Fortsetzungskerze.** Danach muss eine Fünf-Minuten-Kerze die Richtung
   bestätigen: fester Körper, Schluss über dem Hoch der Vorkerze. Ohne diese
   Bestätigung war der Sweep nur ein Ausschlag.

3. **1m — Struktur oder Lücke.** Auf der Minute entweder ein Bruch der
   Struktur (Schluss über dem letzten bestätigten Swing-Hoch) oder eine
   Fair-Value-Gap. Erst jetzt ist das Setup scharf.

4. **Einstieg.** Entweder ein Pullback in die Lücke — Limit mitten in der
   Gap —, oder die Entstehung einer invertierten Lücke: eine gegenläufige
   FVG, durch die der Kurs schließt, dreht ihre Bedeutung um und trägt von
   unten.

Jede Stufe hat eine Frist. Läuft sie ab, beginnt alles von vorn. Ein neuer
Sweep setzt ein offenes Setup zurück.

Der ganze Ablauf wird in `prepare()` einmal über die Daten gerechnet, nicht
über Aufrufe hinweg angesammelt. Dadurch liefert der Bot nach einem Neustart
dieselben Signale wie im Backtest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Sequence

from . import indicators as ind
from .config import Config
from .model import Candle, Side, Signal
from .strategy import ExitRules
from .timeframes import (Gap, Sweep, SwingPoint, close_time, fair_value_gaps,
                         liquidity_sweeps, resample, swing_points)

MINUTE = timedelta(minutes=1)


@dataclass(frozen=True, slots=True)
class SwingContext:
    """Was die Maschine je Minutenkerze braucht."""

    atr: list[float | None]
    signals: dict[int, Signal]
    stages: dict[int, str]          # nur zur Nachschau und für die Tests

    def ready(self, i: int) -> bool:
        return self.atr[i] is not None


@dataclass
class _Setup:
    """Der Zustand zwischen Sweep und Einstieg."""

    sweep: Sweep
    stage: str                      # "sweep" | "continuation" | "armed"
    deadline: datetime
    trigger: str = ""
    armed_ts: datetime | None = None
    bos_level: float | None = None
    gaps: list[Gap] = field(default_factory=list)       # gleichgerichtete Lücken
    inverse: list[Gap] = field(default_factory=list)    # Kandidaten für ein IFVG
    extreme_low: float = float("inf")
    extreme_high: float = float("-inf")

    @property
    def side(self) -> Side:
        return self.sweep.side


class SwingTrader:
    name = "Swing"

    def __init__(self, config: Config) -> None:
        self.cfg = config
        self.p = config.swing
        self.pip = config.market.pip

    # ---- Vorlauf --------------------------------------------------------
    def warmup_bars(self) -> int:
        return (2 * self.p.swing_lookback_h1 + 3) * 60 + 40

    def exit_rules(self) -> ExitRules:
        p = self.p
        return ExitRules(
            partial_r=p.partial_r,
            partial_fraction=p.partial_fraction,
            trail_atr=p.trail_atr,
            time_stop_bars=p.max_hold_minutes,
            friday_cutoff_hour=p.friday_cutoff_hour,
        )

    def in_session(self, candle: Candle) -> bool:
        p = self.p
        ts = candle.ts
        if ts.weekday() >= 5:
            return False
        if not (p.session_start_hour <= ts.hour < p.session_end_hour):
            return False
        if ts.weekday() == 4 and ts.hour >= p.friday_cutoff_hour:
            return False
        return True

    # ---- Bausteine -------------------------------------------------------
    def _continuations(self, m5: Sequence[Candle]) -> list[tuple[datetime, Candle, Side]]:
        """Fünf-Minuten-Kerzen, die eine Richtung bestätigen."""
        out = []
        for i in range(1, len(m5)):
            c, prev = m5[i], m5[i - 1]
            span = c.high - c.low
            if span <= 0:
                continue
            body = abs(c.close - c.open) / span
            if body < self.p.min_continuation_body:
                continue
            known = close_time(c, 5)
            if c.close > c.open and c.close > prev.high:
                out.append((known, c, Side.LONG))
            elif c.close < c.open and c.close < prev.low:
                out.append((known, c, Side.SHORT))
        return out

    # ---- Ablauf ----------------------------------------------------------
    def prepare(self, candles: Sequence[Candle]) -> SwingContext:
        p = self.p
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        closes = [c.close for c in candles]
        atr = ind.atr(highs, lows, closes, p.atr_period)

        m5 = resample(candles, 5)
        h1 = resample(candles, 60)
        h1_points = swing_points(h1, p.swing_lookback_h1, 60)
        sweeps = liquidity_sweeps(h1, h1_points, 60)
        conts = self._continuations(m5)
        m1_points = swing_points(candles, p.swing_lookback_m1, 1)
        gaps = fair_value_gaps(candles, 1, min_size=p.min_gap_pips * self.pip)

        signals: dict[int, Signal] = {}
        stages: dict[int, str] = {}

        si = ci = gi = pi = 0
        setup: _Setup | None = None
        pending_conts: list[tuple[datetime, Candle, Side]] = []
        pending_gaps: list[Gap] = []
        swing_high: SwingPoint | None = None
        swing_low: SwingPoint | None = None

        for i, bar in enumerate(candles):
            ts = bar.ts

            # Alles einsammeln, was bis zum Beginn dieser Minute bekannt war.
            while ci < len(conts) and conts[ci][0] <= ts:
                pending_conts.append(conts[ci]); ci += 1
            while gi < len(gaps) and gaps[gi].known_ts <= ts:
                pending_gaps.append(gaps[gi]); gi += 1
            while pi < len(m1_points) and m1_points[pi].known_ts <= ts:
                pt = m1_points[pi]
                if pt.kind == "high":
                    swing_high = pt
                else:
                    swing_low = pt
                pi += 1

            fresh: Sweep | None = None
            while si < len(sweeps) and sweeps[si].known_ts <= ts:
                fresh = sweeps[si]; si += 1

            # Ein neuer Sweep macht alles Alte ungültig.
            if fresh is not None:
                setup = _Setup(sweep=fresh, stage="sweep",
                               deadline=fresh.known_ts +
                               timedelta(minutes=p.continuation_window_minutes))
                pending_conts = [x for x in pending_conts if x[0] > fresh.known_ts]
                pending_gaps = [g for g in pending_gaps if g.known_ts > fresh.known_ts]

            if setup is None:
                continue
            if ts > setup.deadline:
                setup = None
                continue

            setup.extreme_low = min(setup.extreme_low, bar.low)
            setup.extreme_high = max(setup.extreme_high, bar.high)
            side = setup.side

            # Stufe 2: Fortsetzungskerze auf 5m
            if setup.stage == "sweep":
                match = next((x for x in pending_conts
                              if x[2] is side and x[0] > setup.sweep.known_ts), None)
                if match is not None:
                    setup.stage = "continuation"
                    setup.deadline = match[0] + timedelta(minutes=p.trigger_window_minutes)
                    setup.armed_ts = match[0]
                stages[i] = setup.stage
                continue

            # Stufe 3: Bruch der Struktur oder eine Lücke auf 1m
            if setup.stage == "continuation":
                since = setup.armed_ts
                ref = swing_high if side is Side.LONG else swing_low
                bos = False
                if ref is not None and ref.known_ts <= ts:
                    bos = (bar.close > ref.price if side is Side.LONG
                           else bar.close < ref.price)
                    if bos:
                        setup.bos_level = ref.price
                same = [g for g in pending_gaps if g.side is side and g.known_ts >= since]
                if bos or same:
                    setup.stage = "armed"
                    setup.trigger = "bos" if bos else "fvg"
                    setup.armed_ts = ts
                    setup.deadline = ts + timedelta(minutes=p.entry_window_minutes)
                    setup.gaps = same
                    setup.inverse = [g for g in pending_gaps
                                     if g.side is side.opposite
                                     and g.known_ts > setup.sweep.known_ts]
                stages[i] = setup.stage
                continue

            # Stufe 4: Einstieg
            stages[i] = "armed"
            setup.gaps = [g for g in pending_gaps
                          if g.side is side and g.known_ts >= setup.sweep.known_ts
                          and not self._invalidated(g, candles, i)]
            setup.inverse = [g for g in pending_gaps
                             if g.side is side.opposite
                             and g.known_ts > setup.sweep.known_ts]

            signal = self._entry(bar, i, setup, candles, atr[i])
            if signal is not None:
                signals[i] = signal
                setup = None

        return SwingContext(atr=atr, signals=signals, stages=stages)

    # ---- Einstiegsprüfung -------------------------------------------------
    def _invalidated(self, gap: Gap, candles: Sequence[Candle], i: int) -> bool:
        """Eine Lücke ist tot, sobald eine Kerze jenseits von ihr schließt."""
        for j in range(gap.index + 1, i + 1):
            c = candles[j]
            if gap.side is Side.LONG and c.close < gap.low:
                return True
            if gap.side is Side.SHORT and c.close > gap.high:
                return True
        return False

    def _entry(self, bar: Candle, i: int, setup: _Setup,
               candles: Sequence[Candle], atr: float | None) -> Signal | None:
        p = self.p
        side = setup.side
        if atr is None or not self.in_session(bar):
            return None

        entry: float | None = None
        how = ""
        zone: Gap | None = None

        # a) Pullback in die Lücke — Limit mitten in der Gap.
        if p.allow_pullback and setup.gaps:
            gap = max(setup.gaps, key=lambda g: g.known_ts)
            if gap.known_ts <= bar.ts:
                level = gap.level(p.entry_fill)
                touched = bar.low <= level if side is Side.LONG else bar.high >= level
                if touched:
                    entry, how, zone = level, "Pullback in die FVG", gap

        # b) Invertierte Lücke — der Kurs schließt durch eine gegenläufige Gap.
        if entry is None and p.allow_ifvg:
            for gap in sorted(setup.inverse, key=lambda g: g.known_ts, reverse=True):
                if gap.known_ts > bar.ts:
                    continue
                through = (bar.close > gap.high if side is Side.LONG
                           else bar.close < gap.low)
                if through:
                    entry, how, zone = bar.close, "IFVG entstanden", gap
                    break

        if entry is None:
            return None

        stop = self._stop(side, setup, zone, entry)
        risk = abs(entry - stop)
        if risk <= 0:
            return None
        pips = risk / self.pip
        if not (p.min_stop_pips <= pips <= p.max_stop_pips):
            return None

        partial = entry + risk * p.partial_r * side.sign
        final = self._final_target(side, entry, risk, setup)
        reason = (f"1h-Sweep {setup.sweep.level:.2f} · 5m-Fortsetzung · "
                  f"1m-{setup.trigger.upper()} · {how}")
        return Signal(ts=bar.ts, side=side, entry=entry, stop=stop,
                      target=partial, atr=float(atr), adx=0.0,
                      reason=reason, final_target=final)

    def _stop(self, side: Side, setup: _Setup, zone: Gap | None,
              entry: float) -> float:
        buffer = self.p.stop_buffer_pips * self.pip
        source = self.p.stop_source
        if source == "sweep":
            base = setup.sweep.extreme
        elif source == "fvg" and zone is not None:
            base = zone.low if side is Side.LONG else zone.high
        else:  # "structure"
            base = setup.extreme_low if side is Side.LONG else setup.extreme_high
        return base - buffer if side is Side.LONG else base + buffer

    def _final_target(self, side: Side, entry: float, risk: float,
                      setup: _Setup) -> float:
        by_r = entry + risk * self.p.target_r * side.sign
        if self.p.target_mode != "liquidity":
            return by_r
        pool = setup.sweep.level
        if side is Side.LONG and pool > entry:
            return max(pool, entry + risk)
        if side is Side.SHORT and pool < entry:
            return min(pool, entry - risk)
        return by_r

    # ---- Schnittstelle zur Maschine ---------------------------------------
    def evaluate(self, candles: Sequence[Candle], ctx: SwingContext,
                 i: int) -> Signal | None:
        return ctx.signals.get(i)
