import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from tests.helpers import START
from bengx_bot.config import Config
from bengx_bot.data import synthetic, write_csv
from bengx_bot.journal import Journal, signals_payload, stats, write_signals
from bengx_bot.model import ExitReason, Side, Trade
from bengx_bot.runner import LiveGateError, Runner, backtest_path


def trade(n=1, pnl=100.0, pips=200.0, side=Side.LONG, hours=0):
    ts = START + timedelta(hours=hours)
    return Trade(id=f"sig-{n}", side=side, size=1.0, entry=2000.0, stop=1990.0,
                 target=2015.0, exit_price=2020.0, opened_at=ts,
                 closed_at=ts + timedelta(hours=2), pips=pips, pnl=pnl,
                 r_multiple=pnl / 100.0,
                 reason=ExitReason.TARGET if pnl > 0 else ExitReason.STOP,
                 note="Test")


class TestConfig(unittest.TestCase):
    def test_defaults_are_valid(self):
        Config().validate()

    def test_unknown_key_is_refused(self):
        with self.assertRaises(ValueError) as cm:
            Config.from_dict({"risk": {"risk_per_trade": 0.01, "tippfehler": 1}})
        self.assertIn("tippfehler", str(cm.exception))

    def test_absurd_risk_is_refused(self):
        with self.assertRaises(ValueError):
            Config.from_dict({"risk": {"risk_per_trade": 0.9}})

    def test_drawdown_order_is_checked(self):
        with self.assertRaises(ValueError):
            Config.from_dict({"risk": {"drawdown_halve": 0.2, "drawdown_stop": 0.1}})

    def test_session_must_be_within_a_day(self):
        with self.assertRaises(ValueError):
            Config.from_dict({"strategy": {"session_start_hour": 20,
                                           "session_end_hour": 7}})

    def test_fingerprint_is_stable_and_rule_sensitive(self):
        a, b = Config(), Config()
        self.assertEqual(a.fingerprint(), b.fingerprint())
        b.strategy.breakout = 30
        self.assertNotEqual(a.fingerprint(), b.fingerprint())

    def test_fingerprint_ignores_paths(self):
        a, b = Config(), Config()
        b.data.csv = "woanders.csv"
        b.live.poll_seconds = 999
        self.assertEqual(a.fingerprint(), b.fingerprint())

    def test_toml_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.toml"
            p.write_text('[risk]\nrisk_per_trade = 0.01\n\n[strategy]\nbreakout = 25\n',
                         encoding="utf-8")
            cfg = Config.load(p)
            self.assertAlmostEqual(cfg.risk.risk_per_trade, 0.01)
            self.assertEqual(cfg.strategy.breakout, 25)

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            Config.load("gibt-es-nicht.toml")


