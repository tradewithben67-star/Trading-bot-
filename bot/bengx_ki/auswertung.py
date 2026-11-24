"""Teil 4 — ehrlich prüfen.

Zwei Fragen, beide nur auf Kerzen, die die KI beim Lernen nie gesehen hat:

1. **Trifft sie besser als Raten?** Verglichen wird mit dem dümmsten möglichen
   Gegner: immer die Antwort zu geben, die im Lern-Teil am häufigsten war.
2. **Würde ihr Handel Geld verdienen?** Sie handelt nur, wenn sie sich sicher
   genug ist (`schwelle`), immer nur eine Position zur Zeit, mit Stop und Ziel
   im gleichen Abstand. Verglichen wird mit „bei jeder freien Kerze kaufen“.

Alle Ergebnisse in R: +1 R ist ein Gewinn in Höhe des Risikos, −1 R ein Stop.
Gebühren und Spread sind NICHT eingerechnet — real wird es also schlechter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import torch

from .merkmale import HOCH, KLASSEN, RUNTER, Ausgang


@dataclass
class Bilanz:
    trades: int = 0
    gewinner: int = 0
    summe_r: float = 0.0
    tiefster_einbruch_r: float = 0.0

    @property
    def trefferquote(self) -> float:
        return self.gewinner / self.trades if self.trades else 0.0

    @property
    def schnitt_r(self) -> float:
        return self.summe_r / self.trades if self.trades else 0.0

    def zeile(self) -> str:
        if not self.trades:
            return "keine Trades"
        return (f"{self.trades:>5} Trades · Treffer {self.trefferquote:5.1%} · "
                f"Summe {self.summe_r:+8.1f} R · je Trade {self.schnitt_r:+.3f} R · "
                f"tiefster Einbruch {self.tiefster_einbruch_r:.1f} R")


def _handeln(stellen: Sequence[int], ausgang: dict[int, Ausgang],
             entscheide) -> Bilanz:
    b = Bilanz()
    frei_ab = -1
    stand = spitze = 0.0
    for n, i in enumerate(stellen):
        if i < frei_ab:
            continue                       # noch im laufenden Trade
        richtung = entscheide(n)
        if richtung is None:
            continue
        a = ausgang[i]
        r = a.r_long if richtung == HOCH else a.r_short
        b.trades += 1
        b.gewinner += r > 0
        b.summe_r += r
        stand += r
        spitze = max(spitze, stand)
        b.tiefster_einbruch_r = min(b.tiefster_einbruch_r, stand - spitze)
        frei_ab = i + a.dauer + 1
    return b


def handel_ki(stellen: Sequence[int], ausgang: dict[int, Ausgang],
              p: torch.Tensor, schwelle: float) -> Bilanz:
    def entscheide(n: int):
        hoch, runter = p[n, HOCH].item(), p[n, RUNTER].item()
        if hoch >= schwelle and hoch > runter:
            return HOCH
        if runter >= schwelle and runter > hoch:
            return RUNTER
        return None
    return _handeln(stellen, ausgang, entscheide)


def handel_immer_long(stellen: Sequence[int], ausgang: dict[int, Ausgang]) -> Bilanz:
    return _handeln(stellen, ausgang, lambda n: HOCH)


def bericht(stellen: Sequence[int], ausgang: dict[int, Ausgang], p: torch.Tensor,
            schwellen: Sequence[float] = (0.40, 0.50, 0.60, 0.70, 0.80)) -> str:
    wahr = torch.tensor([ausgang[i].klasse for i in stellen])
    tipp = p.argmax(dim=1)
    treffer = (tipp == wahr).float().mean().item()
    haeufigste = torch.bincount(wahr, minlength=len(KLASSEN)).argmax().item()
    raten = (wahr == haeufigste).float().mean().item()

    zeilen = [
        f"Getestet auf {len(stellen)} Kerzen, die die KI nie gesehen hat.",
        "",
        "1) Trifft sie besser als Raten?",
        f"   KI:                          {treffer:.1%} richtig",
        f"   immer „{KLASSEN[haeufigste]}“ sagen:   {raten:.1%} richtig",
        "",
        "   Wenn die KI sagt …    stimmt es    (sagt es so oft)",
    ]
    for k in range(len(KLASSEN)):
        gesagt = tipp == k
        anteil = (wahr[gesagt] == k).float().mean().item() if gesagt.any() else 0.0
        zeilen.append(f"   {KLASSEN[k]:<12}          {anteil:6.1%}      ({int(gesagt.sum())}×)")

    zeilen += ["", "2) Würde ihr Handel Geld verdienen?  (ohne Gebühren und Spread)"]
    for s in schwellen:
        zeilen.append(f"   KI ab {s:.0%} Sicherheit: {handel_ki(stellen, ausgang, p, s).zeile()}")
    zeilen.append(f"   Vergleich, immer kaufen: {handel_immer_long(stellen, ausgang).zeile()}")
    return "\n".join(zeilen)


def kennzahlen(stellen: Sequence[int], ausgang: dict[int, Ausgang], p: torch.Tensor,
               schwellen: Sequence[float] = (0.40, 0.50, 0.60, 0.70, 0.80)) -> dict:
    """Dasselbe wie `bericht`, aber als Daten für die Oberfläche."""
    wahr = torch.tensor([ausgang[i].klasse for i in stellen])
    tipp = p.argmax(dim=1)
    haeufigste = torch.bincount(wahr, minlength=len(KLASSEN)).argmax().item()

    def bilanz(b: Bilanz) -> dict:
        return {"trades": b.trades, "treffer": b.trefferquote, "summe_r": b.summe_r,
                "schnitt_r": b.schnitt_r, "einbruch_r": b.tiefster_einbruch_r}

    klassen = []
    for k in range(len(KLASSEN)):
        gesagt = tipp == k
        klassen.append({
            "name": KLASSEN[k],
            "gesagt": int(gesagt.sum()),
            "stimmt": (wahr[gesagt] == k).float().mean().item() if gesagt.any() else None,
        })
    return {
        "kerzen": len(stellen),
        "treffer": (tipp == wahr).float().mean().item(),
        "raten": (wahr == haeufigste).float().mean().item(),
        "raten_klasse": KLASSEN[haeufigste],
        "klassen": klassen,
        "schwellen": [{"schwelle": s, **bilanz(handel_ki(stellen, ausgang, p, s))}
                      for s in schwellen],
        "immer_kaufen": bilanz(handel_immer_long(stellen, ausgang)),
    }
