import json
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from tests.helpers import START, rows_to_candles
from bengx_bot.backtest import run_backtest
from bengx_bot.config import Config
from bengx_bot.copier import (FileSource, HttpSource, Kopierer, SourceSignal,
                              make_source, parse_payload)
from bengx_bot.data import synthetic
from bengx_bot.journal import signals_payload, write_signals
from bengx_bot.model import ExitReason, Side

HOUR = timedelta(hours=1)


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def raw(sid="s1", side="long", entry=2000.0, sl=1990.0, tp=2015.0,
        status="offen", opened=START, closed=None, note=""):
    return {"id": sid, "pair": "XAU/USD", "side": side, "entry": entry,
            "sl": sl, "tp": tp, "note": note, "status": status, "pips": 0,
            "openedAt": iso(opened),
            "closedAt": iso(closed) if closed else None}


class Fixed:
    """Eine Quelle, die genau das liefert, was der Test vorgibt."""

    def __init__(self, items):
        self.items = items

    def load(self):
        return parse_payload({"signals": self.items})


def copy_cfg(**over):
    cfg = Config()
    cfg.bot.name = "kopierer"
    cfg.data.warmup_bars = 20
    for k, v in over.items():
        setattr(cfg.copy, k, v)
    cfg.validate()
    return cfg


def flat_candles(n=60, price=2000.0, span=12.0, start=START):
    """Stundenkerzen, deren Spanne Bens Einstiegskurs sicher enthält."""
    rows = [(price, price + span, price - span, price) for _ in range(n)]
    return rows_to_candles(rows, start=start, minutes=60)


class TestParsing(unittest.TestCase):
    def test_reads_the_website_format(self):
        s = parse_payload({"signals": [raw()]})[0]
        self.assertEqual(s.id, "s1")
        self.assertIs(s.side, Side.LONG)
        self.assertAlmostEqual(s.entry, 2000.0)
        self.assertTrue(s.is_open)
        self.assertIsNone(s.closed_at)

    def test_sorted_by_opening(self):
        items = [raw("b", opened=START + 2 * HOUR), raw("a", opened=START)]
        self.assertEqual([s.id for s in parse_payload({"signals": items})], ["a", "b"])

    def test_missing_list(self):
        with self.assertRaises(ValueError):
            parse_payload({"foo": 1})

    def test_missing_id(self):
        bad = raw(); del bad["id"]
        with self.assertRaises(ValueError) as cm:
            parse_payload({"signals": [bad]})
        self.assertIn("id", str(cm.exception))

    def test_bad_side(self):
        with self.assertRaises(ValueError):
            parse_payload({"signals": [raw(side="seitwärts")]})

    def test_bad_status(self):
        with self.assertRaises(ValueError):
            parse_payload({"signals": [raw(status="vielleicht")]})

    def test_closed_without_time(self):
        bad = raw(status="gewonnen")
        with self.assertRaises(ValueError) as cm:
            parse_payload({"signals": [bad]})
        self.assertIn("closedAt", str(cm.exception))

    def test_missing_entry(self):
        bad = raw(); bad["entry"] = None
        with self.assertRaises(ValueError):
            parse_payload({"signals": [bad]})

    def test_unreadable_time(self):
        bad = raw(); bad["openedAt"] = "neulich"
        with self.assertRaises(ValueError):
            parse_payload({"signals": [bad]})

    def test_missing_stop_is_allowed(self):
        item = raw(); item["sl"] = None
        self.assertIsNone(parse_payload({"signals": [item]})[0].stop)


