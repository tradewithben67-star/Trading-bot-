"""Backtest. Rechnet das Regelwerk über historische Kerzen nach — mit Spread,
Slippage und Kommission, ohne Blick in die Zukunft.

Ein Signal entsteht erst auf der *geschlossenen* Kerze, und eine Position wird
frühestens ab der nächsten Kerze verwaltet. Liegen Stop und Ziel in derselben
Kerze, zählt der Stop.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Sequence

from .broker import PaperBroker
from .config import Config
from .engine import TradeEngine
from .model import Candle, Trade
from .bots import make_strategy
from .risk import RiskManager


@dataclass
class BacktestResult:
    bot: str
    symbol: str
    fingerprint: str
    bars: int
    start: str
    end: str
    start_equity: float
    end_equity: float
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[tuple[str, float]] = field(default_factory=list)
    rejections: dict[str, int] = field(default_factory=dict)

    # ---- Kennzahlen ----------------------------------------------------
    @property
    def closed(self) -> list[Trade]:
        return self.trades

    @property
    def wins(self) -> list[Trade]:
        return [t for t in self.trades if t.won]

    @property
    def losses(self) -> list[Trade]:
        return [t for t in self.trades if t.lost]

    @property
    def winrate(self) -> float | None:
        decided = len(self.wins) + len(self.losses)
        return len(self.wins) / decided if decided else None

    @property
    def total_pips(self) -> float:
        return round(sum(t.pips for t in self.trades), 1)

    @property
    def net_pnl(self) -> float:
        return round(self.end_equity - self.start_equity, 2)

    @property
    def net_return(self) -> float:
        return self.net_pnl / self.start_equity if self.start_equity else 0.0

    @property
    def profit_factor(self) -> float | None:
        gain = sum(t.pnl for t in self.wins)
        loss = abs(sum(t.pnl for t in self.losses))
        if loss == 0:
            return None if gain == 0 else float("inf")
        return round(gain / loss, 2)

    @property
    def expectancy_r(self) -> float | None:
        if not self.trades:
            return None
        return round(statistics.fmean(t.r_multiple for t in self.trades), 3)

    @property
    def max_drawdown(self) -> float:
        peak, worst = self.start_equity, 0.0
        for _, value in self.equity_curve:
            peak = max(peak, value)
            if peak > 0:
                worst = max(worst, (peak - value) / peak)
        return round(worst, 4)

    @property
    def longest_loss_streak(self) -> int:
        best = run = 0
        for t in self.trades:
            run = run + 1 if t.lost else 0
            best = max(best, run)
        return best

    def summary(self) -> dict[str, Any]:
        return {
            "bot": self.bot,
            "symbol": self.symbol,
            "fingerprint": self.fingerprint,
            "bars": self.bars,
            "start": self.start,
            "end": self.end,
            "trades": len(self.trades),
            "wins": len(self.wins),
            "losses": len(self.losses),
            "winrate": round(self.winrate, 4) if self.winrate is not None else None,
            "total_pips": self.total_pips,
            "start_equity": round(self.start_equity, 2),
            "end_equity": round(self.end_equity, 2),
            "net_pnl": self.net_pnl,
            "net_return": round(self.net_return, 4),
            "profit_factor": self.profit_factor,
            "expectancy_r": self.expectancy_r,
            "max_drawdown": self.max_drawdown,
            "longest_loss_streak": self.longest_loss_streak,
            "rejections": self.rejections,
        }

    def to_dict(self) -> dict[str, Any]:
        d = self.summary()
        d["trade_log"] = [t.to_dict() for t in self.trades]
        return d

    def report(self) -> str:
        s = self.summary()
        pct = lambda v: "—" if v is None else f"{v * 100:.1f} %"
        num = lambda v: "—" if v is None else f"{v}"
        lines = [
            f"Backtest {s['bot']} auf {s['symbol']}   Regelwerk {s['fingerprint']}",
            f"Zeitraum        {s['start'][:10]} bis {s['end'][:10]}  ({s['bars']} Kerzen)",
            "",
            f"Trades          {s['trades']}   davon {s['wins']} im Plus, {s['losses']} im Minus",
            f"Trefferquote    {pct(s['winrate'])}",
            f"Pips gesamt     {s['total_pips']:+.1f}",
            f"Ergebnis        {s['net_pnl']:+.2f} ({pct(s['net_return'])})",
            f"Kapital         {s['start_equity']:.2f} → {s['end_equity']:.2f}",
            f"Profitfaktor    {num(s['profit_factor'])}",
            f"Erwartungswert  {num(s['expectancy_r'])} R je Trade",
            f"Max. Rückgang   {pct(s['max_drawdown'])}",
            f"Längste Serie   {s['longest_loss_streak']} Verluste in Folge",
        ]
        if s["rejections"]:
            lines.append("")
            lines.append("Abgelehnte Signale:")
            for reason, count in sorted(s["rejections"].items(), key=lambda kv: -kv[1]):
                lines.append(f"  {count:>5}  {reason}")
        return "\n".join(lines)


def run_backtest(config: Config, candles: Sequence[Candle],
                 strategy=None) -> BacktestResult:
    if len(candles) < 50:
        raise ValueError("Zu wenige Kerzen für einen Backtest")

    strategy = strategy or make_strategy(config)
    ctx = strategy.prepare(candles)
    broker = PaperBroker(config)
    risk = RiskManager(config)
    engine = TradeEngine(config, strategy, risk, broker)

    warmup = max(strategy.warmup_bars(), config.data.warmup_bars)
    if warmup >= len(candles):
        raise ValueError(
            f"Die Vorlaufzeit von {warmup} Kerzen ist länger als die Daten "
            f"({len(candles)} Kerzen)."
        )

    result = BacktestResult(
        bot=strategy.name,
        symbol=config.market.symbol,
        fingerprint=config.fingerprint(),
        bars=len(candles),
        start=candles[0].ts.isoformat(),
        end=candles[-1].ts.isoformat(),
        start_equity=config.risk.start_equity,
        end_equity=config.risk.start_equity,
    )

    for i in range(warmup, len(candles)):
        closed = engine.step(candles, ctx, i)
        result.trades.extend(closed)
        result.equity_curve.append(
            (candles[i].ts.isoformat(), round(broker.mark_to_market(candles[i].close), 2))
        )

    # Was am Ende noch offen ist, wird zum letzten Kurs geschlossen —
    # sonst stünde ein unrealisierter Gewinn im Ergebnis.
    from .model import ExitReason
    result.trades.extend(engine.flatten(candles[-1], ExitReason.MANUAL))

    result.end_equity = round(broker.equity, 2)
    result.rejections = dict(engine.rejections)
    return result
