"""Bedienung von der Kommandozeile.

    python -m bengx_ki lernprobe                          # beweist, dass sie lernt
    python -m bengx_ki trainieren --csv data/xauusd_h1.csv
    python -m bengx_ki testen     --csv data/neuere_kerzen.csv
    python -m bengx_ki vorhersage --csv data/xauusd_h1.csv
    python -m bengx_ki oberflaeche --csv data/xauusd_h1.csv   # im Browser
    python -m bengx_ki tokens --aufladen 500
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
from .training import (Einstellungen, daten_fuer, laden, speichern,
                       trainieren, wahrscheinlichkeiten)

STANDARD_MODELL = "ki/modell.pt"
HINWEIS = ("Hinweis: Das ist ein Werkzeug, keine Anlageberatung. Ohne Gebühren und "
           "Spread gerechnet; erst auf Papier handeln.")


def _plan(args: argparse.Namespace) -> Bauplan:
    return Bauplan(fenster=args.fenster, breite=args.breite, koepfe=args.koepfe,
                   schichten=args.schichten)


def _einstellungen(args: argparse.Namespace) -> Einstellungen:
    return Einstellungen(horizont=args.horizont, abstand_atr=args.abstand,
                         epochen=args.epochen, zufall=args.zufall)


def _lernen_und_berichten(kerzen, args) -> None:
    start = time.time()
    paket = trainieren(kerzen, _plan(args), _einstellungen(args))
    daten, test = paket["_daten"], paket["_test"]
    p = wahrscheinlichkeiten(paket["_gehirn"], daten.tabelle, test)
    print(f"\nFertig nach {time.time() - start:.0f}s. Test-Teil ab {paket['test_ab'][:10]}.\n")
    print(bericht(test, daten.ausgang, p))
    paket["ergebnis"] = kennzahlen(test, daten.ausgang, p)
    if args.modell:
        print(f"\nGespeichert: {speichern(paket, args.modell)}")
    print(f"\n{HINWEIS}")


def cmd_lernprobe(args) -> int:
    print("=== Lernprobe 1: Kurse MIT verstecktem Muster ===")
    print("Erwartung: die KI findet es und schlägt das Raten deutlich.\n")
    _lernen_und_berichten(lernprobe.kerzen(args.kerzen, muster=True), args)
    if args.gegenprobe:
        print("\n=== Lernprobe 2: reiner Zufall, KEIN Muster ===")
        print("Erwartung: nichts zu finden — die KI darf hier nicht glänzen.\n")
        args.modell = None
        _lernen_und_berichten(lernprobe.kerzen(args.kerzen, muster=False, zufall=11), args)
    return 0


def cmd_trainieren(args) -> int:
    kerzen = load_csv(args.csv)
    print(f"{len(kerzen)} Kerzen aus {args.csv} "
          f"({kerzen[0].ts:%Y-%m-%d} bis {kerzen[-1].ts:%Y-%m-%d})\n")
    _lernen_und_berichten(kerzen, args)
    return 0


def cmd_testen(args) -> int:
    gehirn, paket = laden(args.modell)
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

    gehirn, paket = laden(args.modell)
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
    modell = args.modell or (ordner / ("lernprobe.pt" if args.lernprobe else "modell.pt"))
    quelle = Quelle(None if args.lernprobe else args.csv, nur_lernprobe=args.lernprobe)
    starten(App(quelle, modell, ordner, epochen=args.epochen), args.port,
            browser=not args.kein_browser)
    return 0


def cmd_tokens(args) -> int:
    from .konto import Konto

    konto = Konto(Path(args.ordner) / "konto.json")
    if args.abo:
        konto.abo_wechseln(args.abo)
    if args.aufladen:
        konto.aufladen(args.aufladen, "Aufgeladen (Inhaber)")
    s = konto.stand()
    print(f"Tokens: {s['gesamt']}  (Abo {s['abo_name']}: {s['abo_rest']} von "
          f"{s['abo_monat']} · Extra: {s['extra']})")
    print(f"Nächste Auffüllung: {s['auffuellung']}")
    print("\nLetzte Buchungen:")
    for b in konto.buchungen(10):
        print(f"  {b['zeit'][:16].replace('T', ' ')}  {b['menge']:+6}  {b['text']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bengx_ki", description="BENGX KI — eigenes Gehirn für Kerzen")
    sub = ap.add_subparsers(dest="befehl", required=True)

    def lern_optionen(p):
        g = p.add_argument_group("Gehirn")
        g.add_argument("--fenster", type=int, default=64, help="Kerzen pro Blick (64)")
        g.add_argument("--breite", type=int, default=64, help="innere Breite (64)")
        g.add_argument("--koepfe", type=int, default=4, help="Aufmerksamkeits-Köpfe (4)")
        g.add_argument("--schichten", type=int, default=3, help="Blöcke (3)")
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
    p.add_argument("--modell", default=None, help="hier speichern (sonst nicht)")
    p.set_defaults(func=cmd_lernprobe)

    p = sub.add_parser("trainieren", help="aus einer Kerzen-CSV lernen")
    p.add_argument("--csv", required=True)
    p.add_argument("--modell", default=STANDARD_MODELL)
    lern_optionen(p)
    p.set_defaults(func=cmd_trainieren)

    p = sub.add_parser("testen", help="gespeichertes Modell auf neuen Kerzen prüfen")
    p.add_argument("--csv", required=True)
    p.add_argument("--modell", default=STANDARD_MODELL)
    p.set_defaults(func=cmd_testen)

    p = sub.add_parser("vorhersage", help="Einschätzung für die letzte Kerze")
    p.add_argument("--csv", required=True)
    p.add_argument("--modell", default=STANDARD_MODELL)
    p.add_argument("--schwelle", type=float, default=0.5)
    p.set_defaults(func=cmd_vorhersage)

    p = sub.add_parser("oberflaeche", help="die Oberfläche im Browser öffnen")
    p.add_argument("--csv", default="data/xauusd_h1.csv")
    p.add_argument("--lernprobe", action="store_true",
                   help="mit erfundenen Kursen statt einer CSV (zum Ausprobieren)")
    p.add_argument("--modell", default=None)
    p.add_argument("--ordner", default="ki", help="hier liegen Modell, Tokens, Verlauf (ki)")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--epochen", type=int, default=30)
    p.add_argument("--kein-browser", action="store_true")
    p.set_defaults(func=cmd_oberflaeche)

    p = sub.add_parser("tokens", help="Tokens ansehen, aufladen, Abo wechseln")
    p.add_argument("--ordner", default="ki")
    p.add_argument("--aufladen", type=int, default=0)
    p.add_argument("--abo", choices=("start", "pro", "elite"))
    p.set_defaults(func=cmd_tokens)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
