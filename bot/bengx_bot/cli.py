"""Kommandozeile.

    python -m bengx_bot selftest                  Mechanik auf erfundenen Daten prüfen
    python -m bengx_bot backtest --csv daten.csv  Regelwerk nachrechnen
    python -m bengx_bot backtest --save           Bericht ablegen (Freigabe für live)
    python -m bengx_bot paper --once              einen Durchlauf auf dem Papierkonto
    python -m bengx_bot paper --loop              durchgängig laufen lassen
    python -m bengx_bot report                    Zahlen aus dem Protokoll
    python -m bengx_bot export                    signals.json neu schreiben
    python -m bengx_bot telegram                  den Assistenten in Telegram betreiben
    python -m bengx_bot pruefen                   prüft Token, Schlüssel und Modelle
    python -m bengx_bot rules                     das Regelwerk im Klartext
    python -m bengx_bot --bot swing rules         das Regelwerk des Swing-Bots
    python -m bengx_bot --bot kopierer rules      das Regelwerk des Kopierers

Welcher Bot läuft, steht in der Konfiguration unter [bot] name und lässt sich
mit --bot überschreiben. Der Dauerläufer arbeitet auf Stundenkerzen, der
Swing-Bot auf Minutenkerzen, aus denen er 5m und 1h selbst rechnet, und der
Kopierer spiegelt fremde Signale aus einer signals.json.
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


def _rules_swing(cfg: Config) -> str:
    w, r = cfg.swing, cfg.risk
    return (f"""Swing — Regelwerk {cfg.fingerprint()}

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


def _rules_copy(cfg: Config) -> str:
    c, r = cfg.copy, cfg.risk
    quelle = c.url if c.source == "http" else c.path
    return (f"""Signal-Kopierer — Regelwerk {cfg.fingerprint()}

Er denkt sich nichts aus. Er liest Bens Signale und spiegelt sie.

  Quelle       {c.source}: {quelle}
  Format       dieselbe signals.json, die die Website im Bereich G liest

Übernommen wird:
  Richtung     eins zu eins
  Stop         {"Bens Stop" if c.follow_stop else f"eigener, {c.fallback_stop_atr:g} × ATR"}
  Ziel         {"Bens Ziel" if c.follow_target else "keins, es gilt nur der Stop"}
  Ausstieg     {"mitschließen, sobald Ben schließt" if c.close_with_source else "nur eigener Stop und eigenes Ziel"}

Nicht übernommen wird:
  Größe        aus dem eigenen Konto: {r.risk_per_trade:.2%} Risiko je Trade.
               Bens Größe passt auf Bens Konto, nicht auf deins.
  Nachlaufen   {"nur innerhalb von " + format(c.max_slippage_pips, "g") + " Pips um Bens Kurs" if c.entry_mode == "limit" else "Einstieg zum aktuellen Kurs (market)"}

Ausgelassen wird ein Signal, wenn:
  * es älter als {c.max_age_minutes:g} Minuten ist
  * der Kurs zu weit weggelaufen ist
  * es beim Eintreffen schon geschlossen war
  * der Stop-Abstand außerhalb von {c.min_stop_pips:g} bis {c.max_stop_pips:g} Pips liegt
  * Bens Stop auf der falschen Seite des eigenen Einstiegs läge

Dazu gelten alle Risikogrenzen: höchstens {r.max_positions} Positionen,
{r.daily_loss_limit:.1%} Tagesverlust, Drawdown-Bremse ab {r.drawdown_halve:.1%},
kein Einstieg ab {r.drawdown_stop:.1%}, Not-Aus über {cfg.live.killswitch_file}.""")


