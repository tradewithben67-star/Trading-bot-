import base64
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from tests.helpers import START
from bengx_bot import report
from bengx_bot.assistant import Assistant, AssistantSettings
from bengx_bot.config import Config
from bengx_bot.journal import Journal
from bengx_bot.model import ExitReason, Side, Trade
from bengx_bot.telegram import (FakeTransport, TelegramBot, TelegramSettings,
                                _split, load_env_file)

PNG = b"\x89PNG\r\n\x1a\n" + b"rest"


class StubAI(Assistant):
    """Ein Assistent, der nicht ins Netz geht."""

    def __init__(self):
        super().__init__(AssistantSettings())
        self.gefragt = []

    def ready(self):
        return True

    def answer(self, frage, lage, bilder=()):
        self.gefragt.append({"frage": frage, "lage": lage, "bilder": list(bilder)})
        return "Antwort des Assistenten"

    def reset(self):
        self.gefragt.append({"reset": True})


def update(text=None, chat="42", photo=None, caption=None, uid=1):
    message = {"message_id": uid, "chat": {"id": int(chat)}}
    if text is not None:
        message["text"] = text
    if caption is not None:
        message["caption"] = caption
    if photo is not None:
        message["photo"] = photo
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
        self.ai = StubAI()
        self.bot = TelegramBot(self.cfg, self.tg, self.net, self.ai)

    def tearDown(self):
        self.dir.cleanup()

    def say(self, *a, **k):
        return self.bot.handle(update(*a, **k))


class TestZugang(Base):
    def test_fremder_chat_bekommt_nichts(self):
        antwort = self.say("/stand", chat="999")
        self.assertEqual(len(antwort), 1)
        self.assertIn("nicht freigegeben", antwort[0])
        self.assertNotIn("Kapital", antwort[0])

    def test_ohne_hinterlegte_kennung_nennt_er_sie(self):
        self.bot.tg.chat_id = ""
        antwort = self.say("/stand", chat="777")
        self.assertIn("777", antwort[0])
        self.assertIn("TELEGRAM_CHAT_ID", antwort[0])

    def test_eigener_chat_wird_bedient(self):
        self.assertIn("Bot:", self.say("/stand")[0])

    def test_nachricht_ohne_chat_wird_übergangen(self):
        self.assertEqual(self.bot.handle({"update_id": 1, "message": {}}), [])


class TestBefehle(Base):
    def test_hilfe(self):
        for befehl in ("/start", "/hilfe", "/help"):
            self.assertIn("/signale", self.say(befehl)[0])

    def test_befehl_mit_botnamen(self):
        self.assertIn("/signale", self.say("/hilfe@bengx_bot")[0])

    def test_stand_nennt_die_lage(self):
        text = self.say("/stand")[0]
        self.assertIn("Kapital", text)
        self.assertIn("Offene Positionen", text)

    def test_signale_ohne_daten(self):
        self.assertIn("Keine abgeschlossenen Signale", self.say("/signale")[0])

    def test_signale_mit_daten(self):
        journal = Journal(self.cfg.live.journal)
        journal.append(Trade(
            id="s1", side=Side.LONG, size=1.0, entry=2000.0, stop=1990.0,
            target=2015.0, exit_price=2020.0, opened_at=START,
            closed_at=START + timedelta(hours=2), pips=200.0, pnl=20.0,
            r_multiple=2.0, reason=ExitReason.TARGET))
        text = self.say("/signale alles")[0]
        self.assertIn("+200.0 Pips", text)
        self.assertIn("1 Trades", text)

    def test_signale_mit_unsinnigem_zeitraum(self):
        self.assertIn("Zeitraum", self.say("/signale irgendwann")[0])

    def test_regeln_aller_bots(self):
        self.assertIn("Dauerläufer", self.say("/regeln")[0])
        self.assertIn("Swing", self.say("/regeln swing")[0])
        self.assertIn("Signal-Kopierer", self.say("/regeln kopierer")[0])
        self.assertIn("Unbekannter Bot", self.say("/regeln quatsch")[0])

    def test_aufgabe_anlegen_und_lesen(self):
        self.assertIn("So:", self.say("/aufgabe")[0])
        self.assertIn("Notiert", self.say("/aufgabe Keine Signale seit gestern")[0])
        self.assertIn("Keine Signale seit gestern", self.say("/aufgaben")[0])
        self.assertEqual(len(report.aufgaben_lesen(self.cfg)), 1)

    def test_aufgaben_leer(self):
        self.assertIn("Keine offenen", self.say("/aufgaben")[0])

    def test_not_aus_setzen_und_loesen(self):
        datei = Path(self.cfg.live.killswitch_file)
        self.assertIn("Not-Aus gesetzt", self.say("/aus")[0])
        self.assertTrue(datei.exists())
        self.assertIn("NOT-AUS IST AKTIV", self.say("/stand")[0])
        self.assertIn("gelöst", self.say("/an")[0])
        self.assertFalse(datei.exists())
        self.assertIn("war nicht gesetzt", self.say("/an")[0])

    def test_neu_vergisst_den_faden(self):
        self.say("/neu")
        self.assertTrue(any("reset" in g for g in self.ai.gefragt))

    def test_unbekannter_befehl(self):
        self.assertIn("kenne ich nicht", self.say("/tanzen")[0])


