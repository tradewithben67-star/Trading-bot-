"""Signal-Bot: verteilt Bens Signale an die Telegram-Gruppen.

Zwei Stufen:

    VIP            bezahlt. Bekommt jedes Signal, mit Begründung
                   (Sweep, BOS, FVG) und dem Chance-Risiko-Verhältnis.
    Inner Circle   offen. Bekommt genau zwei Signale am Tag — eins in
                   der London-Sitzung, eins in der New-York-Sitzung —
                   ohne Begründung, mit dem Hinweis auf VIP darunter.

Nicht die ersten zwei des Tages, sondern eins je Sitzung. Sonst
entscheidet der Zufall: liegen morgens zwei schwache Signale und
nachmittags das gute, sähe der Inner Circle nur die schwachen.

Die zwei gehen zur selben Zeit raus wie an VIP, nicht später. Wer sie
nicht mithandeln kann, weil der Einstieg längst weg ist, sieht auch
nicht, dass es funktioniert — und darum geht es im Inner Circle.

Der Unterschied zu VIP ist nicht die Zeit, sondern die Menge: zwei
statt aller, und ohne die Begründung. Ein Verzug lässt sich über
TELEGRAM_INNER_VERZUG trotzdem einstellen.

Die Fenster gelten nach der Uhr dieser Maschine — Ben sitzt in
Deutschland, also deutsche Zeit. Fällt ein Signal in kein Fenster
(nachts, Asien), geht es nur an VIP.

Verschickt wird über dieselbe Bot-API wie beim Assistenten. Der Verzug
läuft ohne Hintergrundfaden: wartende Nachrichten stehen in einer Datei,
und die Abrufschleife ruft bei jedem Durchgang `faellige_senden()`. Das
überlebt einen Neustart — ein Faden im Arbeitsspeicher täte das nicht.

Zu jedem verschickten Signal wird die Nachrichtenkennung gemerkt. Das
Ergebnis (Ziel, Stop, ausgeglichen) hängt später als Antwort darunter,
sodass in der Gruppe Signal und Ausgang zusammenstehen.

Chat-Kennungen kommen aus der Umgebung, nie aus dem Repository:

    TELEGRAM_INNER_CHAT_ID   die Inner-Circle-Gruppe
    TELEGRAM_VIP_CHAT_ID     die VIP-Gruppe
    TELEGRAM_VIP_VERZUG      Minuten Vorsprung für Inner Circle (Vorgabe 5)
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

HINWEIS = "Keine Anlageberatung. Risiko selbst bestimmen."

# Steht unter jedem Gratis-Signal im Inner Circle.
WERBUNG = ("Zwei Signale am Tag gibt es hier — handel sie mit und sieh "
           "selbst. Alle anderen laufen in VIP, mit Begründung und "
           "Chance-Risiko-Verhältnis.")

STATUS_TEXT = {
    "gewonnen": "Ziel erreicht",
    "verloren": "Stop",
    "be": "ausgeglichen geschlossen",
    "offen": "läuft",
}


# ---- Einstellungen --------------------------------------------------------
@dataclass
class GruppenSettings:
    inner_chat_id: str = ""
    vip_chat_id: str = ""
    inner_verzug_min: int = 0
    # Je ein Gratis-Signal pro Fenster, in deutscher Zeit. London endet,
    # wo New York beginnt: so faellt jedes Signal in hoechstens eins.
    frei_london: str = "09:00-15:30"
    frei_newyork: str = "15:30-23:00"
    rueckblick_um: str = "23:15"        # leer schaltet ihn ab
    state_file: str = "state/gruppen.json"

    @staticmethod
    def from_env(env: dict[str, str] | None = None) -> "GruppenSettings":
        e = env if env is not None else os.environ
        try:
            verzug = int(e.get("TELEGRAM_INNER_VERZUG", "0") or 0)
        except (TypeError, ValueError):
            verzug = 0
        return GruppenSettings(
            inner_chat_id=str(e.get("TELEGRAM_INNER_CHAT_ID", "")).strip(),
            vip_chat_id=str(e.get("TELEGRAM_VIP_CHAT_ID", "")).strip(),
            inner_verzug_min=max(0, min(240, verzug)),
            frei_london=str(e.get("TELEGRAM_FREI_LONDON", "09:00-15:30")).strip()
                        or "09:00-15:30",
            frei_newyork=str(e.get("TELEGRAM_FREI_NEWYORK", "15:30-23:00")).strip()
                         or "15:30-23:00",
            rueckblick_um=str(e.get("TELEGRAM_RUECKBLICK", "23:15")).strip(),
            state_file=str(e.get("TELEGRAM_GRUPPEN_STATE", "state/gruppen.json")).strip()
            or "state/gruppen.json",
        )


@dataclass(frozen=True)
class Gruppe:
    schluessel: str
    name: str
    chat_id: str
    verzug: int            # Sekunden bis zum Versand
    ausfuehrlich: bool     # mit Begründung und CRV


# ---- Zahlen und Text ------------------------------------------------------
def de(wert: float, stellen: int = 2) -> str:
    """Deutsche Schreibweise: Komma als Dezimaltrenner, Punkt für Tausender."""
    text = f"{wert:,.{stellen}f}"
    return text.replace(",", "\u0000").replace(".", ",").replace("\u0000", ".")


def pips(von: float, bis: float, pip: float) -> float:
    return abs(bis - von) / pip


def crv(entry: float, sl: float, tp: float) -> float | None:
    risiko = abs(entry - sl)
    if risiko <= 0:
        return None
    return abs(tp - entry) / risiko


def pruefen(signal: dict[str, Any]) -> dict[str, Any]:
    """Prüft ein Signal und gibt es sauber zurück.

    Lieber hier hart werden als in der Gruppe ein Signal stehen haben, bei
    dem der Stop auf der falschen Seite liegt.
    """
    seite = str(signal.get("side", "")).strip().lower()
    if seite in ("kaufen", "buy"):
        seite = "long"
    if seite in ("verkaufen", "sell"):
        seite = "short"
    if seite not in ("long", "short"):
        raise ValueError("Seite muss long oder short sein.")

    def zahl(name: str) -> float:
        roh = signal.get(name)
        if roh is None or roh == "":
            raise ValueError(f"{name} fehlt.")
        try:
            return float(str(roh).replace(",", "."))
        except (TypeError, ValueError):
            raise ValueError(f"{name} ist keine Zahl: {roh!r}") from None

    # Mehrere Teilziele: MetaTrader kennt je Position ein TP, wer gestaffelt
    # aussteigt eroeffnet mehrere. Das naechste Ziel ist dann das erste —
    # und reicht allein, auch wenn kein einzelnes tp dabeisteht.
    ziele = [float(z) for z in (signal.get("ziele") or []) if float(z) > 0]
    entry, sl = zahl("entry"), zahl("sl")
    tp = ziele[0] if ziele else zahl("tp")
    if entry <= 0:
        raise ValueError("Einstieg muss größer als null sein.")
    if seite == "long" and not (sl < entry < tp):
        raise ValueError("Bei long muss der Stop unter und das Ziel über dem "
                         f"Einstieg liegen (Stop {de(sl)}, Einstieg {de(entry)}, "
                         f"Ziel {de(tp)}).")
    if seite == "short" and not (tp < entry < sl):
        raise ValueError("Bei short muss der Stop über und das Ziel unter dem "
                         f"Einstieg liegen (Stop {de(sl)}, Einstieg {de(entry)}, "
                         f"Ziel {de(tp)}).")

    for z in ziele[1:]:
        if seite == "long" and z <= tp:
            raise ValueError("Die weiteren Ziele müssen bei long über dem "
                             "ersten liegen.")
        if seite == "short" and z >= tp:
            raise ValueError("Die weiteren Ziele müssen bei short unter dem "
                             "ersten liegen.")

    raus = {
        "id": str(signal.get("id") or "").strip(),
        "pair": str(signal.get("pair") or "XAU/USD").strip().upper(),
        "side": seite,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "note": str(signal.get("note") or "").strip(),
    }
    if ziele:
        raus["ziele"] = ziele
    # Stellen und Symbol kommen aus der MT5-Bruecke mit; ohne sie bleibt
    # es bei Gold.
    for feld in ("stellen", "symbol"):
        if signal.get(feld) is not None:
            raus[feld] = signal[feld]
    # Bei "pip" ist None eine Aussage, kein Fehlen: in Bitcoin oder im DAX
    # rechnet niemand in Pips. Deshalb zaehlt hier, ob der Schluessel da
    # ist — sonst griffe Golds Pipgroesse und aus 1000 Dollar wuerden
    # 10.000 Pips.
    if "pip" in signal:
        raus["pip"] = signal["pip"]
    return raus


def text_signal(signal: dict[str, Any], ausfuehrlich: bool, pip: float,
                werbung: bool = False) -> str:
    """Die Nachricht für eine Gruppe."""
    richtung = "BUY" if signal["side"] == "long" else "SELL"
    markt = signal.get("pair") or "XAU/USD"
    stellen = int(signal.get("stellen") or 2)
    # In Bitcoin oder im DAX rechnet niemand in Pips. Dann nennt das
    # Signal nur Kurse und das Chance-Risiko-Verhältnis.
    pip_hier = signal.get("pip", pip)
    ziele = signal.get("ziele") or [signal["tp"]]

    zeilen = [f"BEN {markt} {richtung}", ""]
    zeilen.append(f"Einstieg  {de(signal['entry'], stellen)}")

    def mit_pips(preis: float) -> str:
        text = de(preis, stellen)
        if ausfuehrlich and pip_hier:
            text += f"   ({pips(signal['entry'], preis, pip_hier):.0f} Pips)"
        return text

    zeilen.append(f"Stop      {mit_pips(signal['sl'])}")
    if len(ziele) == 1:
        zeilen.append(f"Ziel      {mit_pips(ziele[0])}")
    else:
        for i, z in enumerate(ziele, 1):
            zeilen.append(f"TP{i}       {mit_pips(z)}")

    if ausfuehrlich:
        v = crv(signal["entry"], signal["sl"], ziele[-1])
        if v is not None:
            zeilen.append(f"CRV       {de(v, 1)}")
        if signal["note"]:
            zeilen += ["", signal["note"]]

    if werbung:
        zeilen += ["", WERBUNG]
    zeilen += ["", HINWEIS]
    return "\n".join(zeilen)


def text_ergebnis(signal: dict[str, Any], status: str, pip_zahl: float) -> str:
    richtung = "BUY" if signal.get("side") == "long" else "SELL"
    kopf = (f"BEN {signal.get('pair', 'XAU/USD')} {richtung} — "
            f"{STATUS_TEXT.get(status, status)}")
    if status == "be":
        return kopf
    return f"{kopf}\n{pip_zahl:+.0f} Pips"


# ---- Der Verteiler --------------------------------------------------------
@dataclass
class Verteiler:
    """Schickt Signale an die Gruppen und merkt sich, was wohin ging."""

    settings: GruppenSettings
    transport: Any                       # .call(methode, nutzlast)
    pip: float = 0.1
    uhr: Callable[[], float] = time.time
    _stand: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._laden()

    # ---- Gruppen ----------------------------------------------------------
    def gruppen(self) -> list[Gruppe]:
        """Nur Gruppen mit hinterlegter Kennung. Ohne Kennung kein Versand."""
        raus: list[Gruppe] = []
        if self.settings.vip_chat_id:
            raus.append(Gruppe("vip", "VIP", self.settings.vip_chat_id,
                               0, True))
        if self.settings.inner_chat_id:
            raus.append(Gruppe("inner", "Inner Circle",
                               self.settings.inner_chat_id,
                               self.settings.inner_verzug_min * 60, False))
        return raus

    def gruppe(self, schluessel: str) -> Gruppe:
        gesucht = (schluessel or "").strip().lower()
        for g in self.gruppen():
            if g.schluessel == gesucht or g.name.lower() == gesucht:
                return g
        bekannt = ", ".join(g.schluessel for g in self.gruppen()) or "keine"
        raise ValueError(f"Gruppe {schluessel!r} kenne ich nicht. "
                         f"Eingerichtet: {bekannt}.")

    # ---- Zustand ----------------------------------------------------------
    def _pfad(self) -> Path:
        return Path(self.settings.state_file)

    def _laden(self) -> None:
        p = self._pfad()
        if p.exists():
            try:
                self._stand = json.loads(p.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                self._stand = {}
        self._stand.setdefault("wartend", [])
        self._stand.setdefault("nachrichten", {})
        self._stand.setdefault("signale", {})
        self._stand.setdefault("zaehler", 0)
        self._stand.setdefault("frei", {})

    def _sichern(self) -> None:
        p = self._pfad()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".neu")
        tmp.write_text(json.dumps(self._stand, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(p)

    # ---- Gratis-Kontingent nach Sitzung -----------------------------------
    def fenster(self) -> list[tuple[str, str, int, int]]:
        """Die Sitzungsfenster als (Schlüssel, Name, von, bis) in Minuten."""
        raus = []
        for schluessel, name, spanne in (
                ("london", "London", self.settings.frei_london),
                ("newyork", "New York", self.settings.frei_newyork)):
            grenzen = _spanne_lesen(spanne)
            if grenzen:
                raus.append((schluessel, name, grenzen[0], grenzen[1]))
        return raus

    def fenster_jetzt(self) -> tuple[str, str] | None:
        """In welcher Sitzung wir gerade sind, oder None."""
        from datetime import datetime
        jetzt = datetime.fromtimestamp(self.uhr())
        minute = jetzt.hour * 60 + jetzt.minute
        for schluessel, name, von, bis in self.fenster():
            if von <= minute < bis:
                return schluessel, name
        return None

    def _frei_tag(self) -> dict[str, int]:
        frei = self._stand.setdefault("frei", {})
        eintrag = frei.get(self._tag())
        if not isinstance(eintrag, dict):      # alte Form war eine Zahl
            eintrag = {}
            frei[self._tag()] = eintrag
        return eintrag

    def _tag(self) -> str:
        """Datum nach der Uhr dieses Rechners — Ben sitzt in Deutschland."""
        from datetime import datetime
        return datetime.fromtimestamp(self.uhr()).strftime("%Y-%m-%d")

    def frei_moeglich(self) -> tuple[bool, str]:
        """Darf jetzt ein Gratis-Signal raus? Mit Begründung, wenn nicht."""
        wo = self.fenster_jetzt()
        if wo is None:
            namen = " und ".join(n for _, n, _, _ in self.fenster()) or "keine"
            return False, f"ausserhalb der Sitzungen ({namen})"
        schluessel, name = wo
        if self._frei_tag().get(schluessel, 0) >= 1:
            return False, f"das {name}-Signal von heute ist schon raus"
        return True, name

    def _frei_buchen(self) -> None:
        wo = self.fenster_jetzt()
        if wo is None:
            return
        eintrag = self._frei_tag()
        eintrag[wo[0]] = int(eintrag.get(wo[0], 0)) + 1
        # Alte Tage nicht mitschleppen.
        frei = self._stand["frei"]
        for alt in sorted(k for k in frei if k < self._tag())[:-14]:
            frei.pop(alt, None)

    # ---- Versand ----------------------------------------------------------
    def _senden(self, chat_id: str, text: str,
                antwort_auf: int | None = None) -> int | None:
        nutzlast: dict[str, Any] = {
            "chat_id": chat_id, "text": text,
            "disable_web_page_preview": True,
        }
        if antwort_auf:
            nutzlast["reply_to_message_id"] = antwort_auf
            nutzlast["allow_sending_without_reply"] = True
        antwort = self.transport.call("sendMessage", nutzlast)
        kennung = ((antwort or {}).get("result") or {}).get("message_id")
        return int(kennung) if kennung else None

    def signal_senden(self, signal: dict[str, Any]) -> dict[str, Any]:
        """Verteilt ein Signal an beide Gruppen.

        Der Inner Circle bekommt eins je Sitzung: London und New York.
        Ist das Fenster schon belegt oder liegt die Zeit ausserhalb beider
        Sitzungen, geht das Signal nur an VIP — und die Antwort sagt den
        Grund, damit Ben es weiss.
        """
        sauber = pruefen(signal)
        if not sauber["id"]:
            self._stand["zaehler"] = int(self._stand.get("zaehler", 0)) + 1
            sauber["id"] = f"sig-{self._stand['zaehler']:04d}"
        sauber["openedAt"] = _jetzt_iso(self.uhr())

        ziele = self.gruppen()
        if not ziele:
            raise RuntimeError(
                "Keine Gruppe eingerichtet. Trag TELEGRAM_INNER_CHAT_ID und "
                "TELEGRAM_VIP_CHAT_ID in bot/.env ein.")

        self._stand["signale"][sauber["id"]] = sauber
        self._stand["nachrichten"].setdefault(sauber["id"], {})

        sofort: list[str] = []
        wartet: list[str] = []
        ausgelassen: list[str] = []
        jetzt = self.uhr()
        for g in ziele:
            frei = g.schluessel == "inner"
            if frei:
                darf, grund = self.frei_moeglich()
                if not darf:
                    ausgelassen.append(f"{g.name} ({grund})")
                    continue
            text = text_signal(sauber, g.ausfuehrlich, self.pip, werbung=frei)
            if frei:
                self._frei_buchen()
            if g.verzug <= 0:
                kennung = self._senden(g.chat_id, text)
                if kennung:
                    self._stand["nachrichten"][sauber["id"]][g.schluessel] = kennung
                sofort.append(g.name)
            else:
                self._stand["wartend"].append({
                    "faellig": jetzt + g.verzug,
                    "gruppe": g.schluessel,
                    "signal": sauber["id"],
                    "text": text,
                })
                wartet.append(f"{g.name} in {g.verzug // 60} min")

        self._sichern()
        return {"id": sauber["id"], "sofort": sofort, "wartet": wartet,
                "ausgelassen": ausgelassen, "signal": sauber}

    # ---- Entwurf und Freigabe --------------------------------------------
    # Ein Signal geht an zahlende Mitglieder und ist nicht zurückzuholen.
    # Deshalb steckt die Rückfrage im Ablauf, nicht bloß in der Anweisung an
    # das Modell: erst `entwurf`, dann `freigeben`.
    def entwurf(self, signal: dict[str, Any]) -> dict[str, Any]:
        sauber = pruefen(signal)
        ziele = self.gruppen()
        if not ziele:
            raise RuntimeError(
                "Keine Gruppe eingerichtet. Trag TELEGRAM_INNER_CHAT_ID und "
                "TELEGRAM_VIP_CHAT_ID in bot/.env ein.")
        vorschau = {g.name: text_signal(sauber, g.ausfuehrlich, self.pip)
                    for g in ziele}
        self._stand["entwurf"] = {"signal": sauber, "angelegt": self.uhr()}
        self._sichern()
        return {"signal": sauber, "vorschau": vorschau,
                "gruppen": [g.name for g in ziele]}

    def freigeben(self) -> dict[str, Any]:
        entwurf = self._stand.get("entwurf")
        if not entwurf:
            raise ValueError("Es liegt kein Entwurf bereit. Erst den Entwurf "
                             "anlegen, dann freigeben.")
        if self.uhr() - float(entwurf.get("angelegt", 0)) > 3600:
            self._stand.pop("entwurf", None)
            self._sichern()
            raise ValueError("Der Entwurf ist über eine Stunde alt — zu alt "
                             "für einen Einstieg. Leg ihn neu an.")
        self._stand.pop("entwurf", None)
        return self.signal_senden(dict(entwurf["signal"]))

    def entwurf_vorschau(self) -> dict[str, str]:
        """Wie der bereitliegende Entwurf in jeder Gruppe aussähe."""
        entwurf = self._stand.get("entwurf")
        if not entwurf:
            return {}
        return {g.name: text_signal(entwurf["signal"], g.ausfuehrlich, self.pip,
                                    werbung=(g.schluessel == "inner"))
                for g in self.gruppen()}

    def entwurf_liegt(self) -> bool:
        """Wartet gerade ein Entwurf auf das Ja?"""
        return bool(self._stand.get("entwurf"))

    def entwurf_verwerfen(self) -> str:
        if not self._stand.pop("entwurf", None):
            return "Es lag kein Entwurf bereit."
        self._sichern()
        return "Entwurf verworfen, nichts verschickt."

    def faellige_senden(self) -> int:
        """Schickt, was inzwischen dran ist. Gehört in die Abrufschleife."""
        wartend = self._stand.get("wartend") or []
        if not wartend:
            return 0
        jetzt = self.uhr()
        bleibt: list[dict[str, Any]] = []
        gesendet = 0
        for eintrag in wartend:
            if float(eintrag.get("faellig", 0)) > jetzt:
                bleibt.append(eintrag)
                continue
            try:
                g = self.gruppe(str(eintrag.get("gruppe", "")))
            except ValueError:
                continue          # Gruppe wurde entfernt: Eintrag verfällt
            try:
                kennung = self._senden(g.chat_id, str(eintrag.get("text", "")))
            except ConnectionError:
                bleibt.append(eintrag)      # später noch einmal versuchen
                continue
            sig = str(eintrag.get("signal", ""))
            if kennung and sig:
                self._stand["nachrichten"].setdefault(sig, {})[g.schluessel] = kennung
            gesendet += 1
        self._stand["wartend"] = bleibt
        if gesendet or len(bleibt) != len(wartend):
            self._sichern()
        return gesendet

    def ergebnis_senden(self, signal_id: str, status: str,
                        pip_zahl: float | None = None) -> dict[str, Any]:
        """Hängt den Ausgang als Antwort unter das ursprüngliche Signal."""
        kennung = (signal_id or "").strip()
        signale = self._stand.get("signale") or {}
        if kennung not in signale:
            bekannt = ", ".join(sorted(signale)[-5:]) or "keins"
            raise ValueError(f"Signal {kennung!r} kenne ich nicht. "
                             f"Zuletzt verschickt: {bekannt}.")
        lage = str(status or "").strip().lower()
        if lage not in STATUS_TEXT:
            raise ValueError("Ergebnis muss gewonnen, verloren oder be sein.")

        signal = signale[kennung]
        if pip_zahl is None:
            if lage == "gewonnen":
                pip_zahl = pips(signal["entry"], signal["tp"], self.pip)
            elif lage == "verloren":
                pip_zahl = -pips(signal["entry"], signal["sl"], self.pip)
            else:
                pip_zahl = 0.0

        signal["status"] = lage
        signal["pips"] = round(float(pip_zahl), 1)
        signal["closedAt"] = _jetzt_iso(self.uhr())

        text = text_ergebnis(signal, lage, float(pip_zahl))
        erreicht: list[str] = []
        # Seit der Inner Circle ein Tageskontingent hat, bekommt er nicht
        # mehr jedes Signal. Ein Ergebnis zu einem Signal, das dort nie
        # stand, waere ratlos machend — also nur an die Gruppen, die es
        # wirklich bekommen haben oder noch bekommen.
        bekam = set(self._stand.get("nachrichten", {}).get(kennung, {}))
        for e in self._stand.get("wartend") or []:
            if e.get("signal") == kennung:
                bekam.add(str(e.get("gruppe", "")))
        for g in self.gruppen():
            if g.schluessel not in bekam:
                continue
            # Wartet das Signal für diese Gruppe noch, geht erst das Signal
            # raus und danach das Ergebnis — sonst steht das Ergebnis vor
            # dem Signal in der Gruppe. Der Bezug wird danach gelesen, sonst
            # hinge das Ergebnis unter nichts.
            self._nachziehen(kennung, g)
            bezug = self._stand.get("nachrichten", {}).get(kennung, {})
            self._senden(g.chat_id, text, bezug.get(g.schluessel))
            erreicht.append(g.name)
        self._sichern()
        return {"id": kennung, "status": lage, "pips": signal["pips"],
                "gruppen": erreicht}

    def _nachziehen(self, signal_id: str, g: Gruppe) -> None:
        """Holt ein noch wartendes Signal für diese Gruppe sofort nach."""
        bleibt = []
        for eintrag in self._stand.get("wartend") or []:
            if (eintrag.get("signal") == signal_id
                    and eintrag.get("gruppe") == g.schluessel):
                kennung = self._senden(g.chat_id, str(eintrag.get("text", "")))
                if kennung:
                    self._stand["nachrichten"].setdefault(
                        signal_id, {})[g.schluessel] = kennung
                continue
            bleibt.append(eintrag)
        self._stand["wartend"] = bleibt

    # ---- Mitglieder -------------------------------------------------------
    def einladung(self, gruppe: str, name: str = "", stunden: int = 24) -> str:
        """Ein Einladungslink, der genau einmal gilt."""
        g = self.gruppe(gruppe)
        try:
            dauer = max(1, min(720, int(stunden)))
        except (TypeError, ValueError):
            dauer = 24
        nutzlast: dict[str, Any] = {
            "chat_id": g.chat_id,
            "member_limit": 1,
            "expire_date": int(self.uhr()) + dauer * 3600,
        }
        if name.strip():
            nutzlast["name"] = name.strip()[:32]
        antwort = self.transport.call("createChatInviteLink", nutzlast)
        link = ((antwort or {}).get("result") or {}).get("invite_link")
        if not link:
            raise RuntimeError(
                f"Telegram hat keinen Link geliefert. Bin ich in {g.name} "
                "Administrator mit dem Recht, Nutzer einzuladen?")
        return link

    def entfernen(self, gruppe: str, user_id: str) -> str:
        """Wirft jemanden raus, ohne ihn dauerhaft zu sperren."""
        g = self.gruppe(gruppe)
        kennung = str(user_id).strip()
        if not kennung.lstrip("-").isdigit():
            raise ValueError("Dafür brauche ich die Zahlen-Kennung des Nutzers.")
        self.transport.call("banChatMember", {
            "chat_id": g.chat_id, "user_id": int(kennung),
            "revoke_messages": False})
        self.transport.call("unbanChatMember", {
            "chat_id": g.chat_id, "user_id": int(kennung),
            "only_if_banned": True})
        return f"Aus {g.name} entfernt. Mit einem neuen Link darf die Person wieder rein."

    # ---- Auskunft ---------------------------------------------------------
    def uebersicht(self) -> str:
        ziele = self.gruppen()
        if not ziele:
            return ("Keine Gruppe eingerichtet. Trag TELEGRAM_INNER_CHAT_ID "
                    "und TELEGRAM_VIP_CHAT_ID in bot/.env ein.")
        zeilen = []
        for g in ziele:
            wann = "sofort" if g.verzug <= 0 else f"nach {g.verzug // 60} min"
            tiefe = "mit Begründung" if g.ausfuehrlich else "knapp"
            zusatz = ""
            if g.schluessel == "inner":
                offen = [n for k, n, _, _ in self.fenster()
                         if self._frei_tag().get(k, 0) < 1]
                zusatz = (", noch offen: " + ", ".join(offen)) if offen \
                    else ", beide Sitzungen für heute raus"
            zeilen.append(f"{g.name}: {wann}, {tiefe}{zusatz}")
        wartend = self._stand.get("wartend") or []
        if wartend:
            jetzt = self.uhr()
            offen = sorted(max(0, float(e.get("faellig", 0)) - jetzt) for e in wartend)
            zeilen.append(f"Wartend: {len(wartend)}, nächste in "
                          f"{offen[0] / 60:.0f} min")
        return "\n".join(zeilen)

    # ---- Tagesrückblick ---------------------------------------------------
    def signale_am(self, tag: str) -> list[dict[str, Any]]:
        """Alle Signale eines Tages, älteste zuerst."""
        raus = [x for x in (self._stand.get("signale") or {}).values()
                if str(x.get("openedAt", ""))[:10] == tag]
        raus.sort(key=lambda x: str(x.get("openedAt", "")))
        return raus

    def rueckblick_text(self, tag: str, ausfuehrlich: bool) -> str:
        """Was heute lief — als Nachricht für eine Gruppe."""
        from datetime import datetime
        heute = self.signale_am(tag)
        datum = datetime.strptime(tag, "%Y-%m-%d")
        wochentage = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
        kopf = (f"Tagesrückblick · {wochentage[datum.weekday()]} "
                f"{datum.day:02d}.{datum.month:02d}.")

        if not heute:
            return kopf + "\n\nHeute kein Signal. Kein Setup heißt kein Trade."

        zu = [x for x in heute if x.get("status") in ("gewonnen", "verloren", "be")]
        gewonnen = sum(1 for x in zu if x.get("status") == "gewonnen")
        verloren = sum(1 for x in zu if x.get("status") == "verloren")
        offen = len(heute) - len(zu)
        summe = sum(float(x.get("pips") or 0) for x in zu)

        zeilen = [kopf, ""]
        zeilen.append(f"{len(heute)} Signal" + ("e" if len(heute) != 1 else ""))
        teile = []
        if gewonnen:
            teile.append(f"{gewonnen} im Ziel")
        if verloren:
            teile.append(f"{verloren} am Stop")
        if offen:
            teile.append(f"{offen} läuft noch" if offen == 1 else f"{offen} laufen noch")
        if teile:
            zeilen.append(", ".join(teile))
        if zu:
            zeilen.append(f"{summe:+.0f} Pips")

        if ausfuehrlich and zu:
            zeilen.append("")
            for x in heute:
                lage = x.get("status", "offen")
                seite = "LONG " if x.get("side") == "long" else "SHORT"
                if lage == "offen":
                    zeilen.append(f"{seite}  {de(x['entry'])}   läuft")
                else:
                    zeilen.append(f"{seite}  {de(x['entry'])}   "
                                  f"{float(x.get('pips') or 0):+.0f}  "
                                  f"{STATUS_TEXT.get(lage, lage)}")

        if not ausfuehrlich:
            # Ehrlich bleiben: der Inner Circle hat nicht alle gesehen.
            # "3 Signale, +166 Pips" ohne diesen Zusatz waere
            # schoengerechnet.
            hier = sum(1 for x in heute
                       if "inner" in (self._stand.get("nachrichten") or {})
                       .get(x.get("id", ""), {}))
            if hier < len(heute):
                zeilen.append(f"davon hier: {hier}")
            zeilen += ["", WERBUNG]
        zeilen += ["", HINWEIS]
        return "\n".join(zeilen)

    def rueckblick_faellig(self) -> bool:
        """Ist der Rückblick für heute dran und noch nicht raus?"""
        grenzen = _spanne_lesen((self.settings.rueckblick_um or "") + "-23:59")
        if not self.settings.rueckblick_um or not grenzen:
            return False
        from datetime import datetime
        jetzt = datetime.fromtimestamp(self.uhr())
        if jetzt.hour * 60 + jetzt.minute < grenzen[0]:
            return False
        return not (self._stand.get("rueckblick") or {}).get(self._tag())

    def rueckblick_senden(self, tag: str | None = None) -> dict[str, Any]:
        """Schickt den Rückblick an alle Gruppen und merkt sich den Tag."""
        tag = tag or self._tag()
        ziele = self.gruppen()
        if not ziele:
            raise RuntimeError("Keine Gruppe eingerichtet.")
        erreicht = []
        for g in ziele:
            self._senden(g.chat_id, self.rueckblick_text(tag, g.ausfuehrlich))
            erreicht.append(g.name)
        marken = self._stand.setdefault("rueckblick", {})
        marken[tag] = True
        for alt in sorted(k for k in marken if k < tag)[:-14]:
            marken.pop(alt, None)
        self._sichern()
        return {"tag": tag, "gruppen": erreicht,
                "signale": len(self.signale_am(tag))}

    def stand_text(self, anzahl: int = 5) -> str:
        """Übersicht plus die zuletzt verschickten Signale mit Kennung."""
        teile = [self.uebersicht()]
        letzte = self.letzte(anzahl)
        if letzte:
            teile += ["", "Zuletzt verschickt:"]
            for s in letzte:
                lage = s.get("status", "offen")
                p = s.get("pips")
                zusatz = (f", {p:+.0f} Pips"
                          if lage != "offen" and p is not None else "")
                teile.append(f"{s['id']}  {s['side']} {de(s['entry'])}  "
                             f"{STATUS_TEXT.get(lage, lage)}{zusatz}")
        return "\n".join(teile)

    def letzte(self, anzahl: int = 5) -> list[dict[str, Any]]:
        signale = list((self._stand.get("signale") or {}).values())
        signale.sort(key=lambda s: str(s.get("openedAt", "")), reverse=True)
        return signale[:max(1, anzahl)]


def _spanne_lesen(text: str) -> tuple[int, int] | None:
    """"09:00-15:30" -> (540, 930). Unlesbares ergibt None."""
    teile = str(text or "").replace(" ", "").split("-")
    if len(teile) != 2:
        return None
    raus = []
    for stueck in teile:
        stunde, _, minute = stueck.partition(":")
        if not stunde.isdigit() or (minute and not minute.isdigit()):
            return None
        h, m = int(stunde), int(minute or 0)
        if not (0 <= h <= 24 and 0 <= m < 60):
            return None
        raus.append(h * 60 + m)
    if raus[0] >= raus[1]:
        return None
    return raus[0], raus[1]


def _jetzt_iso(epoch: float) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds")


def aus_umgebung(env: dict[str, str] | None, transport: Any,
                 pip: float = 0.1) -> Verteiler:
    return Verteiler(GruppenSettings.from_env(env), transport, pip=pip)


def alle_schluessel() -> Iterable[str]:
    return ("inner", "vip")
