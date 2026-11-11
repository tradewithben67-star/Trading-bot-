"""Handelsprotokoll und Ausgabe für die Website.

Jeder abgeschlossene Trade landet als eine Zeile JSON in einer Datei, die nur
wächst. Daraus werden die Kennzahlen gerechnet und `signals.json` geschrieben —
genau das Format, das die Seite im Bereich G liest.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from .model import ExitReason, Position, Trade


class Journal:
    """Append-only Protokoll im JSONL-Format."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, trade: Trade) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(trade.to_dict(), ensure_ascii=False) + "\n")

    def extend(self, trades: Iterable[Trade]) -> None:
        for t in trades:
            self.append(t)

    def load(self) -> list[Trade]:
        if not self.path.exists():
            return []
        out: list[Trade] = []
        for n, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(Trade.from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                raise ValueError(f"{self.path}, Zeile {n}: {exc}") from exc
        out.sort(key=lambda t: t.opened_at)
        return out


def stats(trades: Sequence[Trade]) -> dict[str, Any]:
    """Die Zahlen, die auch auf der Seite stehen."""
    wins = [t for t in trades if t.won]
    losses = [t for t in trades if t.lost]
    decided = len(wins) + len(losses)
    gain = sum(t.pnl for t in wins)
    loss = abs(sum(t.pnl for t in losses))
    return {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(trades) - decided,
        "winrate": round(len(wins) / decided, 4) if decided else None,
        "total_pips": round(sum(t.pips for t in trades), 1),
        "net_pnl": round(sum(t.pnl for t in trades), 2),
        "profit_factor": (None if loss == 0 and gain == 0
                          else (float("inf") if loss == 0 else round(gain / loss, 2))),
        "expectancy_r": (round(statistics.fmean(t.r_multiple for t in trades), 3)
                         if trades else None),
    }


def _status_for(trade: Trade) -> str:
    if trade.won:
        return "gewonnen"
    if trade.lost:
        return "verloren"
    return "be"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def signals_payload(trades: Sequence[Trade],
                    open_positions: Sequence[Position] = (),
                    pip: float = 0.1,
                    limit: int = 500) -> dict[str, Any]:
    """Baut den Inhalt von `signals.json` für die Website."""
    items: list[dict[str, Any]] = []

    for pos in open_positions:
        items.append({
            "id": pos.id,
            "pair": "XAU/USD",
            "side": pos.side.value,
            "entry": round(pos.entry, 2),
            "sl": round(pos.stop, 2),
            "tp": round(pos.target, 2),
            "note": pos.note,
            "status": "offen",
            "pips": 0,
            "openedAt": _iso(pos.opened_at),
            "closedAt": None,
        })

    for t in sorted(trades, key=lambda x: x.opened_at, reverse=True)[:limit]:
        items.append({
            "id": t.id,
            "pair": "XAU/USD",
            "side": t.side.value,
            "entry": round(t.entry, 2),
            "sl": round(t.stop, 2),
            "tp": round(t.target, 2),
            "note": t.note,
            "status": _status_for(t),
            "pips": round(t.pips, 1),
            "openedAt": _iso(t.opened_at),
            "closedAt": _iso(t.closed_at),
        })

    items.sort(key=lambda d: d["openedAt"], reverse=True)
    return {
        "_erzeugt": _iso(datetime.now(timezone.utc)),
        "_quelle": "BENGX Dauerläufer",
        "signals": items,
    }


def write_signals(path: str | Path, payload: dict[str, Any]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                 encoding="utf-8")
    return p
