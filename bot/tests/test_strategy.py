import unittest
from datetime import datetime, timedelta, timezone

from tests.helpers import trending, series, candle, choppy
from bengx_bot.config import Config
from bengx_bot.model import Side
from bengx_bot.strategy import Dauerlaeufer


def strat(**overrides) -> tuple[Dauerlaeufer, Config]:
    cfg = Config()
    for k, v in overrides.items():
        setattr(cfg.strategy, k, v)
    cfg.validate()
    return Dauerlaeufer(cfg), cfg


class TestSession(unittest.TestCase):
    def test_inside_and_outside_hours(self):
        s, _ = strat()
        day = datetime(2024, 1, 3, tzinfo=timezone.utc)      # Mittwoch
        self.assertTrue(s.in_session(candle(day.replace(hour=8), 1, 2, 0.5, 1.5)))
        self.assertFalse(s.in_session(candle(day.replace(hour=3), 1, 2, 0.5, 1.5)))
        self.assertFalse(s.in_session(candle(day.replace(hour=21), 1, 2, 0.5, 1.5)))

    def test_weekend_is_closed(self):
        s, _ = strat()
        sat = datetime(2024, 1, 6, 10, tzinfo=timezone.utc)
        self.assertFalse(s.in_session(candle(sat, 1, 2, 0.5, 1.5)))

    def test_friday_stops_early(self):
        s, cfg = strat()
        fri = datetime(2024, 1, 5, tzinfo=timezone.utc)
        h = cfg.strategy.friday_cutoff_hour
        self.assertTrue(s.in_session(candle(fri.replace(hour=h - 1), 1, 2, 0.5, 1.5)))
        self.assertFalse(s.in_session(candle(fri.replace(hour=h), 1, 2, 0.5, 1.5)))


class TestFilters(unittest.TestCase):
    def setUp(self):
        self.s, self.cfg = strat()
        self.candles = trending(400)
        self.ctx = self.s.prepare(self.candles)
        self.i = len(self.candles) - 1

    def test_trend_bias_follows_price_against_ema(self):
        bias = self.s.trend_bias(self.ctx, self.i, self.candles[self.i].close)
        self.assertIs(bias, Side.LONG)
        far_below = self.ctx.ema[self.i] - 500
        self.assertIsNone(self.s.trend_bias(self.ctx, self.i, far_below),
                          "fallender Kurs bei steigendem EMA ist keine Short-Freigabe")

    def test_volatility_corridor(self):
        self.assertTrue(self.s.volatility_ok(self.ctx, self.i))
        self.s.p.min_atr_pips = 10_000
        self.assertFalse(self.s.volatility_ok(self.ctx, self.i))

    def test_strength_threshold_is_exactly_the_adx(self):
        """Die Schwelle greift genau am ADX-Wert, nicht irgendwo daneben."""
        value = self.ctx.adx[self.i]
        self.s.p.adx_min = value - 0.1
        self.assertTrue(self.s.strength_ok(self.ctx, self.i))
        self.s.p.adx_min = value + 0.1
        self.assertFalse(self.s.strength_ok(self.ctx, self.i))

    def test_chop_is_weaker_than_trend(self):
        """Über die ganze Reihe gesehen ist die Seitwärtsphase deutlich schwächer."""
        import statistics

        chop_ctx = self.s.prepare(choppy(500))
        trend_vals = [v for v in self.ctx.adx if v is not None]
        chop_vals = [v for v in chop_ctx.adx if v is not None]
        self.assertGreater(statistics.median(trend_vals),
                           statistics.median(chop_vals) * 2)

    def test_warmup_covers_the_longest_indicator(self):
        self.assertGreaterEqual(self.s.warmup_bars(), self.cfg.strategy.trend_ema)


class TestSignal(unittest.TestCase):
    def test_clean_uptrend_produces_a_long(self):
        s, _ = strat()
        candles = trending(400)
        ctx = s.prepare(candles)
        found = [s.evaluate(candles, ctx, i) for i in range(s.warmup_bars(), len(candles))]
        signals = [x for x in found if x]
        self.assertTrue(signals, "im sauberen Aufwärtstrend muss ein Signal entstehen")
        self.assertTrue(all(x.side is Side.LONG for x in signals))

    def test_stop_and_target_sit_on_the_right_side(self):
        s, cfg = strat()
        candles = trending(400)
        ctx = s.prepare(candles)
        sig = next(x for x in (s.evaluate(candles, ctx, i)
                               for i in range(s.warmup_bars(), len(candles))) if x)
        self.assertLess(sig.stop, sig.entry)
        self.assertGreater(sig.target, sig.entry)
        self.assertAlmostEqual(sig.risk_per_unit, cfg.strategy.stop_atr * sig.atr, places=6)
        reward = sig.target - sig.entry
        self.assertAlmostEqual(reward / sig.risk_per_unit, cfg.strategy.partial_r, places=6)

    def test_no_signal_outside_the_session(self):
        s, _ = strat()
        night = datetime(2024, 1, 1, 1, 0, tzinfo=timezone.utc)
        candles = trending(400, start=night)
        ctx = s.prepare(candles)
        inside = [c for c in candles if s.in_session(c)]
        self.assertTrue(inside, "der Test braucht beide Fälle")
        for i in range(s.warmup_bars(), len(candles)):
            if not s.in_session(candles[i]):
                self.assertIsNone(s.evaluate(candles, ctx, i))

    def test_flat_market_gives_nothing(self):
        s, _ = strat()
        candles = choppy(500)
        ctx = s.prepare(candles)
        signals = [s.evaluate(candles, ctx, i)
                   for i in range(s.warmup_bars(), len(candles))]
        self.assertFalse([x for x in signals if x],
                         "in der Seitwärtsphase darf nichts ausgelöst werden")

    def test_evaluate_ignores_unready_bars(self):
        s, _ = strat()
        candles = trending(400)
        ctx = s.prepare(candles)
        self.assertIsNone(s.evaluate(candles, ctx, 0))
        self.assertIsNone(s.evaluate(candles, ctx, 5))


if __name__ == "__main__":
    unittest.main()
