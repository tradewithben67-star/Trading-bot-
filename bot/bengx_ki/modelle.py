"""Die Modellfamilie: drei Gehirne unterschiedlicher Größe.

Alle drei sind derselbe Transformer aus `gehirn.py`, nur verschieden groß:
mehr Kerzen im Blick, breitere Vektoren, mehr Blöcke. Ein größeres Gehirn kann
feinere und längere Muster erfassen, braucht aber mehr Daten und Rechenzeit —
und auf zu wenig Daten lernt es eher auswendig. Ob Max auf deinen Kursen
wirklich besser ist, zeigt nur der Strategie-Test.

`faktor` sagt, wie viel eine Nutzung im Vergleich zu Mini verbraucht.
Diese Datei braucht kein PyTorch, damit Nutzung und Abos auch ohne laufen.
"""

from __future__ import annotations

MODELLE: dict[str, dict] = {
    "mini": {
        "name": "Mini",
        "text": "Schnell und sparsam. Sieht 32 Kerzen, erkennt einfache Muster.",
        "plan": {"fenster": 32, "breite": 32, "koepfe": 2, "schichten": 2},
        "faktor": 1,
    },
    "standard": {
        "name": "Standard",
        "text": "Ausgewogen. Sieht 64 Kerzen, für den Alltag.",
        "plan": {"fenster": 64, "breite": 64, "koepfe": 4, "schichten": 3},
        "faktor": 3,
    },
    "max": {
        "name": "Max",
        "text": "Am stärksten. Sieht 128 Kerzen, erfasst längere Zusammenhänge.",
        "plan": {"fenster": 128, "breite": 96, "koepfe": 6, "schichten": 4},
        "faktor": 10,
    },
}

STANDARD = "standard"


def pruefe(modell: str) -> str:
    if modell not in MODELLE:
        raise ValueError(f"Unbekanntes Modell: {modell}. Möglich: {', '.join(MODELLE)}")
    return modell
