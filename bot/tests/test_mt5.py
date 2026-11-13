"""Der MT5-Anschluss gegen eine Attrappe.

Geprüft wird alles außer dem letzten Schritt — dass das echte Paket antwortet,
lässt sich nur unter Windows zeigen. Alles davor schon: Unzen in Lots,
Serverzeit in UTC, der echte Füllkurs statt des gewünschten, und der Abgleich
mit dem, was der Broker von sich aus geschlossen hat.
"""

import unittest
from datetime import datetime, timedelta, timezone

from tests.fake_mt5 import (FakeMT5, Konto, Symbol, TRADE_MODE_CONTEST,
                            TRADE_MODE_DEMO, TRADE_MODE_REAL,
                            RETCODE_INVALID_VOLUME)
from tests.helpers import quiet_minutes, rows_to_candles
from bengx_bot.config import Config
from bengx_bot.model import ExitReason, Side
from bengx_bot.mt5 import (MT5Broker, MT5Error, MT5Terminal, Zugang, lots,
                           unzen, verbinden)

def cfg_mt5(**over):
    cfg = Config()
    cfg.bot.name = "einzelschuss"
    cfg.live.broker = "mt5"
    cfg.live.enabled = True
    for k, v in over.items():
        setattr(cfg.mt5, k, v)
    cfg.validate()
    return cfg


def terminal(fake: FakeMT5) -> MT5Terminal:
    t = MT5Terminal(fake)
    t.verbinden()
    return t


def info(**over):
    """Die Spezifikation, wie der Bot sie sieht — durch die Übersetzung
    gereicht, damit der Test auch die prüft (MT5 nennt es
    `trade_contract_size`, der Bot `contract_size`)."""
    return terminal(FakeMT5(symbol=Symbol(**over))).symbol("XAUUSD")


GOLD = info()


# ---- Unzen und Lots ------------------------------------------------------
class TestMengen(unittest.TestCase):
    def test_one_lot_of_gold_is_a_hundred_ounces(self):
        self.assertAlmostEqual(lots(100.0, GOLD), 1.0)
        self.assertAlmostEqual(unzen(1.0, GOLD), 100.0)

    def test_the_size_is_rounded_down_never_up(self):
        """Lieber etwas weniger Risiko als etwas mehr."""
        self.assertAlmostEqual(lots(199.0, GOLD), 1.99)
        self.assertAlmostEqual(lots(199.9, GOLD), 1.99)

    def test_floating_point_does_not_eat_a_step(self):
        # 0,3 Lots sind 30 Unzen — und dürfen nicht als 0,29 herauskommen.
        self.assertAlmostEqual(lots(30.0, GOLD), 0.30)
        self.assertAlmostEqual(lots(70.0, GOLD), 0.70)

    def test_below_the_minimum_it_refuses_instead_of_guessing(self):
        with self.assertRaises(MT5Error) as ctx:
            lots(0.5, GOLD)
        self.assertIn("mindestens", str(ctx.exception))

    def test_it_never_exceeds_the_maximum(self):
        self.assertAlmostEqual(lots(10_000_000.0, GOLD), GOLD.volume_max)

    def test_a_cent_account_makes_small_positions_tradable(self):
        """Genau der Grund, warum solche Bots Cent-Konten empfehlen."""
        cent = info(trade_contract_size=1.0)
        self.assertAlmostEqual(lots(0.5, cent), 0.5)

    def test_zero_or_negative_is_refused(self):
        for menge in (0.0, -1.0):
            with self.assertRaises(MT5Error):
                lots(menge, GOLD)


