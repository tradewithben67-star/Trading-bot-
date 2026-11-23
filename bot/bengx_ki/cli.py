"""Bedienung von der Kommandozeile.

    python -m bengx_ki lernprobe                          # beweist, dass sie lernt
    python -m bengx_ki trainieren --csv data/xauusd_h1.csv
    python -m bengx_ki testen     --csv data/neuere_kerzen.csv
    python -m bengx_ki vorhersage --csv data/xauusd_h1.csv
"""

from __future__ import annotations

import argparse
import sys
import time

import torch

from bengx_bot.data import load_csv

from . import lernprobe
from .auswertung import bericht
from .gehirn import Bauplan
from .merkmale import HOCH, KLASSEN, RUNTER
from .training import (Einstellungen, daten_fuer, erste_stelle, laden, speichern,
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
    from bengx_bot.indicators import atr
    from .training import normieren, tabelle_bauen

    gehirn, paket = laden(args.modell)
    kerzen = load_csv(args.csv)
    if len(kerzen) <= erste_stelle(paket["plan"]["fenster"]):
        print("Zu wenig Kerzen für eine Vorhersage.")
        return 1
    tabelle = normieren(tabelle_bauen(kerzen), torch.tensor(paket["mittel"]),
                        torch.tensor(paket["streuung"]))
    letzte = len(kerzen) - 1
    p = wahrscheinlichkeiten(gehirn, tabelle, [letzte])[0]
    k = kerzen[letzte]
    a = atr([x.high for x in kerzen], [x.low for x in kerzen],
            [x.close for x in kerzen], 14)[letzte]
    weg = paket["abstand_atr"] * a

    print(f"Letzte Kerze: {k.ts:%Y-%m-%d %H:%M} UTC, Schluss {k.close:.2f}")
    print(f"Blick nach vorn: {paket['horizont']} Kerzen, Stop/Ziel je {weg:.2f} entfernt\n")
    for i, name in enumerate(KLASSEN):
        balken = "█" * round(p[i].item() * 40)
        print(f"  {name:<10} {p[i].item():6.1%}  {balken}")
    print()
    hoch, runter = p[HOCH].item(), p[RUNTER].item()
    if hoch >= args.schwelle and hoch > runter:
        print(f"→ KAUFEN-Idee: Stop {k.close - weg:.2f} · Ziel {k.close + weg:.2f}")
    elif runter >= args.schwelle and runter > hoch:
        print(f"→ VERKAUFEN-Idee: Stop {k.close + weg:.2f} · Ziel {k.close - weg:.2f}")
    else:
        print(f"→ Kein Signal: die KI ist sich unter {args.schwelle:.0%} sicher.")
    print(f"\n{HINWEIS}")
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

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
