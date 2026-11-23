"""Tokens und Abos.

Jede Aktion der KI kostet Tokens. Es gibt zwei Töpfe:

* **Abo-Guthaben** — wird zu jedem Monatsbeginn auf die Menge des Abos
  zurückgesetzt. Was übrig bleibt, verfällt.
* **Extra-Guthaben** — aufgeladene Tokens. Sie verfallen nicht.

Abgebucht wird zuerst vom Abo, dann vom Extra. Jede Bewegung steht als
Buchung im Konto, nichts verschwindet stillschweigend.

Bezahlung gibt es noch nicht: Abos wechseln und Aufladen geht nur über den
Inhaber (Oberfläche auf dem eigenen Rechner oder `python -m bengx_ki tokens`).
Preise stehen in `ABOS` und sind bewusst noch leer.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

ABOS: dict[str, dict] = {
    "start": {"name": "Start", "tokens_monat": 200, "preis": None,
              "text": "Zum Kennenlernen: tägliche Analysen und Indikatoren."},
    "pro": {"name": "Pro", "tokens_monat": 2000, "preis": None,
            "text": "Für aktiven Handel: Analysen, Strategie-Tests, Training."},
    "elite": {"name": "Elite", "tokens_monat": 10000, "preis": None,
              "text": "Ohne Grenzen im Alltag: regelmäßig neu trainieren."},
}

KOSTEN: dict[str, int] = {
    "indikatoren": 1,
    "analyse": 5,
    "strategie": 10,
    "training": 50,
}

AKTIONEN = {
    "indikatoren": "Indikatoren lesen",
    "analyse": "KI-Analyse",
    "strategie": "Strategie testen",
    "training": "KI neu trainieren",
}


class ZuWenigTokens(Exception):
    def __init__(self, noetig: int, vorhanden: int) -> None:
        super().__init__(f"Zu wenig Tokens: {noetig} nötig, {vorhanden} vorhanden.")
        self.noetig = noetig
        self.vorhanden = vorhanden


def _jetzt() -> datetime:
    return datetime.now(timezone.utc)


def _monat(t: datetime) -> str:
    return t.strftime("%Y-%m")


class Konto:
    def __init__(self, pfad: str | Path, uhr=_jetzt) -> None:
        self.pfad = Path(pfad)
        self._uhr = uhr
        self._sperre = threading.Lock()
        if self.pfad.exists():
            self._d = json.loads(self.pfad.read_text(encoding="utf-8"))
        else:
            self._d = {"abo": "start", "monat": "", "abo_rest": 0, "extra": 0,
                       "buchungen": []}
        with self._sperre:
            self._monat_pruefen()
            self._sichern()

    # -- intern ---------------------------------------------------------

    def _sichern(self) -> None:
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.pfad.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._d, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.pfad)

    def _buchen(self, art: str, menge: int, text: str) -> dict:
        b = {"zeit": self._uhr().isoformat(timespec="seconds"), "art": art,
             "menge": menge, "text": text, "stand": self._gesamt()}
        self._d["buchungen"].append(b)
        return b

    def _gesamt(self) -> int:
        return self._d["abo_rest"] + self._d["extra"]

    def _monat_pruefen(self) -> None:
        m = _monat(self._uhr())
        if self._d["monat"] != m:
            self._d["monat"] = m
            self._d["abo_rest"] = ABOS[self._d["abo"]]["tokens_monat"]
            self._buchen("monat", self._d["abo_rest"],
                         f"Monatsguthaben {ABOS[self._d['abo']]['name']}")

    # -- öffentlich -----------------------------------------------------

    def stand(self) -> dict:
        with self._sperre:
            self._monat_pruefen()
            abo = ABOS[self._d["abo"]]
            jetzt = self._uhr()
            naechster = (datetime(jetzt.year + (jetzt.month == 12),
                                  jetzt.month % 12 + 1, 1, tzinfo=timezone.utc))
            return {
                "abo": self._d["abo"],
                "abo_name": abo["name"],
                "abo_monat": abo["tokens_monat"],
                "abo_rest": self._d["abo_rest"],
                "extra": self._d["extra"],
                "gesamt": self._gesamt(),
                "auffuellung": naechster.date().isoformat(),
                "kosten": KOSTEN,
                "aktionen": AKTIONEN,
                "abos": ABOS,
            }

    def buchungen(self, anzahl: int = 300) -> list[dict]:
        with self._sperre:
            return list(reversed(self._d["buchungen"][-anzahl:]))

    def abbuchen(self, aktion: str) -> dict:
        kosten = KOSTEN[aktion]
        with self._sperre:
            self._monat_pruefen()
            if self._gesamt() < kosten:
                raise ZuWenigTokens(kosten, self._gesamt())
            vom_abo = min(kosten, self._d["abo_rest"])
            self._d["abo_rest"] -= vom_abo
            self._d["extra"] -= kosten - vom_abo
            b = self._buchen("verbrauch", -kosten, AKTIONEN[aktion])
            self._sichern()
            return b

    def erstatten(self, aktion: str, grund: str) -> dict:
        """Zurück aufs Extra-Guthaben, wenn eine bezahlte Aktion scheitert."""
        with self._sperre:
            self._d["extra"] += KOSTEN[aktion]
            b = self._buchen("erstattung", KOSTEN[aktion], f"Erstattung: {grund}")
            self._sichern()
            return b

    def aufladen(self, menge: int, text: str = "Aufgeladen") -> dict:
        if menge <= 0 or menge > 1_000_000:
            raise ValueError("Menge muss zwischen 1 und 1.000.000 liegen.")
        with self._sperre:
            self._d["extra"] += menge
            b = self._buchen("aufladung", menge, text)
            self._sichern()
            return b

    def abo_wechseln(self, abo: str) -> dict:
        if abo not in ABOS:
            raise ValueError(f"Unbekanntes Abo: {abo}. Möglich: {', '.join(ABOS)}")
        with self._sperre:
            if abo != self._d["abo"]:
                self._d["abo"] = abo
                # Der neue Monatstopf gilt sofort, der alte verfällt.
                self._d["abo_rest"] = ABOS[abo]["tokens_monat"]
                self._buchen("abo", ABOS[abo]["tokens_monat"],
                             f"Abo gewechselt zu {ABOS[abo]['name']}")
                self._sichern()
        return self.stand()
