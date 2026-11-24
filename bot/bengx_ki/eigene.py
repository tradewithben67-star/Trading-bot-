"""Eigene Indikatoren: aus einer Formel, sicher ausgewertet.

Beispiele:

    ema(close, 20)                                  eine Linie im Chart
    ema(close, 12) - ema(close, 26)                 MACD, unter dem Chart
    rsi(close, 14) < 30                             eine Bedingung
    crossover(ema(close, 50), ema(close, 200))      goldenes Kreuz
    (min(open, close) - low) > 1.5 * atr(14)        Hammer

Erlaubt sind nur die Kursreihen, Zahlen, + - * /, Vergleiche, and/or/not
und die Funktionen in `FUNKTIONEN`. Die Formel wird mit `ast` zerlegt und
Knoten für Knoten ausgerechnet; `eval` kommt nie vor. Alles andere wird
abgelehnt.

Eine Bedingung (wahr/falsch) wird zusätzlich geprüft: wie oft trifft sie
zu, und wohin ging der Kurs danach? Gemessen wie das Etikett der KI: kam
zuerst das Ziel oben oder der Stop unten, je 1,5 × ATR entfernt.
"""

from __future__ import annotations

import ast
import json
import math
import os
import threading
import uuid
from pathlib import Path
from typing import Sequence

from bengx_bot.indicators import atr as _atr
from bengx_bot.indicators import ema as _ema
from bengx_bot.indicators import rsi as _rsi
from bengx_bot.indicators import sma as _sma
from bengx_bot.model import Candle

from .merkmale import HOCH, RUNTER, ausgaenge

MAX_LAENGE = 300
MAX_PERIODE = 500
MAX_JE_NUTZER = 30
REIHEN = ("open", "high", "low", "close", "volume", "hl2", "hlc3")

VORLAGEN = [
    {"name": "EMA 20", "formel": "ema(close, 20)", "anzeige": "chart"},
    {"name": "Bollinger oben", "formel": "sma(close, 20) + 2 * stdev(close, 20)", "anzeige": "chart"},
    {"name": "Bollinger unten", "formel": "sma(close, 20) - 2 * stdev(close, 20)", "anzeige": "chart"},
    {"name": "RSI 14", "formel": "rsi(close, 14)", "anzeige": "unten"},
    {"name": "MACD", "formel": "ema(close, 12) - ema(close, 26)", "anzeige": "unten"},
    {"name": "RSI unter 30", "formel": "rsi(close, 14) < 30", "anzeige": "chart"},
    {"name": "Goldenes Kreuz", "formel": "crossover(ema(close, 50), ema(close, 200))", "anzeige": "chart"},
    {"name": "Hammer", "formel": "(min(open, close) - low) > 1.5 * atr(14) and (high - max(open, close)) < 0.3 * atr(14)", "anzeige": "chart"},
]

HILFE = {
    "sma(x, n)": "einfacher Durchschnitt über n Kerzen",
    "ema(x, n)": "gleitender Durchschnitt, neuere Kerzen zählen mehr",
    "rsi(x, n)": "Relative Stärke, 0 bis 100",
    "atr(n)": "durchschnittliche Schwankung je Kerze",
    "stdev(x, n)": "Streuung über n Kerzen",
    "highest(x, n) / lowest(x, n)": "höchster / tiefster Wert der letzten n Kerzen",
    "change(x, n)": "Veränderung gegenüber vor n Kerzen",
    "ref(x, n)": "der Wert von vor n Kerzen",
    "crossover(a, b) / crossunder(a, b)": "a kreuzt b nach oben / nach unten",
    "abs, min, max": "wie üblich",
}

Reihe = list  # list[float | None] oder list[bool | None]


class FormelFehler(ValueError):
    pass


# -- Rechenbausteine auf Reihen -------------------------------------------------

def _laenge(*werte) -> int:
    return max((len(w) for w in werte if isinstance(w, list)), default=0)


