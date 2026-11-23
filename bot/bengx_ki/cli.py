"""Bedienung von der Kommandozeile.

    python -m bengx_ki lernprobe                          # beweist, dass sie lernt
    python -m bengx_ki trainieren --csv data/xauusd_h1.csv --modell max
    python -m bengx_ki testen     --csv data/neuere_kerzen.csv --modell mini
    python -m bengx_ki vorhersage --csv data/xauusd_h1.csv
    python -m bengx_ki oberflaeche --csv data/xauusd_h1.csv   # im Browser
    python -m bengx_ki nutzer anlegen Anna --abo pro
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from bengx_bot.data import load_csv

from . import lernprobe
from .auswertung import bericht, kennzahlen
from .gehirn import Bauplan
from .modelle import MODELLE, STANDARD
from .training import (Einstellungen, daten_fuer, laden, speichern,
                       trainieren, wahrscheinlichkeiten)

ORDNER = Path("ki")
HINWEIS = ("Hinweis: Das ist ein Werkzeug, keine Anlageberatung. Ohne Gebühren und "
           "Spread gerechnet; erst auf Papier handeln.")


def _plan(args: argparse.Namespace) -> Bauplan:
    """Bauplan des gewählten Modells; einzelne Werte lassen sich überschreiben."""
    plan = dict(MODELLE[args.modell]["plan"])
    for k in ("fenster", "breite", "koepfe", "schichten"):
        if getattr(args, k) is not None:
            plan[k] = getattr(args, k)
    return Bauplan(**plan)


def umziehen(ordner: Path) -> None:
    """Das Modell aus der ersten Fassung (ki/modell.pt) wird zu Standard."""
    alt, neu = ordner / "modell.pt", ordner / "modelle" / f"{STANDARD}.pt"
    if alt.exists() and not neu.exists():
        neu.parent.mkdir(parents=True, exist_ok=True)
        alt.rename(neu)
        print(f"Altes Modell übernommen als {MODELLE[STANDARD]['name']}: {neu}")


def _datei(args: argparse.Namespace) -> Path:
    if args.datei:
        return Path(args.datei)
    umziehen(ORDNER)
    return ORDNER / "modelle" / f"{args.modell}.pt"


def _einstellungen(args: argparse.Namespace) -> Einstellungen:
    return Einstellungen(horizont=args.horizont, abstand_atr=args.abstand,
                         epochen=args.epochen, zufall=args.zufall)


def _lernen_und_berichten(kerzen, args) -> None:
    start = time.time()
    print(f"Modell: {MODELLE[args.modell]['name']}\n")
    paket = trainieren(kerzen, _plan(args), _einstellungen(args))
    daten, test = paket["_daten"], paket["_test"]
    p = wahrscheinlichkeiten(paket["_gehirn"], daten.tabelle, test)
    print(f"\nFertig nach {time.time() - start:.0f}s. Test-Teil ab {paket['test_ab'][:10]}.\n")
    print(bericht(test, daten.ausgang, p))
    paket["ergebnis"] = kennzahlen(test, daten.ausgang, p)
    paket["modell"] = args.modell
    ziel = _datei(args) if args.speichern else None
    if ziel:
        print(f"\nGespeichert: {speichern(paket, ziel)}")
    print(f"\n{HINWEIS}")


def cmd_lernprobe(args) -> int:
    args.speichern = bool(args.datei)
    print("=== Lernprobe 1: Kurse MIT verstecktem Muster ===")
    print("Erwartung: die KI findet es und schlägt das Raten deutlich.\n")
    _lernen_und_berichten(lernprobe.kerzen(args.kerzen, muster=True), args)
    if args.gegenprobe:
        print("\n=== Lernprobe 2: reiner Zufall, KEIN Muster ===")
        print("Erwartung: nichts zu finden — die KI darf hier nicht glänzen.\n")
        args.speichern = False
        _lernen_und_berichten(lernprobe.kerzen(args.kerzen, muster=False, zufall=11), args)
    return 0


def cmd_trainieren(args) -> int:
    args.speichern = True
    kerzen = load_csv(args.csv)
    print(f"{len(kerzen)} Kerzen aus {args.csv} "
          f"({kerzen[0].ts:%Y-%m-%d} bis {kerzen[-1].ts:%Y-%m-%d})\n")
    _lernen_und_berichten(kerzen, args)
    return 0


def cmd_testen(args) -> int:
    gehirn, paket = laden(_datei(args))
    daten = daten_fuer(load_csv(args.csv), paket)
    if not daten.stellen:
        print("Zu wenig Kerzen zum Testen.")
        return 1
    print(f"Modell vom {paket['erstellt'][:10]}, gelernt bis {paket['test_ab'][:10]}.")
    print("Aussagekräftig ist nur, was NACH diesem Datum liegt.\n")
    p = wahrscheinlichkeiten(gehirn, daten.tabelle, daten.stellen)
    print(bericht(daten.stellen, daten.ausgang, p))
    print(f"\n{HINWEIS}")
    return 0


def cmd_vorhersage(args) -> int:
    from .dienste import analyse

    gehirn, paket = laden(_datei(args))
    d = analyse(load_csv(args.csv), gehirn, paket, args.schwelle)
    print(f"Letzte Kerze: {d['kerze'][:16].replace('T', ' ')} UTC, Schluss {d['schluss']:.2f}")
    print(f"Blick nach vorn: {d['horizont']} Kerzen, Stop/Ziel je {d['abstand']:.2f} entfernt\n")
    for name, wert in d["wahrscheinlichkeiten"].items():
        print(f"  {name:<10} {wert:6.1%}  {'█' * round(wert * 40)}")
    print()
    i = d["idee"]
    if i:
        print(f"→ {i['richtung'].upper()}-Idee: Stop {i['stop']:.2f} · Ziel {i['ziel']:.2f}")
    else:
        print(f"→ Kein Signal: die KI ist sich unter {args.schwelle:.0%} sicher.")
    print(f"\n{HINWEIS}")
    return 0


def cmd_oberflaeche(args) -> int:
    from .dienste import Quelle
    from .server import App, starten

    ordner = Path(args.ordner)
    umziehen(ordner)
    modelle = ordner / ("lernprobe-modelle" if args.lernprobe else "modelle")
    quelle = Quelle(None if args.lernprobe else args.csv, nur_lernprobe=args.lernprobe)
    starten(App(quelle, ordner, modelle, epochen=args.epochen), args.port,
            browser=not args.kein_browser, offen=args.offen)
    return 0


def cmd_nutzer(args) -> int:
    import getpass

    from .konto import Nutzung
    from .nutzer import Nutzerliste

    ordner = Path(args.ordner)
    liste = Nutzerliste(ordner / "nutzer.json")
    nutzung = Nutzung(ordner / "nutzung.json")

    def finden(name: str) -> dict:
        n = next((n for n in liste.liste() if n["name"].lower() == name.lower()), None)
        if n is None:
            raise ValueError(f"Keinen Nutzer {name} gefunden.")
        return n

    def passwort() -> str:
        pw = getpass.getpass("Passwort: ")
        if pw != getpass.getpass("Noch einmal: "):
            raise ValueError("Die Passwörter sind verschieden.")
        return pw

    if args.aktion == "anlegen":
        n = liste.anlegen(args.name, passwort(), args.abo)
        print(f"Angelegt: {n['name']} ({'Inhaber' if n['rolle'] == 'inhaber' else 'Abo ' + n['abo']})")
    elif args.aktion == "abo":
        n = liste.abo_setzen(finden(args.name)["id"], args.abo)
        print(f"{n['name']} hat jetzt das Abo {n['abo']}.")
    elif args.aktion == "passwort":
        liste.passwort_setzen(finden(args.name)["id"], passwort())
        print("Passwort geändert.")
    elif args.aktion == "loeschen":
        n = finden(args.name)
        liste.loeschen(n["id"])
        nutzung.vergessen(n["id"])
        print(f"{n['name']} gelöscht.")

    print()
    for n in liste.liste():
        s = nutzung.stand(n)
        teile = []
        for m in s["modelle"].values():
            if m["gesperrt"]:
                teile.append(f"{m['name']} gesperrt")
            elif m["limit"] is None:
                teile.append(f"{m['name']} {m['verbraucht']}/∞")
            else:
                teile.append(f"{m['name']} {m['verbraucht']}/{m['limit']}")
        print(f"  {n['name']:<20} {s['abo_name']:<8} " + " · ".join(teile))
    if not liste.liste():
        print("  Noch keine Nutzer. Der erste wird Inhaber.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bengx_ki", description="BENGX KI — eigenes Gehirn für Kerzen")
    sub = ap.add_subparsers(dest="befehl", required=True)

    def modell_optionen(p):
        p.add_argument("--modell", choices=list(MODELLE), default=STANDARD,
                       help="mini, standard oder max (standard)")
        p.add_argument("--datei", default=None,
                       help="eigener Speicherort (sonst ki/modelle/MODELL.pt)")

    def lern_optionen(p):
        modell_optionen(p)
        g = p.add_argument_group("Gehirn (überschreibt das gewählte Modell)")
        g.add_argument("--fenster", type=int, default=None, help="Kerzen pro Blick")
        g.add_argument("--breite", type=int, default=None, help="innere Breite")
        g.add_argument("--koepfe", type=int, default=None, help="Aufmerksamkeits-Köpfe")
        g.add_argument("--schichten", type=int, default=None, help="Blöcke")
        t = p.add_argument_group("Lernen")
        t.add_argument("--horizont", type=int, default=24, help="Kerzen bis Zeitstop (24)")
        t.add_argument("--abstand", type=float, default=1.5, help="Stop/Ziel in ATR (1.5)")
        t.add_argument("--epochen", type=int, default=30, help="höchstens so viele Durchgänge (30)")
        t.add_argument("--zufall", type=int, default=1, help="Startwert für den Zufall")

    p = sub.add_parser("lernprobe", help="auf erfundenen Kursen mit verstecktem Muster lernen")
    lern_optionen(p)
    p.add_argument("--kerzen", type=int, default=12000)
    p.add_argument("--gegenprobe", action="store_true",
                   help="zusätzlich auf reinem Zufall lernen (darf nichts finden)")
    p.set_defaults(func=cmd_lernprobe)

    p = sub.add_parser("trainieren", help="aus einer Kerzen-CSV lernen")
    p.add_argument("--csv", required=True)
    lern_optionen(p)
    p.set_defaults(func=cmd_trainieren)

    p = sub.add_parser("testen", help="gespeichertes Modell auf neuen Kerzen prüfen")
    p.add_argument("--csv", required=True)
    modell_optionen(p)
    p.set_defaults(func=cmd_testen)

    p = sub.add_parser("vorhersage", help="Einschätzung für die letzte Kerze")
    p.add_argument("--csv", required=True)
    modell_optionen(p)
    p.add_argument("--schwelle", type=float, default=0.5)
    p.set_defaults(func=cmd_vorhersage)

    p = sub.add_parser("oberflaeche", help="die Oberfläche im Browser öffnen")
    p.add_argument("--csv", default="data/xauusd_h1.csv")
    p.add_argument("--lernprobe", action="store_true",
                   help="mit erfundenen Kursen statt einer CSV (zum Ausprobieren)")
    p.add_argument("--ordner", default="ki", help="Modelle, Nutzer, Nutzung, Verlauf (ki)")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--epochen", type=int, default=30)
    p.add_argument("--offen", action="store_true",
                   help="auch aus dem Netz erreichbar (fürs Internet nur hinter HTTPS)")
    p.add_argument("--kein-browser", action="store_true")
    p.set_defaults(func=cmd_oberflaeche)

    p = sub.add_parser("nutzer", help="Nutzer ansehen, anlegen, Abo ändern")
    p.add_argument("--ordner", default="ki")
    nsub = p.add_subparsers(dest="aktion")
    q = nsub.add_parser("anlegen", help="neuer Nutzer (der erste wird Inhaber)")
    q.add_argument("name")
    q.add_argument("--abo", choices=("start", "pro", "elite"), default="start")
    q = nsub.add_parser("abo", help="Abo eines Nutzers ändern")
    q.add_argument("name")
    q.add_argument("abo", choices=("start", "pro", "elite"))
    q = nsub.add_parser("passwort", help="Passwort neu setzen")
    q.add_argument("name")
    q = nsub.add_parser("loeschen", help="Nutzer löschen")
    q.add_argument("name")
    p.set_defaults(func=cmd_nutzer)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