# ---- Verbindung ----------------------------------------------------------
class TestVerbindung(unittest.TestCase):
    def test_a_failed_login_explains_what_to_check(self):
        fake = FakeMT5()
        fake.initialize_ok = False
        with self.assertRaises(MT5Error) as ctx:
            MT5Terminal(fake).verbinden(login=1, password="x", server="s")
        text = str(ctx.exception)
        self.assertIn("MT5_LOGIN", text)
        self.assertIn("Algo-Handel", text)

    def test_credentials_are_passed_through(self):
        fake = FakeMT5()
        MT5Terminal(fake).verbinden(login=42, password="geheim", server="Demo")
        self.assertEqual(fake.init_args["login"], 42)
        self.assertEqual(fake.init_args["server"], "Demo")

    def test_an_account_that_may_not_trade_is_refused(self):
        fake = FakeMT5(konto=Konto(trade_allowed=False))
        with self.assertRaises(MT5Error) as ctx:
            verbinden(cfg_mt5(), env={}, modul=fake)
        self.assertIn("darf nicht handeln", str(ctx.exception))

    def test_demo_and_contest_count_as_practice_real_does_not(self):
        for modus, demo in ((TRADE_MODE_DEMO, True), (TRADE_MODE_CONTEST, True),
                            (TRADE_MODE_REAL, False)):
            fake = FakeMT5(konto=Konto(trade_mode=modus))
            _, konto = verbinden(cfg_mt5(), env={}, modul=fake)
            with self.subTest(modus=modus):
                self.assertEqual(konto.demo, demo)

    def test_an_unknown_symbol_names_the_usual_alternatives(self):
        fake = FakeMT5()
        fake.kein_symbol = True
        with self.assertRaises(MT5Error) as ctx:
            terminal(fake).symbol("XAUUSD")
        self.assertIn("GOLD", str(ctx.exception))


class TestZugang(unittest.TestCase):
    def test_it_reads_the_env(self):
        z = Zugang.from_env({"MT5_LOGIN": "123", "MT5_PASSWORD": "p",
                             "MT5_SERVER": "s"})
        self.assertEqual(z.login, 123)
        self.assertTrue(z.vollstaendig)

    def test_an_empty_env_is_allowed_then_the_terminal_decides(self):
        z = Zugang.from_env({})
        self.assertIsNone(z.login)
        self.assertFalse(z.vollstaendig)

    def test_a_login_that_is_not_a_number_says_so(self):
        with self.assertRaises(MT5Error):
            Zugang.from_env({"MT5_LOGIN": "mein-konto"})


# ---- Zeit ----------------------------------------------------------------
class TestZeit(unittest.TestCase):
    def test_the_server_offset_is_measured_not_believed(self):
        fake = FakeMT5(server_offset_hours=3.0)
        self.assertEqual(terminal(fake).zeitversatz("XAUUSD"), timedelta(hours=3))

    def test_candles_come_back_in_utc(self):
        fake = FakeMT5(server_offset_hours=2.0)
        kerzen = rows_to_candles(quiet_minutes(30))
        fake.setze_kerzen("XAUUSD", kerzen)
        zurueck = terminal(fake).kerzen("XAUUSD", 1, 100)
        self.assertEqual(zurueck[0].ts, kerzen[0].ts)
        self.assertEqual(zurueck[0].ts.tzinfo, timezone.utc)

    def test_the_running_candle_is_left_out(self):
        fake = FakeMT5()
        kerzen = rows_to_candles(quiet_minutes(30))
        fake.setze_kerzen("XAUUSD", kerzen)
        self.assertEqual(len(terminal(fake).kerzen("XAUUSD", 1, 100)),
                         len(kerzen) - 1)

    def test_a_stale_tick_on_the_weekend_is_not_mistaken_for_a_timezone(self):
        """Am Wochenende ist der letzte Tick Tage alt. Daraus einen Versatz
        zu lesen hieße, zur völlig falschen Minute zu handeln."""
        fake = FakeMT5(server_offset_hours=0.0)
        fake.tick_zeit = datetime.now(timezone.utc) - timedelta(days=2)
        with self.assertRaises(MT5Error) as ctx:
            MT5Terminal(fake).zeitversatz("XAUUSD")
        self.assertIn("server_utc_offset_hours", str(ctx.exception))

    def test_a_configured_offset_wins_over_measuring(self):
        fake = FakeMT5(server_offset_hours=0.0)
        fake.tick_zeit = datetime.now(timezone.utc) - timedelta(days=2)
        t = MT5Terminal(fake)
        t.offset_vorgabe = 3.0
        self.assertEqual(t.zeitversatz("XAUUSD"), timedelta(hours=3))

    def test_an_unknown_timeframe_is_refused(self):
        with self.assertRaises(MT5Error):
            terminal(FakeMT5())._timeframe(7)


