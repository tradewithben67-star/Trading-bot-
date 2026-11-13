"""Was ein Broker-Symbol bedeutet.

MetaTrader-Broker nennen dasselbe Ding unterschiedlich: XAUUSD, XAUUSD.r,
GOLD, GOLD#, XAUUSD_i. Für die Gruppe soll immer dasselbe dastehen, und
für die Pip-Rechnung muss klar sein, wie groß ein Pip in diesem Markt
ist — bei Gold sind 0,10 ein Pip, bei EUR/USD 0,0001, bei Bitcoin gibt
es gar keine.
"""

from __future__ import annotations

import re

# Anhängsel mit Trennzeichen: XAUUSD.r, XAUUSD_i, GOLD#2
MIT_TRENNER = re.compile(r"[._\-#][A-Za-z0-9]{1,5}$")
# Angehängte Ziffern direkt hinter Buchstaben: XYZ123
NUR_ZIFFERN = re.compile(r"(?<=[A-Za-z])\d+$")

# Anzeigename je bereinigtem Symbol. Was nicht drinsteht, wird so
# angezeigt, wie der Broker es nennt — lieber das als ein falscher Name.
NAMEN = {
    "XAUUSD": "GOLD",
    "GOLD": "GOLD",
    "XAGUSD": "SILBER",
    "SILVER": "SILBER",
    "XTIUSD": "ÖL",
    "USOIL": "ÖL",
    "WTI": "ÖL",
    "BTCUSD": "BTCUSD",
    "ETHUSD": "ETHUSD",
    "US30": "DOW",
    "NAS100": "NASDAQ",
    "US100": "NASDAQ",
    "SPX500": "S&P 500",
    "US500": "S&P 500",
    "GER40": "DAX",
    "DE40": "DAX",
}

# Wie groß ein Pip ist. None heißt: in diesem Markt rechnet man nicht in
# Pips — dann nennt das Signal nur Kurse und das Chance-Risiko-Verhältnis.
PIPS = {
    "XAUUSD": 0.1, "GOLD": 0.1,
    "XAGUSD": 0.01, "SILVER": 0.01,
    "XTIUSD": 0.01, "USOIL": 0.01, "WTI": 0.01,
}

# Währungspaare: vier Nachkommastellen, außer mit Yen.
WAEHRUNGEN = ("USD", "EUR", "GBP", "JPY", "CHF", "AUD", "NZD", "CAD")


def _bekannt(name: str) -> bool:
    return name in NAMEN or name in PIPS or _waehrungspaar(name)


def _waehrungspaar(name: str) -> bool:
    return (len(name) == 6
            and name[:3] in WAEHRUNGEN and name[3:] in WAEHRUNGEN)


def bereinigen(symbol: str) -> str:
    """„XAUUSD.r" und „EURUSDm" werden zu „XAUUSD" und „EURUSD".

    Blind Buchstaben am Ende abzuschneiden ist gefährlich — dabei würde
    aus „XYZ" ein „XY". Ohne Trennzeichen wird deshalb nur gekürzt, wenn
    dabei ein Symbol herauskommt, das wir kennen.
    """
    roh = str(symbol or "").strip().upper()
    if not roh:
        return ""
    if _bekannt(roh):
        return roh

    kandidat = MIT_TRENNER.sub("", roh)
    if len(kandidat) < 3:
        kandidat = roh
    if _bekannt(kandidat):
        return kandidat

    ohne_ziffern = NUR_ZIFFERN.sub("", kandidat)
    if len(ohne_ziffern) >= 3:
        kandidat = ohne_ziffern
    if _bekannt(kandidat):
        return kandidat

    # Letzter Versuch: ein oder zwei Zeichen weniger — aber nur, wenn das
    # etwas Bekanntes ergibt.
    for weniger in (1, 2):
        kuerzer = kandidat[:-weniger]
        if len(kuerzer) >= 3 and _bekannt(kuerzer):
            return kuerzer
    return kandidat


def anzeigename(symbol: str) -> str:
    """Wie das Symbol in der Gruppe heißen soll."""
    sauber = bereinigen(symbol)
    return NAMEN.get(sauber, sauber or str(symbol or "").upper())


def ist_waehrungspaar(symbol: str) -> bool:
    return _waehrungspaar(bereinigen(symbol))


def pipgroesse(symbol: str) -> float | None:
    """Wie viel Kursbewegung ein Pip ist, oder None."""
    sauber = bereinigen(symbol)
    if sauber in PIPS:
        return PIPS[sauber]
    if ist_waehrungspaar(sauber):
        return 0.01 if "JPY" in sauber else 0.0001
    return None


def nachkommastellen(symbol: str) -> int:
    """Wie viele Stellen das Signal anzeigen soll."""
    sauber = bereinigen(symbol)
    if ist_waehrungspaar(sauber):
        return 3 if "JPY" in sauber else 5
    if sauber in ("XAUUSD", "GOLD", "XTIUSD", "USOIL", "WTI"):
        return 2
    if sauber in ("XAGUSD", "SILVER"):
        return 3
    return 2
