"""Kerzendaten einlesen.

Unterstützt wird eine CSV-Datei mit den Spalten Zeit, Open, High, Low, Close
und optional Volumen. Die Spaltennamen dürfen variieren; Zeiten dürfen als
ISO-Text oder als Unix-Zeitstempel stehen. Zeiten ohne Zeitzone werden als UTC
gelesen.
"""

from __future__ import annotations

import csv
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Iterator, Sequence

from .model import Candle

_TIME_KEYS = ("time", "timestamp", "date", "datetime", "ts", "open_time")
_ALIASES = {
    "open": ("open", "o"),
    "high": ("high", "h"),
    "low": ("low", "l"),
    "close": ("close", "c", "price"),
    "volume": ("volume", "vol", "v", "tickvolume", "tick_volume"),
}


def _norm(name: str) -> str:
    return name.strip().lower().replace(" ", "").replace("<", "").replace(">", "")


def _parse_time(raw: str) -> datetime:
    raw = raw.strip()
    if not raw:
        raise ValueError("leerer Zeitstempel")
    if raw.isdigit() or (raw.startswith("-") and raw[1:].isdigit()):
        value = int(raw)
        if value > 10_000_000_000:        # Millisekunden
            value //= 1000
        return datetime.fromtimestamp(value, tz=timezone.utc)
    text = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y.%m.%d %H:%M",
                    "%d.%m.%Y %H:%M", "%Y/%m/%d %H:%M"):
            try:
                dt = datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"Zeitstempel nicht lesbar: {raw!r}")
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _parse_number(raw: str) -> float:
    text = raw.strip().replace(" ", "")
    if text.count(",") and not text.count("."):
        text = text.replace(",", ".")
    else:
        text = text.replace(",", "")
    return float(text)


