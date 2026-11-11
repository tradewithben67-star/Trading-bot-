import unittest
from datetime import datetime, timedelta, timezone

from tests.helpers import (ifvg_entry_phase, long_entry_phase, m1_hour,
                           rows_to_candles, sweep_scenario)
from bengx_bot.config import Config
from bengx_bot.model import Side
from bengx_bot.swing import SwingTrader
from bengx_bot.timeframes import liquidity_sweeps, resample, swing_points


def swing_cfg(**over):
    cfg = Config()
    cfg.bot.name = "swing"
    for k, v in over.items():
        setattr(cfg.swing, k, v)
    cfg.validate()
    return cfg


def only_signal(cfg, candles):
    ctx = SwingTrader(cfg).prepare(candles)
    return ctx, list(ctx.signals.values())


class TestFullSetup(unittest.TestCase):
    def setUp(self):
        self.cfg = swing_cfg()
        self.candles = sweep_scenario()
        self.ctx, self.signals = only_signal(self.cfg, self.candles)

    def test_the_sequence_produces_exactly_one_entry(self):
        self.assertEqual(len(self.signals), 1)
        self.assertIs(self.signals[0].side, Side.LONG)

    def test_all_four_stages_are_reached(self):
        self.assertEqual({"sweep", "continuation", "armed"},
                         set(self.ctx.stages.values()))

    def test_stop_below_entry_and_target_above(self):
        s = self.signals[0]
        self.assertLess(s.stop, s.entry)
        self.assertGreater(s.target, s.entry)
        self.assertGreater(s.final_target, s.target)

    def test_reason_names_every_step(self):
        r = self.signals[0].reason
        for part in ("1h-Sweep", "5m-Fortsetzung", "1m-"):
            self.assertIn(part, r)

    def test_entry_comes_after_everything_it_depends_on(self):
        """Kein Blick in die Zukunft: der Einstieg liegt nach dem Sweep-Schluss."""
        h1 = resample(self.candles, 60)
        sweep = liquidity_sweeps(h1, swing_points(h1, 2, 60), 60)[0]
        self.assertGreaterEqual(self.signals[0].ts, sweep.known_ts)

    def test_target_is_three_times_the_risk(self):
        s = self.signals[0]
        risk = s.entry - s.stop
        self.assertAlmostEqual((s.final_target - s.entry) / risk,
                               self.cfg.swing.target_r, places=6)


class TestStagesAreRequired(unittest.TestCase):
    def test_no_continuation_means_no_entry(self):
        quiet = []
        p = 2002.0
        for _ in range(60):
            quiet.append((round(p, 2), round(p + 0.2, 2),
                          round(p - 0.2, 2), round(p + 0.02, 2)))
            p += 0.02
        _, signals = only_signal(swing_cfg(), sweep_scenario(entry_phase=quiet))
        self.assertEqual(signals, [])

    def test_continuation_window_can_expire(self):
        cfg = swing_cfg(continuation_window_minutes=1)
        _, signals = only_signal(cfg, sweep_scenario())
        self.assertEqual(signals, [])

    def test_entry_window_can_expire(self):
        cfg = swing_cfg(entry_window_minutes=1)
        _, signals = only_signal(cfg, sweep_scenario())
        self.assertEqual(signals, [])

    def test_without_a_sweep_nothing_happens(self):
        rows = []
        for _ in range(7):
            rows += m1_hour(2000, 2000.5, low=1999)
        _, signals = only_signal(swing_cfg(), rows_to_candles(rows))
        self.assertEqual(signals, [])


class TestEntryVariants(unittest.TestCase):
    def test_entry_fill_moves_the_limit_into_the_gap(self):
        near = only_signal(swing_cfg(entry_fill=0.0, allow_ifvg=False),
                           sweep_scenario())[1][0]
        far = only_signal(swing_cfg(entry_fill=1.0, allow_ifvg=False),
                          sweep_scenario())[1][0]
        self.assertGreater(near.entry, far.entry,
                           "tiefer in der Lücke heißt günstiger einsteigen")

    def test_ifvg_entry(self):
        cfg = swing_cfg(allow_pullback=False, allow_ifvg=True)
        _, signals = only_signal(cfg, sweep_scenario(entry_phase=ifvg_entry_phase()))
        self.assertEqual(len(signals), 1)
        self.assertIn("IFVG", signals[0].reason)

    def test_pullback_entry(self):
        cfg = swing_cfg(allow_pullback=True, allow_ifvg=False)
        _, signals = only_signal(cfg, sweep_scenario())
        self.assertEqual(len(signals), 1)
        self.assertIn("Pullback", signals[0].reason)

    def test_both_disabled_is_a_config_error(self):
        with self.assertRaises(ValueError):
            swing_cfg(allow_pullback=False, allow_ifvg=False)