# ---- Order ---------------------------------------------------------------
class TestOrder(unittest.TestCase):
    def setUp(self):
        self.fake = FakeMT5()
        self.cfg = cfg_mt5()
        self.t = terminal(self.fake)
        self.broker = MT5Broker(self.cfg, self.t)
        self.jetzt = datetime(2024, 1, 15, 12, 30, tzinfo=timezone.utc)

    def _open(self, size=20.0, stop=1997.5, ziel=2005.0):
        return self.broker.open(side=Side.LONG, size=size, price=2000.30,
                                when=self.jetzt, bar=5, stop=stop, target=ziel,
                                note="CPI", final_target=ziel)

    def test_an_order_reaches_the_terminal_with_magic_and_stops(self):
        self._open()
        gesendet = self.fake.gesendet[-1]
        self.assertEqual(gesendet["magic"], self.cfg.mt5.magic)
        self.assertEqual(gesendet["volume"], 0.20)
        self.assertEqual(gesendet["sl"], 1997.50)
        self.assertEqual(gesendet["tp"], 2005.00)

    def test_the_booked_price_is_the_fill_not_the_wish(self):
        self.fake.slippage = 0.40            # 4 Pips schlechter
        pos = self._open()
        self.assertAlmostEqual(pos.entry, 2000.70, places=2)
        self.assertGreater(pos.initial_risk, 2000.30 - 1997.50)

    def test_the_slippage_is_recorded_for_later(self):
        self.fake.slippage = 0.40
        pos = self._open()
        kontext = self.broker.kontext[pos.id]
        self.assertAlmostEqual(kontext["slippage_pips"], 4.0, places=1)
        self.assertAlmostEqual(kontext["spread_pips"], 3.0, places=1)

    def test_a_rejected_order_raises_instead_of_pretending(self):
        self.fake.naechster_retcode = RETCODE_INVALID_VOLUME
        with self.assertRaises(MT5Error) as ctx:
            self._open()
        self.assertIn("abgelehnt", str(ctx.exception))

    def test_stops_too_close_are_left_off_rather_than_killing_the_order(self):
        self.fake.symbol_obj.trade_stops_level = 500      # 5 USD Mindestabstand
        broker = MT5Broker(self.cfg, self.t)
        broker.open(side=Side.LONG, size=20.0, price=2000.30, when=self.jetzt,
                    bar=5, stop=1999.90, target=2000.70, final_target=2000.70)
        gesendet = self.fake.gesendet[-1]
        self.assertNotIn("sl", gesendet)
        self.assertNotIn("tp", gesendet)

    def test_closing_sends_a_counter_order_on_the_same_ticket(self):
        pos = self._open()
        ticket = self.broker.tickets[pos.id]
        trade = self.broker.close(pos, 2004.0, self.jetzt, ExitReason.TARGET)
        gesendet = self.fake.gesendet[-1]
        self.assertEqual(gesendet["position"], ticket)
        self.assertEqual(gesendet["type"], 1)             # SELL schließt LONG
        self.assertEqual(trade.reason, ExitReason.TARGET)
        self.assertEqual(self.broker.positions, [])

    def test_a_trailing_stop_is_written_into_the_terminal(self):
        """Ein Stop, der nur im Speicher steht, löst nichts aus."""
        pos = self._open()
        ticket = self.broker.tickets[pos.id]
        pos.stop = 2001.00
        self.assertEqual(self.broker.stops_nachziehen(), 1)
        self.assertAlmostEqual(self.fake.positionen[ticket].sl, 2001.00, places=2)

    def test_an_unchanged_stop_sends_nothing(self):
        self._open()
        self.assertEqual(self.broker.stops_nachziehen(), 0)

    def test_a_partial_reduces_the_position_but_keeps_it(self):
        pos = self._open(size=40.0)
        self.broker.reduce(pos, 0.5, 2003.0)
        self.assertTrue(pos.partial_done)
        self.assertAlmostEqual(pos.size, 20.0)
        self.assertIn(pos, self.broker.positions)

    def test_a_partial_too_small_to_trade_is_skipped_silently(self):
        pos = self._open(size=1.0)           # 0,01 Lots, nicht teilbar
        vorher = len(self.fake.gesendet)
        self.broker.reduce(pos, 0.5, 2003.0)
        self.assertEqual(len(self.fake.gesendet), vorher)
        self.assertAlmostEqual(pos.size, 1.0)


