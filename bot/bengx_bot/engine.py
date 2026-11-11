"""Die Maschine: aus Kerze wird Signal, aus Signal wird Position, aus Position
wird irgendwann ein Trade. Backtest und Live-Betrieb benutzen genau diesen Code —
damit der Test prüft, was später wirklich läuft.
"""

from __future__ import annotations

from typing import Callable, Sequence

from .broker import PaperBroker
from .config import Config
from .model import Candle, ExitReason, Position, Side, Trade
from .risk import RiskManager
from .strategy import Context, Dauerlaeufer


class TradeEngine:
    def __init__(self, config: Config, strategy: Dauerlaeufer,
                 risk: RiskManager, broker: PaperBroker,
                 on_event: Callable[[str, dict], None] | None = None) -> None:
        self.cfg = config
        self.strategy = strategy
        self.risk = risk
        self.broker = broker
        self.on_event = on_event or (lambda kind, data: None)
        self.rejections: dict[str, int] = {}

    # ---- Ausstiege -----------------------------------------------------
    def _trail_for(self, pos: Position, atr: float) -> float:
        """Nachgezogener Stop im Abstand von `trail_atr` ATR vom Extrem."""
        d = self.cfg.strategy.trail_atr * atr
        if pos.side is Side.LONG:
            return pos.high_water - d
        return pos.low_water + d

    def _manage(self, candles: Sequence[Candle], ctx: Context, i: int) -> list[Trade]:
        candle = candles[i]
        atr = ctx.atr[i]
        closed: list[Trade] = []
        p = self.cfg.strategy

        for pos in list(self.broker.positions):
            if pos.opened_bar >= i:          # in dieser Kerze erst eröffnet
                continue
            pos.mark(candle.high, candle.low)
            long = pos.side is Side.LONG
            held = i - pos.opened_bar

            # 1. Stop zuerst. Liegen Stop und Ziel in derselben Kerze, gilt der
            #    Stop — wir wissen nicht, was zuerst kam, und rechnen uns nicht reich.
            hit_stop = candle.low <= pos.stop if long else candle.high >= pos.stop
            if hit_stop:
                reason = ExitReason.TRAIL if pos.partial_done else ExitReason.STOP
                trade = self.broker.close(pos, pos.stop, candle.ts, reason)
                closed.append(trade)
                continue

            # 2. Teilziel: die Hälfte raus, Rest auf Einstand absichern.
            if not pos.partial_done and p.partial_fraction > 0:
                hit_target = candle.high >= pos.target if long else candle.low <= pos.target
                if hit_target:
                    self.broker.reduce(pos, p.partial_fraction, pos.target)
                    pos.stop = max(pos.stop, pos.entry) if long else min(pos.stop, pos.entry)
                    self.on_event("partial", {"id": pos.id, "price": pos.target})

            # 3. Stop nachziehen, sobald das Teilziel gelaufen ist.
            if pos.partial_done and atr:
                trail = self._trail_for(pos, float(atr))
                pos.stop = max(pos.stop, trail) if long else min(pos.stop, trail)

            # 4. Zeitstop: was sich nach N Kerzen nicht bewegt hat, blockiert nur Kapital.
            if held >= p.time_stop_bars:
                trade = self.broker.close(pos, candle.close, candle.ts, ExitReason.TIME)
                closed.append(trade)
                continue

            # 5. Vor dem Wochenende glattstellen — über Nacht von Freitag auf
            #    Montag reißen Kurslücken jeden Stop.
            if candle.ts.weekday() == 4 and candle.ts.hour >= p.friday_cutoff_hour:
                trade = self.broker.close(pos, candle.close, candle.ts, ExitReason.SESSION)
                closed.append(trade)

        for t in closed:
            self.risk.on_trade_closed(t, i)
            self.on_event("close", {"trade": t})
        return closed

    # ---- Einstiege -----------------------------------------------------
    def _enter(self, candles: Sequence[Candle], ctx: Context, i: int) -> Position | None:
        signal = self.strategy.evaluate(candles, ctx, i)
        if signal is None:
            return None
        decision = self.risk.evaluate(signal, len(self.broker.positions), i)
        if not decision.allowed:
            self.rejections[decision.reason] = self.rejections.get(decision.reason, 0) + 1
            self.on_event("rejected", {"signal": signal, "reason": decision.reason})
            return None
        pos = self.broker.open(
            side=signal.side,
            size=decision.size,
            price=signal.entry,
            when=signal.ts,
            bar=i,
            stop=signal.stop,
            target=signal.target,
            note=signal.reason,
        )
        self.on_event("open", {"position": pos, "signal": signal})
        return pos

    # ---- Ein Schritt ----------------------------------------------------
    def step(self, candles: Sequence[Candle], ctx: Context, i: int) -> list[Trade]:
        """Verarbeitet genau eine abgeschlossene Kerze."""
        trades = self._manage(candles, ctx, i)
        self.risk.equity = self.broker.equity
        self.risk.peak = max(self.risk.peak, self.risk.equity)
        if not self.risk.halted_reason:
            self._enter(candles, ctx, i)
        return trades

    def flatten(self, candle: Candle, reason: ExitReason = ExitReason.KILL) -> list[Trade]:
        """Not-Aus: alles zum Marktkurs schließen."""
        out = []
        for pos in list(self.broker.positions):
            out.append(self.broker.close(pos, candle.close, candle.ts, reason))
        return out
