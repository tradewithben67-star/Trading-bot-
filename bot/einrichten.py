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


def chat_aus_updates(antwort: dict) -> tuple[str, str] | None:
    """Holt Chat-Kennung und Namen aus einer getUpdates-Antwort."""
    for update in antwort.get("result") or []:
        nachricht = update.get("message") or update.get("edited_message") or {}
        chat = nachricht.get("chat") or {}
        if chat.get("id") is not None:
            name = chat.get("first_name") or chat.get("username") or ""
            return str(chat["id"]), name
    return None


# ---- Netz ----------------------------------------------------------------
def telegram(token: str, methode: str, nutzlast: dict | None = None,
             frist: float = 40.0) -> dict:
    daten = json.dumps(nutzlast or {}).encode("utf-8")
    anfrage = urllib.request.Request(
        f"{API}/bot{token}/{methode}", data=daten,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(anfrage, timeout=frist) as antwort:
        return json.loads(antwort.read().decode("utf-8"))


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


def main() -> int:
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
                  + (", Google-Schlüssel vorhanden"
                     if alt.get("GOOGLE_API_KEY") else "")
                  + (", Anthropic-Schlüssel vorhanden"
                     if alt.get("ANTHROPIC_API_KEY") else ""))
            if ja("   Übernehmen?", True):
                vorlage = (VORLAGE.read_text(encoding="utf-8")
                           if VORLAGE.exists() else "")
                ENV.write_text(zusammenfuehren(vorlage, alt), encoding="utf-8")
                try:
                    os.chmod(ENV, 0o600)
                except OSError:
                    pass
                print(f"\nÜbernommen nach {ENV}")
                print("Fertig. Starten mit:  python3 -m bengx_bot telegram")
                print("(oder starten.bat doppelklicken)")
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

    # 3. Wer antwortet
    print("\n3. Wer soll antworten?")
    print("   [1] Gemini von Google — hat ein kostenloses Kontingent.")
    print("       Schlüssel unter aistudio.google.com, ohne Kreditkarte.")
    print("   [2] Claude von Anthropic — kostet Geld, antwortet gründlicher")
    print("       und kann als einziger am Code weiterbauen.")
    print("   [3] Erst mal keiner — dann gehen nur die Befehle.")
    print()
    print("   Hinweis zum kostenlosen Kontingent: Google behält sich vor,")
    print("   die Inhalte zur Verbesserung seiner Dienste auszuwerten.")
    print("   Schick also nichts durch, was niemanden angehen soll.")
    wahl = frage("   Deine Wahl [1/2/3]", "1")

    schluessel = ""
    if wahl == "1":
        print("\n   aistudio.google.com öffnen, anmelden, Schlüssel erstellen.")
        print("   Rechtsklick fügt ein. Oder Enter, dann hole ich ihn aus")
        print("   der Zwischenablage.")
        schluessel = geheimnis_abfragen("   Google-Schlüssel: ")
        if schluessel:
            werte["GOOGLE_API_KEY"] = schluessel
            werte["BENGX_ANBIETER"] = "gemini"
            print(f"   Übernommen ({maskieren(schluessel)}).")
    elif wahl == "2":
        print("\n   platform.claude.com öffnen, anmelden, Schlüssel erstellen.")
        print("   Achtung: das ist nicht dein Claude-Abo, sondern getrennt")
        print("   abgerechnet — dort muss Guthaben liegen.")
        schluessel = geheimnis_abfragen("   Anthropic-Schlüssel: ")
        if schluessel:
            werte["ANTHROPIC_API_KEY"] = schluessel
            werte["BENGX_ANBIETER"] = "claude"
            print(f"   Übernommen ({maskieren(schluessel)}).")
    if not schluessel:
        print("   Übersprungen. Du kannst den Schlüssel später in .env "
              "nachtragen.")

    # 4. Weiterbauen — geht nur mit Claude
    if wahl == "2" and schluessel:
        print("\n4. Am Code weiterbauen")
        print("   Damit startet „baue an der Website weiter“ einen Coding-Agenten,")
        print("   der hier Dateien ändert, testet und committet. Er schiebt nichts")
        print("   nach außen und hört nach 40 Schritten oder 2 Dollar auf.")
        if ja("   Einschalten?"):
            werte["BENGX_CODER"] = "1"
    elif wahl == "1" and schluessel:
        print("\n   (Am Code weiterbauen geht nur mit Claude. Mit Gemini")
        print("   notiert der Assistent stattdessen eine Aufgabe.)")

    # 5. Schreiben
    vorlage = VORLAGE.read_text(encoding="utf-8") if VORLAGE.exists() else ""
    ENV.write_text(zusammenfuehren(vorlage, werte), encoding="utf-8")
    try:
        os.chmod(ENV, 0o600)
    except OSError:
        pass
    print(f"\nGeschrieben: {ENV}")
    print("Diese Datei steht in .gitignore und bleibt auf deinem Rechner.")

    # 6. Fehlende Pakete
    fehlt = []
    gebraucht = []
    if werte.get("GOOGLE_API_KEY"):
        gebraucht.append(("google.genai", "google-genai", "Antworten über Gemini"))
    if werte.get("ANTHROPIC_API_KEY"):
        gebraucht.append(("anthropic", "anthropic", "Antworten über Claude"))
    if werte.get("BENGX_CODER") == "1":
        gebraucht.append(("claude_agent_sdk", "claude-agent-sdk",
                          "am Code weiterbauen"))
    for modul, paket, zweck in gebraucht:
        try:
            __import__(modul)
        except ImportError:
            fehlt.append((paket, zweck))
    if fehlt:
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
                    print(f"   Hat nicht geklappt. Von Hand: "
                          f"pip install {paket}")
        else:
            print("\n   Später von Hand:")
            for paket, _ in fehlt:
                print(f"   pip install {paket}")

    print("\nFertig. Starten mit:")
    print("   python3 -m bengx_bot telegram")
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
