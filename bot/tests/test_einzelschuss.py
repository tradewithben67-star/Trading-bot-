"""Der Einzelschuss: Kalender, die zwei Order, der eine Schuss."""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tests.helpers import (news_scenario, quiet_minutes, rows_to_candles,
                           whipsaw_scenario)
from bengx_bot.backtest import run_backtest
from bengx_bot.bots import BOTS, make_strategy
from bengx_bot.config import BOT_NAMES, Config
from bengx_bot.model import ExitReason, Side
from bengx_bot.news import (Einzelschuss, NewsEvent, load_calendar,
                            parse_calendar)

PIP = 0.1


def cfg_einzel(**over):
    cfg = Config()
    cfg.bot.name = "einzelschuss"
    for k, v in over.items():
        setattr(cfg.einzelschuss, k, v)
    # Der Vorlauf von 260 Kerzen gilt dem EMA(200) des Dauerläufers auf
    # Stundenkerzen. Der Einzelschuss braucht nur den ATR.
    cfg.data.warmup_bars = 55
    cfg.validate()
    return cfg


def signale(cfg, candles, event_ts, name="CPI"):
    bot = Einzelschuss(cfg, events=[NewsEvent(ts=event_ts, name=name)])
    ctx = bot.prepare(candles)
    return ctx, list(ctx.signals.values())


