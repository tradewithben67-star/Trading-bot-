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
    python -m bengx_bot konto                     Verbindung zu MetaTrader 5 prüfen\n    python -m bengx_bot lernen                    was die bisherigen Trades sagen\n    python -m bengx_bot rules                     das Regelwerk im Klartext
    python -m bengx_bot --bot swing rules         das Regelwerk des Swing-Bots
    python -m bengx_bot --bot einzelschuss rules  das Regelwerk des Einzelschuss
    python -m bengx_bot --bot kopierer rules      das Regelwerk des Kopierers

Welcher Bot läuft, steht in der Konfiguration unter [bot] name und lässt sich
mit --bot überschreiben. Der Dauerläufer arbeitet auf Stundenkerzen, der
Swing-Bot auf Minutenkerzen, aus denen er 5m und 1h selbst rechnet, der
Einzelschuss legt Minutenkerzen um einen Nachrichtentermin, und der Kopierer
spiegelt fremde Signale aus einer signals.json.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from .backtest import run_backtest
from .config import BOT_NAMES, Config
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


def _betrieb(runner, args) -> int:
    """Einen Runner laufen lassen und Fehler als Satz melden, nicht als
    Traceback. Wer vor einem Stapel Python-Zeilen steht, liest die Ursache
    nicht mehr."""
    try:
        if getattr(args, "loop", False):
            runner.loop(getattr(args, "interval", None))
        else:
            print(runner.tick())
    except FileNotFoundError as exc:
        print(f"Eine Datei fehlt.\n\n{exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nAbgebrochen.", file=sys.stderr)
        return 130
    return 0


def cmd_paper(args) -> int:
    cfg = _load(args)
    runner = Runner(cfg, live=False)
    try:
        if args.loop:
            runner.loop(args.interval)
            return 0
        print(json.dumps(runner.tick(), ensure_ascii=False, indent=2))
    except FileNotFoundError as exc:
        print(f"Eine Datei fehlt.\n\n{exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nAbgebrochen.", file=sys.stderr)
        return 130
    return 0


def cmd_live(args) -> int:
    """Handel am echten Konto. Die Sperren stehen im Runner."""
    cfg = _load(args)
    try:
        runner = Runner(cfg, live=True)
    except LiveGateError as exc:
        print(f"Live-Betrieb gesperrt.\n\n{exc}", file=sys.stderr)
        return 3

    konto = runner.konto
    if konto is not None:
        print(f"Konto {konto.login} bei {konto.server} — {konto.art}")
        if not konto.demo:
            print("Das ist ECHTES GELD. Beenden mit Strg+C.")
        print(f"Symbol {cfg.mt5.symbol}, Takt {cfg.live.poll_seconds} s. "
              f"Not-Aus: Datei {cfg.live.killswitch_file} anlegen.\n")

    from .mt5 import MT5Error
    try:
        return _betrieb(runner, args)
    except MT5Error as exc:
        print(f"MetaTrader 5 meldet ein Problem.\n\n{exc}", file=sys.stderr)
        return 4
    finally:
        if runner.terminal is not None:
            runner.terminal.schliessen()


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