class TestJournal(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            j = Journal(Path(d) / "trades.jsonl")
            self.assertEqual(j.load(), [])
            j.append(trade(1))
            j.append(trade(2, pnl=-50.0, pips=-100.0, hours=3))
            back = j.load()
            self.assertEqual(len(back), 2)
            self.assertEqual(back[0].id, "sig-1")
            self.assertIs(back[1].side, Side.LONG)
            self.assertAlmostEqual(back[1].pnl, -50.0)

    def test_broken_line_names_the_line(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "trades.jsonl"
            p.write_text('{"kaputt": true}\n', encoding="utf-8")
            with self.assertRaises(ValueError) as cm:
                Journal(p).load()
            self.assertIn("Zeile 1", str(cm.exception))

    def test_stats_math(self):
        s = stats([trade(1, pnl=100.0), trade(2, pnl=-50.0), trade(3, pnl=200.0)])
        self.assertEqual(s["trades"], 3)
        self.assertEqual(s["wins"], 2)
        self.assertEqual(s["losses"], 1)
        self.assertAlmostEqual(s["winrate"], 2 / 3, places=4)
        self.assertAlmostEqual(s["net_pnl"], 250.0)
        self.assertAlmostEqual(s["profit_factor"], 6.0)

    def test_stats_without_losses(self):
        s = stats([trade(1, pnl=10.0)])
        self.assertEqual(s["profit_factor"], float("inf"))

    def test_empty_stats(self):
        s = stats([])
        self.assertIsNone(s["winrate"])
        self.assertEqual(s["trades"], 0)


class TestWebsitePayload(unittest.TestCase):
    """Der Vertrag zwischen Bot und Website: genau diese Felder liest die Seite."""

    EXPECTED = {"id", "pair", "side", "entry", "sl", "tp", "note",
                "status", "pips", "openedAt", "closedAt"}

    def test_field_names(self):
        payload = signals_payload([trade(1)])
        self.assertEqual(set(payload["signals"][0]), self.EXPECTED)

    def test_status_words_match_the_page(self):
        payload = signals_payload([trade(1, pnl=10.0), trade(2, pnl=-10.0, hours=1),
                                   trade(3, pnl=0.0, hours=2)])
        self.assertEqual({s["status"] for s in payload["signals"]},
                         {"gewonnen", "verloren", "be"})

    def test_newest_first(self):
        payload = signals_payload([trade(1, hours=0), trade(2, hours=5),
                                   trade(3, hours=2)])
        times = [s["openedAt"] for s in payload["signals"]]
        self.assertEqual(times, sorted(times, reverse=True))

    def test_open_position_comes_first_and_has_no_close(self):
        from bengx_bot.broker import PaperBroker

        b = PaperBroker(Config())
        pos = b.open(Side.LONG, 1.0, 2000.0, START + timedelta(hours=9), 0,
                     1990.0, 2015.0, "offen")
        payload = signals_payload([trade(1)], [pos])
        first = payload["signals"][0]
        self.assertEqual(first["status"], "offen")
        self.assertIsNone(first["closedAt"])

    def test_times_end_with_z(self):
        payload = signals_payload([trade(1)])
        self.assertTrue(payload["signals"][0]["openedAt"].endswith("Z"))

    def test_file_is_written(self):
        with tempfile.TemporaryDirectory() as d:
            p = write_signals(Path(d) / "signals.json", signals_payload([trade(1)]))
            data = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(len(data["signals"]), 1)


class TestRunner(unittest.TestCase):
    def _setup(self, d: str, bars: int = 1200) -> Config:
        root = Path(d)
        write_csv(root / "candles.csv", synthetic(bars, seed=4))
        cfg = Config()
        cfg.data.csv = str(root / "candles.csv")
        cfg.live.state_dir = str(root / "state")
        cfg.live.journal = str(root / "state" / "trades.jsonl")
        cfg.live.killswitch_file = str(root / "state" / "KILLSWITCH")
        cfg.live.signals_out = "signals.json"
        return cfg

    def test_tick_processes_and_persists(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._setup(d)
            info = Runner(cfg).tick()
            self.assertEqual(info["status"], "ok")
            self.assertGreater(info["new"], 0)
            self.assertTrue((Path(cfg.live.state_dir) / "state.json").exists())
            self.assertTrue((Path(cfg.live.state_dir) / "signals.json").exists())

    def test_second_tick_does_not_repeat_work(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._setup(d)
            first = Runner(cfg).tick()
            second = Runner(cfg).tick()
            self.assertEqual(second["new"], 0)
            self.assertAlmostEqual(second["equity"], first["equity"], places=2)

    def test_new_candles_are_picked_up(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._setup(d, bars=1200)
            Runner(cfg).tick()
            candles = synthetic(1260, seed=4)
            write_csv(cfg.data.csv, candles)
            self.assertEqual(Runner(cfg).tick()["new"], 60)

    def test_state_from_another_ruleset_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._setup(d)
            Runner(cfg).tick()
            cfg.strategy.breakout = 33
            with self.assertRaises(LiveGateError):
                Runner(cfg).tick()

    def test_killswitch_flattens_and_halts(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._setup(d)
            Runner(cfg).tick()
            Path(cfg.live.killswitch_file).parent.mkdir(parents=True, exist_ok=True)
            Path(cfg.live.killswitch_file).write_text("aus", encoding="utf-8")
            info = Runner(cfg).tick()
            self.assertEqual(info["status"], "Not-Aus")

    def test_live_needs_to_be_enabled(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._setup(d)
            with self.assertRaises(LiveGateError) as cm:
                Runner(cfg, live=True)
            self.assertIn("live.enabled", str(cm.exception))

    def test_live_needs_a_backtest(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._setup(d)
            cfg.live.enabled = True
            with self.assertRaises(LiveGateError) as cm:
                Runner(cfg, live=True)
            self.assertIn("Backtest", str(cm.exception))

    def test_live_still_refuses_with_the_paper_broker(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._setup(d)
            cfg.live.enabled = True
            p = backtest_path(cfg)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("{}", encoding="utf-8")
            with self.assertRaises(LiveGateError) as cm:
                Runner(cfg, live=True)
            self.assertIn("paper", str(cm.exception))

    def test_changing_a_rule_invalidates_the_release(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._setup(d)
            cfg.live.enabled = True
            p = backtest_path(cfg)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("{}", encoding="utf-8")
            cfg.strategy.stop_atr = 3.0          # Regel geändert
            with self.assertRaises(LiveGateError) as cm:
                Runner(cfg, live=True)
            self.assertIn("Backtest", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
