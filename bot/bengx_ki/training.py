"""Teil 3 — Lernen.

Die Kerzen werden **in zeitlicher Reihenfolge** in drei Teile geschnitten:

    |------------- Lernen 70 % -------------|-- Prüfen 15 % --|-- Test 15 % --|

* Aus dem **Lern-Teil** lernt die KI.
* Am **Prüf-Teil** merken wir, wann sie aufhört, Neues zu lernen, und anfängt,
  auswendig zu lernen. Dann wird gestoppt und der beste Stand behalten.
* Den **Test-Teil** sieht sie erst ganz am Ende, ein einziges Mal. Nur diese
  Zahlen sagen etwas darüber, wie sie sich im echten Handel schlagen könnte.

Nie wird gemischt, und an den Schnittstellen fällt eine Lücke von `horizont`
Kerzen weg: sonst würde das Etikett der letzten Lern-Kerze schon in den
Prüf-Teil hineinschauen, und die KI hätte die Zukunft heimlich gesehen.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

import torch
from torch.nn import functional as F

from bengx_bot.model import Candle

from .gehirn import Bauplan, Gehirn
from .merkmale import KLASSEN, MERKMALE, VORLAUF, Ausgang, ausgaenge, merkmale


@dataclass
class Daten:
    tabelle: torch.Tensor        # (kerzen, merkmale), schon normiert
    stellen: list[int]           # Kerzen, zu denen es Fenster und Etikett gibt
    ausgang: dict[int, Ausgang]  # Etikett je Stelle
    zeiten: list[datetime]


def tabelle_bauen(kerzen: Sequence[Candle]) -> torch.Tensor:
    zeilen = merkmale(kerzen)
    leer = [0.0] * len(MERKMALE)
    return torch.tensor([z if z is not None else leer for z in zeilen],
                        dtype=torch.float32)


def normieren(tabelle: torch.Tensor, mittel: torch.Tensor,
              streuung: torch.Tensor) -> torch.Tensor:
    # Jede Spalte auf Mittelwert 0 und Streuung 1, Ausreißer bei ±5 gekappt.
    return ((tabelle - mittel) / streuung).clamp(-5.0, 5.0)


def fenster_holen(tabelle: torch.Tensor, stellen: Sequence[int],
                  fenster: int) -> torch.Tensor:
    """Für jede Stelle die letzten `fenster` Kerzen bis einschließlich ihr."""
    idx = torch.tensor(stellen).unsqueeze(1) + torch.arange(-fenster + 1, 1)
    return tabelle[idx]


def erste_stelle(fenster: int) -> int:
    return VORLAUF + fenster - 1


def wahrscheinlichkeiten(gehirn: Gehirn, tabelle: torch.Tensor,
                         stellen: Sequence[int], stapel: int = 512) -> torch.Tensor:
    gehirn.eval()
    teile = []
    with torch.no_grad():
        for a in range(0, len(stellen), stapel):
            x = fenster_holen(tabelle, stellen[a:a + stapel], gehirn.plan.fenster)
            teile.append(F.softmax(gehirn(x), dim=-1))
    return torch.cat(teile) if teile else torch.empty(0, len(KLASSEN))


@dataclass
class Einstellungen:
    horizont: int = 24          # so viele Kerzen hat ein Trade Zeit
    abstand_atr: float = 1.5    # Stop und Ziel, in ATR
    epochen: int = 30
    stapel: int = 128           # so viele Beispiele pro Lernschritt
    lernrate: float = 3e-4
    geduld: int = 5             # so viele Epochen ohne Besserung, dann Schluss
    zufall: int = 1


def trainieren(kerzen: Sequence[Candle], plan: Bauplan, e: Einstellungen,
               melden: Callable[[str], None] = print) -> dict:
    """Lernt ein Gehirn und gibt alles zurück, was zum Speichern nötig ist."""
    random.seed(e.zufall)
    torch.manual_seed(e.zufall)

    roh = tabelle_bauen(kerzen)
    etiketten = ausgaenge(kerzen, e.horizont, e.abstand_atr)
    stellen = [i for i in range(erste_stelle(plan.fenster), len(kerzen))
               if etiketten[i] is not None]
    if len(stellen) < 500:
        raise ValueError(
            f"Zu wenig Kerzen: {len(stellen)} nutzbare Beispiele, mindestens 500 "
            f"nötig (also gut {500 + erste_stelle(plan.fenster) + e.horizont} Kerzen)."
        )

    n = len(stellen)
    a, b = int(n * 0.70), int(n * 0.85)
    lern = stellen[:a - e.horizont]
    pruef = stellen[a:b - e.horizont]
    test = stellen[b:]

    # Mittelwert und Streuung NUR aus dem Lern-Teil: auch das wäre sonst ein
    # Blick in die Zukunft.
    lern_zeilen = roh[VORLAUF:lern[-1] + 1]
    mittel = lern_zeilen.mean(dim=0)
    streuung = lern_zeilen.std(dim=0).clamp_min(1e-6)
    tabelle = normieren(roh, mittel, streuung)

    ziel = {i: etiketten[i].klasse for i in stellen}
    zaehler = torch.bincount(torch.tensor([ziel[i] for i in lern]),
                             minlength=len(KLASSEN)).float()
    # Seltene Antworten zählen beim Lernen mehr, sonst sagt die KI immer nur
    # die häufigste. Aber höchstens doppelt: eine Antwort, die fast nie
    # vorkommt, würde sonst mit riesigem Gewicht alles andere übertönen.
    gewicht = (zaehler.sum() / (len(KLASSEN) * zaehler.clamp_min(1))).clamp(0.5, 2.0)

    gehirn = Gehirn(plan)
    optimierer = torch.optim.AdamW(gehirn.parameters(), lr=e.lernrate,
                                   weight_decay=0.05)
    melden(f"Gehirn mit {gehirn.anzahl_gewichte():,} Gewichten".replace(",", "."))
    melden(f"Beispiele: {len(lern)} lernen · {len(pruef)} prüfen · {len(test)} testen")
    melden("Verteilung im Lern-Teil: " + ", ".join(
        f"{KLASSEN[k]} {zaehler[k] / zaehler.sum():.0%}" for k in range(len(KLASSEN))))

    def verlust(teil: Sequence[int]) -> float:
        gehirn.eval()
        summe = 0.0
        with torch.no_grad():
            for s in range(0, len(teil), 512):
                stueck = teil[s:s + 512]
                x = fenster_holen(tabelle, stueck, plan.fenster)
                y = torch.tensor([ziel[i] for i in stueck])
                summe += F.cross_entropy(gehirn(x), y, weight=gewicht,
                                         reduction="sum").item()
        return summe / len(teil)

    bester = (float("inf"), None, 0)
    ohne_besserung = 0
    for epoche in range(1, e.epochen + 1):
        start = time.time()
        gehirn.train()
        reihe = lern[:]
        random.shuffle(reihe)              # innerhalb des Lern-Teils ist das erlaubt
        summe = 0.0
        for s in range(0, len(reihe), e.stapel):
            stueck = reihe[s:s + e.stapel]
            x = fenster_holen(tabelle, stueck, plan.fenster)
            y = torch.tensor([ziel[i] for i in stueck])
            fehler = F.cross_entropy(gehirn(x), y, weight=gewicht)
            optimierer.zero_grad()
            fehler.backward()              # wer war wie schuld am Fehler?
            torch.nn.utils.clip_grad_norm_(gehirn.parameters(), 1.0)
            optimierer.step()              # alle Gewichte ein kleines Stück korrigieren
            summe += fehler.item() * len(stueck)
        lern_v = summe / len(reihe)
        pruef_v = verlust(pruef)
        besser = pruef_v < bester[0] - 1e-4
        if besser:
            bester = (pruef_v, {k: v.clone() for k, v in gehirn.state_dict().items()}, epoche)
            ohne_besserung = 0
        else:
            ohne_besserung += 1
        melden(f"Epoche {epoche:>2}: Fehler lernen {lern_v:.4f} · prüfen {pruef_v:.4f}"
               f"{'  ← bester Stand' if besser else ''}  ({time.time() - start:.0f}s)")
        if ohne_besserung >= e.geduld:
            melden(f"Seit {e.geduld} Epochen keine Besserung — Schluss, "
                   f"zurück zum Stand aus Epoche {bester[2]}.")
            break

    gehirn.load_state_dict(bester[1])
    return {
        "plan": plan.als_dict(),
        "gewichte": gehirn.state_dict(),
        "mittel": mittel.tolist(),
        "streuung": streuung.tolist(),
        "merkmale": list(MERKMALE),
        "horizont": e.horizont,
        "abstand_atr": e.abstand_atr,
        "erstellt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "beste_epoche": bester[2],
        "test_ab": kerzen[test[0]].ts.isoformat(),
        "_test": test,
        "_daten": Daten(tabelle, stellen, {i: etiketten[i] for i in stellen},
                        [k.ts for k in kerzen]),
        "_gehirn": gehirn,
    }


def speichern(paket: dict, pfad: str | Path) -> Path:
    p = Path(pfad)
    p.parent.mkdir(parents=True, exist_ok=True)
    torch.save({k: v for k, v in paket.items() if not k.startswith("_")}, p)
    return p


def laden(pfad: str | Path) -> tuple[Gehirn, dict]:
    p = Path(pfad)
    if not p.exists():
        raise FileNotFoundError(f"Kein Modell unter {p}. Erst trainieren.")
    paket = torch.load(p, map_location="cpu", weights_only=True)
    gehirn = Gehirn(Bauplan(**paket["plan"]))
    gehirn.load_state_dict(paket["gewichte"])
    gehirn.eval()
    return gehirn, paket


def daten_fuer(kerzen: Sequence[Candle], paket: dict) -> Daten:
    """Kerzen so aufbereiten, wie das gespeicherte Gehirn sie gelernt hat."""
    tabelle = normieren(tabelle_bauen(kerzen), torch.tensor(paket["mittel"]),
                        torch.tensor(paket["streuung"]))
    etiketten = ausgaenge(kerzen, paket["horizont"], paket["abstand_atr"])
    stellen = [i for i in range(erste_stelle(paket["plan"]["fenster"]), len(kerzen))
               if etiketten[i] is not None]
    return Daten(tabelle, stellen, {i: etiketten[i] for i in stellen},
                 [k.ts for k in kerzen])