def _rules_einzelschuss(cfg: Config) -> str:
    e, r = cfg.einzelschuss, cfg.risk
    if e.trigger == "ausbruch":
        termin = (f"""  Termin       ohne Kalender: eine Minutenkerze, deren Spanne
               {e.burst_atr:g} × ATR({e.atr_period}) erreicht und mindestens
               {e.min_burst_pips:g} Pips misst, ist selbst das Ereignis
  Stufen       über dem Hoch und unter dem Tief dieser Kerze,
               je {e.offset_pips:g} Pips Abstand""")
    else:
        termin = (f"""  Termin       aus {e.calendar}, Wichtigkeit: {", ".join(e.impacts) or "alle"}
  Referenz     Schluss der letzten Kerze, die {e.arm_seconds_before} s vor dem
               Termin fertig ist
  Stufen       {e.offset_pips:g} Pips über und unter der Referenz
  Ruhe davor   Spanne der letzten {e.prerange_minutes} Minuten höchstens
               {e.max_prerange_pips:g} Pips — sonst wird nicht gehandelt""")

    return (f"""Einzelschuss — Regelwerk {cfg.fingerprint()}

Zwei Order um eine Nachricht. Eine wird gehandelt, die andere gestrichen.

{termin}

  Einzelschuss die erste Seite, die berührt wird, wird gehandelt; die andere
               Order verfällt im selben Augenblick
  Frist        {e.window_minutes} Minuten nach dem Termin; wird keine Seite
               berührt, verfallen beide
  Mehrdeutig   beide Seiten in einer Minute: {"ungünstige Annahme — gehandelt wird die Seite gegen die Kerze" if e.tie_break == "pessimistic" else "Termin wird ausgelassen"}

Nach dem Einstieg:
  Fill         Orderstufe plus {e.news_slippage_pips:g} Pips Aufschlag — bei einer
               Nachricht füllt keine Stop-Order zum Wunschkurs
  Stop         {e.stop_pips:g} Pips von der Orderstufe
  Ziel         {e.target_pips:g} Pips von der Orderstufe
  {"Teilziel     " + format(e.partial_r, "g") + " R, dort " + format(e.partial_fraction, ".0%") + " raus, Rest auf Einstand" if e.partial_fraction > 0 else "Teilziel     keins — kein Teilverkauf, damit auch kein Einstand-Stop"}
  Trailing     {e.trail_atr:g} × ATR, nur enger
  Haltedauer   höchstens {e.max_hold_minutes} Minuten
  Handelszeit  {e.session_start_hour:02d}:00 bis {e.session_end_hour:02d}:00 UTC,
               freitags bis {e.friday_cutoff_hour:02d}:00, nie am Wochenende

Was dieser Bot nicht tut:
  Kein Nachkaufen, kein Netz, keine Verdopplung nach einem Verlust. Pro
  Termin gibt es einen Trade, auch wenn er sofort in den Stop läuft. Es gibt
  kein zweites Mal — daher der Name.

Grenzen:
  Termine      höchstens {e.max_events_per_day} am Tag
  Abstand      mindestens {e.min_minutes_between} Minuten zwischen zwei Trades

Risiko (steht über der Strategie):
  je Trade     {r.risk_per_trade:.2%} des Kontos
  Positionen   höchstens {r.max_positions} gleichzeitig
  Tagesverlust Schluss ab {r.daily_loss_limit:.1%}
  Drawdown     ab {r.drawdown_halve:.1%} halbe Größe, ab {r.drawdown_stop:.1%} kein Einstieg
  Not-Aus      Datei {cfg.live.killswitch_file} anlegen

Der Einzelschuss braucht Minutenkerzen. Der Stop wird schon in der Minute
geprüft, in der eingestiegen wurde: bei einer Nachricht fallen Einstieg und
Stop oft in dieselbe Minute, und wer das übergeht, schönt den Backtest genau
an der Stelle, auf die es ankommt.""")


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
    if gewaehlt == "einzelschuss":
        return _rules_einzelschuss(config)
    if gewaehlt == "dauerlaeufer":
        return _rules_main(config)
    raise ValueError(f"Unbekannter Bot: {name!r} "
                     f"(erlaubt: {', '.join(BOT_NAMES)})")


