"""Die Datentypen, die durch den ganzen Bot laufen."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class Side(str, Enum):
    LONG = "long"
    SHORT = "short"

    @property
    def sign(self) -> int:
        return 1 if self is Side.LONG else -1

    @property
    def opposite(self) -> "Side":
        return Side.SHORT if self is Side.LONG else Side.LONG


class ExitReason(str, Enum):
    STOP = "stop"
    TARGET = "target"
    TRAIL = "trail"
    TIME = "time"
    SESSION = "session"
    KILL = "kill"
    MANUAL = "manual"


@dataclass(frozen=True, slots=True)
class Candle:
    """Eine abgeschlossene Kerze. `ts` ist immer der Öffnungszeitpunkt in UTC."""

    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    def __post_init__(self) -> None:
        if self.ts.tzinfo is None:
            raise ValueError("Kerzen brauchen einen Zeitpunkt mit Zeitzone (UTC)")
        if not (self.low <= self.open <= self.high and self.low <= self.close <= self.high):
            raise ValueError(f"unplausible Kerze bei {self.ts.isoformat()}")


@dataclass(frozen=True, slots=True)
class Signal:
    """Was die Strategie aus einer Kerze macht — noch ohne Größe und Risiko."""

    ts: datetime
    side: Side
    entry: float
    stop: float
    target: float
    atr: float
    adx: float
    reason: str

    @property
    def risk_per_unit(self) -> float:
        return abs(self.entry - self.stop)


@dataclass
class Position:
    """Eine offene Position im Markt."""

    id: str
    side: Side
    size: float
    entry: float
    stop: float
    target: float
    opened_at: datetime
    opened_bar: int
    initial_risk: float
    original_size: float = 0.0
    partial_done: bool = False
    realised_pnl: float = 0.0
    high_water: float = 0.0
    low_water: float = 0.0
    note: str = ""

    def __post_init__(self) -> None:
        if self.original_size <= 0:
            self.original_size = self.size
        if self.high_water <= 0:
            self.high_water = self.entry
        if self.low_water <= 0:
            self.low_water = self.entry

    def unrealised(self, price: float) -> float:
        return (price - self.entry) * self.side.sign * self.size

    def mark(self, high: float, low: float) -> None:
        """Höchst- und Tiefstkurs seit Einstieg mitführen — für den Trailing-Stop."""
        self.high_water = max(self.high_water, high)
        self.low_water = min(self.low_water, low)


@dataclass
class Trade:
    """Ein abgeschlossener Handel, so wie er ins Protokoll geht."""

    id: str
    side: Side
    size: float
    entry: float
    stop: float
    target: float
    exit_price: float
    opened_at: datetime
    closed_at: datetime
    pips: float
    pnl: float
    r_multiple: float
    reason: ExitReason
    note: str = ""
    tags: dict[str, Any] = field(default_factory=dict)

    @property
    def won(self) -> bool:
        return self.pnl > 0

    @property
    def lost(self) -> bool:
        return self.pnl < 0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["side"] = self.side.value
        d["reason"] = self.reason.value
        d["opened_at"] = self.opened_at.astimezone(timezone.utc).isoformat()
        d["closed_at"] = self.closed_at.astimezone(timezone.utc).isoformat()
        return d

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Trade":
        return Trade(
            id=d["id"],
            side=Side(d["side"]),
            size=float(d["size"]),
            entry=float(d["entry"]),
            stop=float(d["stop"]),
            target=float(d["target"]),
            exit_price=float(d["exit_price"]),
            opened_at=datetime.fromisoformat(d["opened_at"]),
            closed_at=datetime.fromisoformat(d["closed_at"]),
            pips=float(d["pips"]),
            pnl=float(d["pnl"]),
            r_multiple=float(d["r_multiple"]),
            reason=ExitReason(d["reason"]),
            note=d.get("note", ""),
            tags=d.get("tags", {}),
        )
