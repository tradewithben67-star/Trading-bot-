"""Der Chat-Teil: fragt Claude über das offizielle Anthropic-SDK.

Ben schreibt normal — keine Befehle. Damit das geht, bekommt Claude Werkzeuge:
den Stand abfragen, Signale lesen, das Regelwerk zeigen, eine Aufgabe notieren
und den Handel stoppen oder wieder erlauben. Was Ben in Worten sagt, führt
Claude damit aus.

Das SDK ist die einzige Abhängigkeit des Projekts und bleibt freiwillig: fehlt
es oder fehlt der Schlüssel, laufen die Befehle als Rückfallebene weiter.

    pip install anthropic
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from . import report
from .coder import Coder
from .config import Config

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
    "dass es notiert ist. Claude Code arbeitet die Liste ab.\n"
    "- Sagt er, der Bot soll aufhören, stoppen, Schluss machen → "
    "handel_stoppen. Das ist jederzeit umkehrbar, also zögere nicht.\n"
    "- Soll wieder gehandelt werden → frag einmal nach, bevor du "
    "handel_erlauben benutzt.\n"
    "- Sagt er, du sollst an der Website, am Bot oder am Code weiterbauen, "
    "etwas ändern oder reparieren → am_code_bauen. Dahinter läuft ein "
    "richtiger Coding-Agent auf Bens Rechner, der Dateien ändert, testet und "
    "committet. Gib ihm einen vollständigen Auftrag in einem Absatz, nicht "
    "nur Bens Stichwort. Es dauert ein paar Minuten; sag das vorher. Ist "
    "unklar, was genau gebaut werden soll, frag einmal nach.\n\n"
    "Zu jeder Nachricht steht ein Abschnitt LAGE mit den aktuellen Zahlen. "
    "Reicht er, antworte sofort daraus statt ein Werkzeug zu rufen — das "
    "spart Zeit. Reicht er nicht, ruf das Werkzeug.\n\n"
    "Erfinde nie eine Zahl und schätze nicht. Weißt du etwas nicht, sag es. "
    "Du kannst keinen Code ändern und nichts am Regelwerk umstellen — dafür "
    "legst du eine Aufgabe an.\n\n"
    "Für alles, was draußen passiert — Kurse, Termine, Nachrichten zu Gold, "
    "Broker-Meldungen — benutzt du die Websuche und nennst die Quelle. Für "
    "Zahlen aus Bens eigenem Bot niemals die Websuche, dafür hast du die "
    "Werkzeuge.\n\n"
    "Schickt Ben ein Bild, sieh es dir an und antworte darauf.\n\n"
    "Rede ihm nicht nach dem Mund. Sehen die Zahlen schlecht aus, sag es."
)


# ---- Was die Werkzeuge wirklich tun --------------------------------------
class Werkzeuge:
    """Die Arbeit hinter den Werkzeugen — ohne SDK, damit sie prüfbar bleibt."""

    def __init__(self, config: Config, coder: Coder | None = None,
                 melden: Any = None) -> None:
        self.cfg = config
        self.coder = coder
        self.melden = melden
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

    def erlauben(self) -> str:
        self._merken("erlauben")
        p = Path(self.cfg.live.killswitch_file)
        if not p.exists():
            return "Der Handel war gar nicht gestoppt."
        p.unlink()
        return "Not-Aus gelöst. Der Bot darf wieder handeln."


def build_tools(w: Werkzeuge) -> list[Any]:
    """Verpackt die Werkzeuge so, wie das SDK sie erwartet."""
    from anthropic import beta_tool

    @beta_tool
    def stand_abfragen() -> str:
        """Der aktuelle Stand des Handelsbots: Kapital, offene Positionen,
        letzte verarbeitete Kerze, Zahlen von heute und insgesamt, ob der
        Not-Aus gesetzt ist. Für Fragen wie „wie läuft es“ oder „wie steht es“.
        """
        return w.stand()

    @beta_tool
    def signale_lesen(zeitraum: str = "heute", anzahl: int = 8) -> str:
        """Die abgeschlossenen Signale mit Einstieg, Pips und Grund des
        Ausstiegs.

        Args:
            zeitraum: heute, woche, monat oder alles.
            anzahl: wie viele Signale, höchstens 20.
        """
        return w.signale(zeitraum, anzahl)

    @beta_tool
    def regelwerk(bot: str = "") -> str:
        """Das Regelwerk eines Bots im Klartext: Filter, Einstieg, Stop,
        Ziele, Handelszeiten und Risikogrenzen.

        Args:
            bot: dauerlaeufer, swing oder kopierer. Leer heißt der Bot, der
                gerade eingestellt ist.
        """
        return w.regeln(bot)

    @beta_tool
    def aufgabe_anlegen(text: str) -> str:
        """Notiert ein Problem oder einen Wunsch, damit Claude Code es später
        abarbeitet. Benutze das, wenn etwas kaputt ist oder geändert werden
        soll.

        Args:
            text: Was genau passiert und was erwartet wird.
        """
        return w.aufgabe(text)

    @beta_tool
    def aufgaben_lesen() -> str:
        """Die offenen Aufgaben, die bisher notiert wurden."""
        return w.aufgaben()

    @beta_tool
    def handel_stoppen() -> str:
        """Setzt den Not-Aus: der Bot schließt beim nächsten Durchlauf alles
        und eröffnet nichts Neues. Jederzeit umkehrbar.
        """
        return w.stoppen()

    @beta_tool
    def handel_erlauben() -> str:
        """Löst den Not-Aus wieder, der Bot darf danach handeln. Vorher beim
        Nutzer nachfragen.
        """
        return w.erlauben()

    werkzeuge = [stand_abfragen, signale_lesen, regelwerk, aufgabe_anlegen,
                 aufgaben_lesen, handel_stoppen, handel_erlauben]

    if w.coder is not None:
        @beta_tool
        def am_code_bauen(auftrag: str) -> str:
            """Lässt einen Coding-Agenten am Repository weiterbauen: Website
            und Handelsbot. Er liest die Dateien, ändert sie, führt die Tests
            aus und committet. Dauert einige Minuten.

            Args:
                auftrag: Der vollständige Auftrag in einem Absatz — was gebaut
                    oder geändert werden soll und woran man erkennt, dass es
                    fertig ist.
            """
            return w.bauen(auftrag)

        werkzeuge.append(am_code_bauen)

    return werkzeuge


# ---- Der Assistent --------------------------------------------------------
WEB_SEARCH = {"type": "web_search_20260209", "name": "web_search", "max_uses": 4}


@dataclass
class AssistantSettings:
    api_key: str = ""
    model: str = "claude-opus-5-5"
    effort: str = "low"
    max_tokens: int = 1500
    history_turns: int = 12
    websuche: bool = True      # läuft bei Anthropic, kein eigener Schlüssel nötig


@dataclass
class Assistant:
    settings: AssistantSettings
    config: Config | None = None
    coder: Coder | None = None
    client: Any = None
    history: list[dict[str, Any]] = field(default_factory=list)

    @staticmethod
    def sdk_available() -> bool:
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False
        return True

    def ready(self) -> bool:
        return self.client is not None or self._connect()

    def _connect(self) -> bool:
        if self.client is not None:
            return True
        try:
            import anthropic
        except ImportError:
            return False
        try:
            self.client = (anthropic.Anthropic(api_key=self.settings.api_key)
                           if self.settings.api_key else anthropic.Anthropic())
        except Exception:
            return False
        return True

    def reset(self) -> None:
        self.history = []

    # ---- Anfrage ---------------------------------------------------------
    def answer(self, frage: str, lage: str,
               bilder: Sequence[tuple[str, str]] = (),
               melden: Any = None) -> str:
        """`bilder` sind Paare aus Medientyp und base64-Daten."""
        if not self.ready():
            return ("Freies Schreiben ist nicht eingerichtet — dafür fehlt das "
                    "Paket anthropic oder der Schlüssel ANTHROPIC_API_KEY. "
                    "Solange gehen nur die Befehle; /hilfe zeigt sie.")

        import anthropic

        inhalt: list[dict[str, Any]] = []
        for media_type, data in bilder:
            inhalt.append({"type": "image", "source": {
                "type": "base64", "media_type": media_type, "data": data}})
        inhalt.append({"type": "text",
                       "text": f"LAGE\n{lage}\n\nNACHRICHT\n"
                               f"{frage or 'Schau dir das an.'}"})

        nachrichten = self.history[-self.settings.history_turns:] + [
            {"role": "user", "content": inhalt}]

        werkzeuge: list[Any] = []
        if self.config is not None:
            try:
                werkzeuge = build_tools(
                    Werkzeuge(self.config, self.coder, melden))
            except Exception:
                werkzeuge = []
        if self.settings.websuche:
            # Server-Werkzeug: läuft bei Anthropic mit, kein zweiter Schlüssel.
            werkzeuge.append(dict(WEB_SEARCH))

        try:
            antwort = self._call(nachrichten, werkzeuge)
        except anthropic.AuthenticationError:
            return "Der API-Schlüssel wird nicht angenommen. Bitte prüfen."
        except anthropic.PermissionDeniedError:
            return "Der API-Schlüssel darf dieses Modell nicht benutzen."
        except anthropic.NotFoundError:
            return f"Das Modell {self.settings.model} gibt es so nicht."
        except anthropic.RateLimitError:
            return "Zu viele Anfragen gerade. Gleich noch einmal."
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                return "Bei Anthropic hakt es gerade. Gleich noch einmal."
            return f"Anfrage abgelehnt: {exc.message}"
        except anthropic.APIConnectionError:
            return "Keine Verbindung zu Anthropic. Netz prüfen."

        if antwort is None:
            return "Darauf kam keine Antwort. Frag es anders."
        if getattr(antwort, "stop_reason", None) == "refusal":
            return "Diese Anfrage hat Claude abgelehnt. Formulier sie anders."

        text = "\n".join(b.text for b in antwort.content
                         if getattr(b, "type", None) == "text").strip()
        if not text:
            return "Darauf kam keine Antwort. Frag es anders."

        # Bilder wandern nicht in den Verlauf — sie gingen sonst jedes Mal mit.
        self.history.append({"role": "user", "content": f"NACHRICHT\n{frage}"})
        self.history.append({"role": "assistant", "content": text})
        self.history = self.history[-self.settings.history_turns:]
        return text

    def _call(self, nachrichten: list[dict[str, Any]], werkzeuge: list[Any]):
        gemeinsam = dict(
            model=self.settings.model,
            max_tokens=self.settings.max_tokens,
            system=SYSTEM,
            messages=nachrichten,
            output_config={"effort": self.settings.effort},
        )
        if not werkzeuge:
            return self.client.messages.create(**gemeinsam)

        runner = self.client.beta.messages.tool_runner(tools=werkzeuge, **gemeinsam)
        if hasattr(runner, "until_done"):
            return runner.until_done()
        letzte = None
        for nachricht in runner:
            letzte = nachricht
        return letzte
