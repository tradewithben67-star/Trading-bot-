import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from tests.helpers import START
from bengx_bot import report
from bengx_bot.assistant import Assistant, AssistantSettings
from bengx_bot.llm import LLMSettings
from bengx_bot.config import Config
from bengx_bot.journal import Journal
from bengx_bot.model import ExitReason, Side, Trade
from bengx_bot.telegram import (FakeTransport, TelegramBot, TelegramSettings,
                                _split, load_env_file)

PNG = b"\x89PNG\r\n\x1a\n" + b"rest"


class StubAI(Assistant):
    """Ein Assistent, der nicht ins Netz geht."""

    def __init__(self):
        super().__init__(AssistantSettings(LLMSettings()))
        self.gefragt = []

    def ready(self):
        return True

    def answer(self, frage, lage, bilder=(), melden=None):
        self.gefragt.append({"frage": frage, "lage": lage,
                             "bilder": list(bilder), "melden": melden})
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
        self.assertEqual(bilder[0][1], PNG, "Bilder gehen roh weiter")
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
            "TELEGRAM_POLL_TIMEOUT": "20"})
        self.assertEqual(s.token, "abc")
        self.assertEqual(s.chat_id, "42")
        self.assertEqual(s.poll_timeout, 20)

    def test_standardwerte(self):
        s = TelegramSettings.from_env({})
        self.assertEqual(s.token, "")
        self.assertEqual(s.chat_id, "")
        self.assertEqual(s.poll_timeout, 50)

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


class TestOhneSchluessel(Base):
    def test_hinweis_statt_absturz(self):
        bot = TelegramBot(self.cfg, self.tg, self.net,
                          Assistant(AssistantSettings(LLMSettings())))
        antwort = bot.handle(update("Hallo"))
        self.assertIn("fehlt", antwort[0])
        self.assertIn("/hilfe", antwort[0])

    def test_gemini_ohne_schluessel_nennt_das_paket(self):
        bot = TelegramBot(self.cfg, self.tg, self.net,
                          Assistant(AssistantSettings(
                              LLMSettings(anbieter="gemini"))))
        self.assertIn("google-genai", bot.handle(update("Hallo"))[0])


if __name__ == "__main__":
    unittest.main()


class TestNatuerlichSchreiben(Base):
    """Ben gibt keine Befehle — der Assistent führt aus, was er meint."""

    def test_hilfe_fuehrt_mit_normalem_schreiben(self):
        text = self.say("/hilfe")[0]
        self.assertIn("Schreib einfach normal", text.splitlines()[0])
        self.assertIn("mach den bot aus", text)

    def test_schreibt_anzeige_vor_der_antwort(self):
        self.say("wie läuft es")
        aktionen = [p for m, p in self.net.calls if m == "sendChatAction"]
        self.assertEqual(len(aktionen), 1)
        self.assertEqual(aktionen[0]["action"], "typing")

    def test_befehle_zeigen_keine_anzeige(self):
        self.say("/stand")
        self.assertFalse([m for m, _ in self.net.calls if m == "sendChatAction"])


