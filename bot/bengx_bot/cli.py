"""Kommandozeile.

    python -m bengx_bot selftest                  Mechanik auf erfundenen Daten prüfen
    python -m bengx_bot backtest --csv daten.csv  Regelwerk nachrechnen
    python -m bengx_bot backtest --save           Bericht ablegen (Freigabe für live)
    python -m bengx_bot paper --once              einen Durchlauf auf dem Papierkonto
    python -m bengx_bot paper --loop              durchgängig laufen lassen
    python -m bengx_bot report                    Zahlen aus dem Protokoll
    python -m bengx_bot export                    signals.json neu schreiben
    python -m bengx_bot rules                     das Regelwerk im Klartext
    python -m bengx_bot --bot swing rules         das Regelwerk des Swing-Bots

Welcher Bot läuft, steht in der Konfiguration unter [bot] name und lässt sich
mit --bot überschreiben. Der Dauerläufer arbeitet auf Stundenkerzen, der
Swing-Bot auf Minutenkerzen, aus denen er 5m und 1h selbst rechnet.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .backtest import run_backtest
from .config import Config
from .data import load_csv, synthetic
from .journal import Journal, signals_payload, stats, write_signals
from .runner import LiveGateError, Runner, backtest_path


def _load(args) -> Config:
    cfg = Config.load(args.config)
    if getattr(args, "csv", None):
        cfg.data.csv = args.csv
    if getattr(args, "bot", None):
        cfg.bot.name = args.bot
    cfg.validate()
    return cfg


def _candles(cfg: Config, args):
    if getattr(args, "synthetic", None):
        print(f"Erfundene Kerzen ({args.synthetic}) — nur zur Prüfung der Mechanik.\n",
              file=sys.stderr)
        return synthetic(args.synthetic, seed=getattr(args, "seed", 7))
    return load_csv(cfg.data.csv)


def cmd_backtest(args) -> int:
    cfg = _load(args)
    result = run_backtest(cfg, _candles(cfg, args))
    print(result.report())
    if args.save:
        if getattr(args, "synthetic", None):
            print("\nNicht gespeichert: ein Backtest auf erfundenen Daten ist keine "
                  "Freigabe.", file=sys.stderr)
            return 2
        p = backtest_path(cfg)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
                     encoding="utf-8")
        print(f"\nBericht gespeichert: {p}")
    if args.json:
        Path(args.json).write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Daten geschrieben: {args.json}")
    return 0


def cmd_paper(args) -> int:
    cfg = _load(args)
    runner = Runner(cfg, live=False)
    if args.loop:
        runner.loop(args.interval)
        return 0
    print(json.dumps(runner.tick(), ensure_ascii=False, indent=2))
    return 0


def cmd_live(args) -> int:
    cfg = _load(args)
    try:
        Runner(cfg, live=True)
    except LiveGateError as exc:
        print(f"Live-Betrieb gesperrt.\n\n{exc}", file=sys.stderr)
        return 3
    return 0


def cmd_report(args) -> int:
    cfg = _load(args)
    trades = Journal(cfg.live.journal).load()
    if not trades:
        print("Noch keine Trades im Protokoll.")
        return 0
    s = stats(trades)
    pct = lambda v: "—" if v is None else f"{v * 100:.1f} %"
    print(f"Trades          {s['trades']}  ({s['wins']} Plus, {s['losses']} Minus)")
    print(f"Trefferquote    {pct(s['winrate'])}")
    print(f"Pips gesamt     {s['total_pips']:+.1f}")
    print(f"Ergebnis        {s['net_pnl']:+.2f}")
    print(f"Profitfaktor    {s['profit_factor']}")
    print(f"Erwartungswert  {s['expectancy_r']} R je Trade")
    return 0


def cmd_export(args) -> int:
    cfg = _load(args)
    trades = Journal(cfg.live.journal).load()
    out = args.out or str(Path(cfg.live.journal).parent / cfg.live.signals_out)
    p = write_signals(out, signals_payload(trades, pip=cfg.market.pip))
    print(f"{len(trades)} Signale geschrieben: {p}")
    return 0


def _rules_swing(cfg: Config) -> None:
    w, r = cfg.swing, cfg.risk
    print(f"""Swing — Regelwerk {cfg.fingerprint()}