def load_csv(path: str | Path) -> list[Candle]:
    """Liest eine CSV-Datei und gibt die Kerzen nach Zeit sortiert zurück."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"Keine Kursdatei unter {p}. Lege eine CSV mit den Spalten "
            "time,open,high,low,close ab oder setze data.csv in der Konfiguration."
        )
    with p.open(newline="", encoding="utf-8-sig") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(fh, dialect=dialect)
        if not reader.fieldnames:
            raise ValueError(f"{p} hat keine Kopfzeile")
        lookup = {_norm(name): name for name in reader.fieldnames}

        def column(keys: Sequence[str], label: str) -> str:
            for k in keys:
                if k in lookup:
                    return lookup[k]
            raise ValueError(
                f"{p}: keine Spalte für {label} gefunden "
                f"(gesucht: {', '.join(keys)}; vorhanden: {', '.join(reader.fieldnames)})"
            )

        t_col = column(_TIME_KEYS, "die Zeit")
        cols = {k: column(v, k) for k, v in _ALIASES.items() if k != "volume"}
        try:
            v_col = column(_ALIASES["volume"], "Volumen")
        except ValueError:
            v_col = None

        candles: list[Candle] = []
        for n, row in enumerate(reader, start=2):
            if not row.get(t_col):
                continue
            try:
                candles.append(Candle(
                    ts=_parse_time(row[t_col]),
                    open=_parse_number(row[cols["open"]]),
                    high=_parse_number(row[cols["high"]]),
                    low=_parse_number(row[cols["low"]]),
                    close=_parse_number(row[cols["close"]]),
                    volume=_parse_number(row[v_col]) if v_col and row.get(v_col) else 0.0,
                ))
            except ValueError as exc:
                raise ValueError(f"{p}, Zeile {n}: {exc}") from exc

    candles.sort(key=lambda c: c.ts)
    return candles


def write_csv(path: str | Path, candles: Iterable[Candle]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["time", "open", "high", "low", "close", "volume"])
        for c in candles:
            w.writerow([c.ts.isoformat(), f"{c.open:.2f}", f"{c.high:.2f}",
                        f"{c.low:.2f}", f"{c.close:.2f}", f"{c.volume:.0f}"])


def synthetic(bars: int = 3000, start: float = 2000.0, seed: int = 7,
              begin: datetime | None = None,
              minutes: int = 60) -> list[Candle]:
    """Erfundene Kerzen für Tests und Trockenläufe.

    Ausdrücklich keine echten Kurse: ein Zufallspfad mit wechselnden Phasen.
    Ergebnisse darauf sagen nichts über den echten Markt — sie zeigen nur,
    dass die Mechanik läuft.
    """
    rng = random.Random(seed)
    t = begin or datetime(2024, 1, 1, tzinfo=timezone.utc)
    step = timedelta(minutes=minutes)
    price = start
    drift = 0.0
    out: list[Candle] = []
    for i in range(bars):
        if i % 180 == 0:                       # alle paar Tage dreht die Lage
            drift = rng.uniform(-0.35, 0.35)
        vol = 2.0 + 1.4 * abs(math.sin(i / 90.0))
        move = rng.gauss(drift, vol)
        o = price
        c = max(1.0, o + move)
        wick = abs(rng.gauss(0, vol * 0.7))
        h = max(o, c) + wick
        l = max(0.5, min(o, c) - abs(rng.gauss(0, vol * 0.7)))
        out.append(Candle(ts=t, open=round(o, 2), high=round(h, 2),
                          low=round(l, 2), close=round(c, 2),
                          volume=round(rng.uniform(500, 5000))))
        price = c
        t += step
    return out


def news_synthetic(days: int = 12, start: float = 2000.0, seed: int = 11,
                   release_hour: int = 12, release_minute: int = 30,
                   spike: float = 6.0, quiet: float = 0.25,
                   begin: datetime | None = None
                   ) -> tuple[list[Candle], list[datetime]]:
    """Ruhige Minutenkerzen mit einer Nachricht an jedem Werktag.

    Für den Einzelschuss-Bot: `synthetic()` schwankt je Minute so stark, dass
    der Ruhe-Filter zu Recht jeden Termin ablehnt — was die Mechanik nicht
    prüft. Hier liegt vor dem Termin Ruhe und danach ein Ausschlag, dessen
    Richtung wechselt.

    Gibt die Kerzen und die Terminzeiten zurück. Auch das sind keine echten
    Kurse: ein Ergebnis darauf sagt nichts über den Markt.
    """
    rng = random.Random(seed)
    t = begin or datetime(2024, 1, 1, tzinfo=timezone.utc)
    price = start
    out: list[Candle] = []
    events: list[datetime] = []
    for tag in range(days):
        hoch = t + timedelta(days=tag)
        if hoch.weekday() >= 5:                      # am Wochenende ruht der Markt
            continue
        termin = hoch.replace(hour=release_hour, minute=release_minute)
        events.append(termin)
        # Von drei Stunden vor bis drei Stunden nach dem Termin.
        minute = termin - timedelta(hours=3)
        richtung = 1 if rng.random() < 0.5 else -1
        for k in range(360):
            o = price
            if k == 180:                             # die Nachrichtenkerze
                c = o + spike * richtung * rng.uniform(0.6, 1.4)
            else:
                nach = 1.0 if k < 180 else 2.5       # danach bleibt es unruhig
                c = o + rng.gauss(0, quiet) * nach
            docht = abs(rng.gauss(0, quiet))
            out.append(Candle(
                ts=minute, open=round(o, 2),
                high=round(max(o, c) + docht, 2),
                low=round(min(o, c) - docht, 2),
                close=round(c, 2),
                volume=round(rng.uniform(500, 5000)),
            ))
            price = c
            minute += timedelta(minutes=1)
    return out, events


def iter_closed(candles: Sequence[Candle], warmup: int) -> Iterator[int]:
    """Indizes der Kerzen, die der Bot bewerten darf."""
    for i in range(max(warmup, 1), len(candles)):
        yield i
