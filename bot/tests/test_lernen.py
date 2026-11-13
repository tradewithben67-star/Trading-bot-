"""Die Live-Sperre und die Auswertung.

Zwei Dinge, die zusammengehören: wann der Bot überhaupt an ein Konto darf,
und was er hinterher aus dem Ergebnis liest.
"""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tests.fake_mt5 import FakeMT5, Konto, TRADE_MODE_DEMO, TRADE_MODE_REAL
from bengx_bot.config import Config
from bengx_bot.lernen import GENUG, Auswertung, Befund, auswerten
from bengx_bot.model import ExitReason, Side, Trade
from bengx_bot.runner import LiveGateError, Runner, backtest_path

START = datetime(2024, 1, 15, 12, 30, tzinfo=timezone.utc)


def trade(pnl=10.0, minuten=20.0, reason=ExitReason.TARGET, side=Side.LONG,
          size=20.0, quelle="CPI", slippage=None, spread=None, r=None,
          start=START):
    marken = {"source_id": quelle, "broker": "mt5"}
    if slippage is not None:
        marken["slippage_pips"] = slippage
    if spread is not None:
        marken["spread_pips"] = spread
    return Trade(
        id=f"mt5-{int(start.timestamp())}", side=side, size=size,
        entry=2000.0, stop=1997.5, target=2005.0,
        exit_price=2005.0 if pnl > 0 else 1997.5,
        opened_at=start, closed_at=start + timedelta(minutes=minuten),
        pips=pnl, pnl=pnl,
        r_multiple=r if r is not None else (1.0 if pnl > 0 else -1.0),
        reason=reason, tags=marken,
    )


def live_cfg(**over):
    cfg = Config()
    cfg.bot.name = "einzelschuss"
    cfg.live.enabled = True
    cfg.live.broker = "mt5"
    for k, v in over.items():
        setattr(cfg.live, k, v)
    cfg.validate()
    return cfg


# ---- Die Sperre ----------------------------------------------------------
class TestLiveSperre(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)

    def _cfg(self, **over):
        cfg = live_cfg(**over)
        cfg.live.state_dir = str(Path(self.d.name) / "state")
        cfg.live.journal = str(Path(self.d.name) / "state" / "trades.jsonl")
        cfg.live.signals_out = str(Path(self.d.name) / "signals.json")
        cfg.mt5.server_utc_offset_hours = 2.0
        return cfg

    def _runner(self, fake, **over):
        return Runner(self._cfg(**over), live=True, mt5_modul=fake)

    def test_a_demo_account_may_run_without_a_backtest(self):
        """Genau das ist gewollt: ausprobieren, ohne vorher zu rechnen."""
        r = self._runner(FakeMT5(konto=Konto(trade_mode=TRADE_MODE_DEMO)))
        self.assertTrue(r.konto.demo)
        self.assertEqual(r.konto.art, "Demokonto")

    def test_a_real_account_without_a_backtest_is_refused(self):
        """Hier gibt es keinen Schalter. Echtes Geld wird nachgerechnet."""
        with self.assertRaises(LiveGateError) as ctx:
            self._runner(FakeMT5(konto=Konto(trade_mode=TRADE_MODE_REAL)))
        text = str(ctx.exception)
        self.assertIn("ECHTGELDKONTO", text)
        self.assertIn("keine Einstellung", text)

    def test_the_switch_does_not_help_a_real_account(self):
        with self.assertRaises(LiveGateError):
            self._runner(FakeMT5(konto=Konto(trade_mode=TRADE_MODE_REAL)),
                         allow_demo_without_backtest=True)

    def test_a_real_account_with_a_backtest_is_allowed(self):
        cfg = self._cfg()
        p = backtest_path(cfg)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"trades": 0}), encoding="utf-8")
        r = Runner(cfg, live=True,
                   mt5_modul=FakeMT5(konto=Konto(trade_mode=TRADE_MODE_REAL)))
        self.assertFalse(r.konto.demo)

    def test_a_demo_account_can_be_held_to_the_backtest_too(self):
        with self.assertRaises(LiveGateError):
            self._runner(FakeMT5(), allow_demo_without_backtest=False)

    def test_live_stays_off_until_it_is_switched_on(self):
        cfg = self._cfg()
        cfg.live.enabled = False
        with self.assertRaises(LiveGateError) as ctx:
            Runner(cfg, live=True, mt5_modul=FakeMT5())
        self.assertIn("live.enabled", str(ctx.exception))

    def test_paper_as_broker_explains_the_way_to_mt5(self):
        cfg = self._cfg()
        cfg.live.broker = "paper"
        with self.assertRaises(LiveGateError) as ctx:
            Runner(cfg, live=True, mt5_modul=FakeMT5())
        self.assertIn("MT5_LOGIN", str(ctx.exception))

    def test_an_unknown_broker_is_named(self):
        cfg = self._cfg()
        cfg.live.broker = "irgendwas"
        with self.assertRaises(LiveGateError) as ctx:
            Runner(cfg, live=True, mt5_modul=FakeMT5())
        self.assertIn("irgendwas", str(ctx.exception))

    def test_a_terminal_that_will_not_open_becomes_a_gate_error(self):
        fake = FakeMT5()
        fake.initialize_ok = False
        with self.assertRaises(LiveGateError):
            self._runner(fake)

    def test_without_live_nothing_touches_mt5(self):
        r = Runner(self._cfg(), live=False)
        self.assertIsNone(r.terminal)
        self.assertIsNone(r.konto)


