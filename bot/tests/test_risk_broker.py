import unittest
from datetime import datetime, timedelta, timezone

from tests.helpers import START
from bengx_bot.broker import PaperBroker
from bengx_bot.config import Config
from bengx_bot.model import ExitReason, Side, Signal, Trade
from bengx_bot.risk import RiskManager


def signal(ts=START, side=Side.LONG, entry=2000.0, stop=1990.0, target=2015.0):
    return Signal(ts=ts, side=side, entry=entry, stop=stop, target=target,
                  atr=5.0, adx=25.0, reason="Test")


def losing_trade(pnl=-50.0, ts=START):
    return Trade(id="t", side=Side.LONG, size=1.0, entry=2000.0, stop=1990.0,
                 target=2015.0, exit_price=1990.0, opened_at=ts, closed_at=ts,
                 pips=-100.0, pnl=pnl, r_multiple=-1.0, reason=ExitReason.STOP)


class TestSizing(unittest.TestCase):
    def test_size_follows_risk_and_stop_distance(self):
        cfg = Config()
        cfg.risk.start_equity = 10_000.0
        cfg.risk.risk_per_trade = 0.005        # 50 Euro Risiko
        r = RiskManager(cfg)
        d = r.evaluate(signal(stop=1990.0), open_positions=0, bar_index=100)
        self.assertTrue(d.allowed)
        self.assertAlmostEqual(d.size, 5.0, places=2)   # 50 / 10 Kursabstand

    def test_wider_stop_means_smaller_position(self):
        cfg = Config()
        r = RiskManager(cfg)
        near = r.evaluate(signal(stop=1995.0), 0, 100).size
        far = r.evaluate(signal(stop=1980.0), 0, 100).size
        self.assertGreater(near, far)

    def test_stop_on_entry_is_refused(self):
        r = RiskManager(Config())
        d = r.evaluate(signal(stop=2000.0), 0, 100)
        self.assertFalse(d.allowed)

    def test_size_below_minimum_is_refused(self):
        cfg = Config()
        cfg.risk.start_equity = 100.0
        cfg.market.min_size = 1.0
        r = RiskManager(cfg)
        d = r.evaluate(signal(stop=1000.0), 0, 100)
        self.assertFalse(d.allowed)
        self.assertIn("Mindestgröße", d.reason)


class TestLimits(unittest.TestCase):
    def test_max_positions(self):
        cfg = Config()
        cfg.risk.max_positions = 2
        r = RiskManager(cfg)
        self.assertTrue(r.evaluate(signal(), 1, 100).allowed)
        self.assertFalse(r.evaluate(signal(), 2, 100).allowed)

    def test_daily_loss_limit_closes_the_day(self):
        cfg = Config()
        cfg.risk.daily_loss_limit = 0.02
        r = RiskManager(cfg)
        r.roll_day(START)
        r.equity = 10_000.0 * 0.979          # 2,1 Prozent im Minus
        d = r.evaluate(signal(), 0, 100)
        self.assertFalse(d.allowed)
        self.assertIn("Tagesverlust", d.reason)

    def test_new_day_lifts_the_limit(self):
        cfg = Config()
        r = RiskManager(cfg)
        r.roll_day(START)
        r.equity = 9_700.0
        self.assertFalse(r.evaluate(signal(), 0, 100).allowed)
        tomorrow = START + timedelta(days=1)
        self.assertTrue(r.evaluate(signal(ts=tomorrow), 0, 101).allowed)

    def test_drawdown_halves_then_stops(self):
        cfg = Config()
        r = RiskManager(cfg)
        r.peak = 10_000.0
        r.equity = 9_100.0                    # 9 Prozent Rückgang
        self.assertEqual(r.size_factor(), 0.5)
        full = 10_000 * cfg.risk.risk_per_trade / 10.0
        self.assertAlmostEqual(r.evaluate(signal(), 0, 100).size, full * 0.91 / 2, delta=0.1)

        r.equity = 8_400.0                    # 16 Prozent Rückgang
        d = r.evaluate(signal(), 0, 100)
        self.assertFalse(d.allowed)
        self.assertIn("Drawdown", d.reason)

    def test_cooldown_after_consecutive_losses(self):
        cfg = Config()
        cfg.strategy.cooldown_after_losses = 2
        cfg.strategy.cooldown_bars = 10
        r = RiskManager(cfg)
        r.on_trade_closed(losing_trade(), bar_index=50)
        self.assertTrue(r.evaluate(signal(), 0, 51).allowed)
        r.on_trade_closed(losing_trade(), bar_index=52)
        self.assertFalse(r.evaluate(signal(), 0, 55).allowed)
        self.assertTrue(r.evaluate(signal(), 0, 63).allowed)

    def test_halt_blocks_everything(self):
        r = RiskManager(Config())
        r.halt("Not-Aus")
        self.assertFalse(r.evaluate(signal(), 0, 100).allowed)
        r.resume()
        self.assertTrue(r.evaluate(signal(), 0, 100).allowed)


