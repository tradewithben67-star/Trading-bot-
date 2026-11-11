"""Risikosteuerung. Sie steht über der Strategie: ein Signal darf anfragen,
aber nur hier wird entschieden, ob und wie groß gehandelt wird.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from .config import Config
from .model import Signal, Trade


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    size: float
    reason: str


class RiskManager:
    def __init__(self, config: Config) -> None:
        self.cfg = config
        self.r = config.risk
        self.m = config.market
        self.equity = config.risk.start_equity
        self.peak = config.risk.start_equity
        self._day: date | None = None
        self._day_start_equity = config.risk.start_equity
        self._consecutive_losses = 0
        self._cooldown_until_bar = -1
        self.halted_reason: str | None = None

    # ---- Zustand ------------------------------------------------------
    def roll_day(self, when: datetime) -> None:
        """Neuer Handelstag: das Tagesverlust-Limit beginnt von vorn."""
        d = when.date()
        if self._day != d:
            self._day = d
            self._day_start_equity = self.equity

    def on_trade_closed(self, trade: Trade, bar_index: int) -> None:
        self.equity += trade.pnl
        self.peak = max(self.peak, self.equity)
        if trade.lost:
            self._consecutive_losses += 1
            if self._consecutive_losses >= self.cfg.strategy.cooldown_after_losses:
                self._cooldown_until_bar = bar_index + self.cfg.strategy.cooldown_bars
                self._consecutive_losses = 0
        elif trade.won:
            self._consecutive_losses = 0

    # ---- Kennzahlen ---------------------------------------------------
    @property
    def drawdown(self) -> float:
        if self.peak <= 0:
            return 0.0
        return max(0.0, (self.peak - self.equity) / self.peak)

    @property
    def day_loss(self) -> float:
        if self._day_start_equity <= 0:
            return 0.0
        return max(0.0, (self._day_start_equity - self.equity) / self._day_start_equity)

    def size_factor(self) -> float:
        """Die Drawdown-Bremse: ab einem Rückgang wird halbiert, nicht erhöht."""
        return 0.5 if self.drawdown >= self.r.drawdown_halve else 1.0

    # ---- Entscheidung --------------------------------------------------
    def evaluate(self, signal: Signal, open_positions: int, bar_index: int) -> Decision:
        self.roll_day(signal.ts)

        if self.halted_reason:
            return Decision(False, 0.0, self.halted_reason)
        if self.equity <= 0:
            return Decision(False, 0.0, "kein Kapital mehr")
        if self.drawdown >= self.r.drawdown_stop:
            return Decision(False, 0.0,
                            f"Drawdown-Grenze erreicht ({self.drawdown:.1%})")
        if self.day_loss >= self.r.daily_loss_limit:
            return Decision(False, 0.0,
                            f"Tagesverlust-Limit erreicht ({self.day_loss:.1%})")
        if open_positions >= self.r.max_positions:
            return Decision(False, 0.0, "schon genug Positionen offen")
        if bar_index <= self._cooldown_until_bar:
            return Decision(False, 0.0, "Pause nach Verlustserie")

        risk_per_unit = signal.risk_per_unit
        if risk_per_unit <= 0:
            return Decision(False, 0.0, "Stop liegt auf dem Einstieg")

        budget = self.equity * self.r.risk_per_trade * self.size_factor()
        raw = budget / risk_per_unit
        size = self._round_size(raw)
        if size < self.m.min_size:
            return Decision(False, 0.0, "Position wäre kleiner als die Mindestgröße")
        if size > self.m.max_size:
            size = self.m.max_size
        return Decision(True, size, "ok")

    def _round_size(self, raw: float) -> float:
        step = self.m.size_step
        if step <= 0:
            return raw
        return int(raw / step) * step

    def halt(self, reason: str) -> None:
        """Not-Aus: ab hier wird nichts Neues mehr eröffnet."""
        self.halted_reason = reason

    def resume(self) -> None:
        self.halted_reason = None
