"""Konfiguration. Alles, was man drehen kann, steht in einer TOML-Datei —
nichts davon ist im Code festgenagelt.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any


@dataclass
class MarketConfig:
    symbol: str = "XAU/USD"
    pip: float = 0.1              # bei Gold üblich: 0,10 USD je Pip
    min_size: float = 0.01        # kleinste handelbare Menge in Unzen
    size_step: float = 0.01
    max_size: float = 1000.0


@dataclass
class CostConfig:
    spread_pips: float = 2.0
    slippage_pips: float = 1.0
    commission_per_unit: float = 0.0


@dataclass
class StrategyConfig:
    """Das Regelwerk des Dauerläufers."""

    trend_ema: int = 200
    trend_slope_bars: int = 20
    breakout: int = 20
    atr_period: int = 14
    adx_period: int = 14
    adx_min: float = 18.0
    min_atr_pips: float = 25.0
    max_atr_pips: float = 400.0
    stop_atr: float = 2.0
    trail_atr: float = 2.5
    partial_r: float = 1.5
    partial_fraction: float = 0.5
    time_stop_bars: int = 48
    session_start_hour: int = 7       # UTC, London-Eröffnung
    session_end_hour: int = 20        # UTC, bis in den New-Yorker Nachmittag
    friday_cutoff_hour: int = 19
    cooldown_bars: int = 12
    cooldown_after_losses: int = 2


@dataclass
class RiskConfig:
    risk_per_trade: float = 0.005     # 0,5 % des Kontos je Position
    max_positions: int = 2
    daily_loss_limit: float = 0.02    # 2 % Tagesverlust, dann Feierabend
    drawdown_halve: float = 0.08      # ab 8 % Rückgang halbe Größe
    drawdown_stop: float = 0.15       # ab 15 % Rückgang kein neuer Trade
    start_equity: float = 10000.0


@dataclass
class DataConfig:
    csv: str = "data/xauusd_h1.csv"
    timeframe_minutes: int = 60
    warmup_bars: int = 260


@dataclass
class LiveConfig:
    enabled: bool = False             # muss bewusst eingeschaltet werden
    broker: str = "paper"             # "paper" ist der einzige fertige Anschluss
    poll_seconds: int = 60
    killswitch_file: str = "state/KILLSWITCH"
    state_dir: str = "state"
    journal: str = "state/trades.jsonl"
    signals_out: str = "../signals.json"


@dataclass
class Config:
    market: MarketConfig = field(default_factory=MarketConfig)
    costs: CostConfig = field(default_factory=CostConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    data: DataConfig = field(default_factory=DataConfig)
    live: LiveConfig = field(default_factory=LiveConfig)

    @staticmethod
    def load(path: str | Path | None) -> "Config":
        if path is None:
            return Config()
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Konfiguration nicht gefunden: {p}")
        with p.open("rb") as fh:
            raw = tomllib.load(fh)
        return Config.from_dict(raw)

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> "Config":
        def build(cls, key):
            data = raw.get(key, {}) or {}
            known = {f for f in cls.__dataclass_fields__}
            unknown = set(data) - known
            if unknown:
                raise ValueError(f"unbekannte Einstellungen in [{key}]: {sorted(unknown)}")
            return cls(**data)

        cfg = Config(
            market=build(MarketConfig, "market"),
            costs=build(CostConfig, "costs"),
            strategy=build(StrategyConfig, "strategy"),
            risk=build(RiskConfig, "risk"),
            data=build(DataConfig, "data"),
            live=build(LiveConfig, "live"),
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        s, r, m = self.strategy, self.risk, self.market
        if m.pip <= 0:
            raise ValueError("market.pip muss größer als 0 sein")
        if s.breakout < 2:
            raise ValueError("strategy.breakout muss mindestens 2 sein")
        if s.stop_atr <= 0 or s.trail_atr <= 0:
            raise ValueError("Stop- und Trail-Abstand müssen größer als 0 sein")
        if not 0 < r.risk_per_trade <= 0.05:
            raise ValueError("risk.risk_per_trade muss zwischen 0 und 0,05 liegen")
        if not 0 < r.daily_loss_limit <= 0.5:
            raise ValueError("risk.daily_loss_limit muss zwischen 0 und 0,5 liegen")
        if r.drawdown_halve >= r.drawdown_stop:
            raise ValueError("drawdown_halve muss kleiner als drawdown_stop sein")
        if not 0 <= s.session_start_hour < s.session_end_hour <= 24:
            raise ValueError("Die Handelszeit muss innerhalb eines Tages liegen")
        if not 0 <= s.partial_fraction < 1:
            raise ValueError("partial_fraction muss zwischen 0 und 1 liegen")
        if r.max_positions < 1:
            raise ValueError("risk.max_positions muss mindestens 1 sein")

    def to_dict(self) -> dict[str, Any]:
        return {k: asdict(v) for k, v in asdict(self).items()} if False else asdict(self)

    def fingerprint(self) -> str:
        """Fingerabdruck über alles, was das Handelsergebnis beeinflusst.

        Der Live-Betrieb verlangt einen Backtest-Bericht zu genau diesem
        Fingerabdruck. Wer eine Regel ändert, muss neu nachrechnen.
        """
        relevant = {
            "market": asdict(self.market),
            "costs": asdict(self.costs),
            "strategy": asdict(self.strategy),
            "risk": asdict(self.risk),
        }
        blob = json.dumps(relevant, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
