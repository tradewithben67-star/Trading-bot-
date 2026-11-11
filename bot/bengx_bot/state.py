"""Zustand über Neustarts hinweg.

Ein Bot, der durchgängig läuft, wird irgendwann neu gestartet. Offene
Positionen, Kapitalstand und die zuletzt verarbeitete Kerze müssen das
überleben, sonst eröffnet er nach dem Neustart doppelt.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .model import Position, Side


def _pos_to_dict(p: Position) -> dict[str, Any]:
    return {
        "id": p.id, "side": p.side.value, "size": p.size, "entry": p.entry,
        "stop": p.stop, "target": p.target, "opened_at": p.opened_at.isoformat(),
        "opened_bar": p.opened_bar, "initial_risk": p.initial_risk,
        "final_target": p.final_target,
        "original_size": p.original_size, "partial_done": p.partial_done,
        "realised_pnl": p.realised_pnl, "high_water": p.high_water,
        "low_water": p.low_water, "note": p.note,
    }


def _pos_from_dict(d: dict[str, Any]) -> Position:
    return Position(
        id=d["id"], side=Side(d["side"]), size=float(d["size"]),
        entry=float(d["entry"]), stop=float(d["stop"]), target=float(d["target"]),
        opened_at=datetime.fromisoformat(d["opened_at"]),
        opened_bar=int(d["opened_bar"]), initial_risk=float(d["initial_risk"]),
        final_target=(None if d.get("final_target") is None else float(d["final_target"])),
        original_size=float(d.get("original_size") or d["size"]),
        partial_done=bool(d.get("partial_done", False)),
        realised_pnl=float(d.get("realised_pnl", 0.0)),
        high_water=float(d.get("high_water", 0.0)),
        low_water=float(d.get("low_water", 0.0)),
        note=d.get("note", ""),
    )


@dataclass
class BotState:
    equity: float
    peak: float
    last_bar_ts: str | None = None
    positions: list[Position] = field(default_factory=list)
    fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "equity": round(self.equity, 2),
            "peak": round(self.peak, 2),
            "last_bar_ts": self.last_bar_ts,
            "fingerprint": self.fingerprint,
            "positions": [_pos_to_dict(p) for p in self.positions],
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "BotState":
        return BotState(
            equity=float(d["equity"]),
            peak=float(d.get("peak", d["equity"])),
            last_bar_ts=d.get("last_bar_ts"),
            fingerprint=d.get("fingerprint", ""),
            positions=[_pos_from_dict(p) for p in d.get("positions", [])],
        )


def load_state(path: str | Path) -> BotState | None:
    p = Path(path)
    if not p.exists():
        return None
    return BotState.from_dict(json.loads(p.read_text(encoding="utf-8")))


def save_state(path: str | Path, state: BotState) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
                   encoding="utf-8")
    tmp.replace(p)        # erst schreiben, dann umbenennen: kein halber Zustand
    return p
