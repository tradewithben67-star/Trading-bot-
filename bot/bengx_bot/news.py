"""Der Einzelschuss-Bot.

Das Vorbild läuft auf TikTok als MetaTrader-EA auf XAU/USD: zwei Order um
eine Nachricht, **eine** davon wird ausgeführt, die andere wird gestrichen.
Kein Nachkaufen, kein Netz, keine Verdopplung — daher der Name.

Der Ablauf in vier Schritten:

1. **Scharfmachen.** Kurz vor dem Ereignis steht der Referenzkurs fest: der
   Schluss der letzten Kerze, die davor fertig ist. Darüber und darunter
   liegt je eine Stop-Order im Abstand `offset_pips`.

2. **Ruhe davor.** Hat sich der Kurs in den Minuten vor dem Termin schon
   bewegt, wird nicht gehandelt. Eine Spanne, die breiter ist als
   `max_prerange_pips`, sägt die Straddle in Stücke, bevor die Nachricht da ist.

3. **Einzelschuss.** Die erste Seite, die berührt wird, wird gehandelt — die
   andere Order verfällt im selben Augenblick. Wird in der Frist keine der
   beiden erreicht, verfallen beide. Pro Ereignis gibt es genau einen Trade,
   auch wenn er sofort in den Stop läuft. Es gibt kein zweites Mal.

4. **Festes Ziel.** Stop und Ziel stehen in Pips, nicht in ATR: bei einer
   Nachricht geht es um die ersten Minuten, nicht um die Tagesvolatilität.

Zwei Arten, an einen Termin zu kommen:

* `trigger = "kalender"` — Termine aus einer JSON-Datei, wie ein
  Wirtschaftskalender sie liefert (CPI, NFP, FOMC, PPI).
* `trigger = "ausbruch"` — ohne Kalender. Eine Minutenkerze, deren Spanne ein
  Vielfaches des ATR erreicht, gilt selbst als Ereignis; die Order liegen dann
  über ihrem Hoch und unter ihrem Tief. Damit läuft der Bot auch, wenn niemand
  den Kalender pflegt.

Alles wird in `prepare()` über die ganze Reihe gerechnet, nicht über Aufrufe
hinweg angesammelt — nach einem Neustart kommen dieselben Signale heraus wie
im Backtest.

**Mehrdeutige Kerzen.** Werden beide Seiten innerhalb derselben Minutenkerze
berührt, ist aus Kerzendaten nicht zu erkennen, welche zuerst kam. Dann gilt
die ungünstige Annahme (`tie_break = "pessimistic"`): gehandelt wird die Seite
*gegen* die Richtung der Kerze — also die, die anschließend in den Stop läuft.
So rechnet sich der Backtest nicht reich. Mit `"skip"` wird so ein Ereignis
stattdessen ausgelassen; das sieht hübscher aus, als es ist.
"""

from __future__ import annotations

import bisect
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

from . import indicators as ind
from .config import Config
from .model import Candle, Side, Signal
from .strategy import ExitRules

MINUTE = timedelta(minutes=1)

# Was in einer Kalenderdatei als "wichtig" gilt. Englisch und deutsch, damit
# ein Export von irgendeinem Kalender ohne Nacharbeit passt.
HIGH = {"hoch", "high", "3", "***"}


@dataclass(frozen=True, slots=True)
class NewsEvent:
    """Ein Termin aus dem Kalender."""

    ts: datetime
    name: str = ""
    impact: str = "hoch"

    @property
    def label(self) -> str:
        return self.name or self.ts.strftime("%Y-%m-%d %H:%M")


