"""Der Signal-Kopierer.

Er denkt sich nichts aus. Er liest Bens Signale und spiegelt sie in ein
eigenes Konto — Richtung, Stop und Ziel eins zu eins.

Zwei Dinge übernimmt er bewusst **nicht**:

* **Die Positionsgröße.** Die rechnet er aus dem eigenen Kontostand und dem
  eigenen Risiko je Trade. Bens Größe passt auf Bens Konto, nicht auf deins.
* **Den Einstiegskurs um jeden Preis.** Ist der Kurs seit Bens Einstieg
  weggelaufen, steigt er nicht hinterher, sondern lässt das Signal aus. Was
  weg ist, ist weg.

Die Quelle ist dieselbe Datei, die die Website im Bereich G liest: eine
`signals.json`, entweder lokal oder über eine Adresse im Netz.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol, Sequence

from . import indicators as ind
from .config import Config
from .model import Candle, ExitReason, Position, Side, Signal
from .strategy import ExitRules

CLOSED = {"gewonnen", "verloren", "be"}


# ---- Was aus der Quelle kommt -------------------------------------------
@dataclass(frozen=True, slots=True)
class SourceSignal:
    id: str
    side: Side
    entry: float
    stop: float | None
    target: float | None
    status: str
    opened_at: datetime
    closed_at: datetime | None
    note: str = ""

    @property
    def is_open(self) -> bool:
        return self.status == "offen"


def _time(value: Any, field: str, sid: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"Signal {sid!r}: {field} fehlt")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Signal {sid!r}: {field} nicht lesbar ({value!r})") from exc
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_payload(data: Any) -> list[SourceSignal]:
    """Liest das Format, das die Website und der Bot schreiben."""
    if not isinstance(data, dict) or not isinstance(data.get("signals"), list):
        raise ValueError("Die Signalquelle hat kein Feld 'signals' mit einer Liste")

    out: list[SourceSignal] = []
    for raw in data["signals"]:
        if not isinstance(raw, dict):
            continue
        sid = str(raw.get("id") or "")
        if not sid:
            raise ValueError("Ein Signal ohne 'id' lässt sich nicht zuordnen")
        side = str(raw.get("side", "")).lower()
        if side not in ("long", "short"):
            raise ValueError(f"Signal {sid!r}: side muss long oder short sein")
        status = str(raw.get("status", "offen")).lower()
        if status not in CLOSED | {"offen"}:
            raise ValueError(f"Signal {sid!r}: unbekannter Status {status!r}")
        entry = _number(raw.get("entry"))
        if entry is None:
            raise ValueError(f"Signal {sid!r}: kein Einstiegskurs")
        closed_at = (_time(raw.get("closedAt"), "closedAt", sid)
                     if raw.get("closedAt") else None)
        if status in CLOSED and closed_at is None:
            raise ValueError(f"Signal {sid!r}: geschlossen, aber ohne closedAt")
        out.append(SourceSignal(
            id=sid,
            side=Side(side),
            entry=entry,
            stop=_number(raw.get("sl")),
            target=_number(raw.get("tp")),
            status=status,
            opened_at=_time(raw.get("openedAt"), "openedAt", sid),
            closed_at=closed_at,
            note=str(raw.get("note") or ""),
        ))
    out.sort(key=lambda s: s.opened_at)
    return out


# ---- Woher die Signale kommen --------------------------------------------
class SignalSource(Protocol):
    def load(self) -> list[SourceSignal]: ...


@dataclass
class FileSource:
    """Eine `signals.json` auf der Platte."""

    path: str | Path

    def load(self) -> list[SourceSignal]:
        p = Path(self.path)
        if not p.exists():
            raise FileNotFoundError(
                f"Keine Signaldatei unter {p}. Entweder schreibt der Bot sie noch "
                "nicht, oder copy.path zeigt woandershin."
            )
        return parse_payload(json.loads(p.read_text(encoding="utf-8")))


@dataclass
class HttpSource:
    """Eine `signals.json` im Netz, etwa die der veröffentlichten Website."""

    url: str
    timeout: float = 10.0

    def load(self) -> list[SourceSignal]:
        request = urllib.request.Request(
            self.url, headers={"User-Agent": "bengx-bot/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as answer:
                body = answer.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ConnectionError(f"Signale nicht abrufbar von {self.url}: {exc}") from exc
        return parse_payload(json.loads(body))


def make_source(config: Config) -> SignalSource:
    c = config.copy
    if c.source == "http":
        if not c.url:
            raise ValueError("copy.source ist \"http\", aber copy.url ist leer")
        return HttpSource(c.url, c.timeout_seconds)
    return FileSource(c.path)


# ---- Der Bot --------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class CopyContext:
    atr: list[float | None]
    signals: dict[int, Signal]
    close_at: dict[str, int]       # Signal-Kennung → Kerze, in der zu schließen ist
    skipped: dict[str, str]        # Signal-Kennung → Grund

    def ready(self, i: int) -> bool:
        return True


class Kopierer:
    name = "Signal-Kopierer"

    def __init__(self, config: Config, source: SignalSource | None = None) -> None:
        self.cfg = config
        self.p = config.copy
        self.pip = config.market.pip
        self.source = source or make_source(config)

    def warmup_bars(self) -> int:
        return self.p.atr_period + 2

    def exit_rules(self) -> ExitRules:
        p = self.p
        return ExitRules(
            partial_r=1.0,                  # ohne Teilverkauf nicht benutzt
            partial_fraction=p.partial_fraction,
            trail_atr=p.trail_atr,
            time_stop_bars=p.max_hold_bars,
            friday_cutoff_hour=p.friday_cutoff_hour,
        )

    # ---- Vorbereitung ---------------------------------------------------
    def prepare(self, candles: Sequence[Candle]) -> CopyContext:
        p = self.p
        atr = ind.atr([c.high for c in candles], [c.low for c in candles],
                      [c.close for c in candles], p.atr_period)
        signals: dict[int, Signal] = {}
        close_at: dict[str, int] = {}
        skipped: dict[str, str] = {}

        if not candles:
            return CopyContext(atr, signals, close_at, skipped)

        source_signals = self.source.load()
        first_ts, last_ts = candles[0].ts, candles[-1].ts
        cursor = 0

        for src in source_signals:
            if src.opened_at < first_ts or src.opened_at > last_ts:
                skipped[src.id] = "außerhalb der vorliegenden Kerzen"
                continue

            i = self._index_at(candles, src.opened_at, cursor)
            if i is None:
                skipped[src.id] = "keine passende Kerze"
                continue
            cursor = i

            if not src.is_open and src.closed_at is not None and src.closed_at <= candles[i].ts:
                skipped[src.id] = "war beim Eintreffen schon geschlossen"
                continue

            delay = (candles[i].ts - src.opened_at).total_seconds() / 60.0
            if delay > p.max_age_minutes:
                skipped[src.id] = f"zu alt ({delay:.0f} Minuten)"
                continue

            built = self._build(src, candles[i], i, atr[i])
            if isinstance(built, str):
                skipped[src.id] = built
                continue
            if i in signals:
                skipped[src.id] = "gleiche Kerze wie ein anderes Signal"
                continue
            signals[i] = built

            if src.closed_at is not None:
                j = self._index_at(candles, src.closed_at, i)
                if j is not None:
                    close_at[src.id] = j

        return CopyContext(atr, signals, close_at, skipped)

    @staticmethod
    def _index_at(candles: Sequence[Candle], when: datetime,
                  start: int = 0) -> int | None:
        for i in range(start, len(candles)):
            if candles[i].ts >= when:
                return i
        return None

    # ---- Ein Signal übernehmen -------------------------------------------
    def _build(self, src: SourceSignal, bar: Candle, i: int,
               atr: float | None) -> Signal | str:
        p = self.p
        tolerance = p.max_slippage_pips * self.pip

        if p.entry_mode == "market":
            entry = bar.close
        else:
            if bar.low <= src.entry <= bar.high:
                entry = src.entry                      # Bens Kurs ist noch da
            elif abs(bar.close - src.entry) <= tolerance:
                entry = bar.close                      # knapp daneben, geht noch
            else:
                away = abs(bar.close - src.entry) / self.pip
                return f"Kurs {away:.0f} Pips weggelaufen"

        if p.follow_stop and src.stop is not None:
            stop = src.stop
        elif atr is not None:
            stop = entry - p.fallback_stop_atr * atr * src.side.sign
        else:
            return "kein Stop übermittelt und kein ATR vorhanden"

        if (src.side is Side.LONG and stop >= entry) or \
                (src.side is Side.SHORT and stop <= entry):
            return "Stop liegt auf der falschen Seite des Einstiegs"

        risk = abs(entry - stop)
        pips = risk / self.pip
        if not (p.min_stop_pips <= pips <= p.max_stop_pips):
            return f"Stop-Abstand {pips:.0f} Pips außerhalb der Grenzen"

        final = src.target if (p.follow_target and src.target is not None) else None
        if final is not None:
            wrong = (final <= entry) if src.side is Side.LONG else (final >= entry)
            if wrong:
                final = None
        partial = entry + risk * src.side.sign      # ohne Teilverkauf ungenutzt

        return Signal(
            ts=bar.ts, side=src.side, entry=entry, stop=stop, target=partial,
            atr=float(atr or 0.0), adx=0.0,
            reason=f"Kopie von {src.id}" + (f" · {src.note}" if src.note else ""),
            final_target=final, source_id=src.id,
        )

    # ---- Schnittstelle zur Maschine ---------------------------------------
    def evaluate(self, candles: Sequence[Candle], ctx: CopyContext,
                 i: int) -> Signal | None:
        return ctx.signals.get(i)

    def exit_now(self, position: Position, candles: Sequence[Candle],
                 ctx: CopyContext, i: int) -> ExitReason | None:
        """Schließt mit, sobald Ben das Original schließt."""
        if not self.p.close_with_source or position.source_id is None:
            return None
        j = ctx.close_at.get(position.source_id)
        return ExitReason.MANUAL if j is not None and i >= j else None