class TestWerkzeuge(unittest.TestCase):
    """Was die Werkzeuge tun, wenn Claude sie ruft."""

    def setUp(self):
        from bengx_bot.assistant import Werkzeuge
        self.dir = tempfile.TemporaryDirectory()
        d = self.dir.name
        self.cfg = Config()
        self.cfg.live.state_dir = d
        self.cfg.live.journal = str(Path(d) / "trades.jsonl")
        self.cfg.live.killswitch_file = str(Path(d) / "KILLSWITCH")
        self.w = Werkzeuge(self.cfg)

    def tearDown(self):
        self.dir.cleanup()

    def test_stand(self):
        self.assertIn("Kapital", self.w.stand())

    def test_signale_mit_unsinnigem_zeitraum_gibt_alles(self):
        self.assertIn("alles", self.w.signale("irgendwann"))

    def test_signale_begrenzt_die_anzahl(self):
        self.assertIn("heute", self.w.signale("heute", 10_000))
        self.assertIn("heute", self.w.signale("heute", "kaputt"))

    def test_regeln_je_bot(self):
        self.assertIn("Dauerläufer", self.w.regeln(""))
        self.assertIn("Swing", self.w.regeln("swing"))
        with self.assertRaises(ValueError):
            self.w.regeln("quatsch")

    def test_aufgabe_braucht_text(self):
        with self.assertRaises(ValueError):
            self.w.aufgabe("   ")
        self.assertIn("notiert", self.w.aufgabe("Etwas klemmt"))
        self.assertIn("Etwas klemmt", self.w.aufgaben())

    def test_stoppen_ist_umkehrbar(self):
        datei = Path(self.cfg.live.killswitch_file)
        self.assertIn("Not-Aus gesetzt", self.w.stoppen())
        self.assertTrue(datei.exists())
        self.assertIn("schon gestoppt", self.w.stoppen())
        self.assertIn("gelöst", self.w.erlauben())
        self.assertFalse(datei.exists())
        self.assertIn("gar nicht gestoppt", self.w.erlauben())

    def test_jede_benutzung_wird_vermerkt(self):
        self.w.stand()
        self.w.aufgaben()
        self.assertEqual(self.w.benutzt, ["stand", "aufgaben"])


class TestAnbieterwahl(unittest.TestCase):
    """Gemini oder Claude — wer antwortet, hängt am vorhandenen Schlüssel."""

    def test_nur_google_nimmt_gemini(self):
        self.assertEqual(
            LLMSettings.from_env({"GOOGLE_API_KEY": "g"}).gewaehlt(), "gemini")

    def test_gemini_key_wird_auch_erkannt(self):
        self.assertEqual(
            LLMSettings.from_env({"GEMINI_API_KEY": "g"}).gewaehlt(), "gemini")

    def test_nur_anthropic_nimmt_claude(self):
        self.assertEqual(
            LLMSettings.from_env({"ANTHROPIC_API_KEY": "a"}).gewaehlt(), "claude")

    def test_beide_nehmen_claude(self):
        self.assertEqual(LLMSettings.from_env(
            {"ANTHROPIC_API_KEY": "a", "GOOGLE_API_KEY": "g"}).gewaehlt(), "claude")

    def test_erzwingen_geht_vor(self):
        self.assertEqual(LLMSettings.from_env(
            {"BENGX_ANBIETER": "gemini", "ANTHROPIC_API_KEY": "a"}).gewaehlt(),
            "gemini")

    def test_standardmodelle(self):
        s = LLMSettings.from_env({})
        self.assertEqual(s.claude_model, "claude-opus-5-5")
        self.assertEqual(s.gemini_model, "",
                         "bei Gemini wird der Schlüssel gefragt, nicht geraten")

    def test_modelle_lassen_sich_setzen(self):
        s = LLMSettings.from_env({"BENGX_GEMINI_MODEL": "gemini-3-flash",
                                  "BENGX_MAX_TOKENS": "500"})
        self.assertEqual(s.gemini_model, "gemini-3-flash")
        self.assertEqual(s.max_tokens, 500)


class TestWebsuche(unittest.TestCase):
    def test_standard_ist_an(self):
        self.assertTrue(LLMSettings.from_env({}).websuche)

    def test_laesst_sich_abschalten(self):
        for wert in ("0", "aus", "false", "nein"):
            self.assertFalse(LLMSettings.from_env({"BENGX_WEBSUCHE": wert}).websuche)


