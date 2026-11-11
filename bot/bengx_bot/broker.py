"""Broker-Anbindung.

`PaperBroker` führt Order gegen Kerzendaten aus und rechnet Spread, Slippage
und Kommission mit ein. Er ist der Standard: der Bot handelt zuerst auf dem
Papierkonto.

`Broker` ist die Schnittstelle, die ein echter Anbieter erfüllen muss. Sie ist
bewusst klein gehalten. Eine echte Anbindung gehört in eine eigene Klasse mit
den Zugangsdaten aus der Umgebung — niemals in diese Datei und niemals ins
Repository.
"""

from __future__ import annotations

import itertools
from datetime import datetime
from typing import Protocol

from .config import Config
from .model import ExitReason, Position, Side, Trade


class Broker(Protocol):
    """Was der Bot von einem Broker braucht."""

    equity: float

    def open(self, side: Side, size: float, price: float, when: datetime,
             bar: int, stop: float, target: float, note: str) -> Position: ...

    def reduce(self, position: Position, fraction: float, price: float) -> None: ...

    def close(self, position: Position, price: float, when: datetime,
              reason: ExitReason) -> Trade: ...


class PaperBroker:
    """Papierkonto. Rechnet jede Ausführung zum schlechteren Kurs ab."""

    def __init__(self, config: Config, equity: float | None = None) -> None:
        self.cfg = config
        self.pip = config.market.pip
        self.costs = config.costs
        self.equity = equity if equity is not None else config.risk.start_equity
        self.positions: list[Position] = []
        self._ids = itertools.count(1)

    # ---- Ausführungskurse ---------------------------------------------
    def _fill(self, price: float, side: Side, entering: bool) -> float:
        """Der Kurs, den man wirklich bekommt: halber Spread plus Slippage,
        immer gegen die eigene Richtung."""
        penalty = (self.costs.spread_pips / 2.0 + self.costs.slippage_pips) * self.pip
        direction = side.sign if entering else -side.sign
        return price + penalty * direction

    def _commission(self, size: float) -> float:
        return abs(size) * self.costs.commission_per_unit

    # ---- Order ----------------------------------------------------------
    def open(self, side: Side, size: float, price: float, when: datetime,
             bar: int, stop: float, target: float, note: str = "") -> Position:
        fill = self._fill(price, side, entering=True)
        pos = Position(
            id=f"sig-{when:%Y%m%d-%H%M}-{next(self._ids):03d}",
            side=side,
            size=size,
            entry=fill,
            stop=stop,
            target=target,
            opened_at=when,
            opened_bar=bar,
            initial_risk=abs(fill - stop),
            original_size=size,
            note=note,
        )
        self.equity -= self._commission(size)
        self.positions.append(pos)
        return pos

    def reduce(self, position: Position, fraction: float, price: float) -> None:
        """Teilverkauf. Der Gewinn wandert in `realised_pnl`, die Position bleibt."""
        if not 0 < fraction < 1:
            raise ValueError("fraction muss zwischen 0 und 1 liegen")
        part = position.size * fraction
        step = self.cfg.market.size_step
        if step > 0:
            part = int(part / step) * step
        if part <= 0 or part >= position.size:
            return
        fill = self._fill(price, position.side, entering=False)
        pnl = (fill - position.entry) * position.side.sign * part
        pnl -= self._commission(part)
        position.realised_pnl += pnl
        position.size -= part
        position.partial_done = True
        self.equity += pnl

    def close(self, position: Position, price: float, when: datetime,
              reason: ExitReason) -> Trade:
        fill = self._fill(price, position.side, entering=False)
        pnl = (fill - position.entry) * position.side.sign * position.size
        pnl -= self._commission(position.size)
        total = position.realised_pnl + pnl
        self.equity += pnl

        base = position.original_size * self.pip
        pips = total / base if base else 0.0
        risk_total = position.initial_risk * position.original_size
        r = total / risk_total if risk_total else 0.0

        if position in self.positions:
            self.positions.remove(position)

        return Trade(
            id=position.id,
            side=position.side,
            size=position.original_size,
            entry=position.entry,
            stop=position.stop,
            target=position.target,
            exit_price=fill,
            opened_at=position.opened_at,
            closed_at=when,
            # ungerundet: gerundete Beträge summieren sich über viele Trades
            # nicht mehr auf den Kontostand. Gerundet wird erst bei der Ausgabe.
            pips=pips,
            pnl=total,
            r_multiple=r,
            reason=reason,
            note=position.note,
            tags={"partial": position.partial_done},
        )

    def mark_to_market(self, price: float) -> float:
        floating = sum(p.unrealised(price) for p in self.positions)
        return self.equity + floating
