import unittest
from datetime import datetime, timedelta, timezone

from tests.helpers import START, candle, trending
from bengx_bot.backtest import run_backtest
from bengx_bot.broker import PaperBroker
from bengx_bot.config import Config
from bengx_bot.data import synthetic
from bengx_bot.engine import TradeEngine
from bengx_bot.model import ExitReason, Side
from bengx_bot.risk import RiskManager
from bengx_bot.strategy import Context, Dauerlaeufer


def flat_ctx(n: int, atr: float = 5.0) -> Context:
    """Kontext, der nur den ATR liefert — mehr braucht die Positionsführung nicht."""
    none = [None] * n
    return Context(ema=list(none), ema_slope=list(none), atr=[atr] * n,
                   adx=list(none), donchian_up=list(none), donchian_dn=list(none))


def build(**costs):
    cfg = Config()
    cfg.costs.spread_pips = costs.get("spread", 0.0)
    cfg.costs.slippage_pips = costs.get("slippage", 0.0)
    broker = PaperBroker(cfg)
    engine = TradeEngine(cfg, Dauerlaeufer(cfg), RiskManager(cfg), broker)
    return cfg, broker, engine


def bars(n: int, high: float, low: float, close: float, start=START):
    out = []
    ts = start
    for _ in range(n):
        out.append(candle(ts, close, high, low, close))
        ts += timedelta(hours=1)
    return out


class TestNoLookahead(unittest.TestCase):
    def test_position_is_not_managed_in_its_own_candle(self):
        cfg, broker, engine = build()
        candles = bars(3, 2100.0, 1900.0, 2000.0)
        pos = broker.open(Side.LONG, 1.0, 2000.0, candles[1].ts, 1, 1990.0, 2015.0)
        closed = engine._manage(candles, flat_ctx(3), 1)
        self.assertEqual(closed, [], "die Eröffnungskerze darf nicht rückwirkend wirken")
        self.assertIn(pos, broker.positions)

    def test_managed_from_the_next_candle(self):
        cfg, broker, engine = build()
        candles = bars(3, 2100.0, 1900.0, 2000.0)
        broker.open(Side.LONG, 1.0, 2000.0, candles[0].ts, 0, 1990.0, 2015.0)
        closed = engine._manage(candles, flat_ctx(3), 1)
        self.assertEqual(len(closed), 1)