Vier Stufen, jede auf ihrem Zeitrahmen, jede mit einer Frist:

  1h  Liquidität abgeräumt
      Eine Stundenkerze sticht unter das jüngste offene Swing-Tief
      (Fraktal {w.swing_lookback_h1}) und schließt wieder darüber.
      Short spiegelbildlich. Danach {w.continuation_window_minutes} Minuten Zeit für:

  5m  Fortsetzungskerze
      Körper mindestens {w.min_continuation_body:.0%} der Spanne, Schluss über dem
      Hoch der Vorkerze (Short: unter dem Tief).
      Danach {w.trigger_window_minutes} Minuten Zeit für:

  1m  Struktur oder Lücke
      Bruch der Struktur (Schluss über dem letzten bestätigten Swing-Hoch,
      Fraktal {w.swing_lookback_m1}) oder eine Fair-Value-Gap ab {w.min_gap_pips:g} Pips.
      Danach {w.entry_window_minutes} Minuten Zeit für:

  1m  Einstieg
      {"Pullback in die Lücke, Limit bei " + format(w.entry_fill, ".0%") + " der Gap" if w.allow_pullback else "Pullback: aus"}
      {"IFVG: Schluss durch eine gegenläufige Lücke, Einstieg zum Schluss" if w.allow_ifvg else "IFVG: aus"}

Läuft eine Frist ab oder kommt ein neuer Sweep, beginnt alles von vorn.

Nach dem Einstieg:
  Stop         {w.stop_source} + {w.stop_buffer_pips:g} Pips Puffer,
               erlaubt zwischen {w.min_stop_pips:g} und {w.max_stop_pips:g} Pips
  Teilziel     {w.partial_r:g} R, dort {w.partial_fraction:.0%} raus, Rest auf Einstand
  Endziel      {"das abgeräumte Niveau" if w.target_mode == "liquidity" else format(w.target_r, "g") + " R"}
  Trailing     {w.trail_atr:g} × ATR, nur enger
  Haltedauer   höchstens {w.max_hold_minutes} Minuten
  Handelszeit  {w.session_start_hour:02d}:00 bis {w.session_end_hour:02d}:00 UTC,
               freitags bis {w.friday_cutoff_hour:02d}:00

Risiko (steht über der Strategie):
  je Trade     {r.risk_per_trade:.2%} des Kontos
  Positionen   höchstens {r.max_positions} gleichzeitig
  Tagesverlust Schluss ab {r.daily_loss_limit:.1%}
  Drawdown     ab {r.drawdown_halve:.1%} halbe Größe, ab {r.drawdown_stop:.1%} kein Einstieg
  Not-Aus      Datei {cfg.live.killswitch_file} anlegen

Der Swing-Bot braucht Minutenkerzen: 5m und 1h rechnet er selbst daraus.""")


def cmd_rules(args) -> int:
    cfg = _load(args)
    if cfg.bot.name == "swing":
        _rules_swing(cfg)
        return 0
    s, r = cfg.strategy, cfg.risk
    print(f"""Dauerläufer — Regelwerk {cfg.fingerprint()}

Ein Signal entsteht nur, wenn alles zugleich zutrifft:
  Trend        Kurs über EMA({s.trend_ema}) und EMA steigt über {s.trend_slope_bars} Kerzen
               (für Short jeweils umgekehrt)
  Stärke       ADX({s.adx_period}) mindestens {s.adx_min:g}
  Volatilität  ATR({s.atr_period}) zwischen {s.min_atr_pips:g} und {s.max_atr_pips:g} Pips
  Handelszeit  {s.session_start_hour:02d}:00 bis {s.session_end_hour:02d}:00 UTC,
               freitags nur bis {s.friday_cutoff_hour:02d}:00, nie am Wochenende
  Ausbruch     Schluss über dem Hoch der letzten {s.breakout} Kerzen (Short: unter dem Tief)