def _breit(w, n: int) -> Reihe:
    return w if isinstance(w, list) else [w] * n


def _je(f, *werte) -> Reihe | float | bool:
    """Wendet f Stelle für Stelle an; None bleibt None."""
    n = _laenge(*werte)
    if n == 0:
        return f(*werte)
    reihen = [_breit(w, n) for w in werte]
    raus = []
    for i in range(n):
        args = [r[i] for r in reihen]
        if any(a is None for a in args):
            raus.append(None)
            continue
        try:
            raus.append(f(*args))
        except (ZeroDivisionError, ValueError, OverflowError):
            raus.append(None)
    return raus


def _periode(n) -> int:
    if isinstance(n, list) or isinstance(n, bool) or not float(n).is_integer():
        raise FormelFehler("Die Periode muss eine ganze Zahl sein, z. B. 14.")
    n = int(n)
    if not 1 <= n <= MAX_PERIODE:
        raise FormelFehler(f"Die Periode muss zwischen 1 und {MAX_PERIODE} liegen.")
    return n


def _reihe(x, name: str) -> Reihe:
    if not isinstance(x, list):
        raise FormelFehler(f"{name} braucht eine Kursreihe, z. B. close.")
    return x


def _fenster(x: Reihe, n: int, f) -> Reihe:
    raus: Reihe = [None] * len(x)
    for i in range(n - 1, len(x)):
        stueck = x[i - n + 1:i + 1]
        if None not in stueck:
            raus[i] = f(stueck)
    return raus


def _mit_luecken(f, x: Reihe, n: int) -> Reihe:
    """Indikatoren des Bots erwarten lückenlose Reihen; Lücken vorn sind erlaubt."""
    start = next((i for i, v in enumerate(x) if v is not None), len(x))
    if any(v is None for v in x[start:]):
        raise FormelFehler("Diese Funktion braucht eine lückenlose Reihe.")
    return [None] * start + f(x[start:], n)


def _stdev(s: list) -> float:
    m = sum(s) / len(s)
    return math.sqrt(sum((v - m) ** 2 for v in s) / len(s))


def _kreuz(a: Reihe, b: Reihe, oben: bool) -> Reihe:
    n = _laenge(a, b)
    a, b = _breit(a, n), _breit(b, n)
    raus: Reihe = [None] * n
    for i in range(1, n):
        if None in (a[i], b[i], a[i - 1], b[i - 1]):
            continue
        raus[i] = (a[i - 1] <= b[i - 1] and a[i] > b[i]) if oben else (a[i - 1] >= b[i - 1] and a[i] < b[i])
    return raus


