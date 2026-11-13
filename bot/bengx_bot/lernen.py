"""Aus Fehlern lernen — ohne dass der Bot sich selbst verstellt.

Der Bot dreht an keiner Regel. Das ist Absicht, und zwar aus einem Grund, der
sich nicht wegprogrammieren lässt: bei höchstens zwei Terminen am Tag kommen
im Monat vierzig Trades zusammen. Aus vierzig Zahlen lässt sich kein Parameter
schätzen, der morgen noch gilt — man fittet Rauschen. Eine Automatik, die nach
drei Verlusten den Abstand verstellt, hätte am Ende ein Regelwerk, das zu
genau diesen drei Verlusten passt und zu sonst nichts. Dazu käme, dass sie
still ändert, wogegen du gerade prüfst: der Fingerabdruck wandert, der
Backtest gilt nicht mehr, und niemand weiß hinterher, welche Fassung welche
Zahlen gemacht hat.

Was stattdessen passiert: jeder Trade wird mit seinem Umfeld festgehalten —
welcher Termin, welche Seite, wie breit der Spread beim Einstieg wirklich war,
wie viel Slippage die Order gefressen hat, wie lange es bis zum Ausstieg
dauerte. Daraus rechnet `auswerten()` Befunde: was auffällt, auf wie vielen
Fällen es beruht, und welche Änderung daraus folgen *könnte*. Entscheiden
tust du.

Jeder Befund nennt seine Stückzahl. Ein Muster aus drei Trades ist kein Muster,
und das steht dann auch dort.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Sequence

from .model import ExitReason, Trade

# Unter so vielen Fällen wird nichts behauptet, nur gezählt.
GENUG = 8
VIEL = 20


@dataclass(frozen=True, slots=True)
class Befund:
    """Etwas, das auffällt — mit Beleg und, wenn möglich, einem Vorschlag."""

    titel: str
    faelle: int
    text: str
    vorschlag: str = ""
    schwer: bool = False          # kostet Geld, nicht nur Schönheit

    @property
    def belastbar(self) -> bool:
        return self.faelle >= GENUG

    def zeilen(self) -> list[str]:
        marke = "!" if self.schwer else "·"
        kopf = f"  {marke} {self.titel}  ({self.faelle} Fälle"
        kopf += ")" if self.belastbar else f", zu wenige für eine Aussage)"
        out = [kopf, f"      {self.text}"]
        if self.vorschlag:
            out.append(f"      → {self.vorschlag}")
        return out


@dataclass
class Auswertung:
    trades: int = 0
    gewonnen: int = 0
    verloren: int = 0
    pnl: float = 0.0
    r_schnitt: float = 0.0
    befunde: list[Befund] = field(default_factory=list)

    @property
    def trefferquote(self) -> float | None:
        entschieden = self.gewonnen + self.verloren
        return self.gewonnen / entschieden if entschieden else None

    def bericht(self) -> str:
        if not self.trades:
            return ("Noch kein einziger abgeschlossener Trade im Protokoll.\n"
                    "Es gibt nichts zu lernen, solange nichts passiert ist.")
        quote = (f"{self.trefferquote:.0%}" if self.trefferquote is not None else "—")
        zeilen = [
            "Was die Trades sagen",
            "",
            f"  Trades        {self.trades}   davon {self.gewonnen} im Plus, "
            f"{self.verloren} im Minus",
            f"  Trefferquote  {quote}",
            f"  Ergebnis      {self.pnl:+.2f}",
            f"  Erwartungswert {self.r_schnitt:+.3f} R je Trade",
            "",
        ]
        if self.trades < GENUG:
            zeilen += [
                f"  Bei {self.trades} Trades ist jede Zahl hier Zufall. Erst ab",
                f"  etwa {VIEL} Stück lohnt sich ein Blick auf Muster — und auch",
                "  dann ist es ein Hinweis, kein Beweis.",
                "",
            ]
        if not self.befunde:
            zeilen.append("  Nichts Auffälliges gefunden.")
            return "\n".join(zeilen)

        zeilen.append("Befunde:")
        zeilen.append("")
        for b in self.befunde:
            zeilen += b.zeilen()
            zeilen.append("")
        zeilen += [
            "Nichts davon wurde geändert. Der Bot verstellt seine Regeln nicht",
            "selbst — was du übernehmen willst, trägst du in config.toml ein",
            "(oder in der Bot-Konsole) und rechnest danach neu nach.",
        ]
        return "\n".join(zeilen)


# ---------------------------------------------------------------------------
# Hilfen
# ---------------------------------------------------------------------------

def _zahl(trade: Trade, name: str) -> float | None:
    wert = trade.tags.get(name)
    try:
        return float(wert)                    # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _median(werte: Sequence[float]) -> float:
    return statistics.median(werte) if werte else 0.0


def _minuten(trade: Trade) -> float:
    return (trade.closed_at - trade.opened_at).total_seconds() / 60.0


# ---------------------------------------------------------------------------
# Die einzelnen Prüfungen
# ---------------------------------------------------------------------------

def _slippage(trades: Sequence[Trade], config) -> Befund | None:
    """Was die Order wirklich gekostet hat, gegen das, was gerechnet wurde."""
    gemessen = [s for s in (_zahl(t, "slippage_pips") for t in trades)
                if s is not None]
    if not gemessen:
        return None
    mitte = _median(gemessen)
    schlimmste = max(gemessen)
    angenommen = float(getattr(config.einzelschuss, "news_slippage_pips", 0.0))
    text = (f"Angenommen waren {angenommen:g} Pips Aufschlag, gemessen wurden "
            f"im Mittel {mitte:.1f} und im schlimmsten Fall {schlimmste:.1f}.")
    if mitte <= angenommen + 0.5:
        return Befund("Slippage liegt im Rahmen", len(gemessen), text)
    return Befund(
        "Die Order füllen schlechter als gerechnet", len(gemessen), text,
        f"einzelschuss.news_slippage_pips auf {mitte:.0f} setzen und den "
        "Backtest damit neu rechnen — sonst sieht er besser aus als die "
        "Wirklichkeit.",
        schwer=True,
    )


def _abweichung(trades: Sequence[Trade], config) -> Befund | None:
    """Kommt der Bot überhaupt dort hinein, wo er hin wollte?

    Das ist der wunde Punkt dieser Bauart. Die Maschine bewertet
    *abgeschlossene* Minutenkerzen und schickt dann eine Marktorder. Zwischen
    dem Augenblick, in dem die Orderstufe berührt wurde, und der Order liegt
    damit bis zu eine Minute — ausgerechnet die, in der sich der Kurs am
    schnellsten bewegt. Im Terminal liegt bei einem echten Nachrichten-EA
    stattdessen eine Stop-Order, die genau an der Stufe auslöst.

    Diese Zahl misst den Unterschied. Ist sie groß, handelt der Bot etwas
    anderes als das, was im Backtest steht.
    """
    gemessen = [a for a in (_zahl(t, "abweichung_pips") for t in trades)
                if a is not None]
    if not gemessen:
        return None
    betraege = [abs(a) for a in gemessen]
    mitte = _median(betraege)
    offset = float(getattr(config.einzelschuss, "offset_pips", 0.0))
    text = (f"Der Einstieg lag im Mittel {mitte:.1f} Pips neben der Stufe, "
            f"die die Strategie wollte (höchstens {max(betraege):.1f}).")
    if offset and mitte <= offset / 3:
        return Befund("Die Einstiege treffen ihre Stufe", len(gemessen), text)
    return Befund(
        "Der Bot steigt woanders ein, als er will", len(gemessen), text,
        "Das ist keine Einstellung, sondern die Bauart: die Maschine "
        "bewertet fertige Minutenkerzen und schickt danach eine Marktorder. "
        "Bei einer Nachricht ist der Kurs dann schon weg. Wer das dicht "
        "haben will, braucht echte Stop-Order im Terminal, die an der Stufe "
        "auslösen — siehe bot/README.md, Abschnitt Einzelschuss am Terminal.",
        schwer=True,
    )


def _spread(trades: Sequence[Trade], config) -> Befund | None:
    """Der Spread im Nachrichtenmoment — der stille Killer dieser Strategie."""
    gemessen = [s for s in (_zahl(t, "spread_pips") for t in trades)
                if s is not None]
    if not gemessen:
        return None
    mitte = _median(gemessen)
    schlimmste = max(gemessen)
    angenommen = float(config.costs.spread_pips)
    text = (f"Gerechnet wird mit {angenommen:g} Pips, beim Einstieg lagen "
            f"im Mittel {mitte:.1f} an, höchstens {schlimmste:.1f}.")
    if mitte <= angenommen + 1.0:
        return Befund("Spread liegt im Rahmen", len(gemessen), text)
    return Befund(
        "Der Spread beim Einstieg ist breiter als angenommen", len(gemessen),
        text,
        f"costs.spread_pips auf {mitte:.0f} setzen. Bei dieser Strategie "
        "entscheidet der Spread über Gewinn und Verlust — zu niedrig "
        "angesetzt macht jeden Backtest wertlos.",
        schwer=True,
    )


def _schnelle_stops(trades: Sequence[Trade], config) -> Befund | None:
    """Verluste, die binnen Minuten kommen: die Order lag zu eng."""
    verlierer = [t for t in trades if t.lost]
    if len(verlierer) < 3:
        return None
    schnell = [t for t in verlierer if _minuten(t) <= 3]
    anteil = len(schnell) / len(verlierer)
    text = (f"{len(schnell)} von {len(verlierer)} Verlusten standen nach "
            f"höchstens drei Minuten fest ({anteil:.0%}).")
    if anteil < 0.5:
        return Befund("Verluste kommen nicht überhastet", len(verlierer), text)
    offset = float(getattr(config.einzelschuss, "offset_pips", 0.0))
    return Befund(
        "Die Order werden vom ersten Ausschlag abgeholt", len(verlierer), text,
        f"einzelschuss.offset_pips liegt bei {offset:g}. Weiter weg "
        f"(z. B. {offset * 1.5:.0f}) wird seltener ausgelöst, dafür nicht vom "
        "ersten Zucken. Alternativ den Stop weiter stellen — aber dann wird "
        "die Position kleiner.",
        schwer=True,
    )


def _je_termin(trades: Sequence[Trade]) -> list[Befund]:
    """Welche Termine tragen und welche nur kosten."""
    nach: dict[str, list[Trade]] = defaultdict(list)
    for t in trades:
        name = str(t.tags.get("source_id") or "ohne Namen")
        nach[name].append(t)
    out: list[Befund] = []
    for name, liste in sorted(nach.items(), key=lambda kv: -len(kv[1])):
        if len(liste) < 3:
            continue
        pnl = sum(t.pnl for t in liste)
        gewonnen = sum(1 for t in liste if t.won)
        text = (f"{name}: {gewonnen} von {len(liste)} im Plus, zusammen "
                f"{pnl:+.2f}.")
        if pnl < 0 and gewonnen * 2 < len(liste):
            out.append(Befund(
                f"Termin {name} kostet bisher", len(liste), text,
                f"{name} aus news.json nehmen oder seine Wichtigkeit "
                "herabstufen — aber erst, wenn genug Fälle zusammen sind.",
            ))
        else:
            out.append(Befund(f"Termin {name}", len(liste), text))
    return out


def _richtung(trades: Sequence[Trade]) -> Befund | None:
    lang = [t for t in trades if t.side.value == "long"]
    kurz = [t for t in trades if t.side.value == "short"]
    if len(lang) < 3 or len(kurz) < 3:
        return None
    pl, pk = sum(t.pnl for t in lang), sum(t.pnl for t in kurz)
    text = (f"Long: {len(lang)} Trades, {pl:+.2f}. "
            f"Short: {len(kurz)} Trades, {pk:+.2f}.")
    if pl * pk >= 0:
        return Befund("Beide Richtungen laufen ähnlich", len(trades), text)
    return Befund(
        "Eine Richtung trägt, die andere kostet", len(trades), text,
        "Vorsicht: bei dieser Stückzahl ist das fast sicher Zufall. Eine "
        "Seite abzuschalten, weil sie bisher schlechter lief, ist der "
        "klassische Weg, eine Strategie kaputtzuoptimieren.",
    )


def _ausstiege(trades: Sequence[Trade]) -> Befund | None:
    """Woran die Trades enden — und ob der Zeitstop zu früh greift."""
    nach: dict[str, int] = defaultdict(int)
    for t in trades:
        nach[t.reason.value] += 1
    text = ", ".join(f"{n}× {grund}" for grund, n in
                     sorted(nach.items(), key=lambda kv: -kv[1]))
    zeit = nach.get(ExitReason.TIME.value, 0)
    if zeit and zeit / len(trades) >= 0.4:
        return Befund(
            "Die meisten Trades laufen in den Zeitstop", len(trades),
            f"{text}. Ein Zeitstop ohne Entscheidung heißt: die Bewegung kam "
            "gar nicht.",
            "Entweder war der Termin die Aufregung nicht wert — dann gehört "
            "er aus dem Kalender —, oder einzelschuss.max_hold_minutes ist zu "
            "kurz für diese Nachricht.",
        )
    return Befund("Woran die Trades enden", len(trades), text)


def _kontostand(trades: Sequence[Trade], config) -> Befund | None:
    """Reicht das Konto für die eingestellte Positionsgröße?"""
    winzig = [t for t in trades if t.size > 0 and t.size < 1.0]
    if not winzig:
        return None
    return Befund(
        "Die Positionen sind an der Mindestmenge", len(winzig),
        f"{len(winzig)} Trades lagen bei oder unter einer Unze. Dort rundet "
        "der Broker, und das eingestellte Risiko je Trade stimmt nicht mehr.",
        "Entweder mehr Kapital, oder ein Cent-Konto — sonst handelt der Bot "
        "etwas anderes, als risk.risk_per_trade sagt.",
        schwer=True,
    )


# ---------------------------------------------------------------------------
# Alles zusammen
# ---------------------------------------------------------------------------

def auswerten(trades: Sequence[Trade], config) -> Auswertung:
    """Die Befunde über alle abgeschlossenen Trades."""
    a = Auswertung(trades=len(trades))
    if not trades:
        return a
    a.gewonnen = sum(1 for t in trades if t.won)
    a.verloren = sum(1 for t in trades if t.lost)
    a.pnl = sum(t.pnl for t in trades)
    a.r_schnitt = statistics.fmean(t.r_multiple for t in trades)

    moegliche: list[Befund | None] = [
        _slippage(trades, config),
        _abweichung(trades, config),
        _spread(trades, config),
        _schnelle_stops(trades, config),
        _kontostand(trades, config),
        _ausstiege(trades),
        _richtung(trades),
    ]
    befunde = [b for b in moegliche if b is not None]
    befunde += _je_termin(trades)
    # Was Geld kostet, zuerst; danach, was auf mehr Fällen beruht.
    befunde.sort(key=lambda b: (not b.schwer, -b.faelle))
    a.befunde = befunde
    return a