def parse_calendar(raw: Any, impacts: Sequence[str] | None = None) -> list[NewsEvent]:
    """Termine aus dem geladenen JSON. Erlaubt sind drei Formen:

    * `{"events": [{"time": ..., "name": ..., "impact": ...}, ...]}`
    * eine Liste solcher Einträge
    * eine Liste reiner Zeitstempel

    Unbekannte Felder werden übergangen, ein unlesbarer Zeitstempel fliegt
    auf — eine stillschweigend verschluckte Zeile wäre ein Termin, an dem
    der Bot nicht handelt, ohne dass es jemand merkt.
    """
    erlaubt = {s.lower() for s in (impacts if impacts is not None else HIGH)}
    if isinstance(raw, dict):
        items = raw.get("events") or raw.get("termine") or []
    else:
        items = raw
    if not isinstance(items, list):
        raise ValueError("Kalender: erwartet wird eine Liste von Terminen")

    out: list[NewsEvent] = []
    for nr, item in enumerate(items, 1):
        if isinstance(item, str):
            item = {"time": item}
        if not isinstance(item, dict):
            raise ValueError(f"Kalender: Eintrag {nr} ist kein Termin")
        rohzeit = item.get("time") or item.get("zeit") or item.get("ts")
        if not rohzeit:
            raise ValueError(f"Kalender: Eintrag {nr} hat keine Zeit")
        try:
            ts = datetime.fromisoformat(str(rohzeit).replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(
                f"Kalender: Eintrag {nr} hat keine lesbare Zeit: {rohzeit!r}"
            ) from None
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        impact = str(item.get("impact") or item.get("wichtigkeit") or "hoch").lower()
        if erlaubt and impact not in erlaubt:
            continue
        out.append(NewsEvent(
            ts=ts.astimezone(timezone.utc),
            name=str(item.get("name") or item.get("titel") or ""),
            impact=impact,
        ))
    out.sort(key=lambda e: e.ts)
    return out


def load_calendar(path: str | Path, impacts: Sequence[str] | None = None) -> list[NewsEvent]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"Kalender nicht gefunden: {p} — Termine eintragen oder "
            'einzelschuss.trigger = "ausbruch" setzen'
        )
    with p.open("r", encoding="utf-8") as fh:
        return parse_calendar(json.load(fh), impacts)


@dataclass(slots=True)
class Straddle:
    """Die zwei Order um ein Ereignis — und was aus ihnen wurde.

    Steht nach dem Backtest zur Nachschau im Kontext: an welchem Termin
    gehandelt wurde, an welchem nicht, und warum nicht.
    """

    label: str
    event_ts: datetime
    arm_index: int
    reference: float
    buy_level: float
    sell_level: float
    deadline: datetime
    outcome: str = "offen"
    fill_index: int | None = None
    fill_side: Side | None = None


@dataclass(frozen=True, slots=True)
class NewsContext:
    """Was die Maschine je Minutenkerze braucht."""

    atr: list[float | None]
    signals: dict[int, Signal]
    straddles: list[Straddle] = field(default_factory=list)
    skipped: dict[str, int] = field(default_factory=dict)

    def ready(self, i: int) -> bool:
        return self.atr[i] is not None