class TestWeiterbauen(unittest.TestCase):
    """Der Coding-Agent: aus, bis er eingeschaltet wird."""

    def setUp(self):
        from bengx_bot.assistant import Werkzeuge
        from bengx_bot.coder import Coder, CoderSettings
        self.dir = tempfile.TemporaryDirectory()
        self.cfg = Config()
        self.cfg.live.state_dir = self.dir.name
        self.cfg.live.journal = str(Path(self.dir.name) / "t.jsonl")
        self.cfg.live.killswitch_file = str(Path(self.dir.name) / "KS")
        self.Werkzeuge = Werkzeuge
        self.Coder = Coder
        self.Settings = CoderSettings

    def tearDown(self):
        self.dir.cleanup()

    def test_standard_ist_aus(self):
        s = self.Settings.from_env({})
        self.assertFalse(s.enabled)
        self.assertIn("ausgeschaltet", self.Coder(s).status())

    def test_einschalten_ueber_die_umgebung(self):
        for wert in ("1", "an", "true", "ja"):
            self.assertTrue(self.Settings.from_env({"BENGX_CODER": wert}).enabled)

    def test_grenzen_kommen_aus_der_umgebung(self):
        s = self.Settings.from_env({
            "BENGX_CODER": "1", "BENGX_CODER_TURNS": "7",
            "BENGX_CODER_BUDGET": "0.5", "BENGX_REPO": "/tmp"})
        self.assertEqual(s.max_turns, 7)
        self.assertAlmostEqual(s.max_budget_usd, 0.5)
        self.assertEqual(s.repo, "/tmp")

    def test_fehlender_ordner_wird_gemeldet(self):
        c = self.Coder(self.Settings(enabled=True, repo="/gibt/es/nicht"),
                       runner=lambda a, s: "nie")
        self.assertIn("gibt es nicht", c.status())
        self.assertFalse(c.ready())

    def test_ausgeschaltet_wirft_mit_begruendung(self):
        w = self.Werkzeuge(self.cfg, coder=self.Coder(self.Settings()))
        with self.assertRaises(RuntimeError) as cm:
            w.bauen("mach was")
        self.assertIn("BENGX_CODER=1", str(cm.exception))

    def test_ohne_coder_wirft(self):
        w = self.Werkzeuge(self.cfg)
        with self.assertRaises(RuntimeError):
            w.bauen("mach was")

    def test_leerer_auftrag_wird_abgelehnt(self):
        c = self.Coder(self.Settings(enabled=True, repo=self.dir.name),
                       runner=lambda a, s: "nie")
        with self.assertRaises(ValueError):
            c.run("   ")

    def test_auftrag_geht_durch_und_meldet_zwischendurch(self):
        gemeldet = []
        c = self.Coder(self.Settings(enabled=True, repo=self.dir.name),
                       runner=lambda auftrag, s: f"fertig: {auftrag}")
        w = self.Werkzeuge(self.cfg, coder=c, melden=gemeldet.append)
        antwort = w.bauen("Fuss der Website aufraeumen")
        self.assertEqual(antwort, "fertig: Fuss der Website aufraeumen")
        self.assertEqual(len(gemeldet), 1)
        self.assertIn("fange an", gemeldet[0])
        self.assertEqual(c.verlauf, ["Fuss der Website aufraeumen"])
        self.assertIn("bauen", w.benutzt)

    def test_der_bot_reicht_den_coder_weiter(self):
        from bengx_bot.telegram import TelegramBot as TB
        c = self.Coder(self.Settings(enabled=True, repo=self.dir.name))
        bot = TB(self.cfg, TelegramSettings(token="t", chat_id="1"),
                 FakeTransport(), coder=c)
        self.assertIs(bot.ai.coder, c)