class _Rechner:
    def __init__(self, kerzen: Sequence[Candle]) -> None:
        self.k = kerzen
        o = [k.open for k in kerzen]
        h = [k.high for k in kerzen]
        l_ = [k.low for k in kerzen]
        c = [k.close for k in kerzen]
        self.reihen = {"open": o, "high": h, "low": l_, "close": c,
                       "volume": [k.volume for k in kerzen],
                       "hl2": [(a + b) / 2 for a, b in zip(h, l_)],
                       "hlc3": [(a + b + d) / 3 for a, b, d in zip(h, l_, c)]}
        self.schritte = 0

    def funktion(self, name: str, args: list):
        n = len(args)

        def zahl(i):
            return _periode(args[i])
        if name == "sma" and n == 2:
            return _mit_luecken(_sma, _reihe(args[0], "sma"), zahl(1))
        if name == "ema" and n == 2:
            return _mit_luecken(_ema, _reihe(args[0], "ema"), zahl(1))
        if name == "rsi" and n == 2:
            return _mit_luecken(_rsi, _reihe(args[0], "rsi"), zahl(1))
        if name == "atr" and n == 1:
            r = self.reihen
            return _atr(r["high"], r["low"], r["close"], zahl(0))
        if name == "stdev" and n == 2:
            return _fenster(_reihe(args[0], "stdev"), zahl(1), _stdev)
        if name == "highest" and n == 2:
            return _fenster(_reihe(args[0], "highest"), zahl(1), max)
        if name == "lowest" and n == 2:
            return _fenster(_reihe(args[0], "lowest"), zahl(1), min)
        if name in ("ref", "change") and n == 2:
            x, k = _reihe(args[0], name), zahl(1)
            vorher = [None] * k + x[:-k]
            return vorher if name == "ref" else _je(lambda a, b: a - b, x, vorher)
        if name == "crossover" and n == 2:
            return _kreuz(args[0], args[1], True)
        if name == "crossunder" and n == 2:
            return _kreuz(args[0], args[1], False)
        if name == "abs" and n == 1:
            return _je(abs, args[0])
        if name in ("min", "max") and n == 2:
            return _je(min if name == "min" else max, args[0], args[1])
        raise FormelFehler(f"Unbekannte Funktion oder falsche Anzahl Werte: {name}().")

    def rechne(self, knoten: ast.AST):
        self.schritte += 1
        if self.schritte > 200:
            raise FormelFehler("Die Formel ist zu verschachtelt.")
        if isinstance(knoten, ast.Expression):
            return self.rechne(knoten.body)
        if isinstance(knoten, ast.Constant) and type(knoten.value) in (int, float):
            return float(knoten.value)
        if isinstance(knoten, ast.Name):
            if knoten.id in self.reihen:
                return self.reihen[knoten.id]
            raise FormelFehler(f"Unbekannter Name: {knoten.id}. Erlaubt: {', '.join(REIHEN)}.")
        if isinstance(knoten, ast.UnaryOp) and isinstance(knoten.op, ast.USub):
            return _je(lambda a: -a, self.rechne(knoten.operand))
        if isinstance(knoten, ast.UnaryOp) and isinstance(knoten.op, ast.Not):
            return _je(lambda a: not a, self.rechne(knoten.operand))
        if isinstance(knoten, ast.BinOp):
            ops = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
                   ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b}
            f = ops.get(type(knoten.op))
            if f is None:
                raise FormelFehler("Erlaubt sind nur + - * /.")
            return _je(f, self.rechne(knoten.left), self.rechne(knoten.right))
        if isinstance(knoten, ast.Compare) and len(knoten.ops) == 1:
            ops = {ast.Gt: lambda a, b: a > b, ast.Lt: lambda a, b: a < b,
                   ast.GtE: lambda a, b: a >= b, ast.LtE: lambda a, b: a <= b}
            f = ops.get(type(knoten.ops[0]))
            if f is None:
                raise FormelFehler("Erlaubte Vergleiche: > < >= <=.")
            return _je(f, self.rechne(knoten.left), self.rechne(knoten.comparators[0]))
        if isinstance(knoten, ast.BoolOp):
            werte = [self.rechne(v) for v in knoten.values]
            f = all if isinstance(knoten.op, ast.And) else any
            return _je(lambda *a: f(a), *werte)
        if isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Name) and not knoten.keywords:
            return self.funktion(knoten.func.id, [self.rechne(a) for a in knoten.args])
        raise FormelFehler("Diesen Teil der Formel verstehe ich nicht. Erlaubt sind Kursreihen, "
                           "Zahlen, + - * /, Vergleiche, and/or/not und die Funktionen aus der Hilfe.")


def berechnen(kerzen: Sequence[Candle], formel: str) -> tuple[Reihe, bool]:
    """Rechnet die Formel über alle Kerzen. Gibt (Reihe, ist_bedingung) zurück."""
    formel = (formel or "").strip()
    if not formel:
        raise FormelFehler("Die Formel ist leer.")
    if len(formel) > MAX_LAENGE:
        raise FormelFehler(f"Die Formel ist zu lang (höchstens {MAX_LAENGE} Zeichen).")
    try:
        baum = ast.parse(formel.replace("&&", " and ").replace("||", " or "), mode="eval")
    except SyntaxError as exc:
        raise FormelFehler(f"Die Formel ist nicht lesbar: {exc.msg}.") from None
    wert = _Rechner(kerzen).rechne(baum)
    if not isinstance(wert, list):
        raise FormelFehler("Die Formel muss sich auf Kurse beziehen, z. B. ema(close, 20).")
    bedingung = any(isinstance(v, bool) for v in wert)
    return wert, bedingung


