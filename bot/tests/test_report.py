import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bengx_bot import report
from bengx_bot.config import Config
from bengx_bot.journal import Journal
from bengx_bot.model import ExitReason, Side, Trade
from bengx_bot.state import BotState, save_state


def trade(hours_ago=1.0, pnl=20.0, pips=200.0):
    close = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return Trade(id=f"t{hours_ago}", side=Side.LONG, size=1.0, entry=2000.0,
                 stop=1990.0, target=2015.0, exit_price=2020.0,
                 opened_at=close - timedelta(hours=1), closed_at=close,
                 pips=pips, pnl=pnl, r_multiple=pnl / 10.0,
                 reason=ExitReason.TARGET if pnl > 0 else ExitReason.STOP)


class TestFenster(unittest.TestCase):
    def setUp(self):
        self.alle = [trade(1), trade(50), trade(400), trade(2000)]

    def test_heute(self):
        self.assertEqual(len(report.window(self.alle, "heute")), 1)

    def test_woche_und_monat(self):
        self.assertGreaterEqual(len(report.window(self.alle, "woche")), 2)
        self.assertGreaterEqual(len(report.window(self.alle, "monat")), 3)

    def test_alles(self):
        self.assertEqual(len(report.window(self.alle, "alles")), 4)
        self.assertEqual(len(report.window(self.alle, "")), 4)

    def test_unbekannter_zeitraum_gibt_alles(self):
        self.assertEqual(len(report.window(self.alle, "irgendwann")), 4)


class TestLage(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        d = self.dir.name
        self.cfg = Config()
        self.cfg.live.state_dir = d
        self.cfg.live.journal = str(Path(d) / "trades.jsonl")
        self.cfg.live.killswitch_file = str(Path(d) / "KILLSWITCH")

    def tearDown(self):
        self.dir.cleanup()

    def test_leerer_stand(self):
        lage = report.build(self.cfg)
        self.assertIsNone(lage.equity)
        self.assertEqual(lage.trades_gesamt, 0)
        self.assertFalse(lage.killswitch)
        self.assertIn("noch kein Lauf", lage.text())

    def test_zahlen_kommen_aus_dem_protokoll(self):
        j = Journal(self.cfg.live.journal)
        j.append(trade(1, pnl=30.0))
        j.append(trade(2, pnl=-10.0, pips=-100.0))
        lage = report.build(self.cfg)
        self.assertEqual(lage.trades_gesamt, 2)
        self.assertEqual(lage.heute["trades"], 2)
        self.assertAlmostEqual(lage.gesamt["net_pnl"], 20.0)
        self.assertIn("Heute:", lage.text())

    def test_not_aus_steht_oben(self):
        Path(self.cfg.live.killswitch_file).write_text("aus", encoding="utf-8")
        lage = report.build(self.cfg)
        self.assertTrue(lage.killswitch)
        self.assertIn("NOT-AUS IST AKTIV", lage.text().splitlines()[1])

    def test_alte_daten_werden_gemeldet(self):
        save_state(Path(self.cfg.live.state_dir) / "state.json", BotState(
            equity=10_000.0, peak=10_000.0,
            last_bar_ts=(datetime.now(timezone.utc) - timedelta(hours=30)).isoformat(),
            fingerprint=self.cfg.fingerprint()))
        lage = report.build(self.cfg)
        self.assertTrue(any("keine neue Kerze" in h for h in lage.hinweise))

    def test_frische_daten_ohne_hinweis(self):
        save_state(Path(self.cfg.live.state_dir) / "state.json", BotState(
            equity=10_000.0, peak=10_000.0,
            last_bar_ts=datetime.now(timezone.utc).isoformat(),
            fingerprint=self.cfg.fingerprint()))
        self.assertEqual(report.build(self.cfg).hinweise, [])

    def test_fremdes_regelwerk_wird_gemeldet(self):
        save_state(Path(self.cfg.live.state_dir) / "state.json", BotState(
            equity=10_000.0, peak=10_000.0,
            last_bar_ts=datetime.now(timezone.utc).isoformat(),
            fingerprint="anderes"))
        self.assertTrue(any("anderen Regelwerk" in h
                            for h in report.build(self.cfg).hinweise))

    def test_signale_text(self):
        Journal(self.cfg.live.journal).append(trade(1, pnl=30.0, pips=300.0))
        text = report.signale_text(self.cfg, "heute")
        self.assertIn("+300.0 Pips", text)

    def test_aufgaben_bleiben_erhalten(self):
        report.aufgabe_anlegen(self.cfg, "erste")
        report.aufgabe_anlegen(self.cfg, "zweite")
        liste = report.aufgaben_lesen(self.cfg)
        self.assertEqual([a["text"] for a in liste], ["erste", "zweite"])
        self.assertTrue(all(a["status"] == "offen" for a in liste))

    def test_kaputte_aufgabendatei_wirft_nicht(self):
        report.aufgaben_datei(self.cfg).parent.mkdir(parents=True, exist_ok=True)
        report.aufgaben_datei(self.cfg).write_text("kein json", encoding="utf-8")
        self.assertEqual(report.aufgaben_lesen(self.cfg), [])


if __name__ == "__main__":
    unittest.main()