class TestPaperBroker(unittest.TestCase):
    def setUp(self):
        self.cfg = Config()
        self.cfg.costs.spread_pips = 2.0      # 0,20 USD
        self.cfg.costs.slippage_pips = 1.0    # 0,10 USD
        self.b = PaperBroker(self.cfg)

    def test_costs_work_against_you_on_both_sides(self):
        pos = self.b.open(Side.LONG, 1.0, 2000.0, START, 0, 1990.0, 2015.0)
        self.assertAlmostEqual(pos.entry, 2000.2, places=6)
        t = self.b.close(pos, 2000.0, START, ExitReason.MANUAL)
        self.assertAlmostEqual(t.exit_price, 1999.8, places=6)
        self.assertLess(t.pnl, 0, "ohne Kursbewegung verliert man die Kosten")

    def test_short_fills_mirror_long(self):
        pos = self.b.open(Side.SHORT, 1.0, 2000.0, START, 0, 2010.0, 1985.0)
        self.assertAlmostEqual(pos.entry, 1999.8, places=6)
        t = self.b.close(pos, 2000.0, START, ExitReason.MANUAL)
        self.assertAlmostEqual(t.exit_price, 2000.2, places=6)

    def test_pips_match_the_money(self):
        pos = self.b.open(Side.LONG, 2.0, 2000.0, START, 0, 1990.0, 2015.0)
        t = self.b.close(pos, 2020.0, START, ExitReason.TARGET)
        self.assertAlmostEqual(t.pips, t.pnl / (self.cfg.market.pip * 2.0), places=1)
        self.assertGreater(t.pips, 0)

    def test_partial_keeps_the_rest_open(self):
        pos = self.b.open(Side.LONG, 2.0, 2000.0, START, 0, 1990.0, 2015.0)
        self.b.reduce(pos, 0.5, 2015.0)
        self.assertTrue(pos.partial_done)
        self.assertAlmostEqual(pos.size, 1.0, places=6)
        self.assertAlmostEqual(pos.original_size, 2.0, places=6)
        self.assertGreater(pos.realised_pnl, 0)
        self.assertIn(pos, self.b.positions)

    def test_partial_and_final_add_up(self):
        pos = self.b.open(Side.LONG, 2.0, 2000.0, START, 0, 1990.0, 2015.0)
        before = self.b.equity
        self.b.reduce(pos, 0.5, 2015.0)
        t = self.b.close(pos, 2030.0, START, ExitReason.TRAIL)
        self.assertAlmostEqual(self.b.equity - before, t.pnl, places=6)

    def test_commission_is_charged(self):
        self.cfg.costs.commission_per_unit = 0.5
        b = PaperBroker(self.cfg)
        start = b.equity
        pos = b.open(Side.LONG, 2.0, 2000.0, START, 0, 1990.0, 2015.0)
        self.assertAlmostEqual(b.equity, start - 1.0, places=6)
        t = b.close(pos, 2000.2, START, ExitReason.MANUAL)
        self.assertLess(t.pnl, 0)

    def test_reduce_rejects_impossible_fractions(self):
        pos = self.b.open(Side.LONG, 2.0, 2000.0, START, 0, 1990.0, 2015.0)
        with self.assertRaises(ValueError):
            self.b.reduce(pos, 1.5, 2015.0)

    def test_mark_to_market_includes_open_positions(self):
        self.b.open(Side.LONG, 1.0, 2000.0, START, 0, 1990.0, 2015.0)
        self.assertGreater(self.b.mark_to_market(2050.0), self.b.equity)


if __name__ == "__main__":
    unittest.main()
