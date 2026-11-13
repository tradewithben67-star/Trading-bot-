"""Betrieb: Papier- und Live-Lauf.

Der Runner verarbeitet alle Kerzen, die seit dem letzten Lauf dazugekommen
sind, sichert den Zustand und schreibt `signals.json` für die Website. Er ist
so gebaut, dass man ihn jede Minute per Cron aufrufen oder als Schleife laufen
lassen kann — doppelt verarbeitet wird nichts.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
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
    def __init__(self, config: Config, live: bool = False,
                 mt5_modul=None) -> None:
        self.cfg = config
        self.live = live
        # Nur für Tests: statt des echten Pakets MetaTrader5 eine Attrappe.
        # Im Betrieb bleibt das None und es wird importiert.
        self._mt5_modul = mt5_modul
        self.strategy = make_strategy(config)
        self.state_file = Path(config.live.state_dir) / "state.json"
        self.journal = Journal(config.live.journal)
        self.killswitch = Path(config.live.killswitch_file)

        self.terminal = None
        self.konto = None

        if live:
            if not config.live.enabled:
                raise LiveGateError(
                    "live.enabled steht auf false. Der Bot handelt nur, wenn das "
                    "bewusst in der Konfiguration eingeschaltet wird."
                )
            art = config.live.broker.lower()
            if art == "paper":
                raise LiveGateError(
                    "live.broker steht auf \"paper\". Für echtes Handeln auf "
                    "live.broker = \"mt5\" stellen und MT5_LOGIN, MT5_PASSWORD "
                    "und MT5_SERVER in bot/.env eintragen."
                )
            if art not in ("mt5", "metatrader5", "tradequo"):
                raise LiveGateError(
                    f"Für live.broker = {config.live.broker!r} ist kein Anschluss "
                    "hinterlegt. Eingebaut ist \"mt5\" (MetaTrader 5, auch für "
                    "Tradequo). Alles andere gehört in eine eigene Klasse nach "
                    "dem Vorbild von broker.Broker."
                )
            self.broker = self._mt5_broker(config)
        else:
            self.broker = PaperBroker(config)

        self.risk = RiskManager(config)
        self.engine = TradeEngine(config, self.strategy, self.risk, self.broker)

    # ---- Anschluss -------------------------------------------------------
    def _mt5_broker(self, config: Config):
        """Terminal öffnen, Konto prüfen, Broker bauen.

        Die Backtest-Pflicht hängt daran, was für ein Konto MT5 meldet — nicht
        daran, was in der Konfiguration steht. Auf einem Übungskonto darf man
        ausprobieren; auf einem Echtgeldkonto wird erst nachgerechnet.
        """
        from .mt5 import MT5Broker, MT5Error, verbinden

        env = dict(os.environ)
        datei = Path(__file__).resolve().parents[1] / ".env"
        if datei.exists():
            from .telegram import load_env_file
            env.update(load_env_file(datei))

        try:
            terminal, konto = verbinden(config, env=env, modul=self._mt5_modul)
        except MT5Error as exc:
            raise LiveGateError(str(exc)) from None

        self.terminal = terminal
        self.konto = konto

        if konto.demo:
            if not config.live.allow_demo_without_backtest:
                require_backtest(config)
        else:
            # Echtes Geld. Hier gibt es keinen Schalter.
            try:
                require_backtest(config)
            except LiveGateError as exc:
                terminal.schliessen()
                raise LiveGateError(
                    f"Konto {konto.login} bei {konto.server} ist ein "
                    f"{konto.art}.\n\n{exc}\n\n"
                    "Auf einem Demokonto darf der Bot ohne Backtest laufen. "
                    "Für echtes Geld nicht — das ist keine Einstellung."
                ) from None

        try:
            return MT5Broker(config, terminal)
        except MT5Error as exc:
            terminal.schliessen()
            raise LiveGateError(str(exc)) from None

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
        if self.terminal is None:
            # Auf dem Papierkonto führt die Datei den Kontostand. Am echten
            # Broker zählt sein Kontostand, nicht unsere Buchhaltung.
            self.broker.equity = st.equity
        self.risk.equity = self.broker.equity
        self.risk.peak = max(st.peak, self.broker.equity)
        index = {c.ts: i for i, c in enumerate(candles)}
        # Der gespeicherte Zustand ersetzt, was im Speicher liegt — er kommt
        # nicht dazu. `loop()` benutzt denselben Runner für jeden Durchlauf;
        # ohne das Leeren verdoppelt sich hier bei jedem Takt die Zahl der
        # offenen Positionen, und mit ihr das gerechnete Risiko.
        self.broker.positions.clear()
        for pos in st.positions:
            pos.opened_bar = index.get(pos.opened_at, -1)
            self.broker.positions.append(pos)
        if self.terminal is not None:
            # Die Tickets stecken in den Kennungen (mt5-<ticket>) und müssen
            # nach einem Neustart wieder bekannt sein, sonst findet der
            # Abgleich die Position im Terminal nicht wieder.
            self.broker.uebernehmen()
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
    def kerzen(self) -> list[Candle]:
        """Woher die Kurse kommen: im Live-Betrieb aus dem Terminal, sonst CSV."""
        if self.terminal is not None:
            return self.terminal.kerzen(self.cfg.mt5.symbol,
                                        self.cfg.mt5.timeframe_minutes,
                                        self.cfg.mt5.candles)
        return load_csv(self.cfg.data.csv)

    def tick(self) -> dict:
        candles = self.kerzen()
        if len(candles) < self.strategy.warmup_bars() + 2:
            return {"status": "zu wenige Kerzen", "bars": len(candles), "new": 0}

        # Erst laden, was wir zu halten glauben ...
        last_ts = self.restore(candles)

        # ... dann mit dem Terminal abgleichen. Die Reihenfolge ist wichtig:
        # umgekehrt holt `restore` die Positionen aus der Zustandsdatei
        # zurück, die der Broker gerade geschlossen hat, und die Maschine
        # versucht danach, ein Gespenst zu schließen.
        vom_broker: list[Trade] = []
        if self.terminal is not None:
            self.broker.aktualisieren()
            vom_broker = self.broker.abgleich()
            for t in vom_broker:
                self.risk.on_trade_closed(t, 0)
            if vom_broker:
                self.journal.extend(vom_broker)
            # Am echten Konto zählt immer der Kontostand des Brokers, auch
            # wenn nichts geschlossen wurde: Swap, Gebühren und offene
            # Positionen bewegen ihn, ohne dass der Bot etwas tut.
            self.risk.equity = self.broker.equity
            self.risk.peak = max(self.risk.peak, self.risk.equity)
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
        if self.terminal is not None and self.cfg.mt5.sync_stops:
            # Ein nachgezogener Stop, der nur im Speicher steht, löst nichts
            # aus. Die Marke muss ins Terminal.
            self.broker.stops_nachziehen()
        self.persist(candles[-1].ts.isoformat())
        self.export()
        info = {
            "status": "ok",
            "bars": len(candles),
            "new": max(0, len(candles) - start),
            "closed": len(new_trades) + len(vom_broker),
            "open": len(self.broker.positions),
            "equity": round(self.broker.equity, 2),
            "last": candles[-1].ts.isoformat(),
        }
        if self.konto is not None:
            info["konto"] = f"{self.konto.login} ({self.konto.art})"
        if vom_broker:
            info["vom_broker"] = len(vom_broker)
        return info

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