def cmd_konto(args) -> int:
    """Nachsehen, ob die Verbindung zum Terminal steht — bevor etwas gehandelt wird."""
    from .mt5 import MT5Broker, MT5Error, lots, verbinden
    from .risk import RiskManager
    from .telegram import load_env_file

    cfg = _load(args)
    env = dict(os.environ)
    datei = Path(getattr(args, "env", None) or (Path(__file__).resolve().parents[1] / ".env"))
    if datei.exists():
        env.update(load_env_file(datei))

    try:
        terminal, konto = verbinden(cfg, env=env)
    except MT5Error as exc:
        print(f"Keine Verbindung.\n\n{exc}", file=sys.stderr)
        return 1

    try:
        info = terminal.symbol(cfg.mt5.symbol)
        print(f"Konto      {konto.login} bei {konto.server}")
        print(f"Art        {konto.art}")
        print(f"Inhaber    {konto.name}")
        print(f"Kapital    {konto.equity:.2f} {konto.currency} "
              f"(Hebel 1:{konto.leverage})")
        print(f"Handel     {'erlaubt' if konto.trade_allowed else 'GESPERRT'}")
        print()
        print(f"Symbol     {info.name}")
        print(f"Ein Lot    {info.contract_size:g} Unzen")
        print(f"Menge      {info.volume_min:g} bis {info.volume_max:g} Lots, "
              f"Schritt {info.volume_step:g}")
        print(f"Spread     {info.spread_preis / cfg.market.pip:.1f} Pips "
              f"({info.bid:.{info.digits}f} / {info.ask:.{info.digits}f})")
        if info.stops_level:
            print(f"Mindestabstand für Stop und Ziel: "
                  f"{info.stops_level * info.point / cfg.market.pip:.0f} Pips")

        try:
            versatz = terminal.zeitversatz(cfg.mt5.symbol)
            stunden = versatz.total_seconds() / 3600
            print(f"Serverzeit UTC{stunden:+.1f} Stunden")
        except MT5Error as exc:
            print(f"Serverzeit unbekannt: {str(exc).splitlines()[0]}")

        # Was die aktuelle Risikoeinstellung an diesem Konto wirklich ergibt.
        print()
        risk = RiskManager(cfg)
        risk.equity = konto.equity
        stop_pips = (cfg.einzelschuss.stop_pips if cfg.bot.name == "einzelschuss"
                     else 25.0)
        je_unze = stop_pips * cfg.market.pip
        groesse = risk._round_size(
            konto.equity * cfg.risk.risk_per_trade / je_unze)
        print(f"Bei {cfg.risk.risk_per_trade:.2%} Risiko und {stop_pips:g} Pips Stop:")
        try:
            menge = lots(groesse, info)
            print(f"  {groesse:.2f} Unzen = {menge:g} Lots je Trade")
        except MT5Error as exc:
            print(f"  {groesse:.2f} Unzen — {str(exc).splitlines()[0]}")
            print("  Der Bot würde an diesem Konto nichts handeln.")
            return 1

        if not konto.demo:
            print()
            print("ACHTUNG: Das ist kein Übungskonto. Der Bot verlangt hier "
                  "einen Backtest,")
            print("bevor er handelt — und das lässt sich nicht abschalten.")
    finally:
        terminal.schliessen()
    return 0


def cmd_lernen(args) -> int:
    """Was die bisherigen Trades sagen."""
    from .lernen import auswerten

    cfg = _load(args)
    trades = Journal(cfg.live.journal).load()
    print(auswerten(trades, cfg).bericht())
    return 0


def cmd_rules(args) -> int:
    cfg = _load(args)
    print(rules_for(cfg))
    return 0


