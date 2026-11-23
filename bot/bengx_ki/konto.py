"""Nutzung und Abos: jedes Modell hat sein eigenes Monatskontingent.

* Jede Aktion verbraucht Tokens: Grundkosten × Faktor des Modells
  (Mini 1, Standard 3, Max 10). Eine Analyse mit Max kostet also zehnmal so
  viel wie mit Mini.
* Das Abo legt **pro Modell** fest, wie viele Tokens im Monat zur Verfügung
  stehen. Ist das Kontingent eines Modells aufgebraucht, hört genau dieses
  Modell auf, bis zum Monatsersten. Die anderen laufen weiter.
* Steht bei einem Modell 0, ist es in diesem Abo gesperrt.
* Der **Inhaber** hat keine Grenzen. Seine Nutzung wird trotzdem gezählt,
  damit er sie sehen kann.
* Indikatoren brauchen kein Modell und kosten nichts. Trainieren darf nur der
  Inhaber.

Mengen, Kosten und Preise stehen hier oben und lassen sich frei ändern.
Bezahlung gibt es noch nicht: Abos vergibt der Inhaber.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from .modelle import MODELLE, pruefe

# Tokens im Monat je Modell. None = unbegrenzt, 0 = gesperrt.
ABOS: dict[str, dict] = {
    "start": {"name": "Start", "preis": None,
              "text": "Zum Kennenlernen.",
              "limits": {"mini": 100, "standard": 30, "max": 0}},
    "pro": {"name": "Pro", "preis": None,
            "text": "Für aktiven Handel, mit Zugang zu Max.",
            "limits": {"mini": 1000, "standard": 600, "max": 200}},
    "elite": {"name": "Elite", "preis": None,
              "text": "Mini ohne Grenze, viel Max.",
              "limits": {"mini": None, "standard": 3000, "max": 1000}},
}
INHABER_ABO = {"name": "Inhaber", "preis": None, "text": "Keine Grenzen.",
               "limits": {m: None for m in MODELLE}}

KOSTEN: dict[str, int] = {"analyse": 1, "strategie": 5}
AKTIONEN = {"analyse": "KI-Analyse", "strategie": "Strategie-Test"}


def kosten(aktion: str, modell: str) -> int:
    return KOSTEN[aktion] * MODELLE[pruefe(modell)]["faktor"]


def _jetzt() -> datetime:
    return datetime.now(timezone.utc)


def naechster_monat(t: datetime) -> str:
    return datetime(t.year + (t.month == 12), t.month % 12 + 1, 1).date().isoformat()


class Grenze(Exception):
    """Diese Nutzung ist nicht (mehr) erlaubt."""

    def __init__(self, text: str, modell: str) -> None:
        super().__init__(text)
        self.modell = modell


def abo_von(nutzer: dict) -> dict:
    if nutzer.get("rolle") == "inhaber":
        return INHABER_ABO
    return ABOS.get(nutzer.get("abo", "start"), ABOS["start"])


class Nutzung:
    def __init__(self, pfad: str | Path, uhr=_jetzt) -> None:
        self.pfad = Path(pfad)
        self._uhr = uhr
        self._sperre = threading.Lock()
        self._d: dict = (json.loads(self.pfad.read_text(encoding="utf-8"))
                         if self.pfad.exists() else {})

    def _sichern(self) -> None:
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.pfad.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._d, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.pfad)

    def _eintrag(self, nid: str) -> dict:
        monat = self._uhr().strftime("%Y-%m")
        e = self._d.setdefault(nid, {"monat": monat, "verbraucht": {}, "buchungen": []})
        if e["monat"] != monat:                     # neuer Monat: alles wieder frei
            e["monat"], e["verbraucht"] = monat, {}
        return e

    def _modelle(self, nutzer: dict, e: dict) -> dict:
        limits = abo_von(nutzer)["limits"]
        raus = {}
        for m, info in MODELLE.items():
            limit = limits.get(m, 0)
            verbraucht = e["verbraucht"].get(m, 0)
            raus[m] = {
                "name": info["name"], "faktor": info["faktor"],
                "limit": limit, "verbraucht": verbraucht,
                "rest": None if limit is None else max(0, limit - verbraucht),
                "gesperrt": limit == 0,
            }
        return raus

    def stand(self, nutzer: dict) -> dict:
        with self._sperre:
            e = self._eintrag(nutzer["id"])
            abo = abo_von(nutzer)
            return {
                "abo": "inhaber" if nutzer.get("rolle") == "inhaber" else nutzer.get("abo"),
                "abo_name": abo["name"],
                "unbegrenzt": nutzer.get("rolle") == "inhaber",
                "modelle": self._modelle(nutzer, e),
                "auffuellung": naechster_monat(self._uhr()),
                "kosten": {a: {m: kosten(a, m) for m in MODELLE} for a in KOSTEN},
                "aktionen": AKTIONEN,
                "abos": ABOS,
            }

    def abbuchen(self, nutzer: dict, modell: str, aktion: str) -> int:
        k = kosten(aktion, modell)
        with self._sperre:
            e = self._eintrag(nutzer["id"])
            m = self._modelle(nutzer, e)[modell]
            if m["gesperrt"]:
                raise Grenze(f"{m['name']} ist im Abo {abo_von(nutzer)['name']} nicht "
                             "enthalten.", modell)
            if m["rest"] is not None and m["rest"] < k:
                tag = datetime.fromisoformat(naechster_monat(self._uhr())).strftime("%d.%m.%Y")
                raise Grenze(f"Limit für {m['name']} erreicht ({m['verbraucht']} von "
                             f"{m['limit']} Tokens). Wieder frei am {tag}.", modell)
            e["verbraucht"][modell] = m["verbraucht"] + k
            self._buchen(e, -k, f"{AKTIONEN[aktion]} · {m['name']}")
            self._sichern()
            return k

    def erstatten(self, nutzer: dict, modell: str, aktion: str, grund: str) -> None:
        k = kosten(aktion, modell)
        with self._sperre:
            e = self._eintrag(nutzer["id"])
            e["verbraucht"][modell] = max(0, e["verbraucht"].get(modell, 0) - k)
            self._buchen(e, k, f"Erstattung · {MODELLE[modell]['name']}: {grund}")
            self._sichern()

    def _buchen(self, e: dict, menge: int, text: str) -> None:
        e["buchungen"].append({"zeit": self._uhr().isoformat(timespec="seconds"),
                               "menge": menge, "text": text})
        del e["buchungen"][:-1000]

    def buchungen(self, nid: str, anzahl: int = 300) -> list[dict]:
        with self._sperre:
            return list(reversed(self._d.get(nid, {}).get("buchungen", [])[-anzahl:]))

    def vergessen(self, nid: str) -> None:
        with self._sperre:
            if self._d.pop(nid, None) is not None:
                self._sichern()
