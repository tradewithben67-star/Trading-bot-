"""Ein MetaTrader 5 aus Pappe.

Das echte Paket gibt es nur für Windows. Damit der Anschluss trotzdem geprüft
werden kann — Lots, Zeitversatz, Abgleich, abgelehnte Order, Demo-Erkennung —
steht hier eine Attrappe mit derselben Oberfläche: dieselben Funktionsnamen,
dieselben Feldnamen, dieselben Rückgabetypen.

Sie ist bewusst streng: wer eine Order ohne `position` zum Schließen schickt
oder eine Menge außerhalb der Schrittweite, bekommt einen Fehlercode, nicht
ein freundliches Ja. Ein Testdouble, das alles durchwinkt, prüft nichts.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

TRADE_MODE_DEMO = 0
TRADE_MODE_CONTEST = 1
TRADE_MODE_REAL = 2

TIMEFRAME_M1 = 1
TIMEFRAME_M5 = 5
TIMEFRAME_H1 = 16385

ORDER_TYPE_BUY = 0
ORDER_TYPE_SELL = 1
POSITION_TYPE_BUY = 0
POSITION_TYPE_SELL = 1

TRADE_ACTION_DEAL = 1
TRADE_ACTION_SLTP = 6

RETCODE_DONE = 10009
RETCODE_INVALID_VOLUME = 10014
RETCODE_INVALID_STOPS = 10016
RETCODE_NO_MONEY = 10019

DEAL_ENTRY_IN = 0
DEAL_ENTRY_OUT = 1


@dataclass
class Konto:
    login: int = 5_000_123
    server: str = "Tradequo-Demo"
    name: str = "Testkonto"
    currency: str = "EUR"
    balance: float = 10_000.0
    equity: float = 10_000.0
    leverage: int = 100
    trade_mode: int = TRADE_MODE_DEMO
    trade_allowed: bool = True


@dataclass
class Symbol:
    name: str = "XAUUSD"
    visible: bool = True
    point: float = 0.01
    digits: int = 2
    trade_contract_size: float = 100.0
    volume_min: float = 0.01
    volume_max: float = 50.0
    volume_step: float = 0.01
    trade_stops_level: int = 0
    filling_mode: int = 2
    bid: float = 2000.00
    ask: float = 2000.30
    spread: int = 30


@dataclass
class Tick:
    time: float
    bid: float
    ask: float
    last: float = 0.0
    volume: int = 1


@dataclass
class Position:
    ticket: int
    time: float
    type: int
    magic: int
    volume: float
    price_open: float
    sl: float
    tp: float
    price_current: float
    symbol: str
    comment: str = ""
    profit: float = 0.0


@dataclass
class Deal:
    ticket: int
    position_id: int
    time: float
    type: int
    entry: int
    volume: float
    price: float
    profit: float
    comment: str = ""


@dataclass
class Ergebnis:
    retcode: int
    order: int = 0
    deal: int = 0
    volume: float = 0.0
    price: float = 0.0
    comment: str = ""


class FakeMT5:
    """Die Attrappe. Ein Exemplar je Test."""

    def __init__(self, konto: Konto | None = None, symbol: Symbol | None = None,
                 server_offset_hours: float = 2.0,
                 jetzt: datetime | None = None) -> None:
        self.konto_obj = konto or Konto()
        self.symbol_obj = symbol or Symbol()
        self.offset = timedelta(hours=server_offset_hours)
        # Zwei Uhren, und das mit Absicht:
        # `jetzt`      — wann Deals und Positionen entstehen. Tests stellen sie.
        # `tick_zeit`  — wann der letzte Kurs kam. Daran misst der Bot den
        #                Zeitzonenversatz, also muss sie der echten Uhr folgen;
        #                sonst prüfte der Test seine eigene Kulisse. Wer einen
        #                toten Markt nachstellen will, setzt sie zurück.
        self.jetzt = jetzt or datetime.now(timezone.utc)
        self.tick_zeit: datetime | None = None
        self.rates: dict[str, list[tuple]] = {}
        self.positionen: dict[int, Position] = {}
        self.deals: list[Deal] = []
        self.gesendet: list[dict[str, Any]] = []
        self._tickets = itertools.count(90_000)
        self._fehler = (0, "ok")
        self.initialisiert = False
        self.init_args: dict[str, Any] = {}
        # Schalter für die Tests
        self.initialize_ok = True
        self.naechster_retcode: int | None = None
        self.slippage: float = 0.0          # wie weit der Fill danebenliegt
        self.kein_symbol = False
        self.kein_tick = False

    # ---- Leben ---------------------------------------------------------
    def initialize(self, **kwargs) -> bool:
        self.init_args = dict(kwargs)
        if not self.initialize_ok:
            self._fehler = (-6, "Terminal: Authorization failed")
            return False
        self.initialisiert = True
        return True

    def shutdown(self) -> None:
        self.initialisiert = False

    def last_error(self) -> tuple[int, str]:
        return self._fehler

    # ---- Konto und Symbol ----------------------------------------------
    def account_info(self):
        return self.konto_obj if self.initialisiert else None

    def symbol_info(self, name: str):
        if self.kein_symbol or name != self.symbol_obj.name:
            return None
        return self.symbol_obj

    def kurs_setzen(self, bid: float, spread_pips: float = 3.0,
                    pip: float = 0.1) -> None:
        """Den laufenden Kurs stellen — so, wie der Markt ihn bewegt.

        Ohne das füllt jede Order zum selben Preis, und eine Sitzung sieht
        aus, als stünde der Markt still.
        """
        self.symbol_obj.bid = round(bid, self.symbol_obj.digits)
        self.symbol_obj.ask = round(bid + spread_pips * pip,
                                    self.symbol_obj.digits)
        self.symbol_obj.spread = int(spread_pips * pip / self.symbol_obj.point)

    def kurs_aus_kerze(self, kerze, spread_pips: float = 3.0,
                       pip: float = 0.1) -> None:
        self.kurs_setzen(kerze.close, spread_pips, pip)

    def stops_pruefen(self, pip: float = 0.1) -> list[int]:
        """Was der Broker selbst tut: SL und TP gegen den laufenden Kurs prüfen.

        Im echten Terminal passiert das ohne Zutun des Bots — genau deshalb
        braucht der Bot seinen Abgleich.
        """
        ausgeloest = []
        for ticket, pos in list(self.positionen.items()):
            lang = pos.type == ORDER_TYPE_BUY
            kurs = self.symbol_obj.bid if lang else self.symbol_obj.ask
            if pos.sl and ((lang and kurs <= pos.sl) or (not lang and kurs >= pos.sl)):
                self.stop_ausloesen(ticket, pos.sl, f"[sl {pos.sl:.2f}]")
                ausgeloest.append(ticket)
            elif pos.tp and ((lang and kurs >= pos.tp) or (not lang and kurs <= pos.tp)):
                self.stop_ausloesen(ticket, pos.tp, f"[tp {pos.tp:.2f}]")
                ausgeloest.append(ticket)
        return ausgeloest

    def symbol_select(self, name: str, an: bool) -> bool:
        self.symbol_obj.visible = an
        return True

    def symbol_info_tick(self, name: str):
        if self.kein_tick or name != self.symbol_obj.name:
            return None
        basis = self.tick_zeit or datetime.now(timezone.utc)
        return Tick(time=(basis + self.offset).timestamp(),
                    bid=self.symbol_obj.bid, ask=self.symbol_obj.ask)

    # ---- Kerzen ----------------------------------------------------------
    def setze_kerzen(self, name: str, kerzen) -> None:
        """Kerzen in Serverzeit ablegen, wie MT5 sie liefert."""
        self.rates[name] = [
            ((c.ts + self.offset).timestamp(), c.open, c.high, c.low, c.close,
             int(c.volume), 0, 0)
            for c in kerzen
        ]

    def copy_rates_from_pos(self, name: str, timeframe: int, start: int,
                            anzahl: int):
        reihe = self.rates.get(name)
        if not reihe:
            self._fehler = (-10, "no history")
            return None
        aus = reihe[-anzahl:] if anzahl < len(reihe) else list(reihe)
        return _Rates(aus)

    # ---- Handel ----------------------------------------------------------
    def positions_get(self, symbol: str | None = None, ticket: int | None = None):
        werte = list(self.positionen.values())
        if symbol:
            werte = [p for p in werte if p.symbol == symbol]
        if ticket:
            werte = [p for p in werte if p.ticket == ticket]
        return tuple(werte)

    def history_deals_get(self, *args, position: int | None = None, **kwargs):
        if position is None:
            return tuple(self.deals)
        return tuple(d for d in self.deals if d.position_id == position)

    def order_send(self, request: dict[str, Any]):
        self.gesendet.append(dict(request))
        if self.naechster_retcode is not None:
            code, self.naechster_retcode = self.naechster_retcode, None
            return Ergebnis(retcode=code, comment="abgelehnt")

        aktion = request.get("action")
        if aktion == TRADE_ACTION_SLTP:
            ticket = int(request.get("position", 0))
            pos = self.positionen.get(ticket)
            if pos is None:
                return Ergebnis(retcode=RETCODE_INVALID_STOPS, comment="keine Position")
            pos.sl = float(request.get("sl", pos.sl))
            pos.tp = float(request.get("tp", pos.tp))
            return Ergebnis(retcode=RETCODE_DONE, order=ticket)

        volume = float(request.get("volume", 0.0))
        step = self.symbol_obj.volume_step
        if volume < self.symbol_obj.volume_min - 1e-9:
            return Ergebnis(retcode=RETCODE_INVALID_VOLUME, comment="zu klein")
        if abs(round(volume / step) * step - volume) > 1e-6:
            return Ergebnis(retcode=RETCODE_INVALID_VOLUME, comment="Schrittweite")

        typ = int(request.get("type", ORDER_TYPE_BUY))
        kurs = float(request.get("price", 0.0))
        # Slippage geht gegen den Käufer: Kauf teurer, Verkauf billiger.
        fill = kurs + self.slippage * (1 if typ == ORDER_TYPE_BUY else -1)
        zeit = (self.jetzt + self.offset).timestamp()
        gegen_ticket = request.get("position")

        if gegen_ticket:                      # schließen oder verkleinern
            ticket = int(gegen_ticket)
            pos = self.positionen.get(ticket)
            if pos is None:
                return Ergebnis(retcode=RETCODE_INVALID_STOPS, comment="keine Position")
            deal = Deal(ticket=next(self._tickets), position_id=ticket, time=zeit,
                        type=typ, entry=DEAL_ENTRY_OUT, volume=volume, price=fill,
                        profit=0.0, comment=str(request.get("comment", "")))
            self.deals.append(deal)
            if volume >= pos.volume - 1e-9:
                del self.positionen[ticket]
            else:
                pos.volume -= volume
            return Ergebnis(retcode=RETCODE_DONE, order=ticket, deal=deal.ticket,
                            volume=volume, price=fill)

        ticket = next(self._tickets)
        self.positionen[ticket] = Position(
            ticket=ticket, time=zeit, type=typ,
            magic=int(request.get("magic", 0)), volume=volume, price_open=fill,
            sl=float(request.get("sl", 0.0)), tp=float(request.get("tp", 0.0)),
            price_current=fill, symbol=str(request.get("symbol", "")),
            comment=str(request.get("comment", "")),
        )
        self.deals.append(Deal(ticket=next(self._tickets), position_id=ticket,
                               time=zeit, type=typ, entry=DEAL_ENTRY_IN,
                               volume=volume, price=fill, profit=0.0))
        return Ergebnis(retcode=RETCODE_DONE, order=ticket, deal=ticket,
                        volume=volume, price=fill)

    # ---- Was der Broker von sich aus tut --------------------------------
    def stop_ausloesen(self, ticket: int, preis: float,
                       kommentar: str = "[sl 1999.00]") -> None:
        """So, wie MT5 eine Position schließt, wenn der Stop fällt:
        ohne dass der Bot etwas davon mitbekommt."""
        pos = self.positionen.pop(ticket, None)
        if pos is None:
            raise AssertionError(f"Position {ticket} gibt es nicht")
        self.deals.append(Deal(
            ticket=next(self._tickets), position_id=ticket,
            time=(self.jetzt + self.offset).timestamp(),
            type=ORDER_TYPE_SELL if pos.type == ORDER_TYPE_BUY else ORDER_TYPE_BUY,
            entry=DEAL_ENTRY_OUT, volume=pos.volume, price=preis,
            profit=(preis - pos.price_open) * pos.volume
                   * self.symbol_obj.trade_contract_size
                   * (1 if pos.type == ORDER_TYPE_BUY else -1),
            comment=kommentar,
        ))


class _Rates(list):
    """Was `copy_rates_from_pos` zurückgibt: wie ein numpy-Array mit Feldnamen.

    Der Zugriff über `r["time"]` wird gebraucht; `dtype.names` sagt dem Leser,
    welche Felder es gibt.
    """

    def __init__(self, zeilen) -> None:
        super().__init__(_Row(z) for z in zeilen)


class _Row(tuple):
    FELDER = ("time", "open", "high", "low", "close", "tick_volume",
              "spread", "real_volume")

    def __getitem__(self, key):
        if isinstance(key, str):
            return tuple.__getitem__(self, self.FELDER.index(key))
        return tuple.__getitem__(self, key)

    @property
    def dtype(self):
        return _Dtype(self.FELDER)


@dataclass(frozen=True)
class _Dtype:
    names: tuple
