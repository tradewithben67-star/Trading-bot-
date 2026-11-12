"""Signal-Bot: verteilt Bens Signale an die Telegram-Gruppen.

Zwei Stufen:

    VIP            bezahlt. Bekommt jedes Signal sofort, mit Begründung
                   (Sweep, BOS, FVG) und dem Chance-Risiko-Verhältnis.
    Inner Circle   offen. Bekommt höchstens zwei Signale am Tag, mit
                   Verzug, ohne Begründung, und darunter den Hinweis auf
                   VIP. Das Schaufenster, nicht das Produkt.

Mehr als die zwei bekommt der Inner Circle nicht: sonst wäre VIP
wertlos. Der Zähler läuft nach Berliner Datum und steht in derselben
Datei wie der Rest.

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
WERBUNG = ("Zwei Signale am Tag gibt es hier. Alle anderen, sofort und "
           "mit Begründung, laufen in VIP.")

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
    inner_verzug_min: int = 20
    inner_pro_tag: int = 2
    state_file: str = "state/gruppen.json"

    @staticmethod
    def from_env(env: dict[str, str] | None = None) -> "GruppenSettings":
        e = env if env is not None else os.environ
        try:
            verzug = int(e.get("TELEGRAM_INNER_VERZUG", "20") or 20)
        except (TypeError, ValueError):
            verzug = 20
        try:
            frei = int(e.get("TELEGRAM_INNER_PRO_TAG", "2") or 2)
        except (TypeError, ValueError):
            frei = 2
        return GruppenSettings(
            inner_chat_id=str(e.get("TELEGRAM_INNER_CHAT_ID", "")).strip(),
            vip_chat_id=str(e.get("TELEGRAM_VIP_CHAT_ID", "")).strip(),
            inner_verzug_min=max(0, min(240, verzug)),
            inner_pro_tag=max(0, min(20, frei)),
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

    entry, sl, tp = zahl("entry"), zahl("sl"), zahl("tp")
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

    return {
        "id": str(signal.get("id") or "").strip(),
        "pair": str(signal.get("pair") or "XAU/USD").strip().upper(),
        "side": seite,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "note": str(signal.get("note") or "").strip(),
    }


def text_signal(signal: dict[str, Any], ausfuehrlich: bool, pip: float,
                werbung: bool = False) -> str:
    """Die Nachricht für eine Gruppe."""
    seite = "LONG" if signal["side"] == "long" else "SHORT"
    sl_p = pips(signal["entry"], signal["sl"], pip)
    tp_p = pips(signal["entry"], signal["tp"], pip)

    zeilen = [f"{signal['pair']} · {seite}", ""]
    if ausfuehrlich:
        zeilen += [
            f"Einstieg  {de(signal['entry'])}",
            f"Stop      {de(signal['sl'])}   ({sl_p:.0f} Pips)",
            f"Ziel      {de(signal['tp'])}   ({tp_p:.0f} Pips)",
        ]
        v = crv(signal["entry"], signal["sl"], signal["tp"])
        if v is not None:
            zeilen.append(f"CRV       {de(v, 1)}")
        if signal["note"]:
            zeilen += ["", signal["note"]]
    else:
        zeilen += [
            f"Einstieg  {de(signal['entry'])}",
            f"Stop      {de(signal['sl'])}",
            f"Ziel      {de(signal['tp'])}",
        ]
    if werbung:
        zeilen += ["", WERBUNG]
    zeilen += ["", HINWEIS]
    return "\n".join(zeilen)


def text_ergebnis(signal: dict[str, Any], status: str, pip_zahl: float) -> str:
    seite = "LONG" if signal.get("side") == "long" else "SHORT"
    kopf = f"{signal.get('pair', 'XAU/USD')} · {seite} — {STATUS_TEXT.get(status, status)}"
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

    # ---- Gratis-Kontingent ------------------------------------------------
    def _tag(self) -> str:
        """Datum nach der Uhr dieses Rechners — Ben sitzt in Deutschland."""
        from datetime import datetime
        return datetime.fromtimestamp(self.uhr()).strftime("%Y-%m-%d")

    def frei_heute(self) -> int:
        return int((self._stand.get("frei") or {}).get(self._tag(), 0))

    def frei_offen(self) -> int:
        return max(0, self.settings.inner_pro_tag - self.frei_heute())

    def _frei_buchen(self) -> None:
        tag = self._tag()
        frei = self._stand.setdefault("frei", {})
        frei[tag] = int(frei.get(tag, 0)) + 1
        # Alte Tage nicht mitschleppen.
        for alt in [k for k in frei if k < tag][:-14]:
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
        """Verteilt ein Signal: VIP sofort, Inner Circle nach Verzug.

        Der Inner Circle bekommt höchstens `inner_pro_tag` Signale am Tag.
        Ist das Kontingent aufgebraucht, geht das Signal nur an VIP — und
        die Antwort sagt das, damit Ben es weiß.
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
            if frei and self.frei_offen() <= 0:
                ausgelassen.append(
                    f"{g.name} (die {self.settings.inner_pro_tag} für heute sind raus)")
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
                zusatz = (f", noch {self.frei_offen()} von "
                          f"{self.settings.inner_pro_tag} heute frei")
            zeilen.append(f"{g.name}: {wann}, {tiefe}{zusatz}")
        wartend = self._stand.get("wartend") or []
        if wartend:
            jetzt = self.uhr()
            offen = sorted(max(0, float(e.get("faellig", 0)) - jetzt) for e in wartend)
            zeilen.append(f"Wartend: {len(wartend)}, nächste in "
                          f"{offen[0] / 60:.0f} min")
        return "\n".join(zeilen)

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


def _jetzt_iso(epoch: float) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds")


def aus_umgebung(env: dict[str, str] | None, transport: Any,
                 pip: float = 0.1) -> Verteiler:
    return Verteiler(GruppenSettings.from_env(env), transport, pip=pip)


def alle_schluessel() -> Iterable[str]:
    return ("inner", "vip")