class TestDurchlauf(unittest.TestCase):
    """Was passiert, wenn der Broker selbst schließt — und der Bot danach
    wieder aufwacht."""

    def setUp(self):
        from bengx_bot.data import news_synthetic
        from bengx_bot.news import Einzelschuss, NewsEvent

        self.d = tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
        self.kerzen, termine = news_synthetic(days=2, seed=11)

        cfg = live_cfg()
        cfg.live.state_dir = str(Path(self.d.name) / "state")
        cfg.live.journal = str(Path(self.d.name) / "state" / "trades.jsonl")
        cfg.live.signals_out = str(Path(self.d.name) / "signals.json")
        cfg.data.warmup_bars = 60
        cfg.mt5.server_utc_offset_hours = 2.0
        cfg.mt5.candles = 5000
        self.cfg = cfg

        # Nur bis kurz nach dem ersten Termin füttern, sonst ist nach dem
        # ersten Durchlauf schon wieder alles geschlossen und es gibt nichts
        # zu beobachten.
        ziel = termine[0]
        self.bis = next(i for i, c in enumerate(self.kerzen) if c.ts >= ziel) + 2
        self.fake = FakeMT5(konto=Konto(trade_mode=TRADE_MODE_DEMO),
                            server_offset_hours=2.0)
        self.fake.setze_kerzen("XAUUSD", self.kerzen[:self.bis])
        self.fake.kurs_aus_kerze(self.kerzen[self.bis - 1])
        self.runner = Runner(cfg, live=True, mt5_modul=self.fake)
        self.runner.strategy = Einzelschuss(
            cfg, events=[NewsEvent(ts=t, name="CPI") for t in termine])
        self.runner.engine.strategy = self.runner.strategy

    def test_a_position_closed_by_the_broker_reaches_the_journal(self):
        from bengx_bot.journal import Journal

        self.runner.tick()
        if not self.fake.positionen:
            self.skipTest("kein offener Trade in diesem Lauf")
        ticket, pos = next(iter(self.fake.positionen.items()))
        self.fake.stop_ausloesen(ticket, pos.sl, kommentar=f"[sl {pos.sl:.2f}]")

        info = self.runner.tick()
        self.assertGreaterEqual(info.get("vom_broker", 0), 1)
        trades = Journal(self.cfg.live.journal).load()
        self.assertTrue(any(t.reason is ExitReason.STOP for t in trades))

    def test_the_bot_does_not_try_to_close_a_ghost(self):
        """Der Reihenfolge-Fehler: wird erst abgeglichen und dann der Zustand
        geladen, holt das Laden die geschlossene Position zurück — und die
        Maschine schickt eine Order auf eine Position, die es nicht gibt."""
        self.runner.tick()
        if not self.fake.positionen:
            self.skipTest("kein offener Trade in diesem Lauf")
        ticket, pos = next(iter(self.fake.positionen.items()))
        self.fake.stop_ausloesen(ticket, pos.sl)
        self.runner.tick()          # darf nicht werfen
        self.assertNotIn(ticket, self.fake.positionen)
        for gesendet in self.fake.gesendet:
            if gesendet.get("position") == ticket:
                self.assertNotEqual(gesendet.get("comment"), "geist")

    def test_the_equity_comes_from_the_account_not_from_the_file(self):
        self.runner.tick()
        self.fake.konto_obj.equity = 12345.0
        self.runner.tick()
        self.assertAlmostEqual(self.runner.broker.equity, 12345.0)
        self.assertAlmostEqual(self.runner.risk.equity, 12345.0)


# ---- Die Auswertung ------------------------------------------------------
class TestAuswertungGrundlagen(unittest.TestCase):
    def test_nothing_to_learn_from_nothing(self):
        a = auswerten([], Config())
        self.assertEqual(a.trades, 0)
        self.assertIn("nichts zu lernen", a.bericht())

    def test_it_counts_what_happened(self):
        a = auswerten([trade(pnl=10), trade(pnl=-5), trade(pnl=20)], Config())
        self.assertEqual((a.trades, a.gewonnen, a.verloren), (3, 2, 1))
        self.assertAlmostEqual(a.pnl, 25.0)

    def test_a_thin_sample_says_so_in_the_report(self):
        bericht = auswerten([trade() for _ in range(3)], Config()).bericht()
        self.assertIn("Zufall", bericht)

    def test_a_finding_below_the_threshold_is_marked_as_weak(self):
        schwach = Befund("x", 3, "y")
        stark = Befund("x", GENUG, "y")
        self.assertFalse(schwach.belastbar)
        self.assertTrue(stark.belastbar)
        self.assertIn("zu wenige", "\n".join(schwach.zeilen()))

    def test_the_report_says_nothing_was_changed(self):
        trades = [trade(pnl=-5, slippage=20.0) for _ in range(10)]
        bericht = auswerten(trades, Config()).bericht()
        self.assertIn("verstellt seine Regeln nicht", bericht)


