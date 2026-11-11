import unittest
from datetime import datetime, timedelta, timezone

from tests.helpers import START, candle, rows_to_candles
from bengx_bot.data import synthetic
from bengx_bot.model import Side
from bengx_bot.timeframes import (close_time, fair_value_gaps, liquidity_sweeps,
                                  resample, swing_points)


class TestResample(unittest.TestCase):
    def test_ohlc_is_aggregated(self):
        rows = [(100, 105, 99, 102), (102, 108, 101, 107),
                (107, 110, 104, 104), (104, 106, 100, 103), (103, 104, 102, 103)]
        m1 = rows_to_candles(rows)
        m5 = resample(m1, 5)
        self.assertEqual(len(m5), 1)
        c = m5[0]
        self.assertAlmostEqual(c.open, 100)
        self.assertAlmostEqual(c.high, 110)
        self.assertAlmostEqual(c.low, 99)
        self.assertAlmostEqual(c.close, 103)

    def test_buckets_start_on_the_hour(self):
        m1 = synthetic(300, seed=1, minutes=1,
                       begin=datetime(2024, 1, 1, 8, 37, tzinfo=timezone.utc))
        h1 = resample(m1, 60)
        self.assertTrue(all(c.ts.minute == 0 for c in h1))

    def test_incomplete_bucket_is_dropped(self):
        m1 = rows_to_candles([(100, 101, 99, 100)] * 7)
        self.assertEqual(len(resample(m1, 5)), 1)     # nur der volle Eimer
        self.assertEqual(len(resample(m1, 5, drop_incomplete=False)), 2)

    def test_volume_adds_up(self):
        m1 = rows_to_candles([(100, 101, 99, 100)] * 5)
        self.assertAlmostEqual(resample(m1, 5)[0].volume, 5000.0)

    def test_rejects_bad_ratios(self):
        m1 = rows_to_candles([(100, 101, 99, 100)] * 10)
        with self.assertRaises(ValueError):
            resample(m1, 7, source_minutes=5)      # kein Vielfaches
        with self.assertRaises(ValueError):
            resample(m1, 1, source_minutes=5)      # kleiner als die Quelle
        self.assertTrue(resample(m1, 7))           # 7 aus 1 ist in Ordnung

    def test_close_time(self):
        c = candle(START, 100, 101, 99, 100)
        self.assertEqual(close_time(c, 60), START + timedelta(hours=1))


class TestSwingPoints(unittest.TestCase):
    def test_finds_a_clear_high_and_low(self):
        rows = [(100, 101, 99, 100), (101, 102, 100, 101), (102, 110, 101, 103),
                (103, 104, 102, 103), (103, 104, 95, 100), (100, 101, 96, 100),
                (100, 101, 90, 95), (95, 96, 94, 95), (95, 97, 94, 96)]
        pts = swing_points(rows_to_candles(rows), 2, 1)
        highs = [p for p in pts if p.kind == "high"]
        lows = [p for p in pts if p.kind == "low"]
        self.assertTrue(any(abs(p.price - 110) < 1e-6 for p in highs))
        self.assertTrue(any(abs(p.price - 90) < 1e-6 for p in lows))

    def test_confirmation_comes_later(self):
        rows = [(100, 101, 99, 100), (101, 102, 100, 101), (102, 110, 101, 103),
                (103, 104, 102, 103), (103, 104, 102, 103)]
        pt = next(p for p in swing_points(rows_to_candles(rows), 2, 1)
                  if p.kind == "high")
        self.assertGreater(pt.known_ts, pt.ts,
                           "ein Hoch steht erst fest, wenn Kerzen danach gelaufen sind")
        self.assertEqual(pt.known_ts, pt.ts + timedelta(minutes=3))

    def test_lookback_must_be_positive(self):
        with self.assertRaises(ValueError):
            swing_points(rows_to_candles([(1, 2, 0.5, 1)] * 5), 0, 1)


