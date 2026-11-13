"""Tests für den Telegram-Bot — ohne Modell, nur fester Ablauf."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bengx_bot.config import Config
from bengx_bot.gruppen import GruppenSettings, Verteiler
from bengx_bot.telegram import (DOPPELT, FakeTransport, TelegramBot,
                                TelegramSettings, Umgezogen, _split,
                                _umgezogen_nach, load_env_file)
from tests.test_gruppen import SIGNAL, Uhr


def update(text=None, chat="42", typ="private", uid=1):
    message = {"message_id": uid, "chat": {"id": int(chat), "type": typ}}
    if text is not None:
        message["text"] = text
    return {"update_id": uid, "message": message}


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        d = self.dir.name
        self.cfg = Config()
        self.cfg.live.state_dir = d
        self.cfg.live.journal = str(Path(d) / "trades.jsonl")
        self.cfg.live.killswitch_file = str(Path(d) / "KILLSWITCH")
        self.tg = TelegramSettings(token="t", chat_id="42")
        self.net = FakeTransport()
        self.takt = Uhr(stunde=11)
        self.verteiler = Verteiler(
            GruppenSettings(vip_chat_id="-200", inner_chat_id="-100",
                            inner_verzug_min=0,
                            state_file=str(Path(d) / "g.json")),
            self.net, pip=0.1, uhr=self.takt)
        self.bot = TelegramBot(self.cfg, self.tg, self.net, self.verteiler)

    def tearDown(self):
        self.dir.cleanup()

    def sag(self, text):
        return "\n".join(self.bot.handle(update(text)))


class TestZugang(Base):
    def test_fremder_einzelchat(self):
        self.assertIn("nicht freigegeben",
                      "\n".join(self.bot.handle(update("hallo", chat="999"))))

    def test_in_gruppen_schweigt_er(self):
        for typ in ("group", "supergroup", "channel"):
            self.assertEqual(
                self.bot.handle(update("test", chat="-100", typ=typ)), [], typ)

    def test_ohne_kennung_nennt_er_sie_nur_im_einzelchat(self):
        bot = TelegramBot(self.cfg, TelegramSettings(token="t"), self.net)
        self.assertIn("Deine lautet: 999",
                      "\n".join(bot.handle(update("hi", chat="999"))))
        self.assertEqual(
            bot.handle(update("hi", chat="-100", typ="supergroup")), [])


class TestSignalDurchgeben(Base):
    def test_vorschau_dann_ja(self):
        antwort = self.sag("long 4012, stop 4004, ziel 4029, 1h sweep")
        self.assertIn("── VIP ──", antwort)
        self.assertIn("── Inner Circle ──", antwort)
        self.assertIn("ja", antwort)
        self.assertEqual(self.net.sent, [])       # noch nichts verschickt

        raus = self.sag("ja")
        self.assertIn("Raus als sig-0001", raus)
        self.assertEqual(sorted(n["chat_id"] for n in self.net.sent),
                         ["-100", "-200"])

    def test_nein_verwirft(self):
        self.sag("long 4012, stop 4004, ziel 4029")
        self.assertIn("verworfen", self.sag("nein"))
        self.assertEqual(self.net.sent, [])

    def test_waehrend_ein_entwurf_liegt_zaehlt_nur_ja_nein(self):
        self.sag("long 4012, stop 4004, ziel 4029")
        self.assertIn("Entwurf liegt noch bereit", self.sag("wie läuft es"))

    def test_falsches_signal_wird_erklaert(self):
        antwort = self.sag("long 4012, stop 4020, ziel 4029")
        self.assertIn("Stop unter", antwort)
        self.assertEqual(self.net.sent, [])

    def test_sagt_wenn_der_inner_circle_leer_ausgeht(self):
        self.sag("long 4012, stop 4004, ziel 4029")
        self.sag("ja")
        antwort = self.sag("long 4013, stop 4005, ziel 4030")
        self.assertIn("Der Inner Circle bekommt es nicht", antwort)


class TestErgebnisMelden(Base):
    def _signal(self):
        self.sag("long 4012, stop 4004, ziel 4029")
        self.sag("ja")
        self.net.sent.clear()

    def test_neuestes_offenes(self):
        self._signal()
        antwort = self.sag("ziel")
        self.assertIn("gewonnen", antwort)
        self.assertIn("+170", antwort)
        self.assertEqual(len(self.net.sent), 2)

    def test_bestimmtes_signal(self):
        self._signal()
        self.assertIn("sig-0001", self.sag("sig-1 stop"))

    def test_ohne_offenes_signal(self):
        self.assertIn("Kein offenes Signal", self.sag("ziel"))


class TestBefehle(Base):
    def test_hilfe(self):
        self.assertIn("long 4012", self.sag("/hilfe"))

    def test_gruppen(self):
        self.assertIn("VIP: sofort", self.sag("/gruppen"))

    def test_einladung(self):
        self.assertIn("https://t.me/+", self.sag("/einladung vip Max"))

    def test_einladung_ohne_gruppe(self):
        self.assertIn("/einladung vip", self.sag("/einladung"))

    def test_rueckblick_von_hand(self):
        self.sag("long 4012, stop 4004, ziel 4029")
        self.sag("ja")
        self.net.sent.clear()
        self.assertIn("verschickt an", self.sag("/rueckblick"))
        self.assertEqual(len(self.net.sent), 2)

    def test_not_aus(self):
        self.assertIn("Not-Aus gesetzt", self.sag("/aus"))
        self.assertTrue(Path(self.cfg.live.killswitch_file).exists())
        self.assertIn("gelöst", self.sag("/an"))

    def test_unbekannt(self):
        self.assertIn("kenne ich nicht", self.sag("/tanzen"))


class TestNebenbei(Base):
    def test_rueckblick_geht_von_selbst_raus(self):
        self.sag("long 4012, stop 4004, ziel 4029")
        self.sag("ja")
        self.net.sent.clear()
        self.bot.poll_once()                       # 11:00, noch nicht dran
        self.assertEqual(self.net.sent, [])
        self.takt.weiter(int(12.5 * 3600))         # 23:30, Rückblickzeit
        self.bot.poll_once()
        an_gruppen = [n for n in self.net.sent if n["chat_id"] in ("-100", "-200")]
        self.assertEqual(len(an_gruppen), 2)
        self.assertIn("Tagesrückblick", an_gruppen[0]["text"])

    def test_nur_einmal_am_tag(self):
        self.takt.weiter(int(12.5 * 3600))
        self.bot.poll_once()
        anzahl = len(self.net.sent)
        self.bot.poll_once()
        self.assertEqual(len(self.net.sent), anzahl)

    def test_ohne_verteiler_stolpert_nichts(self):
        bot = TelegramBot(self.cfg, self.tg, self.net)
        bot.poll_once()
        self.assertIn("nicht eingerichtet", "\n".join(bot.handle(update("/gruppen"))))


class TestBetrieb(Base):
    def test_ein_kaputter_versand_reisst_die_schleife_nicht(self):
        class Bockig(FakeTransport):
            def call(self, method, payload):
                if method == "sendMessage":
                    raise ConnectionError("Chat weg")
                return super().call(method, payload)

        netz = Bockig(updates=[update("hallo", chat="999")])
        bot = TelegramBot(self.cfg, self.tg, netz)
        self.assertEqual(bot.poll_once(), 1)

    def test_lange_nachricht_wird_geteilt(self):
        teile = _split("x" * 9000)
        self.assertGreater(len(teile), 1)
        self.assertTrue(all(len(t) <= 3900 for t in teile))

    def test_umzug_wird_erkannt(self):
        koerper = ('{"ok":false,"error_code":400,"parameters":'
                   '{"migrate_to_chat_id":-1001234567890}}')
        self.assertEqual(_umgezogen_nach(koerper), "-1001234567890")
        self.assertEqual(_umgezogen_nach("kein json"), "")
        self.assertIn("bot/.env", str(Umgezogen("-1", "-100")))

    def test_doppelter_bot_wird_benannt(self):
        self.assertIn("zweiter Bot", DOPPELT)

    def test_env_datei_lesen(self):
        p = Path(self.dir.name) / "x.env"
        p.write_text('A=1\n# weg\nB="zwei"\n', encoding="utf-8")
        self.assertEqual(load_env_file(p), {"A": "1", "B": "zwei"})


if __name__ == "__main__":
    unittest.main()


class TestAusMetaTrader(Base):
    """Trade in MT5 gestellt -> Signal liegt fertig da."""

    def setUp(self):
        super().setUp()
        from bengx_bot.mt5bruecke import Bruecke, BrueckeSettings, FakeMT5
        self.mt5 = FakeMT5()
        self.bruecke = Bruecke(self.mt5, BrueckeSettings(
            state_file=str(Path(self.dir.name) / "mt5.json")))
        self.bot = TelegramBot(self.cfg, self.tg, self.net,
                               self.verteiler, self.bruecke)

    def trade(self, **kw):
        from bengx_bot.mt5bruecke import Position
        werte = dict(ticket=1, symbol="XAUUSD", seite="long", entry=4012.0,
                     sl=4004.0, tp=4029.0, volumen=0.1, geoeffnet=1000.0)
        werte.update(kw)
        self.mt5.dazu(Position(**werte))

    def an_ben(self):
        return "\n".join(n["text"] for n in self.net.sent if n["chat_id"] == "42")

    def test_neuer_trade_wird_als_entwurf_vorgelegt(self):
        self.trade()
        self.bot.neue_trades()
        text = self.an_ben()
        self.assertIn("Neuer Trade in GOLD", text)
        self.assertIn("BEN GOLD BUY", text)
        self.assertIn("Schicken?", text)
        # noch nichts in den Gruppen
        self.assertEqual([n for n in self.net.sent if n["chat_id"] != "42"], [])

    def test_ja_schickt_ihn_raus(self):
        self.trade()
        self.bot.neue_trades()
        self.net.sent.clear()
        self.sag("ja")
        an_gruppen = [n for n in self.net.sent if n["chat_id"] in ("-100", "-200")]
        self.assertEqual(len(an_gruppen), 2)
        self.assertIn("BEN GOLD BUY", an_gruppen[0]["text"])

    def test_anderer_markt(self):
        self.trade(symbol="BTCUSD", entry=60000.0, sl=59000.0, tp=63000.0)
        self.bot.neue_trades()
        text = self.an_ben()
        self.assertIn("BEN BTCUSD BUY", text)
        self.assertNotIn("Pips", text)      # in Bitcoin rechnet niemand in Pips

    def test_short_heisst_sell(self):
        self.trade(seite="short", entry=4030.0, sl=4040.0, tp=4010.0)
        self.bot.neue_trades()
        self.assertIn("BEN GOLD SELL", self.an_ben())

    def test_mehrere_teilziele(self):
        self.trade(ticket=1, tp=4029.0, geoeffnet=1000.0)
        self.trade(ticket=2, tp=4045.0, geoeffnet=1010.0)
        self.bot.neue_trades()
        text = self.an_ben()
        self.assertIn("TP1", text)
        self.assertIn("TP2", text)
        self.assertIn("4.045,00", text)

    def test_ohne_stop_kommt_nichts_raus(self):
        self.trade(sl=0.0)
        self.bot.neue_trades()
        self.assertIn("Stop", self.an_ben())
        self.assertIn("fehlt in MetaTrader", self.an_ben())
        self.assertFalse(self.verteiler.entwurf_liegt())

    def test_ohne_rueckfrage_geht_er_direkt_raus(self):
        self.bruecke.settings.ohne_rueckfrage = True
        self.trade()
        self.bot.neue_trades()
        an_gruppen = [n for n in self.net.sent if n["chat_id"] in ("-100", "-200")]
        self.assertEqual(len(an_gruppen), 2)
        self.assertIn("Automatisch raus", self.an_ben())

    def test_kaputtes_mt5_reisst_nichts(self):
        class Kaputt:
            def positionen(self): raise RuntimeError("Terminal zu")
        from bengx_bot.mt5bruecke import Bruecke, BrueckeSettings
        bot = TelegramBot(self.cfg, self.tg, self.net, self.verteiler,
                          Bruecke(Kaputt(), BrueckeSettings(
                              state_file=str(Path(self.dir.name) / "x.json"))))
        bot.nebenbei()          # darf nicht werfen

    def test_derselbe_trade_nur_einmal(self):
        self.trade()
        self.bot.neue_trades()
        self.net.sent.clear()
        self.bot.neue_trades()
        self.assertEqual(self.net.sent, [])