class TestModellwahl(unittest.TestCase):
    """Ohne feste Vorgabe soll das kleinste und neueste Modell gewinnen."""

    def rang(self, namen):
        from bengx_bot.llm import GeminiProvider, LLMSettings
        g = GeminiProvider(LLMSettings(gemini_key="x"))
        g.client = object()          # verhindert einen echten Verbindungsaufbau
        g.modelle = lambda: namen
        g._kandidaten = []
        return [g._naechstes_modell()]

    def test_flash_lite_vor_flash_und_pro(self):
        namen = ["gemini-3.5-pro", "gemini-3.5-flash", "gemini-3.5-flash-lite"]
        from bengx_bot.llm import GeminiProvider, LLMSettings
        g = GeminiProvider(LLMSettings(gemini_key="x"))
        g._kandidaten = namen
        self.assertEqual(g._naechstes_modell(), "gemini-3.5-pro",
                         "ohne Sortierung wird die Liste so genommen")

    def test_naechstes_ueberspringt_versuchte(self):
        from bengx_bot.llm import GeminiProvider, LLMSettings
        g = GeminiProvider(LLMSettings(gemini_key="x"))
        g._kandidaten = ["a", "b", "c"]
        g.versucht = {"a", "b"}
        self.assertEqual(g._naechstes_modell(), "c")

    def test_nichts_mehr_uebrig(self):
        from bengx_bot.llm import GeminiProvider, LLMSettings
        g = GeminiProvider(LLMSettings(gemini_key="x"))
        g._kandidaten = ["a"]
        g.versucht = {"a"}
        self.assertEqual(g._naechstes_modell(), "")

    def test_eingestelltes_modell_gewinnt(self):
        from bengx_bot.llm import GeminiProvider, LLMSettings
        g = GeminiProvider(LLMSettings(gemini_key="x",
                                       gemini_model="gemini-eigenes"))
        g.client = object()
        g._verbinden()
        self.assertEqual(g.modell, "gemini-eigenes")


class TestModellfilter(unittest.TestCase):
    """Nicht jedes Modell kann sich unterhalten."""

    def test_sprachausgabe_und_bilder_fliegen_raus(self):
        from bengx_bot.llm import nur_text
        for name in ("gemini-3.8-flash-lite-tts", "gemini-3.1-flash-lite-image",
                     "text-embedding-004", "imagen-3.0", "veo-2",
                     "gemini-2.0-flash-live"):
            self.assertFalse(nur_text(name), name)

    def test_echte_modelle_bleiben(self):
        from bengx_bot.llm import nur_text
        for name in ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite",
                     "gemini-2.5-flash", "gemini-3.5-pro"):
            self.assertTrue(nur_text(name), name)

    def test_neuestes_flash_lite_gewinnt(self):
        from bengx_bot.llm import nur_text, rang
        echt = ["gemini-2.5-flash-lite", "gemini-3.1-flash-lite",
                "gemini-3.1-flash-lite-image", "gemini-3.1-flash-lite-preview",
                "gemini-3.5-flash-lite", "gemini-3.8-flash-lite-tts"]
        uebrig = sorted([n for n in echt if nur_text(n)], key=rang)
        self.assertEqual(uebrig[0], "gemini-3.5-flash-lite")

    def test_fertiges_vor_vorschau(self):
        from bengx_bot.llm import rang
        self.assertLess(rang("gemini-3.1-flash-lite"),
                        rang("gemini-3.1-flash-lite-preview"))

    def test_hinweis_auf_nachfolger_wird_gelesen(self):
        from bengx_bot.llm import GeminiProvider, LLMSettings
        g = GeminiProvider(LLMSettings(gemini_key="x"))
        self.assertEqual(g.hinweis_modell(
            "This model models/gemini-2.5-flash-lite is no longer available. "
            "Please update your code to use models/gemini-3.5-flash-lite for "
            "the latest features."), "gemini-3.5-flash-lite")

    def test_ohne_hinweis_leer(self):
        from bengx_bot.llm import GeminiProvider, LLMSettings
        g = GeminiProvider(LLMSettings(gemini_key="x"))
        self.assertEqual(g.hinweis_modell("irgendein anderer Fehler"), "")


