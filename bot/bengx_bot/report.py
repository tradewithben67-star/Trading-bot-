"""Lagebericht: was gerade los ist, in einer Form, die sich verschicken lässt.

Gelesen wird nur, was der Bot selbst geschrieben hat — Protokoll, Zustand und
die Signaldatei. Nichts davon wird geschätzt.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from .config import Config
from .journal import Journal, stats
from .model import Trade
from .state import load_state


def _day(dt: datetime) -> str:
    return f"{dt.year}-{dt.month}-{dt.day}"


def _since(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        when = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - when).total_seconds() / 3600.0


def window(trades: Sequence[Trade], zeitraum: str) -> list[Trade]:
    """Filtert nach heute, woche, monat oder alles."""
    if zeitraum in ("", "alles"):
        return list(trades)
    now = datetime.now(timezone.utc)
    if zeitraum == "heute":
        return [t for t in trades if _day(t.closed_at.astimezone(timezone.utc)) == _day(now)]
    tage = {"woche": 7, "monat": 30}.get(zeitraum)
    if tage is None:
        return list(trades)
    grenze = now.timestamp() - tage * 86400
    return [t for t in trades if t.closed_at.timestamp() >= grenze]


@dataclass
class Lage:
    bot: str
    symbol: str
    fingerprint: str
    equity: float | None
    offene_positionen: int
    letzte_kerze: str | None
    stunden_seit_kerze: float | None
    trades_gesamt: int
    heute: dict[str, Any] = field(default_factory=dict)
    gesamt: dict[str, Any] = field(default_factory=dict)
    killswitch: bool = False
    live: bool = False
    hinweise: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bot": self.bot, "symbol": self.symbol, "regelwerk": self.fingerprint,
            "kapital": self.equity, "offene_positionen": self.offene_positionen,
            "letzte_kerze": self.letzte_kerze,
            "stunden_seit_kerze": self.stunden_seit_kerze,
            "trades_gesamt": self.trades_gesamt,
            "heute": self.heute, "gesamt": self.gesamt,
            "not_aus": self.killswitch, "live": self.live,
            "hinweise": self.hinweise,
        }

    def text(self) -> str:
        zeilen = [f"Bot: {self.bot} auf {self.symbol}   Regelwerk {self.fingerprint}"]
        if self.killswitch:
            zeilen.append("NOT-AUS IST AKTIV — es wird nichts Neues eröffnet.")
        zeilen.append(
            f"Kapital: {self.equity:.2f}" if self.equity is not None
            else "Kapital: noch kein Lauf"
        )
        zeilen.append(f"Offene Positionen: {self.offene_positionen}")
        if self.letzte_kerze:
            alt = (f" (vor {self.stunden_seit_kerze:.1f} h)"
                   if self.stunden_seit_kerze is not None else "")
            zeilen.append(f"Letzte verarbeitete Kerze: {self.letzte_kerze}{alt}")
        else:
            zeilen.append("Letzte verarbeitete Kerze: keine")
        zeilen.append("")
        zeilen.append("Heute:  " + _zahlen(self.heute))
        zeilen.append("Gesamt: " + _zahlen(self.gesamt))
        zeilen.append(f"Betrieb: {'live freigegeben' if self.live else 'Papierkonto'}")
        for h in self.hinweise:
            zeilen.append("Hinweis: " + h)
        return "\n".join(zeilen)


def _zahlen(d: dict[str, Any]) -> str:
    if not d or not d.get("trades"):
        return "keine abgeschlossenen Trades"
    quote = d.get("winrate")
    quote_txt = "—" if quote is None else f"{quote * 100:.0f} %"
    return (f"{d['trades']} Trades, {quote_txt} Treffer, "
            f"{d['total_pips']:+.1f} Pips, {d['net_pnl']:+.2f}")


def build(config: Config) -> Lage:
    """Sammelt den Stand aus Protokoll, Zustand und Konfiguration."""
    trades = Journal(config.live.journal).load()
    zustand = load_state(Path(config.live.state_dir) / "state.json")
    kill = Path(config.live.killswitch_file).exists()

    letzte = zustand.last_bar_ts if zustand else None
    hinweise: list[str] = []
    stunden = _since(letzte)
    if stunden is not None and stunden > 24:
        hinweise.append(
            f"Seit {stunden:.0f} Stunden kam keine neue Kerze an — "
            "läuft der Datenzulauf noch?"
        )
    if zustand and zustand.fingerprint and zustand.fingerprint != config.fingerprint():
        hinweise.append(
            "Der gespeicherte Zustand gehört zu einem anderen Regelwerk."
        )

    return Lage(
        bot=config.bot.name,
        symbol=config.market.symbol,
        fingerprint=config.fingerprint(),
        equity=zustand.equity if zustand else None,
        offene_positionen=len(zustand.positions) if zustand else 0,
        letzte_kerze=letzte,
        stunden_seit_kerze=stunden,
        trades_gesamt=len(trades),
        heute=stats(window(trades, "heute")),
        gesamt=stats(trades),
        killswitch=kill,
        live=bool(config.live.enabled),
        hinweise=hinweise,
    )


def signale_text(config: Config, zeitraum: str = "heute", anzahl: int = 8) -> str:
    """Die letzten Signale als Liste."""
    trades = window(Journal(config.live.journal).load(), zeitraum)
    trades.sort(key=lambda t: t.opened_at, reverse=True)
    if not trades:
        return f"Keine abgeschlossenen Signale ({zeitraum})."
    kopf = stats(trades)
    zeilen = [f"{zeitraum}: " + _zahlen(kopf), ""]
    for t in trades[:anzahl]:
        zeilen.append(
            f"{t.opened_at:%d.%m. %H:%M}  {t.side.value:<5} "
            f"{t.entry:>9.2f}  {t.pips:+7.1f} Pips  {t.reason.value}"
        )
    if len(trades) > anzahl:
        zeilen.append(f"… und {len(trades) - anzahl} weitere")
    return "\n".join(zeilen)


def aufgaben_datei(config: Config) -> Path:
    return Path(config.live.state_dir) / "aufgaben.json"


def aufgabe_anlegen(config: Config, text: str) -> int:
    p = aufgaben_datei(config)
    liste = aufgaben_lesen(config)
    liste.append({
        "text": text.strip()[:1000],
        "status": "offen",
        "angelegt": datetime.now(timezone.utc).isoformat(),
    })
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(liste, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(liste)


def aufgaben_lesen(config: Config) -> list[dict[str, Any]]:
    p = aufgaben_datei(config)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []
