"""Liest Bens offene Positionen aus MetaTrader 5.

Sobald er einen Trade stellt, soll daraus ein Signal werden — in jedem
Markt, nicht nur Gold. Die Brücke merkt sich, welche Positionen sie schon
kennt, und meldet nur neue.

Mehrere Teilziele: MetaTrader kennt je Position genau ein TP. Wer mit
Teilzielen arbeitet, eröffnet dafür mehrere Positionen auf demselben
Symbol. Die Brücke fasst Positionen zusammen, die kurz nacheinander in
dieselbe Richtung aufgemacht wurden, und macht daraus ein Signal mit
TP1, TP2, TP3 — so, wie Ben es ohnehin handelt.

Die eigentliche MT5-Verbindung gibt es nur für Windows und nur bei
laufendem Terminal. Deshalb steckt sie hinter `Quelle`: `EchtesMT5`
spricht mit dem Terminal, `FakeMT5` liefert vorgegebene Positionen. So
ist alles außer der Verbindung selbst prüfbar.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from .maerkte import anzeigename, nachkommastellen, pipgroesse


@dataclass(frozen=True)
class Konto:
    """Welches Handelskonto im Terminal angemeldet ist."""
    nummer: int
    inhaber: str
    broker: str
    waehrung: str
    echt: bool

    def __str__(self) -> str:
        art = "Echtgeld" if self.echt else "Demo"
        teile = [f"Konto {self.nummer}", art]
        if self.broker:
            teile.insert(1, self.broker)
        return " · ".join(teile)


@dataclass(frozen=True)
class Position:
    ticket: int
    symbol: str
    seite: str          # "long" oder "short"
    entry: float
    sl: float
    tp: float
    volumen: float
    geoeffnet: float    # Sekunden seit 1970


class Quelle(Protocol):
    def positionen(self) -> list[Position]: ...
    def konto(self) -> Konto | None: ...


class FakeMT5:
    """Für Tests: liefert, was man hineinlegt."""

    def __init__(self, positionen: list[Position] | None = None,
                 konto: Konto | None = None) -> None:
        self.liste = list(positionen or [])
        self._konto = konto

    def positionen(self) -> list[Position]:
        return list(self.liste)

    def konto(self) -> Konto | None:
        return self._konto

    def dazu(self, *neue: Position) -> None:
        self.liste.extend(neue)

    def weg(self, ticket: int) -> None:
        self.liste = [p for p in self.liste if p.ticket != ticket]


class EchtesMT5:
    """Spricht mit dem laufenden MetaTrader-5-Terminal.

    Nur Windows, nur bei geöffnetem und angemeldetem Terminal. Das Paket
    heißt MetaTrader5 und wird mit `pip install MetaTrader5` installiert.
    """

    def __init__(self) -> None:
        try:
            import MetaTrader5 as mt5          # noqa: N813
        except ImportError as exc:             # pragma: no cover - nur Windows
            raise RuntimeError(
                "Das Paket MetaTrader5 fehlt. Es gibt es nur für Windows.\n"
                "Installieren mit:  pip install MetaTrader5") from exc
        self.mt5 = mt5
        if not mt5.initialize():               # pragma: no cover - nur Windows
            raise RuntimeError(
                "MetaTrader 5 antwortet nicht. Ist das Terminal offen und "
                f"angemeldet? ({mt5.last_error()})")

    def konto(self) -> Konto | None:           # pragma: no cover - nur Windows
        """Das Konto, das im Terminal gerade angemeldet ist.

        Der Bot sucht sich kein Konto aus — er liest das, was offen ist.
        Deshalb soll beim Start dastehen, welches das ist.
        """
        info = self.mt5.account_info()
        if info is None:
            return None
        echt = getattr(self.mt5, "ACCOUNT_TRADE_MODE_REAL", 2)
        return Konto(
            nummer=int(getattr(info, "login", 0)),
            inhaber=str(getattr(info, "name", "") or ""),
            broker=str(getattr(info, "company", "") or ""),
            waehrung=str(getattr(info, "currency", "") or ""),
            echt=getattr(info, "trade_mode", None) == echt,
        )

    def positionen(self) -> list[Position]:    # pragma: no cover - nur Windows
        roh = self.mt5.positions_get()
        if roh is None:
            return []
        raus = []
        for p in roh:
            raus.append(Position(
                ticket=int(p.ticket),
                symbol=str(p.symbol),
                seite="long" if p.type == self.mt5.POSITION_TYPE_BUY else "short",
                entry=float(p.price_open),
                sl=float(p.sl or 0.0),
                tp=float(p.tp or 0.0),
                volumen=float(p.volume),
                geoeffnet=float(p.time),
            ))
        return raus


@dataclass
class BrueckeSettings:
    an: bool = False                  # bewusst aus, bis Ben es einschaltet
    zusammen_sekunden: int = 90       # Fenster, in dem Teilziele zusammengehören
    # Ohne Rückfrage verschicken? Standard ist nein. Ein Trade, den man
    # gleich wieder schließt, waere sonst schon bei zahlenden Leuten.
    ohne_rueckfrage: bool = False
    state_file: str = "state/mt5.json"

    @staticmethod
    def from_env(env: dict[str, str] | None = None) -> "BrueckeSettings":
        import os
        e = env if env is not None else os.environ
        def ja(name: str) -> bool:
            return str(e.get(name, "")).strip().lower() in ("1", "ja", "an", "true")
        try:
            fenster = int(e.get("MT5_ZUSAMMEN", "90") or 90)
        except (TypeError, ValueError):
            fenster = 90
        return BrueckeSettings(
            an=ja("MT5"),
            zusammen_sekunden=max(0, min(600, fenster)),
            ohne_rueckfrage=ja("MT5_OHNE_RUECKFRAGE"),
            state_file=str(e.get("MT5_STATE", "state/mt5.json")).strip()
                       or "state/mt5.json",
        )


def _ziele_sortieren(seite: str, ziele: list[float]) -> list[float]:
    """Nächstes Ziel zuerst — bei long aufsteigend, bei short absteigend."""
    sauber = sorted({z for z in ziele if z > 0})
    return sauber if seite == "long" else list(reversed(sauber))


@dataclass
class Bruecke:
    """Merkt sich bekannte Tickets und meldet, was neu dazukam."""

    quelle: Quelle
    settings: BrueckeSettings = field(default_factory=BrueckeSettings)
    uhr: Callable[[], float] = None  # type: ignore[assignment]
    _bekannt: set[int] = field(default_factory=set)
    _konto: int | None = None
    # True, sobald "ohne Rueckfrage" ueber /auto gesetzt wurde. Dann gilt
    # diese Entscheidung und nicht mehr der Wert aus der .env.
    _auto_gesetzt: bool = False
    # Wird gesetzt, wenn im Terminal ein anderes Konto angemeldet wurde.
    # Der Aufrufer liest es aus und sagt Ben Bescheid.
    gewechselt: tuple[int | None, int] | None = None

    def __post_init__(self) -> None:
        if self.uhr is None:
            import time
            self.uhr = time.time
        self._laden()

    # ---- Zustand ----------------------------------------------------------
    def _pfad(self) -> Path:
        return Path(self.settings.state_file)

    def _laden(self) -> None:
        p = self._pfad()
        if not p.exists():
            return
        try:
            daten = json.loads(p.read_text(encoding="utf-8"))
            self._bekannt = {int(t) for t in daten.get("bekannt", [])}
            nummer = daten.get("konto")
            self._konto = int(nummer) if nummer else None
            if "auto" in daten:
                self.settings.ohne_rueckfrage = bool(daten["auto"])
                self._auto_gesetzt = True
        except (ValueError, OSError, TypeError):
            self._bekannt = set()
            self._konto = None

    def _sichern(self) -> None:
        p = self._pfad()
        p.parent.mkdir(parents=True, exist_ok=True)
        # Nicht ewig wachsen lassen: die jüngsten 500 reichen.
        behalten = sorted(self._bekannt)[-500:]
        self._bekannt = set(behalten)
        daten: dict[str, Any] = {"bekannt": behalten, "konto": self._konto}
        if self._auto_gesetzt:
            daten["auto"] = self.settings.ohne_rueckfrage
        tmp = p.with_suffix(p.suffix + ".neu")
        tmp.write_text(json.dumps(daten), encoding="utf-8")
        tmp.replace(p)

    # ---- Schalter ---------------------------------------------------------
    def auto_setzen(self, an: bool) -> None:
        """Signale ohne Rueckfrage verschicken — oder eben doch fragen.

        Ueber /auto vom Telefon aus, damit Ben dafuer nicht an eine Datei
        muss. Die Entscheidung ueberlebt den Neustart.
        """
        self.settings.ohne_rueckfrage = bool(an)
        self._auto_gesetzt = True
        self._sichern()

    @property
    def auto(self) -> bool:
        return bool(self.settings.ohne_rueckfrage)

    # ---- Konto ------------------------------------------------------------
    def konto(self) -> Konto | None:
        """Welches Konto im Terminal angemeldet ist, oder None."""
        holen = getattr(self.quelle, "konto", None)
        if holen is None:
            return None
        try:
            return holen()
        except Exception:        # ein fehlendes Konto darf nichts reissen
            return None

    def _konto_pruefen(self) -> bool:
        """True, wenn gerade ein anderes Konto angemeldet ist als zuletzt.

        Ohne diese Pruefung waere jede Position des neuen Kontos auf einen
        Schlag ein frisches Signal — beim Wechsel von Demo auf Echtgeld
        waeren das sofort ein Dutzend.
        """
        jetzt = self.konto()
        if jetzt is None or not jetzt.nummer:
            return False
        if self._konto == jetzt.nummer:
            return False
        vorher, self._konto = self._konto, jetzt.nummer
        if vorher is None:
            self._sichern()          # erstes Mal: nur merken
            return False
        self.gewechselt = (vorher, jetzt.nummer)
        return True

    # ---- Erster Lauf ------------------------------------------------------
    def gleichstand(self) -> int:
        """Alles, was jetzt offen ist, gilt als bekannt.

        Beim ersten Start sollen nicht alle Positionen, die ohnehin schon
        laufen, als frische Signale in die Gruppen rauschen.
        """
        jetzt = self.konto()
        if jetzt is not None and jetzt.nummer:
            self._konto = jetzt.nummer
        offen = self.quelle.positionen()
        self._bekannt |= {p.ticket for p in offen}
        self._sichern()
        return len(offen)

    # ---- Neue Trades ------------------------------------------------------
    def neue(self) -> list[dict[str, Any]]:
        """Neue Positionen als fertige Signalvorlagen.

        Positionen auf demselben Symbol, in derselben Richtung und kurz
        nacheinander geöffnet werden zu einem Signal mit mehreren Zielen
        zusammengefasst.
        """
        if self._konto_pruefen():
            # Anderes Konto: dessen laufende Positionen sind kein Signal.
            self.gleichstand()
            return []

        offen = self.quelle.positionen()
        frisch = [p for p in offen if p.ticket not in self._bekannt]
        if not frisch:
            return []

        frisch.sort(key=lambda p: (p.symbol, p.seite, p.geoeffnet))
        gruppen: list[list[Position]] = []
        for p in frisch:
            letzte = gruppen[-1][-1] if gruppen else None
            gehoert_dazu = (
                letzte is not None
                and letzte.symbol == p.symbol
                and letzte.seite == p.seite
                and abs(p.geoeffnet - letzte.geoeffnet)
                <= self.settings.zusammen_sekunden)
            if not gehoert_dazu:
                gruppen.append([])
            gruppen[-1].append(p)

        raus = []
        for teil in gruppen:
            erste = teil[0]
            stops = [p.sl for p in teil if p.sl > 0]
            ziele = _ziele_sortieren(erste.seite, [p.tp for p in teil])
            raus.append({
                "symbol": erste.symbol,
                "pair": anzeigename(erste.symbol),
                "side": erste.seite,
                "entry": sum(p.entry * p.volumen for p in teil)
                         / sum(p.volumen for p in teil),
                "sl": stops[0] if stops else 0.0,
                "ziele": ziele,
                "tp": ziele[0] if ziele else 0.0,
                "volumen": sum(p.volumen for p in teil),
                "tickets": [p.ticket for p in teil],
                "stellen": nachkommastellen(erste.symbol),
                "pip": pipgroesse(erste.symbol),
            })

        self._bekannt |= {p.ticket for p in frisch}
        self._sichern()
        return raus

    def vergessen(self, tickets: list[int]) -> None:
        """Macht ein Melden rückgängig — für den Fall, dass es schiefging."""
        self._bekannt -= {int(t) for t in tickets}
        self._sichern()
