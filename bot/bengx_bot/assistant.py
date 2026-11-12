"""Der Chat-Teil des Assistenten.

Ben schreibt normal — keine Befehle. Damit das geht, bekommt das Modell
Werkzeuge: den Stand abfragen, Signale lesen, das Regelwerk zeigen, eine
Aufgabe notieren, den Handel stoppen und am Code weiterbauen. Was Ben in
Worten sagt, führt das Modell damit aus.

Wer antwortet — Gemini oder Claude — steht in `llm.py`. Die Werkzeuge hier
sind für beide dieselben: einfache Funktionen mit deutscher Beschreibung,
aus der sich jeder Anbieter sein eigenes Format baut.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

from . import report
from .coder import Coder
from .config import Config
from .llm import Bild, LLMSettings, Provider, anbieter_bauen

SYSTEM = (
    "Du bist der Assistent von Ben. Ben ist 18, kommt aus Deutschland und "
    "handelt seit einem Jahr ausschließlich Gold (XAU/USD). Sein Broker ist "
    "Tradequo, der über MetaTrader 5 läuft. Ihr schreibt in Telegram.\n\n"
    "Antworte auf Deutsch, direkt und knapp — Telegram, nicht Aufsatz. Kein "
    "Marketing-Ton, keine Ausrufezeichen, keine Emojis, keine Überschriften.\n\n"
    "Ben gibt dir keine Befehle, er schreibt normal. Du führst aus, was er "
    "meint, und benutzt dafür deine Werkzeuge:\n"
    "- Fragen nach Zahlen, Ergebnissen oder „wie läuft es“ → stand_abfragen "
    "oder signale_lesen.\n"
    "- Fragen nach Regeln, Stops, Zielen, Filtern → regelwerk.\n"
    "- Meldet er ein Problem oder einen Wunsch → aufgabe_anlegen, und sag ihm, "
    "dass es notiert ist.\n"
    "- Sagt er, der Bot soll aufhören oder stoppen → handel_stoppen. Das ist "
    "jederzeit umkehrbar, also zögere nicht.\n"
    "- Soll wieder gehandelt werden → frag einmal nach, bevor du "
    "handel_erlauben benutzt.\n"
    "- Sagt er, du sollst an der Website, am Bot oder am Code weiterbauen, "
    "etwas ändern oder reparieren → am_code_bauen. Dahinter läuft ein "
    "richtiger Coding-Agent auf Bens Rechner. Gib ihm einen vollständigen "
    "Auftrag in einem Absatz, nicht nur Bens Stichwort. Es dauert ein paar "
    "Minuten; sag das vorher. Ist unklar, was gebaut werden soll, frag nach.\n\n"
    "Zu jeder Nachricht steht ein Abschnitt LAGE mit den aktuellen Zahlen. "
    "Reicht er, antworte sofort daraus statt ein Werkzeug zu rufen — das "
    "spart Zeit. Reicht er nicht, ruf das Werkzeug.\n\n"
    "Erfinde nie eine Zahl und schätze nicht. Weißt du etwas nicht, sag es. "
    "Du kannst keinen Code von Hand ändern und nichts am Regelwerk "
    "umstellen — dafür gibt es die Werkzeuge.\n\n"
    "Für alles, was draußen passiert — Kurse, Termine, Nachrichten zu Gold, "
    "Broker-Meldungen — such im Netz und nenn die Quelle. Für Zahlen aus "
    "Bens eigenem Bot niemals suchen, dafür hast du die Werkzeuge.\n\n"
    "Schickt Ben ein Bild, sieh es dir an und antworte darauf.\n\n"
    "GRUPPEN. Es gibt zwei Stufen. VIP ist bezahlt und nur auf Bens "
    "Einladung: jedes Signal, mit Begründung. Der Inner Circle ist offen "
    "für alle und bekommt genau zwei Signale am Tag: eins in der London-, "
    "eins in der New-York-Sitzung. Zur selben Zeit wie VIP, damit sie "
    "mithandelbar sind, aber knapp und ohne Begründung. Ist das Fenster "
    "schon belegt oder liegt die Zeit ausserhalb beider Sitzungen, geht "
    "das Signal nur an VIP — sag Ben den Grund, wenn das passiert. "
    "Gibt Ben ein Signal durch — etwa „long 4012, stop 4004, ziel 4029, "
    "1h sweep und 1m bos“ —, dann ruf signal_entwurf, zeig ihm die Vorschau "
    "und warte auf sein Ja. Erst dann signal_freigeben. Verschick nie ein "
    "Signal ohne diese Zustimmung: in den Gruppen sitzen zahlende Leute, und "
    "eine Nachricht dort ist nicht zurückzuholen. Fehlt eine Zahl, frag "
    "danach, statt sie zu erfinden. Sagt er, ein Signal sei im Ziel oder "
    "ausgestoppt → signal_ergebnis. Soll jemand rein → einladung_erstellen.\n\n"
    "Rede ihm nicht nach dem Mund. Sehen die Zahlen schlecht aus, sag es."
)


# ---- Was die Werkzeuge wirklich tun --------------------------------------
class Werkzeuge:
    """Die Arbeit hinter den Werkzeugen — ohne SDK, damit sie prüfbar bleibt."""

    def __init__(self, config: Config, coder: Coder | None = None,
                 melden: Any = None, verteiler: Any = None) -> None:
        self.cfg = config
        self.coder = coder
        self.melden = melden
        self.verteiler = verteiler
        self.benutzt: list[str] = []

    def _merken(self, name: str) -> None:
        self.benutzt.append(name)

    def stand(self) -> str:
        self._merken("stand")
        return report.build(self.cfg).text()

    def signale(self, zeitraum: str = "heute", anzahl: int = 8) -> str:
        self._merken("signale")
        z = (zeitraum or "heute").lower()
        if z not in ("heute", "woche", "monat", "alles"):
            z = "alles"
        try:
            n = max(1, min(20, int(anzahl)))
        except (TypeError, ValueError):
            n = 8
        return report.signale_text(self.cfg, z, n)

    def regeln(self, bot: str = "") -> str:
        self._merken("regeln")
        from .cli import rules_for
        try:
            return rules_for(self.cfg, bot or None)
        except ValueError as exc:
            raise ValueError(str(exc)) from None

    def aufgabe(self, text: str) -> str:
        self._merken("aufgabe")
        sauber = (text or "").strip()
        if not sauber:
            raise ValueError("Ohne Text lässt sich nichts notieren.")
        nummer = report.aufgabe_anlegen(self.cfg, sauber)
        return f"Als Aufgabe {nummer} notiert: {sauber[:120]}"

    def aufgaben(self) -> str:
        self._merken("aufgaben")
        offen = [a for a in report.aufgaben_lesen(self.cfg)
                 if a.get("status") != "erledigt"]
        if not offen:
            return "Keine offenen Aufgaben."
        return "\n".join(f"{i + 1}. {a.get('text', '')}"
                         for i, a in enumerate(offen))

    def stoppen(self) -> str:
        self._merken("stoppen")
        p = Path(self.cfg.live.killswitch_file)
        if p.exists():
            return "Der Handel war schon gestoppt."
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("gestoppt über Telegram\n", encoding="utf-8")
        return ("Not-Aus gesetzt. Beim nächsten Durchlauf wird alles "
                "geschlossen und nichts Neues eröffnet.")

    def bauen(self, auftrag: str) -> str:
        self._merken("bauen")
        if self.coder is None:
            raise RuntimeError("Weiterbauen ist auf dieser Maschine nicht "
                               "eingerichtet.")
        hindernis = self.coder.status()
        if hindernis:
            raise RuntimeError(hindernis)
        if callable(self.melden):
            self.melden("Alles klar, ich fange an. Das dauert ein paar "
                        "Minuten — ich melde mich, wenn es steht.")
        return self.coder.run(auftrag)

    # ---- Gruppen ----------------------------------------------------------
    def _gruppen(self):
        if self.verteiler is None:
            raise RuntimeError("Die Gruppen sind auf dieser Maschine nicht "
                               "eingerichtet.")
        return self.verteiler

    def signal_entwurf(self, seite: str, einstieg: float, stop: float,
                       ziel: float, begruendung: str = "") -> str:
        self._merken("signal_entwurf")
        raus = self._gruppen().entwurf({
            "side": seite, "entry": einstieg, "sl": stop, "tp": ziel,
            "note": begruendung})
        teile = ["So würde es rausgehen:", ""]
        for name, text in raus["vorschau"].items():
            teile += [f"--- {name} ---", text, ""]
        teile.append("Soll ich das so verschicken?")
        return "\n".join(teile)

    def signal_freigeben(self) -> str:
        self._merken("signal_freigeben")
        raus = self._gruppen().freigeben()
        zeilen = [f"Raus als {raus['id']}."]
        if raus["sofort"]:
            zeilen.append("Sofort: " + ", ".join(raus["sofort"]))
        if raus["wartet"]:
            zeilen.append("Folgt: " + ", ".join(raus["wartet"]))
        return "\n".join(zeilen)

    def signal_verwerfen(self) -> str:
        self._merken("signal_verwerfen")
        return self._gruppen().entwurf_verwerfen()

    def signal_ergebnis(self, signal_id: str, ergebnis: str,
                        pips: float | None = None) -> str:
        self._merken("signal_ergebnis")
        raus = self._gruppen().ergebnis_senden(signal_id, ergebnis, pips)
        return (f"Ergebnis zu {raus['id']} steht in "
                f"{', '.join(raus['gruppen'])}: {raus['pips']:+.0f} Pips.")

    def einladung(self, gruppe: str, name: str = "", stunden: int = 24) -> str:
        self._merken("einladung")
        link = self._gruppen().einladung(gruppe, name, stunden)
        return (f"Einladung für {gruppe}, gilt einmal und läuft nach "
                f"{stunden} Stunden ab:\n{link}")

    def mitglied_entfernen(self, gruppe: str, user_id: str) -> str:
        self._merken("mitglied_entfernen")
        return self._gruppen().entfernen(gruppe, user_id)

    def gruppen_stand(self) -> str:
        self._merken("gruppen_stand")
        return self._gruppen().stand_text()

    def erlauben(self) -> str:
        self._merken("erlauben")
        p = Path(self.cfg.live.killswitch_file)
        if not p.exists():
            return "Der Handel war gar nicht gestoppt."
        p.unlink()
        return "Not-Aus gelöst. Der Bot darf wieder handeln."


def werkzeug_funktionen(w: Werkzeuge) -> list[Callable[..., Any]]:
    """Die Werkzeuge als einfache Funktionen.

    Beschreibung und Argumente stehen im Docstring — daraus bauen sowohl das
    Anthropic- als auch das Google-SDK ihre eigenen Formate.
    """

    def stand_abfragen() -> str:
        """Der aktuelle Stand des Handelsbots: Kapital, offene Positionen,
        letzte verarbeitete Kerze, Zahlen von heute und insgesamt, und ob der
        Not-Aus gesetzt ist. Für Fragen wie "wie laeuft es" oder "wie steht es".
        """
        return w.stand()

    def signale_lesen(zeitraum: str = "heute", anzahl: int = 8) -> str:
        """Die abgeschlossenen Signale mit Einstieg, Pips und Grund des
        Ausstiegs.

        Args:
            zeitraum: heute, woche, monat oder alles.
            anzahl: wie viele Signale, hoechstens 20.
        """
        return w.signale(zeitraum, anzahl)

    def regelwerk(bot: str = "") -> str:
        """Das Regelwerk eines Bots im Klartext: Filter, Einstieg, Stop,
        Ziele, Handelszeiten und Risikogrenzen.

        Args:
            bot: dauerlaeufer, swing oder kopierer. Leer heisst der Bot, der
                gerade eingestellt ist.
        """
        return w.regeln(bot)

    def aufgabe_anlegen(text: str) -> str:
        """Notiert ein Problem oder einen Wunsch, damit es spaeter abgearbeitet
        wird. Benutze das, wenn etwas kaputt ist oder geaendert werden soll.

        Args:
            text: Was genau passiert und was erwartet wird.
        """
        return w.aufgabe(text)

    def aufgaben_lesen() -> str:
        """Die offenen Aufgaben, die bisher notiert wurden."""
        return w.aufgaben()

    def handel_stoppen() -> str:
        """Setzt den Not-Aus: der Bot schliesst beim naechsten Durchlauf alles
        und eroeffnet nichts Neues. Jederzeit umkehrbar.
        """
        return w.stoppen()

    def handel_erlauben() -> str:
        """Loest den Not-Aus wieder, der Bot darf danach handeln. Vorher beim
        Nutzer nachfragen.
        """
        return w.erlauben()

    funktionen: list[Callable[..., Any]] = [
        stand_abfragen, signale_lesen, regelwerk, aufgabe_anlegen,
        aufgaben_lesen, handel_stoppen, handel_erlauben]

    if w.verteiler is not None:
        def signal_entwurf(seite: str, einstieg: float, stop: float,
                           ziel: float, begruendung: str = "") -> str:
            """Legt ein Signal als Entwurf an und zeigt, wie es in jeder
            Gruppe aussehen wuerde. Verschickt wird dabei noch nichts.

            Benutze das, sobald Ben ein Signal durchgibt. Zeig ihm die
            Vorschau und warte auf sein Ja.

            Args:
                seite: long oder short.
                einstieg: Einstiegskurs.
                stop: Stopkurs. Bei long unter dem Einstieg, bei short darueber.
                ziel: Zielkurs. Bei long ueber dem Einstieg, bei short darunter.
                begruendung: Kurz, warum — Sweep, BOS, FVG. Nur der Inner
                    Circle bekommt sie zu sehen.
            """
            return w.signal_entwurf(seite, einstieg, stop, ziel, begruendung)

        def signal_freigeben() -> str:
            """Verschickt den bereitliegenden Entwurf wirklich: Inner Circle
            sofort, VIP mit Verzug. Erst aufrufen, wenn Ben ausdruecklich
            zugestimmt hat.
            """
            return w.signal_freigeben()

        def signal_verwerfen() -> str:
            """Wirft den bereitliegenden Entwurf weg, ohne ihn zu verschicken."""
            return w.signal_verwerfen()

        def signal_ergebnis(signal_id: str, ergebnis: str,
                            pips: float | None = None) -> str:
            """Meldet den Ausgang eines Signals in die Gruppen. Haengt als
            Antwort unter dem urspruenglichen Signal.

            Args:
                signal_id: Die Kennung, etwa sig-0003. gruppen_stand zeigt sie.
                ergebnis: gewonnen, verloren oder be.
                pips: Nur angeben, wenn weder am Ziel noch am Stop geschlossen
                    wurde. Sonst weglassen, dann wird gerechnet.
            """
            return w.signal_ergebnis(signal_id, ergebnis, pips)

        def einladung_erstellen(gruppe: str, name: str = "",
                                stunden: int = 24) -> str:
            """Erzeugt einen Einladungslink, der genau einmal benutzt werden
            kann und danach ablaeuft.

            Args:
                gruppe: inner oder vip.
                name: Fuer wen der Link ist, damit man ihn spaeter zuordnet.
                stunden: Wie lange er gilt, hoechstens 720.
            """
            return w.einladung(gruppe, name, stunden)

        def mitglied_entfernen(gruppe: str, user_id: str) -> str:
            """Entfernt jemanden aus einer Gruppe, ohne ihn dauerhaft zu
            sperren. Mit einem neuen Link darf die Person wieder rein.

            Args:
                gruppe: inner oder vip.
                user_id: Die Zahlen-Kennung des Nutzers, kein @-Name.
            """
            return w.mitglied_entfernen(gruppe, user_id)

        def gruppen_stand() -> str:
            """Welche Gruppen eingerichtet sind, was noch auf Versand wartet,
            und die zuletzt verschickten Signale mit ihren Kennungen.
            """
            return w.gruppen_stand()

        funktionen += [signal_entwurf, signal_freigeben, signal_verwerfen,
                       signal_ergebnis, einladung_erstellen,
                       mitglied_entfernen, gruppen_stand]

    if w.coder is not None:
        def am_code_bauen(auftrag: str) -> str:
            """Laesst einen Coding-Agenten am Repository weiterbauen: Website
            und Handelsbot. Er liest die Dateien, aendert sie, fuehrt die Tests
            aus und committet. Dauert einige Minuten.

            Args:
                auftrag: Der vollstaendige Auftrag in einem Absatz — was gebaut
                    oder geaendert werden soll und woran man erkennt, dass es
                    fertig ist.
            """
            return w.bauen(auftrag)

        funktionen.append(am_code_bauen)

    return funktionen


# ---- Der Assistent --------------------------------------------------------
@dataclass
class AssistantSettings:
    llm: LLMSettings = field(default_factory=LLMSettings)
    history_turns: int = 12


@dataclass
class Assistant:
    settings: AssistantSettings
    config: Config | None = None
    coder: Coder | None = None
    provider: Provider | None = None
    history: list[dict[str, str]] = field(default_factory=list)
    verteiler: Any = None

    def __post_init__(self) -> None:
        if self.provider is None:
            self.provider = anbieter_bauen(self.settings.llm)

    @property
    def anbieter(self) -> str:
        return self.provider.name if self.provider else "—"

    def hindernis(self) -> str:
        return self.provider.hindernis() if self.provider else "kein Anbieter"

    def ready(self) -> bool:
        return self.hindernis() == ""

    def reset(self) -> None:
        self.history = []

    def answer(self, frage: str, lage: str, bilder: Sequence[Bild] = (),
               melden: Any = None) -> str:
        hindernis = self.hindernis()
        if hindernis:
            return (f"{hindernis}\n\nSolange gehen nur die Befehle; "
                    "/hilfe zeigt sie.")

        nachricht = (f"LAGE\n{lage}\n\nNACHRICHT\n"
                     f"{frage or 'Schau dir das an.'}")
        werkzeuge: list[Callable[..., Any]] = []
        if self.config is not None:
            werkzeuge = werkzeug_funktionen(
                Werkzeuge(self.config, self.coder, melden, self.verteiler))

        text = self.provider.frage(
            SYSTEM, self.history[-self.settings.history_turns:],
            nachricht, list(bilder), werkzeuge) or ""
        text = text.strip()
        if not text:
            return "Darauf kam keine Antwort. Frag es anders."

        # Bilder wandern nicht in den Verlauf — sie gingen sonst jedes Mal mit.
        self.history.append({"role": "user", "content": f"NACHRICHT\n{frage}"})
        self.history.append({"role": "assistant", "content": text})
        self.history = self.history[-self.settings.history_turns:]
        return text