class TestBefunde(unittest.TestCase):
    def setUp(self):
        self.cfg = Config()
        self.cfg.bot.name = "einzelschuss"
        self.cfg.validate()

    def _titel(self, trades):
        return [b.titel for b in auswerten(trades, self.cfg).befunde]

    def test_slippage_worse_than_assumed_is_flagged_with_a_number(self):
        trades = [trade(slippage=12.0) for _ in range(10)]
        befund = next(b for b in auswerten(trades, self.cfg).befunde
                      if "füllen schlechter" in b.titel)
        self.assertTrue(befund.schwer)
        self.assertIn("12", befund.vorschlag)
        self.assertIn("news_slippage_pips", befund.vorschlag)

    def test_slippage_within_the_assumption_is_not_a_complaint(self):
        trades = [trade(slippage=2.0) for _ in range(10)]
        self.assertIn("Slippage liegt im Rahmen", self._titel(trades))

    def test_a_wide_spread_at_entry_is_flagged(self):
        trades = [trade(spread=25.0) for _ in range(10)]
        befund = next(b for b in auswerten(trades, self.cfg).befunde
                      if "Spread" in b.titel and "breiter" in b.titel)
        self.assertTrue(befund.schwer)
        self.assertIn("costs.spread_pips", befund.vorschlag)

    def test_losses_within_minutes_suggest_the_orders_sit_too_close(self):
        trades = [trade(pnl=-5, minuten=1.0, reason=ExitReason.STOP)
                  for _ in range(10)]
        befund = next(b for b in auswerten(trades, self.cfg).befunde
                      if "ersten Ausschlag" in b.titel)
        self.assertIn("offset_pips", befund.vorschlag)

    def test_slow_losses_are_not_blamed_on_the_offset(self):
        trades = [trade(pnl=-5, minuten=40.0, reason=ExitReason.STOP)
                  for _ in range(10)]
        self.assertIn("Verluste kommen nicht überhastet", self._titel(trades))

    def test_an_event_that_only_costs_is_named(self):
        trades = ([trade(pnl=-5, quelle="FOMC") for _ in range(4)]
                  + [trade(pnl=10, quelle="CPI") for _ in range(4)])
        titel = self._titel(trades)
        self.assertIn("Termin FOMC kostet bisher", titel)
        self.assertIn("Termin CPI", titel)

    def test_an_event_with_too_few_trades_is_left_out(self):
        trades = [trade(pnl=-5, quelle="PPI") for _ in range(2)]
        self.assertNotIn("Termin PPI kostet bisher", self._titel(trades))

    def test_many_time_stops_point_at_the_event_or_the_holding_time(self):
        trades = [trade(pnl=-1, reason=ExitReason.TIME) for _ in range(10)]
        befund = next(b for b in auswerten(trades, self.cfg).befunde
                      if "Zeitstop" in b.titel)
        self.assertIn("max_hold_minutes", befund.vorschlag)

    def test_positions_at_the_minimum_size_are_flagged_as_a_risk_problem(self):
        trades = [trade(size=0.5) for _ in range(10)]
        befund = next(b for b in auswerten(trades, self.cfg).befunde
                      if "Mindestmenge" in b.titel)
        self.assertTrue(befund.schwer)
        self.assertIn("Cent-Konto", befund.vorschlag)

    def test_a_direction_that_looks_better_is_called_out_as_probably_noise(self):
        trades = ([trade(pnl=10, side=Side.LONG) for _ in range(4)]
                  + [trade(pnl=-10, side=Side.SHORT) for _ in range(4)])
        befund = next(b for b in auswerten(trades, self.cfg).befunde
                      if "Eine Richtung trägt" in b.titel)
        self.assertIn("Zufall", befund.vorschlag)
        self.assertIn("kaputtzuoptimieren", befund.vorschlag)

    def test_what_costs_money_is_listed_before_what_is_merely_interesting(self):
        trades = [trade(pnl=-5, slippage=20.0, minuten=1.0,
                        reason=ExitReason.STOP) for _ in range(10)]
        befunde = auswerten(trades, self.cfg).befunde
        self.assertTrue(befunde[0].schwer)

    def test_trades_without_context_do_not_crash_the_analysis(self):
        """Ein Papierlauf schreibt keine Slippage ins Protokoll."""
        roh = [trade() for _ in range(5)]
        for t in roh:
            t.tags.clear()
        a = auswerten(roh, self.cfg)
        self.assertEqual(a.trades, 5)
        self.assertIsInstance(a.bericht(), str)


if __name__ == "__main__":
    unittest.main()
