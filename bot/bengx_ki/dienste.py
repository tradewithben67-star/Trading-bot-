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
from .training import (daten_fuer, erste_stelle, fenster_holen, laden, normieren,
                       tabelle_bauen, wahrscheinlichkeiten)


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


# Merkmale in Gruppen, so wie ein Händler sie benennen würde.
GRUPPEN = {
    "Kerzenform": ("koerper", "docht_oben", "docht_unten", "spanne"),
    "Bewegung": ("rendite",),
    "Abstand zum Durchschnitt": ("abstand_ema",),
    "Unruhe": ("unruhe",),
    "Volumen": ("volumen",),
    "Uhrzeit und Wochentag": ("stunde_sin", "stunde_cos", "tag_sin", "tag_cos"),
}
CHART_KERZEN = 120


def kerzenform(k: Candle, atr_wert: float) -> str:
    """Wie ein Händler die Kerze nennen würde."""
    a = atr_wert or 1.0
    koerper = abs(k.close - k.open) / a
    oben = (k.high - max(k.open, k.close)) / a
    unten = (min(k.open, k.close) - k.low) / a
    if unten > 0.8 and unten > 2 * oben and koerper < 0.6:
        return "Hammer (langer Docht unten)"
    if oben > 0.8 and oben > 2 * unten and koerper < 0.6:
        return "Sternschnuppe (langer Docht oben)"
    if koerper > 1.2:
        return "starke Kerze nach oben" if k.close > k.open else "starke Kerze nach unten"
    if koerper < 0.15:
        return "Doji (unentschlossen)"
    return "Kerze nach oben" if k.close > k.open else "Kerze nach unten"


def chartdaten(kerzen: Sequence[Candle], anzahl: int = CHART_KERZEN) -> dict:
    stueck = kerzen[-anzahl:]
    e50 = ema([k.close for k in kerzen], 50)[-anzahl:]
    return {"zeit": [k.ts.isoformat() for k in stueck],
            "open": [k.open for k in stueck], "high": [k.high for k in stueck],
            "low": [k.low for k in stueck], "close": [k.close for k in stueck],
            "ema50": e50}


def analyse(kerzen: Sequence[Candle], gehirn: Gehirn, paket: dict,
            schwelle: float = 0.5) -> dict:
    """Einschätzung der KI für die jüngste Kerze — mit Chart und Begründung."""
    fenster = paket["plan"]["fenster"]
    if len(kerzen) <= erste_stelle(fenster):
        raise ValueError("Zu wenig Kerzen für eine Analyse.")
    tabelle = normieren(tabelle_bauen(kerzen), torch.tensor(paket["mittel"]),
                        torch.tensor(paket["streuung"]))
    letzte = len(kerzen) - 1
    p = wahrscheinlichkeiten(gehirn, tabelle, [letzte])[0]
    k = kerzen[letzte]
    atr_reihe = _atr_jetzt(kerzen)
    weg = paket["abstand_atr"] * atr_reihe[letzte]
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
    erklaerung = erklaeren(kerzen, gehirn, tabelle, letzte, fenster, atr_reihe,
                           HOCH if hoch >= runter else RUNTER)
    return {
        "kurz": kurz,
        "kerze": k.ts.isoformat(),
        "schluss": k.close,
        "wahrscheinlichkeiten": {KLASSEN[i]: p[i].item() for i in range(len(KLASSEN))},
        "schwelle": schwelle,
        "idee": idee,
        "horizont": paket["horizont"],
        "abstand": weg,
        "chart": chartdaten(kerzen),
        **erklaerung,
    }


def erklaeren(kerzen: Sequence[Candle], gehirn: Gehirn, tabelle: torch.Tensor,
              letzte: int, fenster: int, atr_reihe: list, richtung: int) -> dict:
    """Warum diese Einschätzung? Zwei ehrliche Blicke ins Gehirn.

    1. **Fokus** — auf welche Kerzen die jüngste Kerze über alle Blöcke hinweg
       geachtet hat (Aufmerksamkeit, durchgerollt).
    2. **Merkmale** — was passiert, wenn man einer Merkmalsgruppe die
       Information nimmt (auf den Durchschnitt setzt)? Sinkt die
       Wahrscheinlichkeit der gewählten Richtung stark, hat diese Gruppe die
       Entscheidung getragen.

    Das sind Messungen am Netz, keine erfundene Begründung.
    """
    x = fenster_holen(tabelle, [letzte], fenster)
    gewicht = gehirn.aufmerksamkeit(x).tolist()
    erste = letzte - fenster + 1
    rangfolge = sorted(range(fenster), key=lambda j: -gewicht[j])
    chart_start = len(kerzen) - CHART_KERZEN
    fokus = []
    for j in rangfolge[:5]:
        i = erste + j
        fokus.append({
            "zeit": kerzen[i].ts.isoformat(),
            "gewicht": gewicht[j],
            "vor": letzte - i,                     # so viele Kerzen vor der jüngsten
            "form": kerzenform(kerzen[i], atr_reihe[i]),
            "chart_index": i - chart_start if i >= chart_start else None,
        })

    gehirn.eval()
    with torch.no_grad():
        basis = torch.softmax(gehirn(x), dim=-1)[0, richtung].item()
        beitraege = []
        for name, spalten in GRUPPEN.items():
            ohne = x.clone()
            for m in spalten:
                ohne[..., MERKMALE.index(m)] = 0.0
            neu = torch.softmax(gehirn(ohne), dim=-1)[0, richtung].item()
            beitraege.append({"gruppe": name, "beitrag": basis - neu})
    beitraege.sort(key=lambda b: -abs(b["beitrag"]))

    def wann(f: dict) -> str:
        if f["vor"] == 0:
            return "die jüngste Kerze"
        return "die Kerze davor" if f["vor"] == 1 else f"die Kerze {f['vor']} Kerzen zurück"

    wort = "steigt" if richtung == HOCH else "fällt"
    gruende = []
    f0 = fokus[0]
    gruende.append(f"Am stärksten achtet das Gehirn auf {wann(f0)}: {f0['form']} "
                   f"({f0['gewicht']:.0%} der Aufmerksamkeit).")
    weitere = [f for f in fokus[1:3] if f["gewicht"] > 0.05]
    if weitere:
        gruende.append("Danach auf " + " und ".join(f"{wann(f)} ({f['form']})" for f in weitere) + ".")
    tragend = [b for b in beitraege if b["beitrag"] > 0.01][:2]
    if tragend:
        gruende.append("Dass der Kurs eher " + wort + ", stützt sich vor allem auf "
                       + " und ".join(f"{b['gruppe']} ({b['beitrag'] * 100:+.0f} Prozentpunkte)"
                                      for b in tragend) + ".")
    dagegen = [b for b in beitraege if b["beitrag"] < -0.01][:1]
    if dagegen:
        b = dagegen[0]
        gruende.append(f"Dagegen spricht: {b['gruppe']} ({b['beitrag'] * 100:+.0f} Prozentpunkte).")
    if not tragend:
        gruende.append("Kein Merkmal gibt klar den Ausschlag. Die Einschätzung ist entsprechend vorsichtig.")
    return {"fokus": fokus, "merkmale": beitraege, "gruende": gruende}


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