class TestSweeps(unittest.TestCase):
    def _series(self, final_close: float):
        rows = [(100, 101, 99, 100), (101, 102, 100, 101), (102, 103, 95, 100),
                (100, 101, 97, 100), (100, 101, 98, 100), (100, 101, 99, 100),
                (100, 102, 94, final_close)]
        return rows_to_candles(rows)

    def test_sweep_needs_the_close_back_inside(self):
        hit = self._series(final_close=100)     # unter 95 gestochen, darüber zu
        pts = swing_points(hit, 2, 1)
        sweeps = liquidity_sweeps(hit, pts, 1)
        self.assertTrue(any(s.side is Side.LONG for s in sweeps))

        miss = self._series(final_close=94.5)   # unten geblieben
        sweeps = liquidity_sweeps(miss, swing_points(miss, 2, 1), 1)
        self.assertFalse([s for s in sweeps if s.side is Side.LONG])

    def test_a_level_is_only_swept_once(self):
        rows = [(100, 101, 99, 100), (101, 102, 100, 101), (102, 103, 95, 100),
                (100, 101, 97, 100), (100, 101, 98, 100),
                (100, 102, 94, 100), (100, 102, 93, 100), (100, 102, 92, 100)]
        c = rows_to_candles(rows)
        sweeps = [s for s in liquidity_sweeps(c, swing_points(c, 2, 1), 1)
                  if s.side is Side.LONG]
        self.assertEqual(len(sweeps), 1, "derselbe Punkt wird nicht mehrfach abgeräumt")

    def test_sweep_records_level_and_extreme(self):
        c = self._series(final_close=100)
        s = next(x for x in liquidity_sweeps(c, swing_points(c, 2, 1), 1)
                 if x.side is Side.LONG)
        self.assertAlmostEqual(s.level, 95.0)
        self.assertAlmostEqual(s.extreme, 94.0)
        self.assertEqual(s.known_ts, s.ts + timedelta(minutes=1))


class TestFairValueGaps(unittest.TestCase):
    def test_bullish_gap(self):
        rows = [(100, 101, 99, 100), (101, 108, 100, 107), (107, 110, 103, 109)]
        g = fair_value_gaps(rows_to_candles(rows), 1)
        self.assertEqual(len(g), 1)
        self.assertIs(g[0].side, Side.LONG)
        self.assertAlmostEqual(g[0].low, 101)     # Hoch der ersten Kerze
        self.assertAlmostEqual(g[0].high, 103)    # Tief der dritten

    def test_bearish_gap(self):
        rows = [(110, 111, 108, 109), (108, 109, 101, 102), (102, 105, 100, 101)]
        g = fair_value_gaps(rows_to_candles(rows), 1)
        self.assertEqual(len(g), 1)
        self.assertIs(g[0].side, Side.SHORT)
        self.assertAlmostEqual(g[0].low, 105)
        self.assertAlmostEqual(g[0].high, 108)

    def test_no_gap_when_candles_overlap(self):
        rows = [(100, 105, 99, 104), (104, 108, 103, 107), (107, 110, 102, 109)]
        self.assertEqual(fair_value_gaps(rows_to_candles(rows), 1), [])

    def test_min_size_filters_crumbs(self):
        rows = [(100, 101, 99, 100), (101, 108, 100, 107), (107, 110, 101.2, 109)]
        self.assertEqual(fair_value_gaps(rows_to_candles(rows), 1, min_size=1.0), [])
        self.assertEqual(len(fair_value_gaps(rows_to_candles(rows), 1, min_size=0.1)), 1)

    def test_level_and_contains(self):
        rows = [(100, 101, 99, 100), (101, 108, 100, 107), (107, 110, 103, 109)]
        g = fair_value_gaps(rows_to_candles(rows), 1)[0]
        self.assertAlmostEqual(g.level(0.0), 103.0)   # zuerst berührte Kante
        self.assertAlmostEqual(g.level(1.0), 101.0)   # ferne Kante
        self.assertAlmostEqual(g.level(0.5), 102.0)
        self.assertTrue(g.contains(102.0))
        self.assertFalse(g.contains(99.0))


if __name__ == "__main__":
    unittest.main()