Nach dem Einstieg:
  Stop         {s.stop_atr:g} × ATR vom Einstieg
  Teilziel     {s.partial_r:g} R, dort {s.partial_fraction:.0%} raus, Rest auf Einstand
  Trailing     danach {s.trail_atr:g} × ATR vom Extrem, nur enger, nie weiter
  Zeitstop     nach {s.time_stop_bars} Kerzen ohne Entscheidung
  Wochenende   freitags ab {s.friday_cutoff_hour:02d}:00 UTC alles glatt

Risiko (steht über der Strategie):
  je Trade     {r.risk_per_trade:.2%} des Kontos
  Positionen   höchstens {r.max_positions} gleichzeitig
  Tagesverlust Schluss ab {r.daily_loss_limit:.1%}
  Drawdown     ab {r.drawdown_halve:.1%} halbe Größe, ab {r.drawdown_stop:.1%} kein Einstieg
  Pause        {s.cooldown_bars} Kerzen nach {s.cooldown_after_losses} Verlusten in Folge
  Not-Aus      Datei {cfg.live.killswitch_file} anlegen — alles zu, nichts Neues""")
    return 0


def cmd_selftest(args) -> int:
    print("Selbsttest auf erfundenen Daten — kein Aussagewert über den Markt.\n")
    ok = True
    for name, bars, seed in (("dauerlaeufer", 3000, 3), ("swing", 30000, 9)):
        cfg = Config()
        cfg.bot.name = name
        cfg.validate()
        result = run_backtest(cfg, synthetic(bars, seed=seed, minutes=1))
        print(result.report())
        print()
        ok = ok and result.bars == bars
    print("Mechanik:", "läuft" if ok else "FEHLER")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bengx_bot",
        description="BENGX Dauerläufer — regelbasierter Bot für XAU/USD",
    )
    p.add_argument("--config", help="Pfad zur TOML-Konfiguration")
    p.add_argument("--bot", choices=("dauerlaeufer", "swing"),
                   help="welcher Bot (überschreibt bot.name)")
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("backtest", help="Regelwerk über historische Kerzen rechnen")
    b.add_argument("--csv", help="Kursdatei (überschreibt data.csv)")
    b.add_argument("--synthetic", type=int, metavar="N",
                   help="statt echter Daten N erfundene Kerzen (nur zur Prüfung)")
    b.add_argument("--seed", type=int, default=7)
    b.add_argument("--save", action="store_true",
                   help="Bericht ablegen; nur damit ist der Live-Betrieb freigegeben")
    b.add_argument("--json", help="Ergebnis zusätzlich als JSON schreiben")
    b.set_defaults(func=cmd_backtest)

    pa = sub.add_parser("paper", help="auf dem Papierkonto handeln")
    pa.add_argument("--csv")
    pa.add_argument("--once", action="store_true", help="einmal durchlaufen (Standard)")
    pa.add_argument("--loop", action="store_true", help="durchgängig laufen")
    pa.add_argument("--interval", type=int, help="Sekunden zwischen den Durchläufen")
    pa.set_defaults(func=cmd_paper)

    li = sub.add_parser("live", help="echtes Geld (gesperrt, solange etwas fehlt)")
    li.add_argument("--csv")
    li.set_defaults(func=cmd_live)

    sub.add_parser("report", help="Zahlen aus dem Protokoll").set_defaults(func=cmd_report)

    ex = sub.add_parser("export", help="signals.json für die Website schreiben")
    ex.add_argument("--out")
    ex.set_defaults(func=cmd_export)

    sub.add_parser("rules", help="Regelwerk im Klartext").set_defaults(func=cmd_rules)
    sub.add_parser("selftest", help="Mechanik auf erfundenen Daten prüfen").set_defaults(
        func=cmd_selftest)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (LiveGateError, FileNotFoundError, ValueError) as exc:
        print(f"Abbruch: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
