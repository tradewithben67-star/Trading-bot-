#!/usr/bin/env python3
"""Einrichtung des Telegram-Assistenten.

Einmal starten, Token einfügen, fertig:

    python3 einrichten.py

Das Programm legt die Datei .env an, prüft den Token gegen Telegram, holt
die Chat-Kennung automatisch ab und schreibt alles hinein. Nichts davon
verlässt deinen Rechner, und .env steht in .gitignore.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HIER = Path(__file__).resolve().parent
ENV = HIER / ".env"
VORLAGE = HIER / ".env.example"
API = "https://api.telegram.org"


# ---- Bausteine (ohne Netz, damit sie prüfbar sind) ----------------------
def lesen(pfad: Path) -> dict[str, str]:
    werte: dict[str, str] = {}
    if not pfad.exists():
        return werte
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        zeile = zeile.strip()
        if not zeile or zeile.startswith("#") or "=" not in zeile:
            continue
        schluessel, _, wert = zeile.partition("=")
        werte[schluessel.strip()] = wert.strip().strip('"').strip("'")
    return werte


def zusammenfuehren(vorlage: str, werte: dict[str, str]) -> str:
    """Setzt die Werte in die Vorlage ein und lässt Kommentare stehen."""
    zeilen, gesetzt = [], set()
    for zeile in vorlage.splitlines():
        blank = zeile.strip()
        if blank and not blank.startswith("#") and "=" in blank:
            schluessel = blank.split("=", 1)[0].strip()
            if schluessel in werte:
                zeilen.append(f"{schluessel}={werte[schluessel]}")
                gesetzt.add(schluessel)
                continue
        zeilen.append(zeile)
    fehlend = [k for k in werte if k not in gesetzt]
    if fehlend:
        zeilen.append("")
        for k in fehlend:
            zeilen.append(f"{k}={werte[k]}")
    return "\n".join(zeilen).rstrip() + "\n"


def maskieren(geheim: str) -> str:
    if len(geheim) <= 8:
        return "*" * len(geheim)
    return geheim[:4] + "…" + geheim[-4:]


def sieht_aus_wie_token(text: str) -> bool:
    """Ein Telegram-Token ist Zahlen, Doppelpunkt, dann ein langer Rest."""
    text = (text or "").strip()
    if ":" not in text or len(text) < 20 or len(text) > 200:
        return False
    links, _, rechts = text.partition(":")
    return links.isdigit() and len(rechts) >= 10 and " " not in text


def zwischenablage() -> str:
    """Liest die Zwischenablage — ohne Zusatzpakete, über das Bordmittel."""
    if sys.platform.startswith("win"):
        versuche = [["powershell", "-NoProfile", "-Command", "Get-Clipboard"]]
    elif sys.platform == "darwin":
        versuche = [["pbpaste"]]
    else:
        versuche = [["wl-paste"], ["xclip", "-o", "-selection", "clipboard"],
                    ["xsel", "-b"]]
    for befehl in versuche:
        try:
            fertig = subprocess.run(befehl, capture_output=True, text=True,
                                    timeout=5)
        except (OSError, subprocess.SubprocessError):
            continue
        if fertig.returncode == 0 and fertig.stdout.strip():
            return fertig.stdout.strip()
    return ""


def geheimnis_abfragen(aufforderung: str, pruefung=None) -> str:
    """Fragt etwas ab, das man eingefügt hat. Sichtbar — sonst weiß niemand,
    ob der Rechtsklick etwas getan hat. Leere Eingabe schaut in der
    Zwischenablage nach."""
    eingabe = input(aufforderung).strip()
    if eingabe:
        return eingabe
    gefunden = zwischenablage()
    if not gefunden:
        return ""
    if pruefung is not None and not pruefung(gefunden):
        return ""
    if len(gefunden) > 120:
        return ""
    print(f"   In der Zwischenablage liegt: {maskieren(gefunden)}")
    return gefunden if ja("   Das nehmen?", True) else ""


def alte_einstellungen(start: Path, tiefe: int = 3) -> list[Path]:
    """Sucht .env-Dateien aus früheren Entpackungen.

    Wer eine neue Fassung herunterlädt, hat seine Zugangsdaten schon im alten
    Ordner. Die soll er nicht noch einmal eintippen müssen.
    """
    gefunden: list[Path] = []
    ordner = start.resolve()
    for _ in range(tiefe):
        ordner = ordner.parent
        if ordner == ordner.parent:
            break
        try:
            for treffer in ordner.glob("*/bot/.env"):
                if treffer.resolve() != (start / ".env").resolve():
                    gefunden.append(treffer)
            for treffer in ordner.glob("*/*/bot/.env"):
                if treffer.resolve() != (start / ".env").resolve():
                    gefunden.append(treffer)
        except OSError:
            continue
        if gefunden:
            break
    einmalig = list(dict.fromkeys(gefunden))
    einmalig.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0,
                  reverse=True)
    return einmalig


def _weiter_so() -> str:
    """Wie es weitergeht — abhängig vom Betriebssystem."""
    if os.name == "nt":
        return ("Weiter mit:  LOSGEHTS.bat doppelklicken\n"
                "Die prüft erst, ob alles da ist, und startet dann.")
    return ("Weiter mit:  ./LOSGEHTS.command\n"
            "Die prüft erst, ob alles da ist, und startet dann.")


def _doppelt() -> None:
    print()
    print("   Es läuft noch ein zweiter Bot mit demselben Token.")
    print("   Telegram lässt immer nur einen gleichzeitig zu, deshalb")
    print("   komme ich gerade nicht an die Nachrichten heran.")
    print()
    print("   Schließ alle anderen schwarzen Fenster — auch die aus")
    print("   einer älteren Entpackung — und starte das hier neu.")
    print()


def gruppen_suchen(token: str, sekunden: int = 90) -> list[tuple[str, str]]:
    """Wartet darauf, dass in den Gruppen etwas geschrieben wird."""
    gefunden: list[tuple[str, str]] = []
    gesehen: set[str] = set()
    letzte = 0
    ende = time.time() + sekunden
    while time.time() < ende:
        try:
            antwort = telegram(token, "getUpdates",
                               {"offset": letzte, "timeout": 20}, frist=35)
        except LaeuftSchon:
            _doppelt()
            return gefunden
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
        for update in antwort.get("result") or []:
            letzte = max(letzte, int(update.get("update_id", 0)) + 1)
        for kennung, titel in gruppen_aus_updates(antwort):
            if kennung in gesehen:
                continue
            gesehen.add(kennung)
            gefunden.append((kennung, titel))
            print(f"   Gefunden: {titel}  ({kennung})")
        if len(gefunden) >= 2:
            break
        print("   … warte", flush=True)
    return gefunden


def chat_aus_updates(antwort: dict) -> tuple[str, str] | None:
    """Holt Chat-Kennung und Namen aus einer getUpdates-Antwort.

    Nur Einzelchats. Hängt der Bot schon in einer Gruppe, käme sonst deren
    Kennung als persönliche heraus — und danach würde der Bot nur noch die
    Gruppe bedienen statt Ben.
    """
    for update in antwort.get("result") or []:
        nachricht = update.get("message") or update.get("edited_message") or {}
        chat = nachricht.get("chat") or {}
        if chat.get("id") is None:
            continue
        if chat.get("type") not in (None, "private"):
            continue
        name = chat.get("first_name") or chat.get("username") or ""
        return str(chat["id"]), name
    return None


def gruppen_aus_updates(antwort: dict) -> list[tuple[str, str]]:
    """Alle Gruppen, aus denen etwas angekommen ist — ohne Doppelte."""
    raus: list[tuple[str, str]] = []
    gesehen: set[str] = set()
    for update in antwort.get("result") or []:
        nachricht = (update.get("message") or update.get("edited_message")
                     or update.get("my_chat_member") or {})
        chat = nachricht.get("chat") or {}
        if chat.get("type") not in ("group", "supergroup"):
            continue
        kennung = str(chat.get("id", ""))
        if not kennung or kennung in gesehen:
            continue
        gesehen.add(kennung)
        raus.append((kennung, chat.get("title") or kennung))
    return raus


# ---- Netz ----------------------------------------------------------------
class LaeuftSchon(Exception):
    """Ein zweiter Bot mit demselben Token hoert bereits zu.

    Telegram laesst nur einen gleichzeitig abrufen. Ohne diese Meldung
    wartet die Einrichtung 90 Sekunden ins Leere und sagt dann nur
    "Nichts angekommen" — der eigentliche Grund bleibt verborgen.
    """


def telegram(token: str, methode: str, nutzlast: dict | None = None,
             frist: float = 40.0) -> dict:
    daten = json.dumps(nutzlast or {}).encode("utf-8")
    anfrage = urllib.request.Request(
        f"{API}/bot{token}/{methode}", data=daten,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(anfrage, timeout=frist) as antwort:
            return json.loads(antwort.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 409:
            raise LaeuftSchon() from exc
        raise


# ---- Ablauf ---------------------------------------------------------------
def frage(text: str, standard: str = "") -> str:
    zusatz = f" [{standard}]" if standard else ""
    eingabe = input(f"{text}{zusatz}: ").strip()
    return eingabe or standard


def ja(text: str, standard: bool = False) -> bool:
    antwort = input(f"{text} [{'J/n' if standard else 'j/N'}]: ").strip().lower()
    if not antwort:
        return standard
    return antwort in ("j", "ja", "y", "yes")


def frage_mt5(werte: dict[str, str]) -> None:
    """Soll der Bot Trades aus MetaTrader melden?"""
    print("\nTrades aus MetaTrader melden")
    print("   Wenn das an ist, erkennt der Bot jeden Trade, den du in")
    print("   MetaTrader 5 stellst, und macht daraus ein fertiges Signal —")
    print("   in jedem Markt, nicht nur Gold.")
    print("   MetaTrader muss dafür offen und angemeldet sein.")
    print()
    if ja("   Einschalten?", werte.get("MT5") == "1"):
        werte["MT5"] = "1"
        print("\n   Soll er die Signale ohne Rückfrage verschicken?")
        print("   Nein heißt: er legt sie dir vor, du sagst ja. Sicherer —")
        print("   ein Trade, den du gleich wieder schließt, wäre sonst")
        print("   schon bei deinen zahlenden Leuten.")
        werte["MT5_OHNE_RUECKFRAGE"] = (
            "1" if ja("   Ohne Rückfrage?", False) else "0")
    else:
        werte["MT5"] = "0"


def nachtrag(werte: dict[str, str], ueberschrift: bool = True) -> bool:
    """Fragt nur nach dem, was in der .env noch gar nicht steht.

    Zwei Wege fuehren hierher: die Einrichtung uebernimmt Einstellungen aus
    einer frueheren Entpackung, oder LOSGEHTS findet eine fertige .env. In
    beiden Faellen waere eine neue Einstellung sonst nie gesetzt worden —
    und genau das ist passiert: MetaTrader blieb aus, weil nach dem
    Uebernehmen niemand mehr danach gefragt hat.
    """
    if "MT5" in werte:
        return False
    if ueberschrift:
        print("\nBENGX — eine neue Einstellung")
        print("=" * 38)
    frage_mt5(werte)
    schreiben(werte)
    pakete_nachziehen(werte)
    return True


def schreiben(werte: dict[str, str]) -> None:
    vorlage = VORLAGE.read_text(encoding="utf-8") if VORLAGE.exists() else ""
    ENV.write_text(zusammenfuehren(vorlage, werte), encoding="utf-8")
    try:
        os.chmod(ENV, 0o600)
    except OSError:
        pass
    print(f"\nGeschrieben: {ENV}")
    print("Diese Datei steht in .gitignore und bleibt auf deinem Rechner.")


def pakete_nachziehen(werte: dict[str, str]) -> None:
    """Installiert, was die gewählten Einstellungen brauchen."""
    gebraucht = []
    if werte.get("MT5") == "1":
        gebraucht.append(("MetaTrader5", "MetaTrader5",
                          "Trades aus MetaTrader lesen"))
    fehlt = []
    for modul, paket, zweck in gebraucht:
        try:
            __import__(modul)
        except ImportError:
            fehlt.append((paket, zweck))
    if not fehlt:
        return
    print("\nEs fehlen noch Pakete:")
    for paket, zweck in fehlt:
        print(f"   {paket}  —  {zweck}")
    if ja("\nSoll ich die jetzt installieren?", True):
        for paket, _ in fehlt:
            print(f"\n   Installiere {paket} ...")
            ergebnis = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--quiet", paket])
            if ergebnis.returncode == 0:
                print(f"   {paket} ist da.")
            else:
                print(f"   Hat nicht geklappt. Von Hand: pip install {paket}")
    else:
        print("\n   Später von Hand:")
        for paket, _ in fehlt:
            print(f"   pip install {paket}")


def main() -> int:
    # --nur-neues: fragt nur nach dem, was in der .env noch gar nicht
    # steht. So bekommt auch jemand, der laengst eingerichtet hat, neue
    # Einstellungen mit, ohne alles noch einmal durchzugehen.
    if "--nur-neues" in sys.argv and ENV.exists():
        werte = lesen(ENV)
        if nachtrag(werte):
            print("\nFertig.")
        return 0                          # sonst still weiter

    print("\nBENGX — Telegram-Assistent einrichten")
    print("=" * 38)

    if sys.version_info < (3, 11):
        print(f"\nPython {sys.version_info.major}.{sys.version_info.minor} ist zu alt. "
              "Gebraucht wird 3.11 oder neuer.")
        return 1

    werte = lesen(ENV)

    # Aus einer früheren Entpackung übernehmen, statt alles neu einzutippen.
    if not werte.get("TELEGRAM_TOKEN"):
        for kandidat in alte_einstellungen(HIER):
            alt = lesen(kandidat)
            if not alt.get("TELEGRAM_TOKEN"):
                continue
            print(f"\nIch habe fertige Einstellungen gefunden:")
            print(f"   {kandidat}")
            print(f"   Token {maskieren(alt['TELEGRAM_TOKEN'])}"
                  + (", Chat-Kennung " + alt["TELEGRAM_CHAT_ID"]
                     if alt.get("TELEGRAM_CHAT_ID") else "")
                  + (", beide Gruppen"
                     if alt.get("TELEGRAM_VIP_CHAT_ID")
                     and alt.get("TELEGRAM_INNER_CHAT_ID") else ""))
            if ja("   Übernehmen?", True):
                schreiben(alt)
                print("Übernommen — Token, Chat-Kennung und Gruppen stehen.")
                # Alles Neue, das es seit der alten Fassung gibt, jetzt
                # nachfragen. Frueher ging es hier sofort raus, und eine
                # neue Einstellung wurde nie gesetzt.
                nachtrag(alt, ueberschrift=False)
                print("\n" + _weiter_so())
                return 0
            break

    if werte.get("TELEGRAM_TOKEN"):
        print(f"\nEs gibt schon eine .env mit einem Token "
              f"({maskieren(werte['TELEGRAM_TOKEN'])}).")
        if not ja("Neu einrichten?"):
            print("Nichts geändert.")
            return 0

    # 1. Token
    print("\n1. Token")
    print("   In Telegram @BotFather schreiben, /newbot, Namen vergeben.")
    print("   Er antwortet mit einer Zeile wie 123456789:AAH...")
    print()
    print("   Einfügen geht in diesem Fenster mit RECHTSKLICK.")
    print("   Strg+V tut hier oft nichts — das liegt an Windows, nicht an dir.")
    print("   Oder: nur Enter drücken, dann hole ich ihn aus der Zwischenablage.")
    token = ""
    while not token:
        token = geheimnis_abfragen("   Token: ", sieht_aus_wie_token)
        if not token:
            print("   Nichts angekommen. Rechtsklick ins Fenster, dann Enter.")
            continue
        if ":" not in token:
            print("   Das sieht nicht nach einem Token aus. Noch einmal.")
            token = ""
            continue
        try:
            antwort = telegram(token, "getMe", frist=15)
        except urllib.error.HTTPError:
            print("   Telegram nimmt diesen Token nicht an. Noch einmal.")
            token = ""
            continue
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"   Keine Verbindung zu Telegram: {exc}")
            return 1
        name = (antwort.get("result") or {}).get("username", "?")
        print(f"   Passt — der Bot heißt @{name}.")
    werte["TELEGRAM_TOKEN"] = token

    # 2. Chat-Kennung
    print("\n2. Deine Chat-Kennung")
    print(f"   Schreib jetzt deinem Bot in Telegram irgendwas, zum Beispiel „hallo“.")
    print("   Ich warte darauf und trage die Kennung selbst ein.")
    kennung = ""
    ende = time.time() + 180
    letzte = 0
    while time.time() < ende:
        try:
            antwort = telegram(token, "getUpdates",
                               {"offset": letzte, "timeout": 25}, frist=40)
        except LaeuftSchon:
            _doppelt()
            break
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
        treffer = chat_aus_updates(antwort)
        if treffer:
            kennung, wer = treffer
            print(f"   Angekommen{' von ' + wer if wer else ''}. Kennung: {kennung}")
            break
        for update in antwort.get("result") or []:
            letzte = max(letzte, int(update.get("update_id", 0)) + 1)
        print("   … warte", flush=True)
    if not kennung:
        print("   Nichts angekommen. Du kannst TELEGRAM_CHAT_ID später von Hand "
              "eintragen — der Bot nennt sie dir beim ersten Schreiben.")
    werte["TELEGRAM_CHAT_ID"] = kennung

    # 3. Die Gruppen
    print("\n3. Deine Gruppen")
    print("   VIP ist bezahlt und nur auf deine Einladung: jedes Signal")
    print("   mit Begründung. Der Inner Circle ist offen für alle und")
    print("   bekommt zwei Signale am Tag — eins in der London-, eins in")
    print("   der New-York-Sitzung, gleichzeitig mit VIP, aber knapper.")
    print()
    if ja("   Hast du die Gruppen schon angelegt?", False):
        print("   Gut. Füge den Bot in JEDE Gruppe ein, mach ihn zum")
        print("   Administrator (Recht „Nutzer einladen“) und schreib dann in")
        print("   jede Gruppe irgendetwas. Ich erkenne sie.")
        gefunden = gruppen_suchen(token)
        if gefunden:
            for schluessel, beschriftung in (("TELEGRAM_INNER_CHAT_ID", "Inner Circle"),
                                             ("TELEGRAM_VIP_CHAT_ID", "VIP")):
                print()
                for i, (kennung, titel) in enumerate(gefunden, 1):
                    print(f"   [{i}] {titel}  ({kennung})")
                print("   [0] keine davon")
                wahl = frage(f"   Welche ist {beschriftung}?", "0")
                try:
                    nummer = int(wahl)
                except ValueError:
                    nummer = 0
                if 1 <= nummer <= len(gefunden):
                    werte[schluessel] = gefunden[nummer - 1][0]
                    print(f"   {beschriftung}: {gefunden[nummer - 1][1]}")
            verzug = frage("\n   Minuten Vorsprung für VIP? (0 = gleichzeitig)", "0")
            werte["TELEGRAM_INNER_VERZUG"] = verzug if verzug.isdigit() else "0"

        else:
            print("   Nichts angekommen. Steht der Bot wirklich in den Gruppen")
            print("   und hast du dort geschrieben? Du kannst die Kennungen")
            print("   später in .env eintragen.")
    else:
        print("   Kein Problem — leg sie später an. Der Signal-Bot ruht so")
        print("   lange, alles andere läuft.")

    # 4. Rückblick
    print("\n4. Tagesrückblick")
    print("   Einmal am Tag schickt der Bot von selbst eine Zusammen-")
    print("   fassung in beide Gruppen: wie viele Signale, wie viele im")
    print("   Ziel, wie viele Pips.")
    zeit = frage("   Um wie viel Uhr? (leer = aus)", "23:15")
    werte["TELEGRAM_RUECKBLICK"] = zeit

    # 5. MetaTrader
    print("\n5. ", end="")
    frage_mt5(werte)

    # 6. Schreiben und nachinstallieren
    schreiben(werte)
    pakete_nachziehen(werte)

    print("\nFertig.")
    print(_weiter_so())
    if not kennung:
        print("\nSchreib dem Bot dann einmal — er nennt dir die Kennung,")
        print("die du bei TELEGRAM_CHAT_ID einträgst.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nAbgebrochen. Nichts geschrieben.")
        raise SystemExit(130)
