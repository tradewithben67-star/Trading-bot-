"""Betrieb: Papier- und Live-Lauf.

Der Runner verarbeitet alle Kerzen, die seit dem letzten Lauf dazugekommen
sind, sichert den Zustand und schreibt `signals.json` für die Website. Er ist
so gebaut, dass man ihn jede Minute per Cron aufrufen oder als Schleife laufen
lassen kann — doppelt verarbeitet wird nichts.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Sequence

from .backtest import BacktestResult
from .broker import PaperBroker
from .config import Config
from .data import load_csv
from .engine import TradeEngine
from .journal import Journal, signals_payload, write_signals
from .model import Candle, ExitReason, Trade
from .risk import RiskManager
from .bots import make_strategy
from .state import BotState, load_state, save_state


class LiveGateError(RuntimeError):
    """Der Live-Betrieb ist gesperrt, solange eine Voraussetzung fehlt."""


def backtest_path(config: Config) -> Path:
    return Path(config.live.state_dir) / "backtests" / f"{config.fingerprint()}.json"


def require_backtest(config: Config) -> Path:
    """Ohne nachgerechnetes Regelwerk kein echtes Geld.

    Genau das verspricht die Seite im Bereich X — hier wird es durchgesetzt.
    """
    p = backtest_path(config)
    if not p.exists():
        raise LiveGateError(
            "Für dieses Regelwerk liegt kein Backtest vor.\n"
            f"Erwartet: {p}\n"
            "Erst nachrechnen:  python -m bengx_bot backtest --config <datei> --save"
        )
    return p


class Runner:
    def __init__(self, config: Config, live: bool = False) -> None:
        self.cfg = config
        self.live = live
        self.strategy = make_strategy(config)
        self.state_file = Path(config.live.state_dir) / "state.json"
        self.journal = Journal(config.live.journal)
        self.killswitch = Path(config.live.killswitch_file)

        if live:
            if not config.live.enabled:
                raise LiveGateError(
                    "live.enabled steht auf false. Der Bot handelt nur, wenn das "
                    "bewusst in der Konfiguration eingeschaltet wird."
                )
            require_backtest(config)
            if config.live.broker == "paper":
                raise LiveGateError(
                    "live.broker steht auf \"paper\". Ein echter Broker-Anschluss "
                    "ist nicht enthalten: er braucht Zugangsdaten und gehört in eine "
                    "eigene Klasse nach dem Vorbild von broker.Broker. Bis dahin "
                    "läuft der Bot auf dem Papierkonto."
                )
            hinweis = ""
            if config.live.broker.lower() in ("tradequo", "mt5", "metatrader5"):
                hinweis = (
                    "\nTradequo läuft über MetaTrader 5. Eine Anbindung braucht "
                    "das Paket MetaTrader5 (nur Windows) oder eine Brücke zu "
                    "einem Expert Advisor, und muss die vier Methoden von "
                    "broker.Broker erfüllen."
                )
            raise LiveGateError(
                f"Für live.broker = {config.live.broker!r} ist kein Anschluss "
                "hinterlegt. Siehe bengx_bot/broker.py." + hinweis
            )

        self.broker = PaperBroker(config)
        self.risk = RiskManager(config)
        self.engine = TradeEngine(config, self.strategy, self.risk, self.broker)

    # ---- Zustand -------------------------------------------------------
    def restore(self, candles: Sequence[Candle]) -> str | None:
        st = load_state(self.state_file)
        if st is None:
            return None
        if st.fingerprint and st.fingerprint != self.cfg.fingerprint():
            raise LiveGateError(
                "Der gespeicherte Zustand gehört zu einem anderen Regelwerk "
                f"({st.fingerprint} statt {self.cfg.fingerprint()}). Offene "
                "Positionen zuerst von Hand schließen, dann state.json entfernen."
            )
        self.broker.equity = st.equity
        self.risk.equity = st.equity
        self.risk.peak = st.peak
        index = {c.ts: i for i, c in enumerate(candles)}
        for pos in st.positions:
            pos.opened_bar = index.get(pos.opened_at, -1)
            self.broker.positions.append(pos)
        return st.last_bar_ts

    def persist(self, last_ts: str | None) -> None:
        save_state(self.state_file, BotState(
            equity=self.broker.equity,
            peak=self.risk.peak,
            last_bar_ts=last_ts,
            positions=list(self.broker.positions),
            fingerprint=self.cfg.fingerprint(),
        ))

    # ---- Ein Durchlauf ---------------------------------------------------
    def tick(self) -> dict:
        candles = load_csv(self.cfg.data.csv)
        if len(candles) < self.strategy.warmup_bars() + 2:
            return {"status": "zu wenige Kerzen", "bars": len(candles), "new": 0}

        last_ts = self.restore(candles)
        ctx = self.strategy.prepare(candles)

        start = max(self.strategy.warmup_bars(), self.cfg.data.warmup_bars)
        if last_ts:
            seen = datetime.fromisoformat(last_ts)
            start = max(start, next((i for i, c in enumerate(candles)
                                     if c.ts > seen), len(candles)))

        if self.killswitch.exists():
            trades = self.engine.flatten(candles[-1], ExitReason.KILL)
            self.journal.extend(trades)
            self.risk.halt(f"Not-Aus aktiv ({self.killswitch})")
            self.persist(candles[-1].ts.isoformat())
            self.export()
            return {"status": "Not-Aus", "closed": len(trades), "new": 0}

        new_trades: list[Trade] = []
        for i in range(start, len(candles)):
            new_trades.extend(self.engine.step(candles, ctx, i))

        self.journal.extend(new_trades)
        self.persist(candles[-1].ts.isoformat())
        self.export()
        return {
            "status": "ok",
            "bars": len(candles),
            "new": max(0, len(candles) - start),
            "closed": len(new_trades),
            "open": len(self.broker.positions),
            "equity": round(self.broker.equity, 2),
            "last": candles[-1].ts.isoformat(),
        }

    def loop(self, seconds: int | None = None) -> None:
        wait = seconds or self.cfg.live.poll_seconds
        while True:
            info = self.tick()
            print(f"[{datetime.now().isoformat(timespec='seconds')}] {info}", flush=True)
            if info.get("status") == "Not-Aus":
                return
            time.sleep(wait)

    # ---- Ausgabe ---------------------------------------------------------
    def export(self) -> Path:
        base = Path(self.cfg.live.journal).parent
        out = (base / self.cfg.live.signals_out).resolve() \
            if not Path(self.cfg.live.signals_out).is_absolute() \
            else Path(self.cfg.live.signals_out)
        payload = signals_payload(
            self.journal.load(),
            self.broker.positions,
            pip=self.cfg.market.pip,
        )
        return write_signals(out, payload)