class TestExits(unittest.TestCase):
    def test_stop_closes_at_the_stop(self):
        cfg, broker, engine = build()
        candles = bars(3, 2005.0, 1985.0, 1995.0)
        broker.open(Side.LONG, 1.0, 2000.0, candles[0].ts, 0, 1990.0, 2015.0)
        trade = engine._manage(candles, flat_ctx(3), 1)[0]
        self.assertIs(trade.reason, ExitReason.STOP)
        self.assertAlmostEqual(trade.exit_price, 1990.0, places=6)

    def test_stop_beats_target_in_the_same_candle(self):
        cfg, broker, engine = build()
        candles = bars(3, 2020.0, 1985.0, 2000.0)   # trifft beides
        broker.open(Side.LONG, 1.0, 2000.0, candles[0].ts, 0, 1990.0, 2015.0)
        trade = engine._manage(candles, flat_ctx(3), 1)[0]
        self.assertIs(trade.reason, ExitReason.STOP,
                      "wir wissen nicht, was zuerst kam — also der Stop")

    def test_short_stop_is_above(self):
        cfg, broker, engine = build()
        candles = bars(3, 2015.0, 1995.0, 2005.0)
        broker.open(Side.SHORT, 1.0, 2000.0, candles[0].ts, 0, 2010.0, 1985.0)
        trade = engine._manage(candles, flat_ctx(3), 1)[0]
        self.assertIs(trade.reason, ExitReason.STOP)
        self.assertAlmostEqual(trade.exit_price, 2010.0, places=6)

    def test_partial_moves_the_stop_to_entry(self):
        cfg, broker, engine = build()
        candles = bars(3, 2020.0, 1999.0, 2016.0)
        pos = broker.open(Side.LONG, 2.0, 2000.0, candles[0].ts, 0, 1990.0, 2015.0)
        engine._manage(candles, flat_ctx(3), 1)
        self.assertTrue(pos.partial_done)
        self.assertAlmostEqual(pos.size, 1.0, places=6)
        self.assertGreaterEqual(pos.stop, pos.entry)

    def test_trailing_only_tightens(self):
        cfg, broker, engine = build()
        cfg.strategy.trail_atr = 2.0
        pos = broker.open(Side.LONG, 2.0, 2000.0, START, 0, 1990.0, 2015.0)
        rising = bars(2, 2040.0, 2030.0, 2035.0, start=START + timedelta(hours=1))
        candles = [candle(START, 2000, 2001, 1999, 2000)] + rising
        pos.partial_done = True
        engine._manage(candles, flat_ctx(3, atr=5.0), 1)
        tightened = pos.stop
        self.assertGreater(tightened, 1990.0)

        falling = [candles[0], candles[1],
                   candle(candles[2].ts, 2010, 2012, 2009, 2010)]
        engine._manage(falling, flat_ctx(3, atr=5.0), 2)
        self.assertGreaterEqual(pos.stop, tightened,
                                "ein Trailing-Stop wird nie wieder weiter")

    def test_time_stop(self):
        cfg, broker, engine = build()
        cfg.strategy.time_stop_bars = 3
        candles = bars(6, 2002.0, 1998.0, 2000.0)
        broker.open(Side.LONG, 1.0, 2000.0, candles[0].ts, 0, 1900.0, 2500.0)
        self.assertEqual(engine._manage(candles, flat_ctx(6), 2), [])
        trade = engine._manage(candles, flat_ctx(6), 3)[0]
        self.assertIs(trade.reason, ExitReason.TIME)

    def test_friday_close(self):
        cfg, broker, engine = build()
        friday = datetime(2024, 1, 5, 18, tzinfo=timezone.utc)
        candles = bars(3, 2002.0, 1998.0, 2000.0, start=friday)
        broker.open(Side.LONG, 1.0, 2000.0, candles[0].ts, 0, 1900.0, 2500.0)
        trade = engine._manage(candles, flat_ctx(3), 1)[0]
        self.assertIs(trade.reason, ExitReason.SESSION)

    def test_flatten_closes_everything(self):
        cfg, broker, engine = build()
        c = bars(1, 2002.0, 1998.0, 2000.0)[0]
        broker.open(Side.LONG, 1.0, 2000.0, c.ts, 0, 1990.0, 2015.0)
        broker.open(Side.SHORT, 1.0, 2000.0, c.ts, 0, 2010.0, 1985.0)
        trades = engine.flatten(c, ExitReason.KILL)
        self.assertEqual(len(trades), 2)
        self.assertEqual(broker.positions, [])


class TestBacktest(unittest.TestCase):
    def setUp(self):
        self.cfg = Config()
        self.result = run_backtest(self.cfg, synthetic(3000, seed=21))

    def test_money_adds_up(self):
        total = sum(t.pnl for t in self.result.trades)
        self.assertAlmostEqual(self.result.end_equity - self.result.start_equity,
                               total, places=2)

    def test_nothing_stays_open(self):
        self.assertTrue(all(t.closed_at >= t.opened_at for t in self.result.trades))

    def test_metrics_are_consistent(self):
        s = self.result.summary()
        self.assertEqual(s["trades"], len(self.result.trades))
        if s["winrate"] is not None:
            self.assertGreaterEqual(s["winrate"], 0.0)
            self.assertLessEqual(s["winrate"], 1.0)
        self.assertGreaterEqual(s["max_drawdown"], 0.0)

    def test_report_is_readable(self):
        text = self.result.report()
        self.assertIn("Trefferquote", text)
        self.assertIn("Pips gesamt", text)

    def test_refuses_short_history(self):
        with self.assertRaises(ValueError):
            run_backtest(self.cfg, synthetic(20))

    def test_refuses_when_warmup_exceeds_data(self):
        with self.assertRaises(ValueError):
            run_backtest(self.cfg, synthetic(100))

    def test_costs_make_results_worse(self):
        cheap = Config()
        cheap.costs.spread_pips = 0.0
        cheap.costs.slippage_pips = 0.0
        dear = Config()
        dear.costs.spread_pips = 20.0
        dear.costs.slippage_pips = 10.0
        candles = synthetic(3000, seed=21)
        self.assertGreater(run_backtest(cheap, candles).net_pnl,
                           run_backtest(dear, candles).net_pnl)

    def test_risk_cap_limits_the_drawdown(self):
        cfg = Config()
        cfg.risk.drawdown_stop = 0.05
        r = run_backtest(cfg, synthetic(4000, seed=33))
        self.assertLess(r.max_drawdown, 0.30)


if __name__ == "__main__":
    unittest.main()