class TestGruppenImBot(Base):
    """Der Signal-Bot haengt an derselben Abrufschleife."""

    def setUp(self):
        super().setUp()
        from bengx_bot.gruppen import GruppenSettings, Verteiler
        from tests.test_gruppen import Uhr
        self.takt = Uhr()
        self.verteiler = Verteiler(
            GruppenSettings(inner_chat_id="-100", vip_chat_id="-200",
                            inner_verzug_min=20,
                            state_file=str(Path(self.dir.name) / "g.json")),
            self.net, pip=0.1, uhr=self.takt)
        self.bot = TelegramBot(self.cfg, self.tg, self.net, self.ai,
                               verteiler=self.verteiler)

    def test_gruppen_befehl(self):
        antwort = self.bot.handle(update("/gruppen"))[0]
        self.assertIn("VIP: sofort", antwort)
        self.assertIn("Inner Circle: nach 20 min", antwort)

    def test_einladung_befehl(self):
        antwort = self.bot.handle(update("/einladung inner Max"))[0]
        self.assertIn("https://t.me/+", antwort)

    def test_einladung_ohne_gruppe_erklaert_sich(self):
        self.assertIn("/einladung inner",
                      self.bot.handle(update("/einladung"))[0])

    def test_unbekannte_gruppe_wird_gemeldet(self):
        self.assertIn("kenne ich nicht",
                      self.bot.handle(update("/einladung platin"))[0])

    def test_abrufschleife_schiebt_wartende_nach(self):
        self.verteiler.signal_senden(
            {"side": "long", "entry": 4012.4, "sl": 4004.1, "tp": 4029.0})
        self.net.sent.clear()
        self.bot.poll_once()                 # noch nicht faellig
        self.assertEqual(self.net.sent, [])
        self.takt.weiter(22 * 60)
        self.bot.poll_once()
        self.assertEqual(len(self.net.sent), 1)
        self.assertEqual(self.net.sent[0]["chat_id"], "-100")

    def test_ohne_verteiler_sagt_der_bot_bescheid(self):
        ohne = TelegramBot(self.cfg, self.tg, self.net, self.ai)
        self.assertIn("nicht eingerichtet", ohne.handle(update("/gruppen"))[0])
        ohne.poll_once()                     # darf nicht stolpern


class TestGruppenWerkzeuge(unittest.TestCase):
    """Was der Assistent mit den Gruppen tun kann."""

    def setUp(self):
        from bengx_bot.assistant import Werkzeuge
        from bengx_bot.gruppen import GruppenSettings, Verteiler
        from tests.test_gruppen import Uhr
        self.dir = tempfile.TemporaryDirectory()
        self.net = FakeTransport()
        self.takt = Uhr()
        self.verteiler = Verteiler(
            GruppenSettings(inner_chat_id="-100", vip_chat_id="-200",
                            inner_verzug_min=20,
                            state_file=str(Path(self.dir.name) / "g.json")),
            self.net, pip=0.1, uhr=self.takt)
        self.w = Werkzeuge(Config(), verteiler=self.verteiler)

    def tearDown(self):
        self.dir.cleanup()

    def test_entwurf_zeigt_beide_fassungen_und_schickt_nichts(self):
        text = self.w.signal_entwurf("long", 4012.4, 4004.1, 4029.0, "1H-Sweep")
        self.assertIn("--- VIP ---", text)
        self.assertIn("--- Inner Circle ---", text)
        self.assertIn("Soll ich das so verschicken?", text)
        self.assertEqual(self.net.sent, [])

    def test_freigeben_schickt_wirklich(self):
        self.w.signal_entwurf("long", 4012.4, 4004.1, 4029.0)
        text = self.w.signal_freigeben()
        self.assertIn("Raus als sig-", text)
        self.assertEqual(len(self.net.sent), 1)

    def test_falsche_seite_wird_abgelehnt_bevor_etwas_rausgeht(self):
        with self.assertRaises(ValueError):
            self.w.signal_entwurf("long", 4012.4, 4020.0, 4029.0)
        self.assertEqual(self.net.sent, [])

    def test_ergebnis_melden(self):
        self.w.signal_entwurf("long", 4012.4, 4004.1, 4029.0)
        self.w.signal_freigeben()
        kennung = self.verteiler.letzte(1)[0]["id"]
        text = self.w.signal_ergebnis(kennung, "gewonnen")
        self.assertIn("+166 Pips", text)

    def test_stand_nennt_die_kennungen(self):
        self.w.signal_entwurf("long", 4012.4, 4004.1, 4029.0)
        self.w.signal_freigeben()
        self.assertIn("sig-0001", self.w.gruppen_stand())

    def test_ohne_gruppen_eine_klare_ansage(self):
        from bengx_bot.assistant import Werkzeuge
        w = Werkzeuge(Config())
        with self.assertRaises(RuntimeError) as fehler:
            w.signal_entwurf("long", 4012.4, 4004.1, 4029.0)
        self.assertIn("nicht eingerichtet", str(fehler.exception))


