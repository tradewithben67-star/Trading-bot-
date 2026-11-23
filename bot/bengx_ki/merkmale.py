"""Teil 1 — Kerzen in Zahlen übersetzen, die das Gehirn versteht.

Ein neuronales Netz kann mit „Gold steht bei 4210“ nichts anfangen: der Preis
selbst sagt nichts, er hängt vom Jahr ab. Deshalb beschreibt jede Kerze sich
hier nur durch Verhältnisse, gemessen an der eigenen Schwankung (ATR):

* wie weit der Schluss gelaufen ist
* wie groß Körper und Dochte sind
* wie weit der Kurs vom Durchschnitt (EMA 50) entfernt ist
* wie unruhig der Markt gerade ist, und wie viel gehandelt wird
* welche Stunde und welcher Wochentag es ist

Dazu kommt die **Antwort**, die die KI lernen soll (das „Etikett“): wird vom
Schluss dieser Kerze aus zuerst das Ziel oben oder der Stop unten erreicht?
Beide liegen `abstand_atr` × ATR entfernt. Wird innerhalb von `horizont`
Kerzen keins von beiden erreicht, heißt die Antwort „seitwärts“.

Wichtig: Die Merkmale einer Kerze benutzen nur diese Kerze und ältere. Nur das
Etikett schaut nach vorn — es ist ja genau das, was die KI vorhersagen soll.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from bengx_bot.indicators import atr, ema
from bengx_bot.model import Candle

MERKMALE = (
    "rendite", "koerper", "docht_oben", "docht_unten", "spanne",
    "abstand_ema", "unruhe", "volumen",
    "stunde_sin", "stunde_cos", "tag_sin", "tag_cos",
)

RUNTER, SEITWAERTS, HOCH = 0, 1, 2
KLASSEN = ("runter", "seitwärts", "hoch")

VORLAUF = 120          # so viele Kerzen braucht es, bis ATR und EMA tragen


def merkmale(kerzen: Sequence[Candle]) -> list[list[float] | None]:
    """Für jede Kerze eine Zeile Zahlen — `None`, solange der Vorlauf fehlt."""
    hochs = [k.high for k in kerzen]
    tiefs = [k.low for k in kerzen]
    schluesse = [k.close for k in kerzen]
    a = atr(hochs, tiefs, schluesse, 14)
    e = ema(schluesse, 50)

    zeilen: list[list[float] | None] = []
    for i, k in enumerate(kerzen):
        if i < VORLAUF or not a[i] or e[i] is None:
            zeilen.append(None)
            continue
        s = a[i]
        davor = kerzen[i - 1].close
        # Unruhe: ist die ATR gerade höher oder tiefer als vor 50 Kerzen?
        alt = a[i - 50] or s
        vol = [kerzen[j].volume for j in range(i - 20, i)]
        vol_mittel = sum(vol) / len(vol)
        stunde = k.ts.hour + k.ts.minute / 60
        tag = k.ts.weekday()
        zeilen.append([
            (k.close - davor) / s,
            (k.close - k.open) / s,
            (k.high - max(k.open, k.close)) / s,
            (min(k.open, k.close) - k.low) / s,
            (k.high - k.low) / s,
            (k.close - e[i]) / s,
            math.log(s / alt),
            math.log((k.volume + 1) / (vol_mittel + 1)),
            math.sin(2 * math.pi * stunde / 24),
            math.cos(2 * math.pi * stunde / 24),
            math.sin(2 * math.pi * tag / 7),
            math.cos(2 * math.pi * tag / 7),
        ])
    return zeilen


@dataclass(frozen=True, slots=True)
class Ausgang:
    """Was ab dieser Kerze tatsächlich passiert ist."""

    klasse: int          # RUNTER, SEITWAERTS oder HOCH
    r_long: float        # Ergebnis eines Kaufs zum Schluss, in R
    r_short: float       # Ergebnis eines Verkaufs zum Schluss, in R
    dauer: int           # nach so vielen Kerzen war der Trade vorbei


def ausgaenge(kerzen: Sequence[Candle], horizont: int,
              abstand_atr: float) -> list[Ausgang | None]:
    """Das Etikett für jede Kerze — `None`, wo die Zukunft fehlt.

    Stop und Ziel liegen gleich weit weg, ein Treffer ist also +1 R, ein
    Stop −1 R. Berühren beide in derselben Kerze, ist unklar, was zuerst kam;
    dann zählt es vorsichtig als Stop für beide Richtungen.
    """
    hochs = [k.high for k in kerzen]
    tiefs = [k.low for k in kerzen]
    schluesse = [k.close for k in kerzen]
    a = atr(hochs, tiefs, schluesse, 14)

    raus: list[Ausgang | None] = []
    n = len(kerzen)
    for i in range(n):
        if not a[i] or i + horizont >= n:
            raus.append(None)
            continue
        einstieg = schluesse[i]
        weg = abstand_atr * a[i]
        oben, unten = einstieg + weg, einstieg - weg
        ergebnis = None
        for j in range(i + 1, i + horizont + 1):
            trifft_oben = hochs[j] >= oben
            trifft_unten = tiefs[j] <= unten
            if trifft_oben and trifft_unten:
                ergebnis = Ausgang(SEITWAERTS, -1.0, -1.0, j - i)
            elif trifft_oben:
                ergebnis = Ausgang(HOCH, 1.0, -1.0, j - i)
            elif trifft_unten:
                ergebnis = Ausgang(RUNTER, -1.0, 1.0, j - i)
            if ergebnis:
                break
        if ergebnis is None:
            bewegung = (schluesse[i + horizont] - einstieg) / weg
            ergebnis = Ausgang(SEITWAERTS, bewegung, -bewegung, horizont)
        raus.append(ergebnis)
    return raus