class Einzelschuss:
    """Zwei Order, ein Schuss."""

    name = "Einzelschuss"

    def __init__(self, config: Config, events: Sequence[NewsEvent] | None = None) -> None:
        self.cfg = config
        self.p = config.einzelschuss
        self.pip = config.market.pip
        self._events = list(events) if events is not None else None

    # ---- Schnittstelle --------------------------------------------------
    def warmup_bars(self) -> int:
        return max(self.p.atr_period * 3, self.p.prerange_minutes) + 10

    def exit_rules(self) -> ExitRules:
        p = self.p
        return ExitRules(
            partial_r=p.partial_r,
            partial_fraction=p.partial_fraction,
            trail_atr=p.trail_atr,
            time_stop_bars=p.max_hold_minutes,
            friday_cutoff_hour=p.friday_cutoff_hour,
            # Bei einer Nachricht kann der Stop in derselben Minute fallen, in
            # der eingestiegen wurde. Wer das nicht prüft, schönt den Backtest
            # genau an der Stelle, auf die es ankommt.
            stop_on_entry_bar=True,
        )

    def in_session(self, candle: Candle) -> bool:
        p = self.p
        ts = candle.ts
        if ts.weekday() >= 5:
            return False
        if not (p.session_start_hour <= ts.hour < p.session_end_hour):
            return False
        if ts.weekday() == 4 and ts.hour >= p.friday_cutoff_hour:
            return False
        return True

    # ---- Termine --------------------------------------------------------
    def events(self) -> list[NewsEvent]:
        """Die Termine: übergeben, oder aus der Kalenderdatei gelesen."""
        if self._events is None:
            self._events = load_calendar(self.p.calendar, self.p.impacts or None)
        return self._events

    def _burst_events(self, candles: Sequence[Candle],
                      atr: Sequence[float | None]) -> list[NewsEvent]:
        """Ohne Kalender: eine Kerze, die aus der Ruhe ausbricht, ist das Ereignis."""
        p = self.p
        out: list[NewsEvent] = []
        letzte: datetime | None = None
        for i, c in enumerate(candles):
            a = atr[i]
            if a is None or a <= 0:
                continue
            spanne = c.high - c.low
            if spanne < p.burst_atr * a:
                continue
            if spanne / self.pip < p.min_burst_pips:
                continue
            ts = c.ts + MINUTE          # die Order liegen nach dieser Kerze
            if letzte is not None and ts - letzte < timedelta(minutes=p.min_minutes_between):
                continue
            letzte = ts
            out.append(NewsEvent(ts=ts, name=f"Ausbruch {spanne / self.pip:.0f}p"))
        return out

    # ---- Vorbereitung ---------------------------------------------------
    def prepare(self, candles: Sequence[Candle]) -> NewsContext:
        p = self.p
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        closes = [c.close for c in candles]
        atr = ind.atr(highs, lows, closes, p.atr_period)

        if not candles:
            return NewsContext(atr=atr, signals={})

        stamps = [c.ts for c in candles]
        if p.trigger == "ausbruch":
            events = self._burst_events(candles, atr)
        else:
            events = [e for e in self.events()
                      if stamps[0] <= e.ts <= stamps[-1] + MINUTE]

        signals: dict[int, Signal] = {}
        straddles: list[Straddle] = []
        skipped: dict[str, int] = {}
        belegt: set[int] = set()        # Minuten, in denen schon ein Signal steht
        pro_tag: dict[Any, int] = {}
        letzter_fill: datetime | None = None

        def verwerfen(grund: str) -> None:
            skipped[grund] = skipped.get(grund, 0) + 1

        for event in events:
            s = self._arm(candles, stamps, atr, event)
            if isinstance(s, str):
                verwerfen(s)
                continue
            tag = s.event_ts.date()
            if pro_tag.get(tag, 0) >= p.max_events_per_day:
                s.outcome = "Tagesgrenze"
                straddles.append(s)
                verwerfen("Tagesgrenze erreicht")
                continue
            if (letzter_fill is not None and s.event_ts - letzter_fill
                    < timedelta(minutes=p.min_minutes_between)):
                s.outcome = "zu kurz nach dem letzten Trade"
                straddles.append(s)
                verwerfen("zu kurz nach dem letzten Trade")
                continue

            signal = self._scan(candles, stamps, atr, s)
            straddles.append(s)
            if signal is None:
                verwerfen(s.outcome)
                continue
            i = s.fill_index
            if i in belegt:
                s.outcome = "Minute schon belegt"
                verwerfen(s.outcome)
                continue
            belegt.add(i)
            signals[i] = signal
            pro_tag[tag] = pro_tag.get(tag, 0) + 1
            letzter_fill = s.event_ts

        return NewsContext(atr=atr, signals=signals,
                           straddles=straddles, skipped=skipped)

    def _arm(self, candles: Sequence[Candle], stamps: Sequence[datetime],
             atr: Sequence[float | None], event: NewsEvent) -> Straddle | str:
        """Die zwei Order legen. Gibt den Grund als Text zurück, wenn nicht."""
        p = self.p
        off = p.offset_pips * self.pip

        if p.trigger == "ausbruch":
            # Das Ereignis ist die Ausbruchskerze; ihre Schlusszeit ist der
            # Terminzeitpunkt. Sie selbst gibt die Stufen vor.
            a = bisect.bisect_right(stamps, event.ts - MINUTE) - 1
        else:
            # Letzte Kerze, die vor dem Scharfmachen abgeschlossen ist.
            arm_bis = event.ts - timedelta(seconds=p.arm_seconds_before)
            a = bisect.bisect_right(stamps, arm_bis - MINUTE) - 1
        if a < self.warmup_bars():
            return "zu wenig Vorlauf"
        if atr[a] is None:
            return "zu wenig Vorlauf"
        if not self.in_session(candles[a]):
            return "außerhalb der Handelszeit"

        if p.trigger == "ausbruch":
            # Das Ereignis ist die Kerze selbst: über ihr Hoch, unter ihr Tief.
            quelle = candles[a]
            referenz = quelle.close
            kauf = quelle.high + off
            verkauf = quelle.low - off
        else:
            referenz = candles[a].close
            kauf = referenz + off
            verkauf = referenz - off
            # Ruhe vor der Nachricht: eine schon laufende Bewegung sägt die
            # Straddle auf, bevor der Termin da ist.
            von = max(0, a - p.prerange_minutes + 1)
            spanne = (max(c.high for c in candles[von:a + 1])
                      - min(c.low for c in candles[von:a + 1]))
            if spanne / self.pip > p.max_prerange_pips:
                return "vor der Nachricht schon zu bewegt"

        if (kauf - verkauf) / self.pip < 2 * p.offset_pips - 1e-9:
            return "Abstand der Order zu klein"

        return Straddle(
            label=event.label,
            event_ts=event.ts,
            arm_index=a,
            reference=referenz,
            buy_level=kauf,
            sell_level=verkauf,
            deadline=event.ts + timedelta(minutes=p.window_minutes),
        )

    def _scan(self, candles: Sequence[Candle], stamps: Sequence[datetime],
              atr: Sequence[float | None], s: Straddle) -> Signal | None:
        """Welche Seite zuerst berührt wird — und ob überhaupt."""
        p = self.p
        # Erste Kerze, die den Termin enthält: ihre Schlusszeit liegt danach.
        start = max(bisect.bisect_right(stamps, s.event_ts - MINUTE), s.arm_index + 1)

        for i in range(start, len(candles)):
            c = candles[i]
            if c.ts >= s.deadline:
                break
            if not self.in_session(c):
                s.outcome = "außerhalb der Handelszeit"
                return None

            kauf = c.high >= s.buy_level
            verkauf = c.low <= s.sell_level
            if not kauf and not verkauf:
                continue

            if kauf and verkauf:
                if p.tie_break == "skip":
                    s.outcome = "beide Seiten in einer Minute"
                    return None
                # Ungünstige Annahme: die Seite gegen die Richtung der Kerze —
                # die, die anschließend in den Stop läuft.
                side = Side.SHORT if c.close >= c.open else Side.LONG
                grund = "beide Seiten in einer Minute, ungünstige Annahme"
            else:
                side = Side.LONG if kauf else Side.SHORT
                grund = "erste Seite berührt"

            s.outcome = side.value
            s.fill_index = i
            s.fill_side = side
            return self._signal(c, i, atr, s, side, grund)

        s.outcome = "keine Seite berührt"
        return None

    def _signal(self, candle: Candle, i: int, atr: Sequence[float | None],
                s: Straddle, side: Side, grund: str) -> Signal:
        p = self.p
        stufe = s.buy_level if side is Side.LONG else s.sell_level
        # Bei einer Nachricht füllt keine Stop-Order zum Wunschkurs. Der
        # Aufschlag geht gegen die eigene Richtung; das Risiko wächst dadurch
        # wirklich, und genau so soll es in der Größenrechnung ankommen.
        entry = stufe + p.news_slippage_pips * self.pip * side.sign
        # Stop und Ziel hängen an der Orderstufe, nicht am Fill — so liegen sie
        # dort, wo sie in der Plattform eingetragen würden.
        stop = stufe - p.stop_pips * self.pip * side.sign
        ziel = stufe + p.target_pips * self.pip * side.sign
        teil = entry + abs(entry - stop) * p.partial_r * side.sign
        a = atr[i]
        return Signal(
            ts=candle.ts,
            side=side,
            entry=entry,
            stop=stop,
            target=teil if p.partial_fraction > 0 else ziel,
            final_target=ziel,
            atr=float(a) if a is not None else 0.0,
            adx=0.0,
            reason=(f"{s.label}: {grund}, "
                    f"{p.offset_pips:g}p über Referenz {s.reference:.2f}"
                    if side is Side.LONG else
                    f"{s.label}: {grund}, "
                    f"{p.offset_pips:g}p unter Referenz {s.reference:.2f}"),
            source_id=s.label or None,
        )

    # ---- Signal ----------------------------------------------------------
    def evaluate(self, candles: Sequence[Candle], ctx: NewsContext,
                 i: int) -> Signal | None:
        if i < 1 or i >= len(candles) or not ctx.ready(i):
            return None
        return ctx.signals.get(i)