def cmd_telegram(args) -> int:
    import os

    from .gruppen import GruppenSettings, Verteiler
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

    netz = HttpTransport(tg.token)
    verteiler = Verteiler(GruppenSettings.from_env(umgebung), netz,
                          pip=cfg.market.pip)

    if not tg.chat_id:
        print("TELEGRAM_CHAT_ID ist leer — der Bot nennt dir beim ersten "
              "Schreiben deine Kennung und antwortet sonst nichts.", file=sys.stderr)

    gruppen = verteiler.gruppen()
    print("Gruppen: " + (", ".join(
        f"{g.name} ({'sofort' if not g.verzug else str(g.verzug // 60) + ' min'})"
        for g in gruppen) if gruppen else
        "keine — TELEGRAM_INNER_CHAT_ID / TELEGRAM_VIP_CHAT_ID fehlen"),
        file=sys.stderr)
    if gruppen and verteiler.settings.rueckblick_um:
        print(f"Rückblick täglich um {verteiler.settings.rueckblick_um}",
              file=sys.stderr)

    bot = TelegramBot(cfg, tg, netz, verteiler)
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

    from .gruppen import GruppenSettings, Verteiler
    from .telegram import HttpTransport, TelegramSettings, load_env_file

    cfg = _load(args)
    datei = load_env_file(args.env or ".env")
    umgebung = {**datei, **{k: v for k, v in os.environ.items() if v}}

    print("BENGX — Prüfung")
    print("=" * 40)
    # Gesammelt, damit am Ende ein Rückgabewert steht, auf den sich eine
    # Startdatei verlassen kann.
    fehlt: list[str] = []
    print(f"\nEinstellungen aus: {args.env or '.env'}"
          f"{' (nicht gefunden)' if not datei else ''}")

    # 1. Telegram
    tg = TelegramSettings.from_env(umgebung)
    print("\n1. Telegram")
    if not tg.token:
        print("   Kein TELEGRAM_TOKEN. Erst einrichten.py laufen lassen.")
        fehlt.append("der Telegram-Token")
    else:
        try:
            antwort = HttpTransport(tg.token, timeout=15).call("getMe", {})
            name = (antwort.get("result") or {}).get("username", "?")
            print(f"   Token gilt. Der Bot heißt @{name}.")
        except ConnectionError as exc:
            print(f"   Token wird nicht angenommen: {exc}")
            fehlt.append("ein gültiger Telegram-Token")
    print(f"   Chat-Kennung: {tg.chat_id or 'fehlt — der Bot nennt sie dir'}")
    if not tg.chat_id:
        fehlt.append("deine Chat-Kennung")

    # 2. Gruppen
    print("\n2. Gruppen")
    verteiler = Verteiler(GruppenSettings.from_env(umgebung),
                          HttpTransport(tg.token or "x", timeout=15),
                          pip=cfg.market.pip)
    gruppen = verteiler.gruppen()
    if not gruppen:
        print("   Keine eingerichtet. Ohne Gruppen kann nichts gepostet werden.")
        fehlt.append("mindestens eine Gruppe")
    else:
        for g in gruppen:
            wann = "sofort" if not g.verzug else f"nach {g.verzug // 60} min"
            print(f"   {g.name}: {g.chat_id}, {wann}")
        fenster = ", ".join(f"{n} {vo // 60:02d}:{vo % 60:02d}–{b // 60:02d}:{b % 60:02d}"
                            for _, n, vo, b in verteiler.fenster())
        print(f"   Gratis-Signale je Sitzung: {fenster or 'keine Fenster gesetzt'}")
        print(f"   Rückblick täglich um: "
              f"{verteiler.settings.rueckblick_um or 'aus'}")

    # 3. Handelsbot
    print("\n3. Handelsbot")
    print(f"   Regelwerk: {cfg.bot.name}")
    p = Path(cfg.live.killswitch_file)
    print(f"   Not-Aus: {'GESETZT — es wird nicht gehandelt' if p.exists() else 'nicht gesetzt'}")

    print("\n" + "=" * 40)
    if fehlt:
        print("Noch nicht startklar. Es fehlt:")
        for was in dict.fromkeys(fehlt):
            print(f"  - {was}")
        print("\nMach ein Foto von diesem Fenster und schick es Claude.")
        print()
        return 1
    print("Alles da. Der Bot ist startklar.")
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

    # Der Einzelschuss braucht Ruhe vor dem Termin; die Reihe aus synthetic()
    # schwankt je Minute so stark, dass der Filter zu Recht alles ablehnt.
    from .data import news_synthetic
    from .news import Einzelschuss, NewsEvent

    candles, termine = news_synthetic(days=12, seed=11)
    cfg = Config()
    cfg.bot.name = "einzelschuss"
    cfg.data.warmup_bars = 60
    cfg.validate()
    bot = Einzelschuss(cfg, events=[NewsEvent(ts=t, name="Termin") for t in termine])
    ctx = bot.prepare(candles)
    schuss = run_backtest(cfg, candles, strategy=bot)
    print(schuss.report())
    print()
    print(f"Termine: {len(ctx.straddles)}, davon gehandelt: {len(ctx.signals)}")
    for grund, anzahl in sorted(ctx.skipped.items()):
        print(f"  {anzahl:>5}  {grund}")
    # Je Termin höchstens ein Trade — das ist der ganze Witz des Bots.
    einzeln = len(schuss.trades) <= len(ctx.straddles)
    print("Ein Schuss je Termin:", "ja" if einzeln else "NEIN")
    ok = ok and einzeln and len(ctx.signals) > 0
    print()

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
    p.add_argument("--bot", choices=BOT_NAMES,
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

    li = sub.add_parser("live", help="am echten Konto handeln (MetaTrader 5)")
    li.add_argument("--csv")
    li.add_argument("--once", action="store_true",
                    help="einmal durchlaufen (Standard)")
    li.add_argument("--loop", action="store_true", help="durchgängig laufen")
    li.add_argument("--interval", type=int, help="Sekunden zwischen den Durchläufen")
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
    pr.add_argument("--schnell", action="store_true",
                    help="die Modelle nicht einzeln anfragen")
    pr.set_defaults(func=cmd_pruefen)

    ko = sub.add_parser("konto", help="Verbindung zu MetaTrader 5 prüfen")
    ko.add_argument("--env", help="Datei mit den Zugangsdaten (Standard: .env)")
    ko.set_defaults(func=cmd_konto)

    le = sub.add_parser("lernen", help="was die bisherigen Trades sagen")
    le.set_defaults(func=cmd_lernen)

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
