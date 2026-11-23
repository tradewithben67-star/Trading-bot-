"""Erfundene Kurse mit einem versteckten Muster — zum Prüfen, ob die KI lernt.

Die Kurse sind ein Zufallspfad. Ab und zu erscheint aber eine besondere Kerze:

* ein **Hammer** (langer Docht unten, Schluss oben) — danach steigt der Kurs
  ein paar Stunden lang leicht an
* eine **Sternschnuppe** (langer Docht oben, Schluss unten) — danach fällt er

Der KI wird das nicht verraten. Findet sie das Muster, schlägt sie im Test
das Raten deutlich. Auf reinem Zufall (`muster=False`) darf sie das nicht —
tut sie es trotzdem, hat sie irgendwo heimlich in die Zukunft geschaut.

Das sind ausdrücklich KEINE echten Kurse.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from bengx_bot.model import Candle


def kerzen(anzahl: int = 12000, muster: bool = True, zufall: int = 3) -> list[Candle]:
    rng = random.Random(zufall)
    t = datetime(2020, 1, 1, tzinfo=timezone.utc)
    preis = 2000.0
    schub, rest = 0.0, 0
    raus: list[Candle] = []
    for _ in range(anzahl):
        streuung = 2.0
        o = preis
        besonders = muster and rest == 0 and rng.random() < 0.04
        if besonders:
            richtung = rng.choice((1, -1))
            koerper = abs(rng.gauss(0, 0.6)) * richtung
            c = o + koerper
            lang = rng.uniform(5, 8)                 # der lange Docht
            kurz = rng.uniform(0, 0.4)
            if richtung > 0:                         # Hammer
                h, l = max(o, c) + kurz, min(o, c) - lang
            else:                                    # Sternschnuppe
                h, l = max(o, c) + lang, min(o, c) - kurz
            schub, rest = 0.7 * richtung, 15
        else:
            bewegung = rng.gauss(schub if rest else 0.0, streuung)
            c = o + bewegung
            h = max(o, c) + abs(rng.gauss(0, streuung * 0.6))
            l = min(o, c) - abs(rng.gauss(0, streuung * 0.6))
            if rest:
                rest -= 1
        raus.append(Candle(ts=t, open=round(o, 2), high=round(h, 2), low=round(l, 2),
                           close=round(c, 2), volume=round(rng.uniform(500, 5000))))
        preis = c
        t += timedelta(hours=1)
    return raus