def _rules_main(cfg: Config) -> str:
    s, r = cfg.strategy, cfg.risk
    return (f"""Dauerläufer — Regelwerk {cfg.fingerprint()}

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


def rules_for(config: Config, name: str | None = None) -> str:
    """Das Regelwerk eines Bots als Text — benutzt von der Kommandozeile und
    von der Telegram-Anbindung."""
    gewaehlt = (name or config.bot.name).lower()
    if gewaehlt == "kopierer":
        return _rules_copy(config)
    if gewaehlt == "swing":
        return _rules_swing(config)
    if gewaehlt == "dauerlaeufer":
        return _rules_main(config)
    raise ValueError(f"Unbekannter Bot: {name!r} "
                     "(dauerlaeufer, swing oder kopierer)")


def cmd_rules(args) -> int:
    cfg = _load(args)
    print(rules_for(cfg))
    return 0


def cmd_telegram(args) -> int:
    import os

    from .assistant import Assistant, AssistantSettings
    from .coder import Coder, CoderSettings
    from .llm import LLMSettings
    from .telegram import (HttpTransport, TelegramBot, TelegramSettings,
                           load_env_file)

    cfg = _load(args)
    datei = load_env_file(args.env or ".env")
    umgebung = {**datei, **{k: v for k, v in os.environ.items() if v}}
    tg = TelegramSettings.from_env(umgebung)

    if not tg.token:
        print(
            "Es fehlt TELEGRAM_TOKEN.\n\n"
            "1. In Telegram @BotFather schreiben, /newbot, Namen vergeben.\n"
            "2. Den Token in bot/.env eintragen:  TELEGRAM_TOKEN=123456:ABC...\n"
            "3. Diesen Befehl noch einmal starten und dem Bot schreiben;\n"
            "   er nennt dir deine Chat-Kennung für TELEGRAM_CHAT_ID.\n\n"
            "Vorlage: .env.example. Die Datei gehört nicht ins Repository.",
            file=sys.stderr)
        return 1

    llm = LLMSettings.from_env(umgebung)
    coder = Coder(CoderSettings.from_env(umgebung))
    assistent = Assistant(AssistantSettings(llm), config=cfg, coder=coder)

    if not tg.chat_id:
        print("TELEGRAM_CHAT_ID ist leer — der Bot nennt dir beim ersten "
              "Schreiben deine Kennung und antwortet sonst nichts.", file=sys.stderr)
    hindernis_ai = assistent.hindernis()
    print("Assistent: " + (hindernis_ai or f"{assistent.anbieter} "
          f"({llm.gemini_model if assistent.anbieter == 'Gemini' else llm.claude_model})"),
          file=sys.stderr)

    hindernis = coder.status()
    print("Weiterbauen: " + (hindernis or
          f"an, Ordner {Path(coder.settings.repo).resolve()}"), file=sys.stderr)

    bot = TelegramBot(cfg, tg, HttpTransport(tg.token), assistent, coder)
    if args.once:
        print(f"{bot.poll_once()} Nachricht(en) verarbeitet.")
        return 0
    try:
        bot.run()
    except KeyboardInterrupt:
        print("\nBeendet.")
    return 0


def cmd_pruefen(args) -> int:
    """Sagt, was wirklich geht — mit den echten Meldungen der Anbieter."""
    import os

    from .assistant import Assistant, AssistantSettings
    from .coder import Coder, CoderSettings
    from .llm import GeminiProvider, LLMSettings
    from .telegram import HttpTransport, TelegramSettings, load_env_file

    cfg = _load(args)
    datei = load_env_file(args.env or ".env")
    umgebung = {**datei, **{k: v for k, v in os.environ.items() if v}}

    print("BENGX — Prüfung")
    print("=" * 40)
    print(f"\nEinstellungen aus: {args.env or '.env'}"
          f"{' (nicht gefunden)' if not datei else ''}")

    # 1. Telegram
    tg = TelegramSettings.from_env(umgebung)
    print("\n1. Telegram")
    if not tg.token:
        print("   Kein TELEGRAM_TOKEN. Erst einrichten.py laufen lassen.")
    else:
        try:
            antwort = HttpTransport(tg.token, timeout=15).call("getMe", {})
            name = (antwort.get("result") or {}).get("username", "?")
            print(f"   Token gilt. Der Bot heißt @{name}.")
        except ConnectionError as exc:
            print(f"   Token wird nicht angenommen: {exc}")
    print(f"   Chat-Kennung: {tg.chat_id or 'fehlt — der Bot nennt sie dir'}")

    # 2. Anbieter
    llm = LLMSettings.from_env(umgebung)
    gewaehlt = llm.gewaehlt()
    print(f"\n2. Antworten über: {gewaehlt}")
    print(f"   Google-Schlüssel:    {'ja' if llm.gemini_key else 'nein'}")
    print(f"   Anthropic-Schlüssel: {'ja' if llm.claude_key else 'nein'}")

    assistent = Assistant(AssistantSettings(llm), config=cfg)
    hindernis = assistent.hindernis()
    if hindernis:
        print(f"   {hindernis}")
    else:
        if gewaehlt == "gemini":
            anbieter = assistent.provider
            assert isinstance(anbieter, GeminiProvider)
            anbieter._verbinden()
            print(f"\n   Modelle, die dein Schlüssel benutzen darf:")
            namen = anbieter.modelle()
            if not namen:
                print("     keine abrufbar — Schlüssel oder Netz prüfen")
            for name in namen[:12]:
                marke = "  <- eingestellt" if name == llm.gemini_model else ""
                print(f"     {name}{marke}")
            if len(namen) > 12:
                print(f"     … und {len(namen) - 12} weitere")
            if namen and llm.gemini_model not in namen:
                print(f"\n   Achtung: {llm.gemini_model} ist nicht dabei. "
                      "Ich nehme beim Antworten automatisch ein anderes.")

        print("\n3. Eine Testfrage")
        text = assistent.answer("Antworte nur mit dem Wort: bereit",
                                "LAGE\nnichts Besonderes")
        print(f"   Antwort: {text[:400]}")
        if gewaehlt == "gemini":
            for notiz in assistent.provider.notizen:
                print(f"   Hinweis: {notiz}")

    # 3. Weiterbauen
    coder = Coder(CoderSettings.from_env(umgebung))
    print("\n4. Am Code weiterbauen")
    print("   " + (coder.status() or
                   f"geht, Ordner {Path(coder.settings.repo).resolve()}"))
    print()
    return 0


def cmd_selftest(args) -> int:
    import tempfile

    from .copier import FileSource, Kopierer

    print("Selbsttest auf erfundenen Daten — kein Aussagewert über den Markt.\n")
    ok = True
    first = None
    for name, bars, seed in (("dauerlaeufer", 3000, 3), ("swing", 30000, 9)):
        cfg = Config()
        cfg.bot.name = name
        cfg.validate()
        result = run_backtest(cfg, synthetic(bars, seed=seed, minutes=1))
        print(result.report())
        print()
        ok = ok and result.bars == bars
        if first is None:
            first = result

    # Der Kopierer bekommt die Signale des ersten Laufs zu sehen.
    candles = synthetic(3000, seed=3, minutes=1)
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "signals.json"
        write_signals(path, signals_payload(first.trades, pip=0.1))
        cfg = Config()
        cfg.bot.name = "kopierer"
        cfg.copy.path = str(path)
        cfg.risk.start_equity = 2000.0
        cfg.validate()
        copy = run_backtest(cfg, candles, strategy=Kopierer(cfg, FileSource(path)))
        print(copy.report())
        print()
        same = len(copy.trades) == len(first.trades)
        print(f"Kopiert: {len(copy.trades)} von {len(first.trades)} Signalen",
              "— vollständig" if same else "— unvollständig")
        ok = ok and same

    print("\nMechanik:", "läuft" if ok else "FEHLER")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bengx_bot",
        description="BENGX Dauerläufer — regelbasierter Bot für XAU/USD",
    )
    p.add_argument("--config", help="Pfad zur TOML-Konfiguration")
    p.add_argument("--bot", choices=("dauerlaeufer", "swing", "kopierer"),
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

    tg = sub.add_parser("telegram", help="den Assistenten in Telegram betreiben")
    tg.add_argument("--env", help="Datei mit den Zugangsdaten (Standard: .env)")
    tg.add_argument("--once", action="store_true",
                    help="einmal abrufen statt dauerhaft zu laufen")
    tg.set_defaults(func=cmd_telegram)

    pr = sub.add_parser("pruefen", help="prüft Token, Schlüssel und Modelle")
    pr.add_argument("--env", help="Datei mit den Zugangsdaten (Standard: .env)")
    pr.set_defaults(func=cmd_pruefen)

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