class TestSources(unittest.TestCase):
    def test_file_source(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "signals.json"
            p.write_text(json.dumps({"signals": [raw()]}), encoding="utf-8")
            self.assertEqual(len(FileSource(p).load()), 1)

    def test_missing_file_says_where_it_looked(self):
        with self.assertRaises(FileNotFoundError) as cm:
            FileSource("/gibt/es/nicht/signals.json").load()
        self.assertIn("signals.json", str(cm.exception))

    def test_http_source(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "signals.json").write_text(
                json.dumps({"signals": [raw(), raw("s2", side="short")]}),
                encoding="utf-8")
            handler = partial(SimpleHTTPRequestHandler, directory=d)
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                url = f"http://127.0.0.1:{server.server_port}/signals.json"
                self.assertEqual(len(HttpSource(url).load()), 2)
            finally:
                server.shutdown()
                server.server_close()

    def test_http_failure_is_clear(self):
        with self.assertRaises(ConnectionError) as cm:
            HttpSource("http://127.0.0.1:1/signals.json", timeout=1.0).load()
        self.assertIn("nicht abrufbar", str(cm.exception))

    def test_make_source_follows_the_config(self):
        self.assertIsInstance(make_source(copy_cfg()), FileSource)
        self.assertIsInstance(
            make_source(copy_cfg(source="http", url="http://x/y.json")), HttpSource)

    def test_http_without_url_is_refused(self):
        with self.assertRaises(ValueError):
            copy_cfg(source="http", url="")


class TestWhatIsCopied(unittest.TestCase):
    def prepare(self, items, candles=None, **over):
        cfg = copy_cfg(**over)
        candles = candles if candles is not None else flat_candles()
        k = Kopierer(cfg, Fixed(items))
        return k, k.prepare(candles), candles

    def test_open_signal_is_mirrored(self):
        _, ctx, _ = self.prepare([raw(opened=START + 5 * HOUR)])
        self.assertEqual(len(ctx.signals), 1)
        sig = next(iter(ctx.signals.values()))
        self.assertIs(sig.side, Side.LONG)
        self.assertEqual(sig.source_id, "s1")
        self.assertAlmostEqual(sig.entry, 2000.0)
        self.assertAlmostEqual(sig.stop, 1990.0)
        self.assertAlmostEqual(sig.final_target, 2015.0)

    def test_short_is_mirrored(self):
        _, ctx, _ = self.prepare([raw(side="short", entry=2000.0, sl=2010.0,
                                      tp=1985.0, opened=START + 5 * HOUR)])
        sig = next(iter(ctx.signals.values()))
        self.assertIs(sig.side, Side.SHORT)
        self.assertGreater(sig.stop, sig.entry)
        self.assertLess(sig.final_target, sig.entry)

    def test_already_closed_signal_is_skipped(self):
        """Fehlen Kerzen — Wochenende, Ausfall —, ist das Signal beim ersten
        verfügbaren Kurs längst erledigt. Dann wird es nicht mehr eröffnet."""
        early = [(2000, 2012, 1988, 2000)] * 6
        candles = rows_to_candles(early, start=START, minutes=60)
        candles += rows_to_candles([(2000, 2012, 1988, 2000)] * 30,
                                   start=START + 20 * HOUR, minutes=60)
        _, ctx, _ = self.prepare(
            [raw(status="gewonnen", opened=START + 7 * HOUR,
                 closed=START + 8 * HOUR)], candles=candles)
        self.assertEqual(ctx.signals, {})
        self.assertIn("schon geschlossen", ctx.skipped["s1"])

    def test_signal_that_closes_later_is_mirrored(self):
        _, ctx, _ = self.prepare([raw(status="gewonnen", opened=START + 5 * HOUR,
                                      closed=START + 9 * HOUR)])
        self.assertEqual(len(ctx.signals), 1,
                         "im Rückblick war der Trade zur Eröffnung noch offen")

    def test_stale_signal_is_skipped(self):
        """Ein Signal von vor Stunden wird nicht nachträglich eröffnet."""
        _, ctx, _ = self.prepare(
            [raw(opened=START + timedelta(minutes=1))], max_age_minutes=5)
        self.assertEqual(ctx.signals, {})
        self.assertIn("zu alt", ctx.skipped["s1"])

    def test_signal_outside_the_candles_is_skipped(self):
        _, ctx, _ = self.prepare([raw(opened=START - 10 * HOUR)])
        self.assertIn("außerhalb", ctx.skipped["s1"])

    def test_runaway_price_is_not_chased(self):
        candles = flat_candles(span=0.5)        # enge Kerzen um 2000
        _, ctx, _ = self.prepare([raw(entry=2100.0, sl=2090.0, tp=2130.0,
                                      opened=START + 5 * HOUR)],
                                 candles=candles, max_slippage_pips=10.0)
        self.assertEqual(ctx.signals, {})
        self.assertIn("weggelaufen", ctx.skipped["s1"])

    def test_small_difference_is_accepted_at_the_current_price(self):
        candles = flat_candles(span=0.5)
        _, ctx, _ = self.prepare([raw(entry=2001.0, sl=1990.0, tp=2015.0,
                                      opened=START + 5 * HOUR)],
                                 candles=candles, max_slippage_pips=200.0)
        sig = next(iter(ctx.signals.values()))
        self.assertAlmostEqual(sig.entry, 2000.0, places=6)

    def test_market_mode_enters_where_limit_mode_gives_up(self):
        candles = flat_candles(span=0.5)
        items = [raw(entry=2005.0, sl=1990.0, tp=2020.0, opened=START + 5 * HOUR)]
        _, limited, _ = self.prepare(items, candles=candles,
                                     max_slippage_pips=10.0)
        self.assertEqual(limited.signals, {})
        _, market, _ = self.prepare(items, candles=candles,
                                    entry_mode="market", max_slippage_pips=10.0)
        self.assertAlmostEqual(next(iter(market.signals.values())).entry,
                               2000.0, places=6)

    def test_market_mode_still_refuses_an_impossible_stop(self):
        """Ist der Kurs weit weg, liegt Bens Stop schnell auf der falschen Seite."""
        candles = flat_candles(span=0.5)
        _, ctx, _ = self.prepare([raw(entry=2100.0, sl=2090.0, tp=2130.0,
                                      opened=START + 5 * HOUR)],
                                 candles=candles, entry_mode="market")
        self.assertIn("falschen Seite", ctx.skipped["s1"])

    def test_stop_on_the_wrong_side_is_refused(self):
        _, ctx, _ = self.prepare([raw(sl=2010.0, opened=START + 5 * HOUR)])
        self.assertIn("falschen Seite", ctx.skipped["s1"])

    def test_stop_distance_bounds(self):
        _, ctx, _ = self.prepare([raw(opened=START + 5 * HOUR)],
                                 min_stop_pips=5000.0, max_stop_pips=9000.0)
        self.assertIn("außerhalb der Grenzen", ctx.skipped["s1"])

    def test_fallback_stop_from_atr(self):
        item = raw(opened=START + 30 * HOUR); item["sl"] = None
        candles = rows_to_candles(
            [(2000, 2006, 1994, 2000)] * 60, start=START, minutes=60)
        _, ctx, _ = self.prepare([item], candles=candles, follow_stop=False)
        sig = next(iter(ctx.signals.values()))
        self.assertLess(sig.stop, sig.entry)

    def test_target_can_be_ignored(self):
        _, ctx, _ = self.prepare([raw(opened=START + 5 * HOUR)], follow_target=False)
        self.assertIsNone(next(iter(ctx.signals.values())).final_target)

    def test_nonsense_target_is_dropped(self):
        _, ctx, _ = self.prepare([raw(tp=1950.0, opened=START + 5 * HOUR)])
        self.assertIsNone(next(iter(ctx.signals.values())).final_target)


class TestSizingAndExits(unittest.TestCase):
    def _trades(self, items, candles, **over):
        cfg = copy_cfg(**over)
        for key in ("start_equity",):
            if key in over:
                setattr(cfg.risk, key, over[key])
        k = Kopierer(cfg, Fixed(items))
        return cfg, run_backtest(cfg, candles, strategy=k)

    def test_size_comes_from_the_own_account(self):
        candles = flat_candles(120)
        small = Config(); small.bot.name = "kopierer"; small.data.warmup_bars = 20
        small.risk.start_equity = 1000.0; small.validate()
        big = Config(); big.bot.name = "kopierer"; big.data.warmup_bars = 20
        big.risk.start_equity = 100_000.0; big.validate()
        item = [raw(opened=START + 30 * HOUR)]
        a = run_backtest(small, candles, strategy=Kopierer(small, Fixed(item)))
        b = run_backtest(big, candles, strategy=Kopierer(big, Fixed(item)))
        self.assertGreater(b.trades[0].size, a.trades[0].size * 10,
                           "die Größe richtet sich nach dem eigenen Konto")
        self.assertAlmostEqual(a.trades[0].entry, b.trades[0].entry, places=6)

    def test_closes_when_the_source_closes(self):
        rows = [(2000, 2002, 1998, 2000)] * 60
        candles = rows_to_candles(rows, start=START, minutes=60)
        items = [raw(sl=1900.0, tp=2500.0, opened=START + 30 * HOUR,
                     status="gewonnen", closed=START + 40 * HOUR)]
        _, result = self._trades(items, candles, min_stop_pips=1.0,
                                 max_stop_pips=5000.0)
        self.assertEqual(len(result.trades), 1)
        self.assertIs(result.trades[0].reason, ExitReason.MANUAL)
        self.assertEqual(result.trades[0].closed_at, START + 40 * HOUR)

    def test_can_be_told_not_to_follow_the_close(self):
        rows = [(2000, 2002, 1998, 2000)] * 60
        candles = rows_to_candles(rows, start=START, minutes=60)
        items = [raw(sl=1900.0, tp=2500.0, opened=START + 30 * HOUR,
                     status="gewonnen", closed=START + 40 * HOUR)]
        _, result = self._trades(items, candles, close_with_source=False,
                                 min_stop_pips=1.0, max_stop_pips=5000.0)
        self.assertGreater(result.trades[0].closed_at, START + 40 * HOUR,
                           "ohne Mitschließen läuft die Position weiter")

    def test_own_stop_wins_over_the_source_close(self):
        rows = [(2000, 2002, 1998, 2000)] * 35 + [(2000, 2002, 1980, 1985)] * 25
        candles = rows_to_candles(rows, start=START, minutes=60)
        items = [raw(sl=1990.0, tp=2500.0, opened=START + 30 * HOUR,
                     status="gewonnen", closed=START + 36 * HOUR)]
        _, result = self._trades(items, candles, max_stop_pips=5000.0)
        self.assertIs(result.trades[0].reason, ExitReason.STOP,
                      "der eigene Stop greift, auch wenn Ben gleichzeitig schließt")

    def test_no_partial_by_default(self):
        self.assertAlmostEqual(Kopierer(copy_cfg(), Fixed([])).exit_rules()
                               .partial_fraction, 0.0)


class TestEndToEnd(unittest.TestCase):
    def test_copies_a_whole_run_of_the_other_bot(self):
        candles = synthetic(3000, seed=42, minutes=60)
        ben = run_backtest(Config(), candles)
        self.assertGreater(len(ben.trades), 5)

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "signals.json"
            write_signals(p, signals_payload(ben.trades, pip=0.1))

            cfg = copy_cfg(path=str(p))
            cfg.risk.start_equity = 2000.0
            copy = run_backtest(cfg, candles, strategy=Kopierer(cfg, FileSource(p)))

            self.assertEqual(len(copy.trades), len(ben.trades),
                             "jedes Signal muss ankommen")
            self.assertEqual([t.side for t in copy.trades],
                             [t.side for t in ben.trades])
            self.assertEqual([t.tags["source_id"] for t in copy.trades],
                             [t.id for t in ben.trades])

    def test_exported_stop_is_the_entry_stop(self):
        """Im Protokoll steht der Stop der Eröffnung, nicht der nachgezogene."""
        candles = synthetic(3000, seed=42, minutes=60)
        for t in run_backtest(Config(), candles).trades:
            if t.side is Side.LONG:
                self.assertLess(t.stop, t.entry)
            else:
                self.assertGreater(t.stop, t.entry)


if __name__ == "__main__":
    unittest.main()