def auswerten(kerzen: Sequence[Candle], formel: str, chart_kerzen: int = 120,
              horizont: int = 24, abstand_atr: float = 1.5) -> dict:
    """Werte für den Chart und, bei einer Bedingung, was danach passierte."""
    reihe, bedingung = berechnen(kerzen, formel)
    start = len(kerzen) - chart_kerzen
    raus = {"bedingung": bedingung, "werte": reihe[start:], "aktuell": reihe[-1]}
    if not bedingung:
        letzte = next((v for v in reversed(reihe) if v is not None), None)
        raus["aktuell"] = letzte
        return raus
    treffer = [i for i, v in enumerate(reihe) if v]
    raus["treffer_chart"] = [i - start for i in treffer if i >= start]
    etiketten = ausgaenge(kerzen, horizont, abstand_atr)
    danach = [etiketten[i] for i in treffer if etiketten[i] is not None]
    alle = [e for e in etiketten if e is not None]

    def quote(liste, klasse):
        return sum(e.klasse == klasse for e in liste) / len(liste) if liste else None
    raus["statistik"] = {
        "treffer": len(treffer),
        "ausgewertet": len(danach),
        "hoch": quote(danach, HOCH), "runter": quote(danach, RUNTER),
        "hoch_sonst": quote(alle, HOCH), "runter_sonst": quote(alle, RUNTER),
        "r_long": sum(e.r_long for e in danach) / len(danach) if danach else None,
        "horizont": horizont, "abstand_atr": abstand_atr,
    }
    return raus


class Ablage:
    """Die gespeicherten Indikatoren jedes Nutzers (`ki/indikatoren.json`)."""

    def __init__(self, pfad: str | Path) -> None:
        self.pfad = Path(pfad)
        self._sperre = threading.Lock()
        self._d: dict = (json.loads(self.pfad.read_text(encoding="utf-8"))
                         if self.pfad.exists() else {})

    def _sichern(self) -> None:
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.pfad.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._d, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.pfad)

    def liste(self, nid: str) -> list[dict]:
        with self._sperre:
            return [dict(i) for i in self._d.get(nid, [])]

    def speichern(self, nid: str, name: str, formel: str, anzeige: str = "chart") -> dict:
        name = (name or "").strip()[:40]
        if not name:
            raise FormelFehler("Der Indikator braucht einen Namen.")
        if anzeige not in ("chart", "unten"):
            raise FormelFehler("Anzeige ist chart oder unten.")
        with self._sperre:
            eigene = self._d.setdefault(nid, [])
            vorhanden = next((i for i in eigene if i["name"].lower() == name.lower()), None)
            if vorhanden:
                vorhanden.update(formel=formel.strip(), anzeige=anzeige)
                eintrag = vorhanden
            else:
                if len(eigene) >= MAX_JE_NUTZER:
                    raise FormelFehler(f"Höchstens {MAX_JE_NUTZER} eigene Indikatoren.")
                eintrag = {"id": uuid.uuid4().hex[:10], "name": name,
                           "formel": formel.strip(), "anzeige": anzeige}
                eigene.append(eintrag)
            self._sichern()
            return dict(eintrag)

    def loeschen(self, nid: str, iid: str) -> None:
        with self._sperre:
            vorher = len(self._d.get(nid, []))
            self._d[nid] = [i for i in self._d.get(nid, []) if i["id"] != iid]
            if len(self._d[nid]) == vorher:
                raise FormelFehler("Indikator nicht gefunden.")
            self._sichern()

    def vergessen(self, nid: str) -> None:
        with self._sperre:
            if self._d.pop(nid, None) is not None:
                self._sichern()
