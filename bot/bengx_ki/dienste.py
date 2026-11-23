"""Was die KI tun kann — als Daten, für Oberfläche und Kommandozeile gleich.

Jede Funktion bekommt Kerzen (und, wo nötig, das gelernte Gehirn) und gibt ein
Wörterbuch zurück, das sich direkt als JSON verschicken lässt.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Sequence

import torch

from bengx_bot.data import load_csv
from bengx_bot.indicators import adx, atr, donchian, ema, rsi, slope
from bengx_bot.model import Candle

from . import lernprobe
from .auswertung import kennzahlen
from .gehirn import Gehirn
from .merkmale import HOCH, KLASSEN, MERKMALE, RUNTER
from .modelle import MODELLE, pruefe
from .training import (daten_fuer, erste_stelle, laden, normieren, tabelle_bauen,
                       wahrscheinlichkeiten)


class Quelle:
    """Die Kursdaten. Neu eingelesen nur, wenn sich die Datei geändert hat."""

    def __init__(self, csv: str | Path | None, nur_lernprobe: bool = False) -> None:
        self.csv = Path(csv) if csv else None
        self.nur_lernprobe = nur_lernprobe
        self._cache: tuple[float, list[Candle]] | None = None

    @property
    def name(self) -> str:
        return "Lernprobe (erfundene Kurse)" if self.nur_lernprobe else str(self.csv)

    def kerzen(self) -> list[Candle]:
        if self.nur_lernprobe:
            if self._cache is None:
                self._cache = (0.0, lernprobe.kerzen(6000, zufall=99))
            return self._cache[1]
        if not self.csv or not self.csv.exists():
            raise FileNotFoundError(
                f"Keine Kursdatei unter {self.csv}. Starte mit --csv PFAD "
                "oder lege die Datei dort ab.")
        stempel = self.csv.stat().st_mtime
        if self._cache is None or self._cache[0] != stempel:
            self._cache = (stempel, load_csv(self.csv))
        return self._cache[1]

    def info(self) -> dict:
        try:
            k = self.kerzen()
        except (FileNotFoundError, ValueError) as exc:
            return {"name": self.name, "fehler": str(exc)}
        return {"name": self.name, "kerzen": len(k),
                "von": k[0].ts.isoformat(), "bis": k[-1].ts.isoformat(),
                "schluss": k[-1].close, "lernprobe": self.nur_lernprobe}


class Modellablage:
    """Das gespeicherte Gehirn. Neu geladen nur, wenn die Datei sich ändert."""

    def __init__(self, pfad: str | Path, name: str = "Das Modell") -> None:
        self.pfad = Path(pfad)
        self.name = name
        self._cache: tuple[float, Gehirn, dict] | None = None

    def vorhanden(self) -> bool:
        return self.pfad.exists()

    def holen(self) -> tuple[Gehirn, dict]:
        if not self.pfad.exists():
            raise FileNotFoundError(f"{self.name} ist noch nicht trainiert.")
        stempel = self.pfad.stat().st_mtime
        if self._cache is None or self._cache[0] != stempel:
            g, p = laden(self.pfad)
            self._cache = (stempel, g, p)
        return self._cache[1], self._cache[2]

    def info(self) -> dict:
        if not self.vorhanden():
            return {"vorhanden": False}
        g, p = self.holen()
        return {
            "vorhanden": True,
            "erstellt": p["erstellt"],
            "test_ab": p["test_ab"],
            "beste_epoche": p.get("beste_epoche"),
            "gewichte": g.anzahl_gewichte(),
            "plan": p["plan"],
            "horizont": p["horizont"],
            "abstand_atr": p["abstand_atr"],
            "merkmale": p["merkmale"],
            "ergebnis": p.get("ergebnis"),
        }


class Modelle:
    """Die drei Modelle Mini, Standard und Max, je eine Datei im Ordner."""

    def __init__(self, ordner: str | Path) -> None:
        self.ordner = Path(ordner)
        self.ablagen = {m: Modellablage(self.ordner / f"{m}.pt", info["name"])
                        for m, info in MODELLE.items()}

    def __getitem__(self, modell: str) -> Modellablage:
        return self.ablagen[pruefe(modell)]

    def info(self) -> dict:
        return {m: {"name": MODELLE[m]["name"], "text": MODELLE[m]["text"],
                    "faktor": MODELLE[m]["faktor"], "bauplan": MODELLE[m]["plan"],
                    **a.info()}
                for m, a in self.ablagen.items()}


def _atr_jetzt(kerzen: Sequence[Candle]) -> list[float | None]:
    return atr([k.high for k in kerzen], [k.low for k in kerzen],
               [k.close for k in kerzen], 14)


def analyse(kerzen: Sequence[Candle], gehirn: Gehirn, paket: dict,
            schwelle: float = 0.5) -> dict:
    """Einschätzung der KI für die jüngste Kerze."""
    if len(kerzen) <= erste_stelle(paket["plan"]["fenster"]):
        raise ValueError("Zu wenig Kerzen für eine Analyse.")
    tabelle = normieren(tabelle_bauen(kerzen), torch.tensor(paket["mittel"]),
                        torch.tensor(paket["streuung"]))
    letzte = len(kerzen) - 1
    p = wahrscheinlichkeiten(gehirn, tabelle, [letzte])[0]
    k = kerzen[letzte]
    weg = paket["abstand_atr"] * _atr_jetzt(kerzen)[letzte]
    hoch, runter = p[HOCH].item(), p[RUNTER].item()
    if hoch >= schwelle and hoch > runter:
        idee = {"richtung": "kaufen", "einstieg": k.close,
                "stop": k.close - weg, "ziel": k.close + weg}
    elif runter >= schwelle and runter > hoch:
        idee = {"richtung": "verkaufen", "einstieg": k.close,
                "stop": k.close + weg, "ziel": k.close - weg}
    else:
        idee = None
    staerkste = max(range(len(KLASSEN)), key=lambda i: p[i].item())
    kurz = (f"{idee['richtung'].capitalize()} · {max(hoch, runter):.0%}" if idee
            else f"Kein Signal · {KLASSEN[staerkste]} {p[staerkste].item():.0%}")
    return {
        "kurz": kurz,
        "kerze": k.ts.isoformat(),
        "schluss": k.close,
        "wahrscheinlichkeiten": {KLASSEN[i]: p[i].item() for i in range(len(KLASSEN))},
        "schwelle": schwelle,
        "idee": idee,
        "horizont": paket["horizont"],
        "abstand": weg,
    }


def indikatoren(kerzen: Sequence[Candle]) -> dict:
    """Die klassischen Indikatoren des Bots, mit kurzer Deutung."""
    if len(kerzen) < 220:
        raise ValueError("Zu wenig Kerzen: mindestens 220 für EMA 200.")
    h = [k.high for k in kerzen]
    l = [k.low for k in kerzen]
    c = [k.close for k in kerzen]
    e50, e200 = ema(c, 50), ema(c, 200)
    steigung = slope(e200, 20)
    r, a, x = rsi(c, 14), adx(h, l, c, 14), atr(h, l, c, 14)
    oben, unten = donchian(h, l, 20)
    i = len(kerzen) - 1

    def ueber(wert: float) -> str:
        return "Kurs darüber" if c[i] > wert else "Kurs darunter"

    trend = "steigend" if (steigung[i] or 0) > 0 else "fallend"
    rsi_d = ("überkauft" if r[i] >= 70 else "überverkauft" if r[i] <= 30 else "neutral")
    adx_d = ("starker Trend" if a[i] >= 25 else "mäßiger Trend" if a[i] >= 18
             else "kein Trend, seitwärts")
    don_d = ("Ausbruch nach oben" if c[i] > oben[i] else
             "Ausbruch nach unten" if c[i] < unten[i] else "im Kanal")
    liste = [
        {"name": "Kurs", "wert": c[i], "deutung": kerzen[i].ts.strftime("%d.%m.%Y %H:%M UTC")},
        {"name": "EMA 50", "wert": e50[i], "deutung": ueber(e50[i])},
        {"name": "EMA 200", "wert": e200[i], "deutung": f"{ueber(e200[i])} · {trend}"},
        {"name": "RSI 14", "wert": r[i], "deutung": rsi_d},
        {"name": "ADX 14", "wert": a[i], "deutung": adx_d},
        {"name": "ATR 14", "wert": x[i], "deutung": f"{x[i] / c[i]:.2%} vom Kurs"},
        {"name": "Hoch 20", "wert": oben[i], "deutung": don_d},
        {"name": "Tief 20", "wert": unten[i], "deutung": ""},
    ]
    gesamt = ("Aufwärtstrend" if c[i] > e200[i] and trend == "steigend" else
              "Abwärtstrend" if c[i] < e200[i] and trend == "fallend" else "uneinheitlich")
    n = 160
    return {
        "kurz": f"{gesamt} · RSI {r[i]:.0f} · ADX {a[i]:.0f}",
        "gesamt": gesamt,
        "liste": liste,
        "verlauf": {"zeit": [k.ts.isoformat() for k in kerzen[-n:]],
                    "schluss": c[-n:], "ema50": e50[-n:], "ema200": e200[-n:]},
    }


def strategie(kerzen: Sequence[Candle], gehirn: Gehirn, paket: dict) -> dict:
    """Prüft die KI-Strategie — nur auf Kerzen ab dem Test-Teil des Trainings."""
    daten = daten_fuer(kerzen, paket)
    ab = datetime.fromisoformat(paket["test_ab"])
    stellen = [i for i in daten.stellen if daten.zeiten[i] >= ab]
    if len(stellen) < 50:
        raise ValueError(
            f"Nur {len(stellen)} Kerzen nach dem Lernzeitraum (ab {ab:%d.%m.%Y}). "
            "Für einen ehrlichen Test braucht es neuere Daten.")
    p = wahrscheinlichkeiten(gehirn, daten.tabelle, stellen)
    z = kennzahlen(stellen, daten.ausgang, p)
    beste = max(z["schwellen"], key=lambda s: s["summe_r"] if s["trades"] else -1e9)
    z["kurz"] = (f"Treffer {z['treffer']:.0%} gegen {z['raten']:.0%} Raten · "
                 f"bestes {beste['summe_r']:+.1f} R ab {beste['schwelle']:.0%}")
    z["ab"] = paket["test_ab"]
    z["regeln"] = {"horizont": paket["horizont"], "abstand_atr": paket["abstand_atr"],
                   "fenster": paket["plan"]["fenster"]}
    return z


__all__ = ["Quelle", "Modellablage", "Modelle", "analyse", "indikatoren", "strategie", "MERKMALE"]
