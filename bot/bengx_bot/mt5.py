"""Anschluss an MetaTrader 5 — der Weg zu Tradequo.

Der Bot entscheidet, MT5 führt aus. Diese Datei ist die Übersetzung zwischen
beiden: aus `broker.Broker` wird ein `order_send`, aus MT5-Kerzen werden
`Candle`-Objekte, aus einem MT5-Konto wird die Antwort auf die Frage, ob hier
echtes Geld liegt.

**Läuft nur unter Windows.** Das Paket `MetaTrader5` gibt es für kein anderes
System; der Terminal selbst muss laufen und angemeldet sein. Deshalb wird das
Modul hier hineingereicht statt importiert: die Tests fahren eine Attrappe,
und auf einem Linux-Rechner lässt sich alles prüfen außer dem letzten Schritt.

Vier Dinge gehen hier erfahrungsgemäß schief, und gegen jedes steht etwas drin:

1. **Lots statt Unzen.** Der Bot rechnet in Unzen, MT5 in Lots. Bei Gold ist
   ein Lot üblicherweise 100 Unzen — wer das verwechselt, handelt das
   Hundertfache. `lots()` rechnet um, rundet *ab* und verweigert lieber, als
   zu raten.

2. **Serverzeit ist nicht UTC.** Die meisten Broker stellen ihren Server auf
   UTC+2 oder UTC+3. Der Einzelschuss hängt an Terminen in UTC; zwei Stunden
   Versatz und er handelt die falsche Minute. `zeitversatz()` misst den
   Versatz am laufenden Terminal, statt ihn zu glauben.

3. **Der Broker schließt, nicht der Bot.** Stop und Ziel liegen als echte
   SL/TP im Terminal. Die meisten Trades enden dort, nicht in `engine.py`.
   `abgleich()` holt sie aus der Historie zurück ins Protokoll — sonst fehlt
   genau das, woraus man lernen will.

4. **Der Füllkurs ist nicht der Wunschkurs.** Was zurückkommt, steht im
   Ergebnis von `order_send`, und nur das wird gebucht.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

from .model import Candle, ExitReason, Position, Side, Trade

# Die Konstanten aus dem Paket. Hier noch einmal, damit die Tests ohne das
# Paket auskommen und damit im Code steht, was die Zahlen bedeuten.
TRADE_MODE_DEMO = 0
TRADE_MODE_CONTEST = 1
TRADE_MODE_REAL = 2

RETCODE_DONE = 10009
RETCODE_DONE_PARTIAL = 10010
RETCODE_PLACED = 10008

ORDER_TYPE_BUY = 0
ORDER_TYPE_SELL = 1
POSITION_TYPE_BUY = 0
POSITION_TYPE_SELL = 1

TRADE_ACTION_DEAL = 1
TRADE_ACTION_SLTP = 6

ORDER_TIME_GTC = 0
ORDER_FILLING_FOK = 0
ORDER_FILLING_IOC = 1
ORDER_FILLING_RETURN = 2

TIMEFRAME_M1 = 1

DEAL_ENTRY_OUT = 1


class MT5Error(RuntimeError):
    """Etwas am Terminal, am Konto oder an einer Order stimmt nicht."""


# ---------------------------------------------------------------------------
# Was wir vom Terminal wissen wollen
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Konto:
    login: int
    server: str
    name: str
    currency: str
    balance: float
    equity: float
    leverage: int
    trade_mode: int
    trade_allowed: bool

    @property
    def demo(self) -> bool:
        """Übungskonto? Wettbewerbskonten zählen mit — auch dort liegt kein Geld."""
        return self.trade_mode in (TRADE_MODE_DEMO, TRADE_MODE_CONTEST)

    @property
    def art(self) -> str:
        return {TRADE_MODE_DEMO: "Demokonto",
                TRADE_MODE_CONTEST: "Wettbewerbskonto",
                TRADE_MODE_REAL: "ECHTGELDKONTO"}.get(self.trade_mode, "unbekannt")


@dataclass(frozen=True, slots=True)
class SymbolInfo:
    name: str
    point: float
    digits: int
    contract_size: float          # Unzen je Lot — bei Gold meist 100
    volume_min: float
    volume_max: float
    volume_step: float
    stops_level: int              # Mindestabstand von SL/TP in Points
    filling: int
    bid: float
    ask: float
    spread_points: int

    @property
    def spread_preis(self) -> float:
        return max(0.0, self.ask - self.bid)


# ---------------------------------------------------------------------------
# Die Hülle um das Paket
# ---------------------------------------------------------------------------

class MT5Terminal:
    """Dünne Hülle um `MetaTrader5`. Alles, was das Paket anfasst, steht hier.

    `modul` wird hineingereicht, damit die Tests eine Attrappe einsetzen
    können. Ohne Angabe wird `MetaTrader5` importiert — das schlägt überall
    außer unter Windows fehl, und zwar mit einer Begründung.
    """

    def __init__(self, modul: Any | None = None) -> None:
        if modul is None:
            modul = _import_mt5()
        self.m = modul
        self._offset: timedelta | None = None
        self._verbunden = False
        # Fest eingetragener Versatz aus der Konfiguration. Gesetzt, wenn der
        # Markt zu ist und sich nichts messen lässt.
        self.offset_vorgabe: float | None = None

    # ---- Verbindung ----------------------------------------------------
    def verbinden(self, login: int | None = None, password: str | None = None,
                  server: str | None = None, path: str | None = None,
                  timeout_ms: int = 60000) -> Konto:
        args: dict[str, Any] = {"timeout": timeout_ms}
        if path:
            args["path"] = path
        if login:
            args["login"] = int(login)
        if password:
            args["password"] = password
        if server:
            args["server"] = server

        if not self.m.initialize(**args):
            code, text = self._fehler()
            raise MT5Error(
                f"MetaTrader 5 lässt sich nicht öffnen ({code}: {text}).\n"
                "Prüfen: Läuft der Terminal? Ist das Konto dort angemeldet? "
                "Stimmen MT5_LOGIN, MT5_PASSWORD und MT5_SERVER in bot/.env? "
                "Und ist unter Extras → Optionen → Expert Advisors der "
                "Algo-Handel erlaubt?"
            )
        self._verbunden = True
        return self.konto()

    def schliessen(self) -> None:
        if self._verbunden:
            self.m.shutdown()
            self._verbunden = False

    def _fehler(self) -> tuple[int, str]:
        try:
            code, text = self.m.last_error()
            return int(code), str(text)
        except Exception:                                  # noqa: BLE001
            return -1, "kein Fehlertext"

    # ---- Konto und Symbol ----------------------------------------------
    def konto(self) -> Konto:
        info = self.m.account_info()
        if info is None:
            code, text = self._fehler()
            raise MT5Error(f"Kein Konto am Terminal ({code}: {text}). "
                           "Ist der Terminal angemeldet?")
        return Konto(
            login=int(getattr(info, "login", 0)),
            server=str(getattr(info, "server", "")),
            name=str(getattr(info, "name", "")),
            currency=str(getattr(info, "currency", "")),
            balance=float(getattr(info, "balance", 0.0)),
            equity=float(getattr(info, "equity", 0.0)),
            leverage=int(getattr(info, "leverage", 0)),
            trade_mode=int(getattr(info, "trade_mode", TRADE_MODE_REAL)),
            trade_allowed=bool(getattr(info, "trade_allowed", True)),
        )

    def alle_symbole(self) -> list[str]:
        """Jeder Name, den der Broker führt — auch die, die in der
        Marktübersicht ausgeblendet sind."""
        try:
            roh = self.m.symbols_get()
        except Exception:                                  # noqa: BLE001
            return []
        return [str(getattr(x, "name", "")) for x in (roh or [])]

    def gold_kandidaten(self) -> list[str]:
        """Was bei diesem Broker nach Gold aussieht.

        Jeder Broker schreibt es anders: XAUUSD, XAUUSD.r, GOLD, GOLD.m,
        XAUUSD_i, #XAUUSD. Raten hilft nicht — fragen schon.
        """
        treffer = [n for n in self.alle_symbole()
                   if "XAU" in n.upper() or "GOLD" in n.upper()]
        # Kurze Namen zuerst: XAUUSD vor XAUUSD.raw vor XAUUSD-ECN.
        treffer.sort(key=lambda n: (len(n), n))
        return treffer

    def symbol(self, name: str) -> SymbolInfo:
        info = self.m.symbol_info(name)
        if info is None:
            kandidaten = self.gold_kandidaten()
            if kandidaten:
                liste = "\n".join(f"    symbol = \"{n}\"" for n in kandidaten[:12])
                raise MT5Error(
                    f"Das Symbol {name!r} kennt dein Broker nicht.\n\n"
                    "Nach Gold sieht bei ihm das hier aus — eine dieser Zeilen "
                    "in config.toml unter [mt5] eintragen:\n\n"
                    f"{liste}\n\n"
                    "Im Zweifel die oberste nehmen."
                )
            raise MT5Error(
                f"Das Symbol {name!r} kennt dein Broker nicht, und unter "
                "seinen Symbolen ist keines, das nach Gold aussieht.\n"
                "Im Terminal Strg+M drücken (Marktübersicht), dort Rechtsklick "
                "→ Symbole → nach Gold suchen und hinzufügen. Danach hier "
                "noch einmal."
            )
        if not getattr(info, "visible", True):
            # Unsichtbare Symbole liefern keine Kurse. Einmal anstupsen.
            self.m.symbol_select(name, True)
            info = self.m.symbol_info(name) or info
        contract = float(getattr(info, "trade_contract_size", 0.0))
        if contract <= 0:
            raise MT5Error(f"{name}: der Broker nennt keine Kontraktgröße. "
                           "Ohne sie lässt sich keine Menge umrechnen.")
        return SymbolInfo(
            name=str(getattr(info, "name", name)),
            point=float(getattr(info, "point", 0.01)),
            digits=int(getattr(info, "digits", 2)),
            contract_size=contract,
            volume_min=float(getattr(info, "volume_min", 0.01)),
            volume_max=float(getattr(info, "volume_max", 100.0)),
            volume_step=float(getattr(info, "volume_step", 0.01)),
            stops_level=int(getattr(info, "trade_stops_level", 0)),
            filling=int(getattr(info, "filling_mode", ORDER_FILLING_IOC)),
            bid=float(getattr(info, "bid", 0.0)),
            ask=float(getattr(info, "ask", 0.0)),
            spread_points=int(getattr(info, "spread", 0)),
        )

    # ---- Zeit ------------------------------------------------------------
    def zeitversatz(self, symbol: str,
                    vorgabe_stunden: float | None = None) -> timedelta:
        """Wie weit die Serverzeit von UTC abweicht — gemessen, nicht geglaubt.

        Die meisten Broker stellen den Server auf UTC+2 oder UTC+3. Der
        Einzelschuss hängt an Terminen in UTC. Gemessen wird am letzten Tick:
        dessen Zeit *sollte* jetzt sein. Gerundet auf halbe Stunden, weil eine
        Verzögerung von Sekunden kein Zeitzonenversatz ist.

        **Am Wochenende geht das nicht.** Dann ist der letzte Tick von Freitag,
        und aus der Differenz würde ein Versatz von zwei Tagen. Deshalb gilt
        ein gemessener Wert nur, solange er in den Bereich echter Zeitzonen
        fällt (−12 bis +14 Stunden). Sonst zählt `mt5.server_utc_offset_hours`
        aus der Konfiguration — und fehlt die auch, bricht der Lauf lieber ab,
        als zur falschen Minute zu handeln.
        """
        if vorgabe_stunden is None:
            vorgabe_stunden = self.offset_vorgabe
        if vorgabe_stunden is not None:
            self._offset = timedelta(hours=float(vorgabe_stunden))
            return self._offset
        if self._offset is not None:
            return self._offset
        tick = self.m.symbol_info_tick(symbol)
        if tick is None:
            raise MT5Error(f"Kein Kurs für {symbol}. Ist der Markt zu, oder "
                           "fehlt das Symbol in der Marktübersicht?")
        server = float(getattr(tick, "time", 0.0))
        if server <= 0:
            raise MT5Error(f"Der letzte Tick für {symbol} hat keine Zeit.")
        roh = server - datetime.now(timezone.utc).timestamp()
        if not -12 * 3600 <= roh <= 14 * 3600:
            alt_stunden = roh / 3600.0
            raise MT5Error(
                f"Der letzte Tick für {symbol} ist {abs(alt_stunden):.1f} Stunden "
                "von jetzt entfernt — daraus lässt sich keine Zeitzone ablesen. "
                "Das ist normal, wenn der Markt zu ist (Wochenende).\n"
                "Entweder warten, bis der Handel läuft, oder den Versatz des "
                "Brokers fest eintragen: mt5.server_utc_offset_hours = 2 "
                "(oder 3 in der Sommerzeit — im Terminal steht die Serverzeit "
                "rechts oben in der Marktübersicht)."
            )
        halbe = round(roh / 1800.0)
        self._offset = timedelta(seconds=halbe * 1800)
        return self._offset

    def _utc(self, server_sekunden: float, offset: timedelta) -> datetime:
        return datetime.fromtimestamp(server_sekunden, timezone.utc) - offset

    # ---- Kerzen ----------------------------------------------------------
    def kerzen(self, symbol: str, minuten: int, anzahl: int) -> list[Candle]:
        """Abgeschlossene Kerzen, älteste zuerst, Zeiten in UTC.

        Die laufende Kerze wird weggelassen: der Bot bewertet nur, was fertig
        ist — im Backtest wie hier.
        """
        timeframe = self._timeframe(minuten)
        rows = self.m.copy_rates_from_pos(symbol, timeframe, 0, anzahl + 1)
        if rows is None or len(rows) == 0:
            code, text = self._fehler()
            raise MT5Error(f"Keine Kerzen für {symbol} ({code}: {text}). "
                           "Im Terminal einmal den Chart öffnen, damit die "
                           "Historie geladen wird.")
        offset = self.zeitversatz(symbol)
        out: list[Candle] = []
        for r in rows[:-1]:                       # die letzte läuft noch
            try:
                ts = self._utc(float(r["time"]), offset)
                o, h, l, c = (float(r["open"]), float(r["high"]),
                              float(r["low"]), float(r["close"]))
                v = float(r["tick_volume"]) if "tick_volume" in r.dtype.names else 0.0
            except (KeyError, TypeError, ValueError, AttributeError):
                ts = self._utc(float(r[0]), offset)
                o, h, l, c = float(r[1]), float(r[2]), float(r[3]), float(r[4])
                v = float(r[5]) if len(r) > 5 else 0.0
            # Ein Broker liefert gelegentlich eine Kerze, deren Schluss knapp
            # außerhalb von Hoch und Tief liegt. Candle lehnt die ab — hier
            # wird sie eingefangen statt den ganzen Lauf abzubrechen.
            h = max(h, o, c)
            l = min(l, o, c)
            out.append(Candle(ts=ts, open=o, high=h, low=l, close=c, volume=v))
        return out

    def _timeframe(self, minuten: int) -> int:
        name = {1: "TIMEFRAME_M1", 5: "TIMEFRAME_M5", 15: "TIMEFRAME_M15",
                30: "TIMEFRAME_M30", 60: "TIMEFRAME_H1", 240: "TIMEFRAME_H4",
                1440: "TIMEFRAME_D1"}.get(minuten)
        if name is None:
            raise MT5Error(f"Für {minuten} Minuten hat MT5 keinen Zeitrahmen. "
                           "Möglich sind 1, 5, 15, 30, 60, 240 und 1440.")
        return int(getattr(self.m, name, TIMEFRAME_M1))

    # ---- Positionen und Order -------------------------------------------
    def positionen(self, symbol: str, magic: int) -> list[Any]:
        roh = self.m.positions_get(symbol=symbol)
        if roh is None:
            return []
        return [p for p in roh if int(getattr(p, "magic", 0)) == magic]

    def senden(self, request: dict[str, Any]) -> Any:
        ergebnis = self.m.order_send(request)
        if ergebnis is None:
            code, text = self._fehler()
            raise MT5Error(f"Die Order kam nicht durch ({code}: {text}).")
        code = int(getattr(ergebnis, "retcode", -1))
        if code not in (RETCODE_DONE, RETCODE_DONE_PARTIAL, RETCODE_PLACED):
            kommentar = str(getattr(ergebnis, "comment", ""))
            raise MT5Error(f"Die Order wurde abgelehnt (retcode {code}"
                           f"{': ' + kommentar if kommentar else ''}).")
        return ergebnis

    def abschluss_deals(self, ticket: int) -> list[Any]:
        """Die Deals zu einer geschlossenen Position, aus der Historie."""
        roh = self.m.history_deals_get(position=ticket)
        return list(roh) if roh else []


def _import_mt5():
    try:
        import MetaTrader5 as modul                        # type: ignore
    except ImportError as exc:
        raise MT5Error(
            "Das Paket MetaTrader5 ist nicht da. Es gibt es nur für Windows:\n"
            "  pip install MetaTrader5\n"
            "Auf Linux und Mac lässt sich kein MT5-Konto anbinden — dort "
            "bleibt der Bot auf dem Papierkonto."
        ) from exc
    return modul


# ---------------------------------------------------------------------------
# Unzen und Lots
# ---------------------------------------------------------------------------

def lots(size_unzen: float, info: SymbolInfo) -> float:
    """Unzen in Lots, abgerundet auf die Schrittweite des Brokers.

    Abgerundet, nie auf: lieber etwas weniger Risiko als etwas mehr. Was unter
    der Mindestmenge landet, wird nicht gehandelt — mit Begründung, denn das
    ist der häufigste Grund, warum ein kleines Konto gar nichts tut.
    """
    if size_unzen <= 0:
        raise MT5Error("Die Menge ist null oder negativ.")
    roh = size_unzen / info.contract_size
    step = info.volume_step if info.volume_step > 0 else 0.01
    # Fließkomma: 0,29999999 soll 0,3 werden, nicht 0,29.
    stufen = math.floor(round(roh / step, 9))
    menge = round(stufen * step, 8)
    if menge < info.volume_min:
        raise MT5Error(
            f"Die Position wäre {roh:.4f} Lots groß, der Broker verlangt "
            f"mindestens {info.volume_min:g}. Dein Risiko je Trade ergibt bei "
            "diesem Stop-Abstand keine handelbare Menge.\n"
            "Entweder: kleineres Konto-Risiko ist nicht das Problem, sondern "
            "ein zu großes — mehr Kapital, ein engerer Stop oder ein "
            "Cent-Konto, auf dem ein Lot ein Hundertstel wiegt."
        )
    return min(menge, info.volume_max)


def unzen(menge_lots: float, info: SymbolInfo) -> float:
    return menge_lots * info.contract_size


# ---------------------------------------------------------------------------
# Der Broker
# ---------------------------------------------------------------------------

class MT5Broker:
    """Erfüllt `broker.Broker`, führt aber wirklich aus.

    Gebucht wird immer der Kurs, den MT5 zurückmeldet — nie der, den die
    Strategie wollte. Der Unterschied ist die Slippage, und die soll im
    Protokoll stehen, nicht verschwinden.
    """

    def __init__(self, config, terminal: MT5Terminal,
                 symbol: str | None = None) -> None:
        self.cfg = config
        self.t = terminal
        self.p = config.mt5
        self.symbol = symbol or self.p.symbol
        self.pip = config.market.pip
        self.info = terminal.symbol(self.symbol)
        self.positions: list[Position] = []
        self._konto = terminal.konto()
        self.equity = self._konto.equity
        # Ticket je Position, damit der Abgleich weiß, wen er sucht.
        self.tickets: dict[str, int] = {}
        # Was beim Einstieg wirklich los war — Slippage und Spread. Wandert
        # beim Schließen in den Trade und ist die Grundlage von `lernen.py`.
        self.kontext: dict[str, dict[str, Any]] = {}

    # ---- Zustand --------------------------------------------------------
    def aktualisieren(self) -> Konto:
        """Kontostand und Kurse frisch holen."""
        self._konto = self.t.konto()
        self.equity = self._konto.equity
        self.info = self.t.symbol(self.symbol)
        return self._konto

    @property
    def konto(self) -> Konto:
        return self._konto

    # ---- Hilfen ----------------------------------------------------------
    def _filling(self) -> int:
        gewaehlt = (self.p.filling or "auto").lower()
        if gewaehlt == "fok":
            return ORDER_FILLING_FOK
        if gewaehlt == "ioc":
            return ORDER_FILLING_IOC
        if gewaehlt == "return":
            return ORDER_FILLING_RETURN
        # "auto": was der Broker für das Symbol anbietet. Das Feld ist eine
        # Bitmaske; IOC ist die verbreitetste Wahl.
        maske = self.info.filling
        if maske & (1 << ORDER_FILLING_IOC):
            return ORDER_FILLING_IOC
        if maske & (1 << ORDER_FILLING_FOK):
            return ORDER_FILLING_FOK
        return ORDER_FILLING_RETURN

    def _abstand_ok(self, preis: float, marke: float) -> bool:
        """Hält der Broker-Mindestabstand für SL und TP?"""
        if self.info.stops_level <= 0:
            return True
        return abs(preis - marke) >= self.info.stops_level * self.info.point

    def _runden(self, preis: float) -> float:
        return round(preis, self.info.digits)

    # ---- Order -----------------------------------------------------------
    def open(self, side: Side, size: float, price: float, when: datetime,
             bar: int, stop: float, target: float, note: str = "",
             final_target: float | None = None,
             source_id: str | None = None) -> Position:
        menge = lots(size, self.info)
        tick = self.t.m.symbol_info_tick(self.symbol)
        kurs = float(getattr(tick, "ask" if side is Side.LONG else "bid", 0.0))
        if kurs <= 0:
            raise MT5Error(f"Kein handelbarer Kurs für {self.symbol}.")

        bid = float(getattr(tick, "bid", 0.0))
        ask = float(getattr(tick, "ask", 0.0))
        spread_pips = (ask - bid) / self.pip if ask > bid else 0.0

        anfrage = {
            "action": TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": menge,
            "type": ORDER_TYPE_BUY if side is Side.LONG else ORDER_TYPE_SELL,
            "price": kurs,
            "deviation": int(self.p.deviation_points),
            "magic": int(self.p.magic),
            "comment": (note or "bengx")[:31],
            "type_time": ORDER_TIME_GTC,
            "type_filling": self._filling(),
        }
        # SL und TP nur mitgeben, wenn der Broker den Abstand zulässt —
        # sonst lehnt er die ganze Order ab statt nur die Marke.
        if self._abstand_ok(kurs, stop):
            anfrage["sl"] = self._runden(stop)
        ziel = final_target if final_target is not None else target
        if ziel and self._abstand_ok(kurs, ziel):
            anfrage["tp"] = self._runden(ziel)

        ergebnis = self.t.senden(anfrage)
        fill = float(getattr(ergebnis, "price", kurs)) or kurs
        ticket = int(getattr(ergebnis, "order", 0) or getattr(ergebnis, "deal", 0))
        echte_menge = unzen(float(getattr(ergebnis, "volume", menge)), self.info)

        pos = Position(
            id=f"mt5-{ticket}" if ticket else f"mt5-{when:%Y%m%d-%H%M%S}",
            side=side,
            size=echte_menge,
            entry=fill,
            stop=stop,
            target=target,
            opened_at=when,
            opened_bar=bar,
            initial_risk=abs(fill - stop),
            final_target=final_target,
            source_id=source_id,
            original_size=echte_menge,
            note=note,
        )
        # Die Position, die MT5 führt, trägt das Ticket des *Deals*. Beim
        # Abgleich wird danach gesucht, deshalb hier merken.
        self.tickets[pos.id] = int(getattr(ergebnis, "order", 0)) or ticket
        # Zwei verschiedene Zahlen, die gern verwechselt werden:
        #
        # slippage_pips   — wie weit der Fill vom Kurs abweicht, den wir in
        #                   diesem Augenblick gesendet haben. Das ist die
        #                   Ausführungsqualität des Brokers.
        # abweichung_pips — wie weit der Fill von dem Kurs abweicht, den die
        #                   Strategie wollte (bei der Straddle: die Orderstufe).
        #                   Darin steckt zusätzlich die Zeit zwischen
        #                   Kerzenschluss und Order — und die ist bei einer
        #                   Nachricht der größere Posten.
        #
        # Beide positiv heißt: schlechter als gewollt.
        self.kontext[pos.id] = {
            "wunsch": round(price, self.info.digits),
            "gesendet": round(kurs, self.info.digits),
            "fill": round(fill, self.info.digits),
            "slippage_pips": round((fill - kurs) * side.sign / self.pip, 2),
            "abweichung_pips": round((fill - price) * side.sign / self.pip, 2),
            "spread_pips": round(spread_pips, 2),
            "lots": menge,
        }
        self.positions.append(pos)
        return pos

    def reduce(self, position: Position, fraction: float, price: float) -> None:
        """Teilverkauf: eine Gegenorder über den Teil, die Position bleibt."""
        if not 0 < fraction < 1:
            raise ValueError("fraction muss zwischen 0 und 1 liegen")
        teil_unzen = position.size * fraction
        try:
            menge = lots(teil_unzen, self.info)
        except MT5Error:
            return                       # zu klein zum Teilen — dann eben nicht
        voll = lots(position.size, self.info)
        if menge >= voll:
            return

        ticket = self.tickets.get(position.id)
        tick = self.t.m.symbol_info_tick(self.symbol)
        gegen = Side.SHORT if position.side is Side.LONG else Side.LONG
        kurs = float(getattr(tick, "bid" if position.side is Side.LONG else "ask", 0.0))
        ergebnis = self.t.senden({
            "action": TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": menge,
            "type": ORDER_TYPE_BUY if gegen is Side.LONG else ORDER_TYPE_SELL,
            "position": ticket,
            "price": kurs,
            "deviation": int(self.p.deviation_points),
            "magic": int(self.p.magic),
            "comment": "teil",
            "type_time": ORDER_TIME_GTC,
            "type_filling": self._filling(),
        })
        fill = float(getattr(ergebnis, "price", kurs)) or kurs
        raus = unzen(menge, self.info)
        gewinn = (fill - position.entry) * position.side.sign * raus
        position.realised_pnl += gewinn
        position.size -= raus
        position.partial_done = True
        self.aktualisieren()

    def close(self, position: Position, price: float, when: datetime,
              reason: ExitReason) -> Trade:
        ticket = self.tickets.get(position.id)
        tick = self.t.m.symbol_info_tick(self.symbol)
        gegen = Side.SHORT if position.side is Side.LONG else Side.LONG
        kurs = float(getattr(tick, "bid" if position.side is Side.LONG else "ask", 0.0))
        menge = lots(position.size, self.info)
        ergebnis = self.t.senden({
            "action": TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": menge,
            "type": ORDER_TYPE_BUY if gegen is Side.LONG else ORDER_TYPE_SELL,
            "position": ticket,
            "price": kurs,
            "deviation": int(self.p.deviation_points),
            "magic": int(self.p.magic),
            "comment": reason.value[:31],
            "type_time": ORDER_TIME_GTC,
            "type_filling": self._filling(),
        })
        fill = float(getattr(ergebnis, "price", kurs)) or kurs
        self.aktualisieren()
        return self._trade(position, fill, when, reason)

    def stops_nachziehen(self) -> int:
        """Veränderte Stops ins Terminal schreiben.

        Die Maschine zieht `pos.stop` nach; im Terminal liegt aber die Marke,
        die wirklich auslöst. Ohne diesen Schritt wäre der Trailing-Stop nur
        eine Zahl im Speicher.
        """
        geaendert = 0
        for pos in self.positions:
            ticket = self.tickets.get(pos.id)
            if not ticket:
                continue
            roh = next((p for p in self.t.positionen(self.symbol, int(self.p.magic))
                        if int(getattr(p, "ticket", 0)) == ticket), None)
            if roh is None:
                continue
            jetzt = float(getattr(roh, "sl", 0.0))
            soll = self._runden(pos.stop)
            if abs(jetzt - soll) < self.info.point / 2:
                continue
            kurs = float(getattr(roh, "price_current", 0.0))
            if kurs and not self._abstand_ok(kurs, soll):
                continue
            self.t.senden({
                "action": TRADE_ACTION_SLTP,
                "symbol": self.symbol,
                "position": ticket,
                "sl": soll,
                "tp": self._runden(pos.final_target or pos.target or 0.0) or 0.0,
                "magic": int(self.p.magic),
            })
            geaendert += 1
        return geaendert

    def uebernehmen(self) -> int:
        """Nach einem Neustart die Tickets aus den Kennungen zurückholen.

        Die Kennung einer Position lautet `mt5-<ticket>`; mehr braucht es
        nicht, um sie im Terminal wiederzufinden. Positionen, deren Kennung
        kein Ticket enthält, stammen aus einem Papierlauf und werden
        verworfen — sie gehören zu keinem echten Handel.
        """
        behalten: list[Position] = []
        for pos in self.positions:
            if not pos.id.startswith("mt5-"):
                continue
            rest = pos.id[4:]
            if not rest.isdigit():
                continue
            self.tickets[pos.id] = int(rest)
            behalten.append(pos)
        self.positions = behalten
        return len(behalten)

    # ---- Abgleich --------------------------------------------------------
    def abgleich(self, jetzt: datetime | None = None) -> list[Trade]:
        """Was MT5 geschlossen hat, zurück ins Protokoll holen.

        Stop und Ziel liegen als echte Marken im Terminal. Die meisten Trades
        enden dort — der Bot erfährt davon nur hier. Ohne diesen Schritt
        stünde im Protokoll nur, was die Maschine selbst geschlossen hat, und
        das wären ausgerechnet die wenigen.
        """
        jetzt = jetzt or datetime.now(timezone.utc)
        offen = {int(getattr(p, "ticket", 0))
                 for p in self.t.positionen(self.symbol, int(self.p.magic))}
        fertig: list[Trade] = []
        for pos in list(self.positions):
            ticket = self.tickets.get(pos.id)
            if not ticket or ticket in offen:
                continue
            fill, zeit, grund = self._aus_historie(ticket, pos)
            fertig.append(self._trade(pos, fill, zeit or jetzt, grund))
        if fertig:
            self.aktualisieren()
        return fertig

    def _aus_historie(self, ticket: int,
                      pos: Position) -> tuple[float, datetime | None, ExitReason]:
        """Schlusskurs, Zeit und Grund aus den Deals der Position."""
        deals = [d for d in self.t.abschluss_deals(ticket)
                 if int(getattr(d, "entry", DEAL_ENTRY_OUT)) == DEAL_ENTRY_OUT]
        if not deals:
            # Position weg, aber keine Historie: der letzte bekannte Kurs
            # ist die ehrlichste Schätzung, und der Grund bleibt offen.
            return pos.entry, None, ExitReason.MANUAL
        letzter = deals[-1]
        fill = float(getattr(letzter, "price", pos.entry))
        roh = float(getattr(letzter, "time", 0.0))
        zeit = None
        if roh > 0:
            offset = self.t.zeitversatz(self.symbol)
            zeit = self.t._utc(roh, offset)
        return fill, zeit, self._grund(letzter, pos, fill)

    def _grund(self, deal: Any, pos: Position, fill: float) -> ExitReason:
        """Woran der Trade gestorben ist — so weit MT5 es verrät."""
        text = str(getattr(deal, "comment", "")).lower()
        if "sl" in text or "stop" in text:
            return ExitReason.TRAIL if pos.partial_done else ExitReason.STOP
        if "tp" in text or "take" in text:
            return ExitReason.TARGET
        # Kein sprechender Kommentar: an der Seite des Einstiegs entscheiden.
        gewinn = (fill - pos.entry) * pos.side.sign
        if gewinn > 0:
            return ExitReason.TARGET
        return ExitReason.TRAIL if pos.partial_done else ExitReason.STOP

    def _trade(self, position: Position, fill: float, when: datetime,
               reason: ExitReason) -> Trade:
        gewinn = (fill - position.entry) * position.side.sign * position.size
        gesamt = position.realised_pnl + gewinn
        basis = position.original_size * self.pip
        risiko = position.initial_risk * position.original_size
        if position in self.positions:
            self.positions.remove(position)
        self.tickets.pop(position.id, None)
        marken = {"partial": position.partial_done,
                  "source_id": position.source_id,
                  "broker": "mt5",
                  "konto": self._konto.art}
        marken.update(self.kontext.pop(position.id, {}))
        return Trade(
            id=position.id,
            side=position.side,
            size=position.original_size,
            entry=position.entry,
            stop=position.entry_stop,
            target=position.target,
            exit_price=fill,
            opened_at=position.opened_at,
            closed_at=when,
            pips=gesamt / basis if basis else 0.0,
            pnl=gesamt,
            r_multiple=gesamt / risiko if risiko else 0.0,
            reason=reason,
            note=position.note,
            tags=marken,
        )

    def mark_to_market(self, price: float) -> float:
        return self.equity


# ---------------------------------------------------------------------------
# Zugangsdaten
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Zugang:
    """Was aus `.env` kommt. Steht nirgends in der Konfiguration und nie im Repo."""

    login: int | None
    password: str | None
    server: str | None
    path: str | None

    @staticmethod
    def from_env(env: dict[str, str] | None = None) -> "Zugang":
        e = env if env is not None else os.environ
        roh = str(e.get("MT5_LOGIN", "")).strip()
        try:
            login = int(roh) if roh else None
        except ValueError:
            raise MT5Error(f"MT5_LOGIN ist keine Zahl: {roh!r}") from None
        return Zugang(
            login=login,
            password=(e.get("MT5_PASSWORD") or "").strip() or None,
            server=(e.get("MT5_SERVER") or "").strip() or None,
            path=(e.get("MT5_PATH") or "").strip() or None,
        )

    @property
    def vollstaendig(self) -> bool:
        """Ohne Angaben versucht MT5 das Konto, das im Terminal angemeldet ist."""
        return bool(self.login and self.password and self.server)


def verbinden(config, env: dict[str, str] | None = None,
              modul: Any | None = None) -> tuple[MT5Terminal, Konto]:
    """Terminal öffnen und das Konto zurückgeben, mit dem gehandelt würde."""
    zugang = Zugang.from_env(env)
    terminal = MT5Terminal(modul)
    terminal.offset_vorgabe = getattr(config.mt5, "server_utc_offset_hours", None)
    konto = terminal.verbinden(login=zugang.login, password=zugang.password,
                               server=zugang.server, path=zugang.path)
    if not konto.trade_allowed:
        raise MT5Error(
            f"Das Konto {konto.login} darf nicht handeln. Im Terminal unter "
            "Extras → Optionen → Expert Advisors den Algo-Handel erlauben, "
            "und prüfen, ob der Broker das Konto gesperrt hat."
        )
    return terminal, konto