class TestGruppenumzug(unittest.TestCase):
    """Telegram vergibt beim Umwandeln in eine Supergruppe eine neue
    Kennung. Das darf nicht als raetselhafter 400er enden."""

    def test_neue_kennung_wird_gelesen(self):
        from bengx_bot.telegram import _umgezogen_nach
        koerper = ('{"ok":false,"error_code":400,"description":'
                   '"Bad Request: group chat was upgraded to a supergroup chat",'
                   '"parameters":{"migrate_to_chat_id":-1001234567890}}')
        self.assertEqual(_umgezogen_nach(koerper), "-1001234567890")

    def test_andere_fehler_bleiben_andere_fehler(self):
        from bengx_bot.telegram import _umgezogen_nach
        self.assertEqual(_umgezogen_nach('{"ok":false,"error_code":403}'), "")
        self.assertEqual(_umgezogen_nach("kein json"), "")
        self.assertEqual(_umgezogen_nach('{"parameters":{}}'), "")

    def test_fehler_sagt_was_zu_tun_ist(self):
        from bengx_bot.telegram import Umgezogen
        f = Umgezogen("-12345", "-1001234567890")
        self.assertIn("-1001234567890", str(f))
        self.assertIn("bot/.env", str(f))
        self.assertIsInstance(f, ConnectionError)


class TestSchweigenInGruppen(Base):
    """In VIP und im Inner Circle sitzt der Bot still."""

    def gruppennachricht(self, typ="supergroup", chat="-1001234567890"):
        return {"update_id": 7, "message": {
            "message_id": 7, "chat": {"id": int(chat), "type": typ,
                                      "title": "BENGX VIP"},
            "text": "test"}}

    def test_keine_antwort_in_die_gruppe(self):
        self.assertEqual(self.bot.handle(self.gruppennachricht()), [])
        self.assertEqual(self.bot.handle(self.gruppennachricht("group")), [])

    def test_auch_ohne_hinterlegte_kennung_still(self):
        # Sonst stuende Bens Chat-Kennung in der Gruppe.
        bot = TelegramBot(self.cfg, TelegramSettings(token="t", chat_id=""),
                          self.net, self.ai)
        self.assertEqual(bot.handle(self.gruppennachricht()), [])

    def test_im_einzelchat_antwortet_er_weiter(self):
        fremd = {"update_id": 8, "message": {
            "message_id": 8, "chat": {"id": 999, "type": "private"},
            "text": "hallo"}}
        self.assertEqual(self.bot.handle(fremd), ["Dieser Chat ist nicht freigegeben."])

    def test_ein_kaputter_versand_reisst_die_schleife_nicht(self):
        class Bockig(FakeTransport):
            def call(self, method, payload):
                if method == "sendMessage":
                    raise ConnectionError("Chat weg")
                return super().call(method, payload)

        netz = Bockig(updates=[{"update_id": 9, "message": {
            "message_id": 9, "chat": {"id": 999, "type": "private"},
            "text": "hallo"}}])
        bot = TelegramBot(self.cfg, self.tg, netz, self.ai)
        self.assertEqual(bot.poll_once(), 1)      # kein Absturz