# ---- Kalender -----------------------------------------------------------
class TestKalender(unittest.TestCase):
    def test_dict_form_with_events_key(self):
        events = parse_calendar({"events": [
            {"time": "2024-01-01T12:30:00Z", "name": "CPI", "impact": "hoch"},
        ]})
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].name, "CPI")
        self.assertEqual(events[0].ts.tzinfo, timezone.utc)

    def test_plain_list_and_bare_timestamps(self):
        self.assertEqual(len(parse_calendar(["2024-01-01T12:30:00Z"])), 1)
        self.assertEqual(len(parse_calendar([{"time": "2024-01-01T12:30:00Z"}])), 1)

    def test_german_field_names_work_too(self):
        events = parse_calendar({"termine": [
            {"zeit": "2024-01-01T12:30:00Z", "titel": "VPI", "wichtigkeit": "hoch"},
        ]})
        self.assertEqual(events[0].name, "VPI")

    def test_low_impact_is_filtered_out(self):
        roh = {"events": [
            {"time": "2024-01-01T12:30:00Z", "impact": "hoch"},
            {"time": "2024-01-01T13:30:00Z", "impact": "niedrig"},
        ]}
        self.assertEqual(len(parse_calendar(roh)), 1)
        self.assertEqual(len(parse_calendar(roh, impacts=["hoch", "niedrig"])), 2)

    def test_naive_timestamps_count_as_utc(self):
        events = parse_calendar(["2024-01-01T12:30:00"])
        self.assertEqual(events[0].ts, datetime(2024, 1, 1, 12, 30, tzinfo=timezone.utc))

    def test_events_come_back_sorted(self):
        events = parse_calendar(["2024-01-02T12:30:00Z", "2024-01-01T12:30:00Z"])
        self.assertLess(events[0].ts, events[1].ts)

    def test_a_broken_timestamp_is_not_swallowed(self):
        with self.assertRaises(ValueError):
            parse_calendar(["irgendwann"])
        with self.assertRaises(ValueError):
            parse_calendar([{"name": "ohne Zeit"}])
        with self.assertRaises(ValueError):
            parse_calendar("keine Liste")

    def test_load_from_file_and_a_missing_file_says_so(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "news.json"
            p.write_text(json.dumps({"events": [{"time": "2024-01-01T12:30:00Z"}]}),
                         encoding="utf-8")
            self.assertEqual(len(load_calendar(p)), 1)
            with self.assertRaises(FileNotFoundError):
                load_calendar(Path(d) / "fehlt.json")


# ---- Die zwei Order -----------------------------------------------------
class TestStraddle(unittest.TestCase):
    def test_levels_sit_symmetrically_around_the_reference(self):
        cfg = cfg_einzel(offset_pips=15.0)
        candles, ts = news_scenario()
        ctx, _ = signale(cfg, candles, ts)
        s = ctx.straddles[0]
        self.assertAlmostEqual(s.reference, 2000.0, places=2)
        self.assertAlmostEqual(s.buy_level, 2000.0 + 1.5, places=2)
        self.assertAlmostEqual(s.sell_level, 2000.0 - 1.5, places=2)

    def test_the_reference_is_the_last_candle_closed_before_arming(self):
        cfg = cfg_einzel(arm_seconds_before=60)
        candles, ts = news_scenario()
        ctx, _ = signale(cfg, candles, ts)
        # Termin 09:00, scharf ab 08:59 — die letzte fertige Kerze öffnet 08:58.
        self.assertEqual(candles[ctx.straddles[0].arm_index].ts.strftime("%H:%M"),
                         "08:58")


class TestEinzelnerSchuss(unittest.TestCase):
    def test_a_spike_up_fills_the_buy_side_only(self):
        cfg = cfg_einzel()
        candles, ts = news_scenario(direction=1)
        ctx, sigs = signale(cfg, candles, ts)
        self.assertEqual(len(sigs), 1)
        s = sigs[0]
        self.assertIs(s.side, Side.LONG)
        self.assertEqual(ctx.straddles[0].outcome, "long")

    def test_a_spike_down_fills_the_sell_side_only(self):
        cfg = cfg_einzel()
        candles, ts = news_scenario(direction=-1)
        ctx, sigs = signale(cfg, candles, ts)
        self.assertEqual(len(sigs), 1)
        self.assertIs(sigs[0].side, Side.SHORT)

    def test_stop_and_target_hang_on_the_order_level_not_the_fill(self):
        cfg = cfg_einzel(offset_pips=15.0, stop_pips=25.0, target_pips=50.0,
                         news_slippage_pips=3.0, partial_fraction=0.0)
        candles, ts = news_scenario(direction=1)
        _, sigs = signale(cfg, candles, ts)
        s = sigs[0]
        stufe = 2000.0 + 15.0 * PIP
        self.assertAlmostEqual(s.entry, stufe + 3.0 * PIP, places=6)
        self.assertAlmostEqual(s.stop, stufe - 25.0 * PIP, places=6)
        self.assertAlmostEqual(s.final_target, stufe + 50.0 * PIP, places=6)
        # Ohne Teilverkauf ist das Ziel das Endziel.
        self.assertAlmostEqual(s.target, s.final_target, places=6)

    def test_the_news_surcharge_makes_the_real_risk_bigger(self):
        ohne = cfg_einzel(news_slippage_pips=0.0)
        mit = cfg_einzel(news_slippage_pips=5.0)
        candles, ts = news_scenario(direction=1)
        a = signale(ohne, candles, ts)[1][0]
        b = signale(mit, candles, ts)[1][0]
        self.assertGreater(b.entry, a.entry)
        self.assertGreater(b.risk_per_unit, a.risk_per_unit)

    def test_with_a_partial_the_first_target_sits_before_the_final_one(self):
        cfg = cfg_einzel(partial_fraction=0.5, partial_r=1.0)
        candles, ts = news_scenario(direction=1)
        s = signale(cfg, candles, ts)[1][0]
        self.assertLess(s.target, s.final_target)
        self.assertAlmostEqual(s.target - s.entry, s.risk_per_unit, places=6)

    def test_the_second_order_is_cancelled_once_the_first_runs(self):
        """Der Kern: nach oben ausgelöst, dann tief nach unten — und trotzdem
        nur ein Trade. Ein Netz-Bot würde unten nachlegen."""
        cfg = cfg_einzel(offset_pips=15.0)
        candles, ts = whipsaw_scenario(up=2.0, down=8.0)
        ctx, sigs = signale(cfg, candles, ts)
        self.assertEqual(len(sigs), 1)
        self.assertIs(sigs[0].side, Side.LONG)

    def test_one_event_gives_at_most_one_trade(self):
        cfg = cfg_einzel()
        candles, ts = news_scenario(direction=1, after=200)
        ctx, sigs = signale(cfg, candles, ts)
        self.assertEqual(len(ctx.straddles), 1)
        self.assertEqual(len(sigs), 1)


class TestMehrdeutig(unittest.TestCase):
    """Beide Seiten in einer Minute: aus Kerzendaten nicht auflösbar."""

    def _beide(self, close_up: bool):
        rows = quiet_minutes(60)
        o = 2000.0
        c = 2000.5 if close_up else 1999.5
        rows.append((o, 2002.5, 1997.5, c))      # berührt +1.5 und -1.5
        rows += quiet_minutes(60, price=c, drift=0.0)
        return rows_to_candles(rows), rows_to_candles(rows)[60].ts

    def test_pessimistic_takes_the_side_against_the_candle(self):
        cfg = cfg_einzel(tie_break="pessimistic")
        candles, ts = self._beide(close_up=True)
        _, sigs = signale(cfg, candles, ts)
        self.assertEqual(len(sigs), 1)
        self.assertIs(sigs[0].side, Side.SHORT)      # Kerze schließt oben

        candles, ts = self._beide(close_up=False)
        _, sigs = signale(cfg, candles, ts)
        self.assertIs(sigs[0].side, Side.LONG)       # Kerze schließt unten

    def test_skip_leaves_the_event_out(self):
        cfg = cfg_einzel(tie_break="skip")
        candles, ts = self._beide(close_up=True)
        ctx, sigs = signale(cfg, candles, ts)
        self.assertEqual(sigs, [])
        self.assertEqual(ctx.straddles[0].outcome, "beide Seiten in einer Minute")


class TestFilter(unittest.TestCase):
    def test_a_restless_market_before_the_news_blocks_the_trade(self):
        cfg = cfg_einzel(max_prerange_pips=60.0, prerange_minutes=15)
        # 0,5 USD je Minute: in 15 Minuten 75 Pips Spanne — zu viel.
        rows = quiet_minutes(60, drift=0.5)
        letzte = 2000.0 + 60 * 0.5
        rows.append((letzte, letzte + 6.2, letzte - 0.2, letzte + 6.0))
        rows += quiet_minutes(60, price=letzte + 6.0)
        candles = rows_to_candles(rows)
        ctx, sigs = signale(cfg, candles, candles[60].ts)
        self.assertEqual(sigs, [])
        self.assertIn("vor der Nachricht schon zu bewegt", ctx.skipped)

    def test_a_quiet_market_passes_the_same_filter(self):
        cfg = cfg_einzel(max_prerange_pips=60.0)
        candles, ts = news_scenario(direction=1)
        self.assertEqual(len(signale(cfg, candles, ts)[1]), 1)

    def test_nothing_happens_means_no_trade(self):
        cfg = cfg_einzel()
        candles, ts = news_scenario(direction=1, spike=0.5, follow=0.0)
        ctx, sigs = signale(cfg, candles, ts)
        self.assertEqual(sigs, [])
        self.assertEqual(ctx.straddles[0].outcome, "keine Seite berührt")

    def test_a_move_after_the_window_does_not_count(self):
        cfg = cfg_einzel(window_minutes=2)
        rows = quiet_minutes(60)
        rows += quiet_minutes(5, price=2000.0)                # Fenster läuft leer
        rows += [(2000.0, 2008.0, 1999.8, 2007.0)]            # erst danach
        rows += quiet_minutes(60, price=2007.0)
        candles = rows_to_candles(rows)
        ctx, sigs = signale(cfg, candles, candles[60].ts)
        self.assertEqual(sigs, [])
        self.assertEqual(ctx.straddles[0].outcome, "keine Seite berührt")

    def test_the_daily_cap_holds(self):
        cfg = cfg_einzel(max_events_per_day=1, min_minutes_between=0)
        rows = quiet_minutes(60)
        rows.append((2000.0, 2006.2, 1999.8, 2006.0))         # Termin 1
        rows += quiet_minutes(60, price=2006.0)
        rows.append((2006.0, 2012.2, 2005.8, 2012.0))         # Termin 2
        rows += quiet_minutes(60, price=2012.0)
        candles = rows_to_candles(rows)
        events = [NewsEvent(ts=candles[60].ts, name="A"),
                  NewsEvent(ts=candles[121].ts, name="B")]
        ctx = Einzelschuss(cfg, events=events).prepare(candles)
        self.assertEqual(len(ctx.signals), 1)
        self.assertIn("Tagesgrenze erreicht", ctx.skipped)

    def test_two_events_too_close_together_give_one_trade(self):
        cfg = cfg_einzel(max_events_per_day=5, min_minutes_between=120)
        rows = quiet_minutes(60)
        rows.append((2000.0, 2006.2, 1999.8, 2006.0))
        rows += quiet_minutes(60, price=2006.0)
        rows.append((2006.0, 2012.2, 2005.8, 2012.0))
        rows += quiet_minutes(60, price=2012.0)
        candles = rows_to_candles(rows)
        events = [NewsEvent(ts=candles[60].ts, name="A"),
                  NewsEvent(ts=candles[121].ts, name="B")]
        ctx = Einzelschuss(cfg, events=events).prepare(candles)
        self.assertEqual(len(ctx.signals), 1)
        self.assertIn("zu kurz nach dem letzten Trade", ctx.skipped)

    def test_an_event_on_the_weekend_is_ignored(self):
        cfg = cfg_einzel()
        candles, ts = news_scenario(start=datetime(2024, 1, 6, 9, 0,
                                                   tzinfo=timezone.utc))
        ctx, sigs = signale(cfg, candles, ts)
        self.assertEqual(sigs, [])
        self.assertIn("außerhalb der Handelszeit", ctx.skipped)

    def test_an_event_outside_trading_hours_is_ignored(self):
        cfg = cfg_einzel(session_start_hour=10, session_end_hour=20)
        candles, ts = news_scenario()                  # 09:00 UTC
        ctx, sigs = signale(cfg, candles, ts)
        self.assertEqual(sigs, [])

    def test_too_little_history_is_refused(self):
        cfg = cfg_einzel()
        candles, ts = news_scenario(event_minute=5)    # Vorlauf reicht nicht
        ctx, sigs = signale(cfg, candles, ts)
        self.assertEqual(sigs, [])
        self.assertIn("zu wenig Vorlauf", ctx.skipped)

    def test_an_event_outside_the_data_is_quietly_dropped(self):
        cfg = cfg_einzel()
        candles, _ = news_scenario()
        weit_weg = candles[-1].ts + timedelta(days=30)
        ctx = Einzelschuss(cfg, events=[NewsEvent(ts=weit_weg)]).prepare(candles)
        self.assertEqual(ctx.signals, {})
        self.assertEqual(ctx.straddles, [])


# ---- Ausbruch-Modus ------------------------------------------------------
class TestAusbruch(unittest.TestCase):
    def _reihe(self):
        """Ruhig, eine große Kerze, dann weiter nach oben."""
        rows = quiet_minutes(80, wick=0.2)
        rows.append((2000.0, 2004.0, 1999.8, 2003.8))     # 40 Pips Spanne
        rows += quiet_minutes(60, price=2003.8, drift=0.3)
        return rows_to_candles(rows)

    def test_a_burst_candle_becomes_the_event(self):
        cfg = cfg_einzel(trigger="ausbruch", burst_atr=3.0, min_burst_pips=30.0)
        ctx = Einzelschuss(cfg).prepare(self._reihe())
        self.assertEqual(len(ctx.straddles), 1)
        self.assertEqual(len(ctx.signals), 1)

    def test_the_orders_sit_around_the_burst_candle(self):
        cfg = cfg_einzel(trigger="ausbruch", offset_pips=10.0)
        ctx = Einzelschuss(cfg).prepare(self._reihe())
        s = ctx.straddles[0]
        self.assertAlmostEqual(s.buy_level, 2004.0 + 1.0, places=2)
        self.assertAlmostEqual(s.sell_level, 1999.8 - 1.0, places=2)

    def test_a_small_candle_is_no_event(self):
        cfg = cfg_einzel(trigger="ausbruch", min_burst_pips=500.0)
        ctx = Einzelschuss(cfg).prepare(self._reihe())
        self.assertEqual(ctx.straddles, [])

    def test_burst_mode_needs_no_calendar(self):
        cfg = cfg_einzel(trigger="ausbruch", calendar="gibt-es-nicht.json")
        ctx = Einzelschuss(cfg).prepare(self._reihe())      # darf nicht werfen
        self.assertEqual(len(ctx.signals), 1)


# ---- Maschine und Backtest ----------------------------------------------
class TestMaschine(unittest.TestCase):
    def test_the_stop_can_be_hit_in_the_very_first_minute(self):
        """Bei einer Nachricht fallen Einstieg und Stop in dieselbe Minute.
        Wer das nicht prüft, schönt den Backtest genau an der Stelle."""
        cfg = cfg_einzel(offset_pips=15.0, stop_pips=20.0, partial_fraction=0.0)
        cfg.risk.start_equity = 20000.0
        rows = quiet_minutes(60)
        # Hoch über der Kaufstufe (2001.5), Tief unter dem Stop (1999.5).
        rows.append((2000.0, 2002.0, 1999.0, 1999.2))
        rows += quiet_minutes(60, price=1999.2)
        candles = rows_to_candles(rows)
        bot = Einzelschuss(cfg, events=[NewsEvent(ts=candles[60].ts)])
        res = run_backtest(cfg, candles, strategy=bot)
        self.assertEqual(len(res.trades), 1)
        self.assertIs(res.trades[0].reason, ExitReason.STOP)
        self.assertLess(res.trades[0].pnl, 0)

    def test_the_other_bots_still_ignore_the_entry_bar(self):
        for name in ("dauerlaeufer", "swing", "kopierer"):
            cfg = Config()
            cfg.bot.name = name
            cfg.validate()
            self.assertFalse(make_strategy(cfg).exit_rules().stop_on_entry_bar,
                             f"{name} darf den Stop nicht in der Eröffnungskerze prüfen")
        self.assertTrue(make_strategy(cfg_einzel()).exit_rules().stop_on_entry_bar)

    def test_a_winning_news_trade_runs_through_the_engine(self):
        cfg = cfg_einzel(partial_fraction=0.0, target_pips=40.0)
        cfg.risk.start_equity = 20000.0
        candles, ts = news_scenario(direction=1, spike=6.0, after=120, follow=0.3)
        bot = Einzelschuss(cfg, events=[NewsEvent(ts=ts, name="CPI")])
        res = run_backtest(cfg, candles, strategy=bot)
        self.assertEqual(len(res.trades), 1)
        t = res.trades[0]
        self.assertIs(t.side, Side.LONG)
        self.assertIs(t.reason, ExitReason.TARGET)
        self.assertGreater(t.pnl, 0)

    def test_the_time_stop_closes_a_trade_that_goes_nowhere(self):
        cfg = cfg_einzel(partial_fraction=0.0, max_hold_minutes=10,
                         target_pips=400.0, stop_pips=200.0)
        cfg.risk.start_equity = 20000.0
        rows = quiet_minutes(60)
        rows.append((2000.0, 2002.0, 1999.9, 2001.9))     # löst die Kaufstufe aus
        rows += quiet_minutes(60, price=2001.9, drift=0.0)
        candles = rows_to_candles(rows)
        bot = Einzelschuss(cfg, events=[NewsEvent(ts=candles[60].ts)])
        res = run_backtest(cfg, candles, strategy=bot)
        self.assertEqual(len(res.trades), 1)
        self.assertIs(res.trades[0].reason, ExitReason.TIME)

    def test_the_bot_is_registered_and_the_names_match(self):
        self.assertIn("einzelschuss", BOTS)
        self.assertEqual(sorted(BOTS), sorted(BOT_NAMES))
        self.assertIsInstance(make_strategy(cfg_einzel()), Einzelschuss)

    def test_the_fingerprint_moves_when_a_rule_moves(self):
        a = cfg_einzel().fingerprint()
        b = cfg_einzel(stop_pips=30.0).fingerprint()
        self.assertNotEqual(a, b)


class TestKonfiguration(unittest.TestCase):
    def test_bad_values_are_refused(self):
        for feld, wert in (("trigger", "irgendwas"), ("tie_break", "egal"),
                           ("offset_pips", 0.0), ("stop_pips", -1.0),
                           ("target_pips", 0.0), ("news_slippage_pips", -1.0),
                           ("window_minutes", 0), ("max_prerange_pips", 0.0),
                           ("burst_atr", 0.0), ("partial_fraction", 1.0),
                           ("partial_r", 0.0), ("max_events_per_day", 0),
                           ("min_minutes_between", -1), ("atr_period", 0),
                           ("max_hold_minutes", 0), ("prerange_minutes", 0)):
            with self.subTest(feld=feld):
                cfg = Config()
                cfg.bot.name = "einzelschuss"
                setattr(cfg.einzelschuss, feld, wert)
                with self.assertRaises(ValueError):
                    cfg.validate()

    def test_an_empty_calendar_path_is_refused(self):
        cfg = Config()
        cfg.bot.name = "einzelschuss"
        cfg.einzelschuss.calendar = ""
        with self.assertRaises(ValueError):
            cfg.validate()
        cfg.einzelschuss.trigger = "ausbruch"
        cfg.validate()                     # ohne Kalender ist das in Ordnung

    def test_the_section_is_read_from_toml(self):
        cfg = Config.from_dict({
            "bot": {"name": "einzelschuss"},
            "einzelschuss": {"offset_pips": 22.0, "trigger": "ausbruch",
                             "impacts": ["hoch"]},
        })
        self.assertEqual(cfg.einzelschuss.offset_pips, 22.0)
        self.assertEqual(cfg.einzelschuss.impacts, ["hoch"])

    def test_an_unknown_setting_is_not_ignored(self):
        with self.assertRaises(ValueError):
            Config.from_dict({"einzelschuss": {"gibtsnicht": 1}})


class TestRegelwerk(unittest.TestCase):
    def test_the_rules_name_the_numbers_that_matter(self):
        from bengx_bot.cli import rules_for
        text = rules_for(cfg_einzel(offset_pips=18.0, stop_pips=22.0,
                                    target_pips=44.0))
        self.assertIn("Einzelschuss", text)
        self.assertIn("18", text)
        self.assertIn("22", text)
        self.assertIn("44", text)
        self.assertIn("news.json", text)
        # Das Versprechen des Bots muss im Regelwerk stehen.
        self.assertIn("Kein Nachkaufen", text)

    def test_burst_mode_describes_itself_differently(self):
        from bengx_bot.cli import rules_for
        text = rules_for(cfg_einzel(trigger="ausbruch"))
        self.assertIn("ohne Kalender", text)
        self.assertNotIn("Ruhe davor", text)

    def test_every_bot_has_a_rule_text(self):
        from bengx_bot.cli import rules_for
        for name in BOT_NAMES:
            cfg = Config()
            cfg.bot.name = name
            cfg.validate()
            with self.subTest(bot=name):
                self.assertGreater(len(rules_for(cfg)), 200)
        with self.assertRaises(ValueError):
            rules_for(Config(), "gibtsnicht")

    def test_the_command_line_knows_the_bot(self):
        from bengx_bot.cli import build_parser
        args = build_parser().parse_args(["--bot", "einzelschuss", "rules"])
        self.assertEqual(args.bot, "einzelschuss")


class TestTestdaten(unittest.TestCase):
    def test_the_news_generator_is_quiet_before_the_release(self):
        from bengx_bot.data import news_synthetic
        candles, termine = news_synthetic(days=6, seed=5)
        self.assertGreater(len(termine), 0)
        self.assertGreater(len(candles), 1000)
        spannen = sorted((c.high - c.low) / PIP for c in candles)
        median = spannen[len(spannen) // 2]
        self.assertLess(median, 30.0, "die ruhigen Minuten sind nicht ruhig")
        self.assertGreater(spannen[-1], 30.0, "keine Nachrichtenkerze dabei")

    def test_no_candles_on_the_weekend(self):
        from bengx_bot.data import news_synthetic
        candles, _ = news_synthetic(days=14, seed=5)
        self.assertEqual({c.ts.weekday() for c in candles} & {5, 6}, set())

    def test_the_generator_runs_through_the_bot(self):
        from bengx_bot.data import news_synthetic
        candles, termine = news_synthetic(days=8, seed=11)
        cfg = cfg_einzel()
        cfg.data.warmup_bars = 60
        bot = Einzelschuss(cfg, events=[NewsEvent(ts=t) for t in termine])
        ctx = bot.prepare(candles)
        self.assertEqual(len(ctx.straddles), len(termine))
        self.assertGreater(len(ctx.signals), 0)
        self.assertLessEqual(len(ctx.signals), len(termine))


if __name__ == "__main__":
    unittest.main()
