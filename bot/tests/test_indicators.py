import unittest

from tests.helpers import series  # noqa: F401  (setzt sys.path)
from bengx_bot import indicators as ind


class TestMovingAverages(unittest.TestCase):
    def test_sma_leading_values_undefined(self):
        out = ind.sma([1, 2, 3, 4], 3)
        self.assertEqual(out[:2], [None, None])
        self.assertAlmostEqual(out[2], 2.0)
        self.assertAlmostEqual(out[3], 3.0)

    def test_ema_starts_on_sma(self):
        values = [10.0] * 5
        out = ind.ema(values, 5)
        self.assertIsNone(out[3])
        self.assertAlmostEqual(out[4], 10.0)

    def test_ema_follows_a_step(self):
        values = [10.0] * 10 + [20.0] * 10
        out = ind.ema(values, 5)
        self.assertLess(out[10], 20.0)       # zieht nach, springt nicht
        self.assertGreater(out[-1], 19.0)

    def test_ema_too_short(self):
        self.assertEqual(ind.ema([1.0, 2.0], 5), [None, None])

    def test_period_must_be_positive(self):
        with self.assertRaises(ValueError):
            ind.ema([1.0], 0)


class TestRanges(unittest.TestCase):
    def test_true_range_uses_the_gap(self):
        highs = [10.0, 12.0]
        lows = [9.0, 11.5]
        closes = [9.5, 12.0]
        tr = ind.true_range(highs, lows, closes)
        self.assertAlmostEqual(tr[0], 1.0)
        self.assertAlmostEqual(tr[1], 2.5)   # 12,0 - 9,5 schlägt 0,5

    def test_atr_is_positive_and_defined_after_period(self):
        c = [float(100 + i) for i in range(40)]
        highs = [v + 2 for v in c]
        lows = [v - 2 for v in c]
        out = ind.atr(highs, lows, c, 14)
        self.assertIsNone(out[12])
        self.assertIsNotNone(out[20])
        self.assertGreater(out[20], 0)


class TestDirection(unittest.TestCase):
    def test_rsi_bounds(self):
        up = [float(i) for i in range(1, 60)]
        out = ind.rsi(up, 14)
        self.assertAlmostEqual(out[-1], 100.0)
        down = list(reversed(up))
        self.assertAlmostEqual(ind.rsi(down, 14)[-1], 0.0)

    def test_adx_higher_in_a_trend_than_in_chop(self):
        n = 120
        trend_c = [100.0 + i for i in range(n)]
        trend = ind.adx([v + 1 for v in trend_c], [v - 1 for v in trend_c], trend_c, 14)
        chop_c = [100.0 + (1 if i % 2 else -1) for i in range(n)]
        chop = ind.adx([v + 1 for v in chop_c], [v - 1 for v in chop_c], chop_c, 14)
        self.assertGreater(trend[-1], chop[-1])


class TestDonchian(unittest.TestCase):
    def test_excludes_the_current_candle(self):
        highs = [10, 11, 12, 50]
        lows = [1, 2, 3, 0]
        up, dn = ind.donchian(highs, lows, 3)
        self.assertEqual(up[3], 12)   # die 50 der laufenden Kerze zählt nicht mit
        self.assertEqual(dn[3], 1)
        self.assertIsNone(up[2])

    def test_slope(self):
        out = ind.slope([1.0, 2.0, 5.0, 9.0], 2)
        self.assertIsNone(out[1])
        self.assertAlmostEqual(out[2], 4.0)
        self.assertAlmostEqual(out[3], 7.0)


if __name__ == "__main__":
    unittest.main()
