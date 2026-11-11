"""Welcher Bot läuft. Beide erfüllen dieselbe Schnittstelle — `prepare`,
`evaluate`, `warmup_bars`, `exit_rules` —, deshalb arbeiten Maschine,
Backtest und Runner mit beiden unverändert.
"""

from __future__ import annotations

from typing import Protocol, Sequence

from .config import Config
from .copier import Kopierer
from .model import Candle, Signal
from .strategy import Dauerlaeufer, ExitRules
from .swing import SwingTrader


class Strategy(Protocol):
    name: str

    def prepare(self, candles: Sequence[Candle]): ...
    def evaluate(self, candles: Sequence[Candle], ctx, i: int) -> Signal | None: ...
    def warmup_bars(self) -> int: ...
    def exit_rules(self) -> ExitRules: ...


BOTS = {
    "dauerlaeufer": Dauerlaeufer,
    "swing": SwingTrader,
    "kopierer": Kopierer,
}


def make_strategy(config: Config) -> Strategy:
    name = config.bot.name
    try:
        return BOTS[name](config)
    except KeyError:
        raise ValueError(
            f"unbekannter Bot: {name!r} (erlaubt: {', '.join(sorted(BOTS))})"
        ) from None