# ---- Abgleich ------------------------------------------------------------
class TestAbgleich(unittest.TestCase):
    """Der wichtigste Teil: Stop und Ziel liegen im Terminal. Die meisten
    Trades enden dort, nicht in engine.py."""

    def setUp(self):
        self.fake = FakeMT5()
        self.cfg = cfg_mt5()
        self.t = terminal(self.fake)
        self.broker = MT5Broker(self.cfg, self.t)
        self.jetzt = datetime(2024, 1, 15, 12, 30, tzinfo=timezone.utc)
        self.pos = self.broker.open(side=Side.LONG, size=20.0, price=2000.30,
                                    when=self.jetzt, bar=5, stop=1997.50,
                                    target=2005.0, note="CPI",
                                    final_target=2005.0, source_id="CPI")
        self.ticket = self.broker.tickets[self.pos.id]

    def test_nothing_closed_means_nothing_to_report(self):
        self.assertEqual(self.broker.abgleich(), [])

    def test_a_stop_hit_by_the_broker_lands_in_the_journal(self):
        self.fake.stop_ausloesen(self.ticket, 1997.50)
        trades = self.broker.abgleich()
        self.assertEqual(len(trades), 1)
        t = trades[0]
        self.assertIs(t.reason, ExitReason.STOP)
        self.assertAlmostEqual(t.exit_price, 1997.50, places=2)
        self.assertLess(t.pnl, 0)
        self.assertEqual(self.broker.positions, [])

    def test_a_target_hit_by_the_broker_is_recognised_as_such(self):
        self.fake.stop_ausloesen(self.ticket, 2005.00, kommentar="[tp 2005.00]")
        trades = self.broker.abgleich()
        self.assertIs(trades[0].reason, ExitReason.TARGET)
        self.assertGreater(trades[0].pnl, 0)

    def test_without_a_comment_the_direction_decides(self):
        self.fake.stop_ausloesen(self.ticket, 2004.00, kommentar="")
        self.assertIs(self.broker.abgleich()[0].reason, ExitReason.TARGET)

    def test_the_context_from_entry_survives_into_the_trade(self):
        self.fake.stop_ausloesen(self.ticket, 1997.50)
        marken = self.broker.abgleich()[0].tags
        self.assertEqual(marken["broker"], "mt5")
        self.assertEqual(marken["source_id"], "CPI")
        self.assertIn("slippage_pips", marken)
        self.assertIn("spread_pips", marken)

    def test_the_closing_time_comes_from_the_deal_in_utc(self):
        spaeter = self.jetzt + timedelta(minutes=7)
        self.fake.jetzt = spaeter
        self.fake.stop_ausloesen(self.ticket, 1997.50)
        self.assertEqual(self.broker.abgleich()[0].closed_at, spaeter)

    def test_tickets_are_recovered_after_a_restart(self):
        neu = MT5Broker(self.cfg, self.t)
        neu.positions.append(self.pos)
        self.assertEqual(neu.uebernehmen(), 1)
        self.assertEqual(neu.tickets[self.pos.id], self.ticket)

    def test_positions_from_a_paper_run_are_dropped_on_takeover(self):
        from bengx_bot.model import Position
        neu = MT5Broker(self.cfg, self.t)
        papier = Position(id="sig-20240115-1230-001", side=Side.LONG, size=1.0,
                          entry=2000.0, stop=1990.0, target=2010.0,
                          opened_at=self.jetzt, opened_bar=1, initial_risk=10.0)
        neu.positions.append(papier)
        self.assertEqual(neu.uebernehmen(), 0)
        self.assertEqual(neu.positions, [])


if __name__ == "__main__":
    unittest.main()