class TestFreiesSchreiben(Base):
    def test_text_geht_an_den_assistenten_mit_lage(self):
        antwort = self.say("Wie läuft es?")
        self.assertEqual(antwort, ["Antwort des Assistenten"])
        self.assertEqual(self.ai.gefragt[0]["frage"], "Wie läuft es?")
        self.assertIn("Kapital", self.ai.gefragt[0]["lage"])

    def test_leere_nachricht(self):
        self.assertIn("nichts anfangen", self.say("")[0])

    def test_bild_wird_mitgeschickt(self):
        self.net.files["abc"] = PNG
        antwort = self.say(None, photo=[{"file_id": "abc", "file_size": 10}],
                           caption="Was ist das?")
        self.assertEqual(antwort, ["Antwort des Assistenten"])
        bilder = self.ai.gefragt[0]["bilder"]
        self.assertEqual(len(bilder), 1)
        self.assertEqual(bilder[0][0], "image/png")
        self.assertEqual(base64.standard_b64decode(bilder[0][1]), PNG)
        self.assertEqual(self.ai.gefragt[0]["frage"], "Was ist das?")

    def test_groesstes_bild_wird_genommen(self):
        self.net.files["gross"] = b"\xff\xd8jpeg"
        self.say(None, photo=[{"file_id": "klein", "file_size": 10},
                              {"file_id": "gross", "file_size": 900}])
        angefragt = [p["file_id"] for m, p in self.net.calls if m == "getFile"]
        self.assertEqual(angefragt, ["gross"])
        self.assertEqual(self.ai.gefragt[0]["bilder"][0][0], "image/jpeg")

    def test_bild_ohne_inhalt_wird_übergangen(self):
        self.say(None, photo=[{"file_id": "leer", "file_size": 5}], caption="hm")
        self.assertEqual(self.ai.gefragt[0]["bilder"], [])


class TestBetrieb(Base):
    def test_poll_verarbeitet_und_antwortet(self):
        self.net.updates = [update("/hilfe", uid=7)]
        self.assertEqual(self.bot.poll_once(), 1)
        self.assertEqual(len(self.net.sent), 1)
        self.assertEqual(self.net.sent[0]["chat_id"], "42")
        self.assertEqual(self.bot.offset, 8)

    def test_offset_waechst(self):
        self.net.updates = [update("/hilfe", uid=3), update("/hilfe", uid=9)]
        self.bot.poll_once()
        self.assertEqual(self.bot.offset, 10)

    def test_fehler_beendet_den_bot_nicht(self):
        def kaputt(_):
            raise RuntimeError("absichtlich")
        self.bot.handle = kaputt
        self.net.updates = [update("/hilfe")]
        self.bot.poll_once()
        self.assertIn("schiefgegangen", self.net.sent[0]["text"])

    def test_lange_antwort_wird_geteilt(self):
        teile = _split("Zeile\n" * 2000)
        self.assertGreater(len(teile), 1)
        self.assertTrue(all(len(t) <= 3900 for t in teile))
        self.assertEqual("".join(t if t.endswith("\n") else t + "\n"
                                 for t in teile).count("Zeile"), 2000)

    def test_kurze_antwort_bleibt_ganz(self):
        self.assertEqual(_split("kurz"), ["kurz"])


class TestEinstellungen(unittest.TestCase):
    def test_aus_der_umgebung(self):
        s = TelegramSettings.from_env({
            "TELEGRAM_TOKEN": " abc ", "TELEGRAM_CHAT_ID": " 42 ",
            "BENGX_EFFORT": "medium", "BENGX_MAX_TOKENS": "500"})
        self.assertEqual(s.token, "abc")
        self.assertEqual(s.chat_id, "42")
        self.assertEqual(s.effort, "medium")
        self.assertEqual(s.max_tokens, 500)

    def test_standardwerte(self):
        s = TelegramSettings.from_env({})
        self.assertEqual(s.token, "")
        self.assertEqual(s.model, "claude-opus-5-5")
        self.assertEqual(s.effort, "low")

    def test_env_datei(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text('# Kommentar\nTELEGRAM_TOKEN="geheim"\n\nLEER\n'
                         "TELEGRAM_CHAT_ID=7\n", encoding="utf-8")
            werte = load_env_file(p)
            self.assertEqual(werte["TELEGRAM_TOKEN"], "geheim")
            self.assertEqual(werte["TELEGRAM_CHAT_ID"], "7")
            self.assertNotIn("LEER", werte)

    def test_fehlende_env_datei(self):
        self.assertEqual(load_env_file("/gibt/es/nicht/.env"), {})


class TestOhneSDK(Base):
    def test_hinweis_statt_absturz(self):
        bot = TelegramBot(self.cfg, self.tg, self.net,
                          Assistant(AssistantSettings()))
        antwort = bot.handle(update("Hallo"))
        self.assertIn("nicht eingerichtet", antwort[0])
        self.assertIn("/hilfe", antwort[0])


if __name__ == "__main__":
    unittest.main()