class TestStops(unittest.TestCase):
    def test_sources_give_different_stops(self):
        # Der Stop am Sweep-Tief ist weit; ohne angehobene Obergrenze lehnt die
        # Prüfung den Trade zu Recht ab.
        structure = only_signal(swing_cfg(stop_source="structure", max_stop_pips=1000.0),
                                sweep_scenario())[1][0]
        sweep = only_signal(swing_cfg(stop_source="sweep", max_stop_pips=1000.0),
                            sweep_scenario())[1][0]
        self.assertLess(sweep.stop, structure.stop,
                        "unter dem Sweep-Tief liegt weiter weg als unter der Struktur")

    def test_a_sweep_stop_can_exceed_the_limit(self):
        """Das 1h-Sweep-Tief ist oft so weit weg, dass die Obergrenze greift."""
        self.assertEqual(only_signal(swing_cfg(stop_source="sweep"),
                                     sweep_scenario())[1], [])

    def test_buffer_widens_the_stop(self):
        tight = only_signal(swing_cfg(stop_buffer_pips=0.0), sweep_scenario())[1][0]
        wide = only_signal(swing_cfg(stop_buffer_pips=50.0), sweep_scenario())[1][0]
        self.assertLess(wide.stop, tight.stop)

    def test_too_tight_a_stop_is_refused(self):
        cfg = swing_cfg(min_stop_pips=5000.0, max_stop_pips=9000.0)
        self.assertEqual(only_signal(cfg, sweep_scenario())[1], [])

    def test_too_wide_a_stop_is_refused(self):
        cfg = swing_cfg(min_stop_pips=0.1, max_stop_pips=1.0)
        self.assertEqual(only_signal(cfg, sweep_scenario())[1], [])

    def test_bounds_must_be_ordered(self):
        with self.assertRaises(ValueError):
            swing_cfg(min_stop_pips=500.0, max_stop_pips=100.0)


class TestSession(unittest.TestCase):
    def test_outside_the_window_there_is_no_entry(self):
        night = datetime(2024, 1, 2, 0, 0, tzinfo=timezone.utc)
        rows = []
        rows += m1_hour(2000, 1999, low=1998)
        rows += m1_hour(1999, 1998, low=1996)
        rows += m1_hour(1998, 1997, low=1990)
        rows += m1_hour(1997, 1996, low=1995)
        rows += m1_hour(1996, 1995, low=1997)
        rows += m1_hour(1995, 2002, low=1985)
        rows += long_entry_phase()
        candles = rows_to_candles(rows, start=night)
        _, signals = only_signal(swing_cfg(), candles)
        self.assertEqual(signals, [], "nachts um zwei wird nicht gehandelt")


class TestRestartSafety(unittest.TestCase):
    def test_truncated_history_gives_the_same_signal(self):
        """Der Ablauf wird aus den Daten gerechnet, nicht über Aufrufe gesammelt."""
        candles = sweep_scenario()
        full = SwingTrader(swing_cfg()).prepare(candles)
        index = max(full.signals)
        shorter = SwingTrader(swing_cfg()).prepare(candles[:index + 1])
        self.assertIn(index, shorter.signals)
        self.assertAlmostEqual(shorter.signals[index].entry,
                               full.signals[index].entry, places=6)


class TestWiring(unittest.TestCase):
    def test_exit_rules_use_the_swing_settings(self):
        cfg = swing_cfg(max_hold_minutes=123, trail_atr=1.75)
        rules = SwingTrader(cfg).exit_rules()
        self.assertEqual(rules.time_stop_bars, 123)
        self.assertAlmostEqual(rules.trail_atr, 1.75)

    def test_factory_picks_the_bot(self):
        from bengx_bot.bots import make_strategy

        self.assertEqual(make_strategy(swing_cfg()).name, "Swing")
        self.assertEqual(make_strategy(Config()).name, "Dauerläufer")

    def test_unknown_bot_is_refused(self):
        cfg = Config()
        cfg.bot.name = "gibtsnicht"
        with self.assertRaises(ValueError):
            cfg.validate()

    def test_fingerprint_covers_the_swing_rules(self):
        a, b = swing_cfg(), swing_cfg(entry_fill=0.25)
        self.assertNotEqual(a.fingerprint(), b.fingerprint())

    def test_fingerprint_separates_the_two_bots(self):
        self.assertNotEqual(Config().fingerprint(), swing_cfg().fingerprint())


if __name__ == "__main__":
    unittest.main()
