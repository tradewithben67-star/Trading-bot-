"""Der Chat-Teil: fragt Claude über das offizielle Anthropic-SDK.

Das SDK ist die einzige Abhängigkeit des Projekts und bleibt freiwillig: fehlt
es oder fehlt der Schlüssel, läuft der Telegram-Bot weiter und beantwortet die
Befehle — nur freies Schreiben fällt dann aus.

    pip install anthropic
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

SYSTEM = (
    "Du bist der Assistent von Ben. Ben ist 18, kommt aus Deutschland und "
    "handelt seit einem Jahr ausschließlich Gold (XAU/USD). Sein Broker ist "
    "Tradequo, der über MetaTrader 5 läuft. Du antwortest ihm in Telegram.\n\n"
    "Antworte auf Deutsch, direkt und knapp — Telegram, nicht Aufsatz. Kein "
    "Marketing-Ton, keine Ausrufezeichen, keine Emojis.\n\n"
    "Zu jeder Nachricht bekommst du einen Abschnitt LAGE mit den echten Zahlen "
    "aus dem Bot: Kapital, offene Positionen, letzte verarbeitete Kerze, Trades "
    "von heute und insgesamt, Not-Aus-Zustand. Beantworte Fragen nach Zahlen "
    "ausschließlich daraus. Steht etwas nicht drin, sag das — erfinde nichts "
    "und schätze nicht.\n\n"
    "Du kannst nichts umstellen und keinen Code ändern. Meldet Ben ein Problem, "
    "sag ihm, dass /aufgabe <text> es notiert; Claude Code arbeitet die Liste "
    "später ab. Die Befehle sind /stand, /signale, /regeln, /aufgabe, "
    "/aufgaben, /aus und /an.\n\n"
    "Schickt Ben ein Bild, sieh es dir an und antworte darauf.\n\n"
    "Rede ihm nicht nach dem Mund. Sehen die Zahlen schlecht aus, sag es."
)


@dataclass
class AssistantSettings:
    api_key: str = ""
    model: str = "claude-opus-5-5"
    effort: str = "low"
    max_tokens: int = 1200
    history_turns: int = 12


@dataclass
class Assistant:
    """Hält den Gesprächsfaden und fragt Claude."""

    settings: AssistantSettings
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
    def answer(self, frage: str, lage: str, bilder: Sequence[tuple[str, str]] = ()) -> str:
        """`bilder` sind Paare aus Medientyp und base64-Daten."""
        if not self.ready():
            return ("Freies Schreiben ist nicht eingerichtet. Dafür fehlt das Paket "
                    "anthropic oder der Schlüssel ANTHROPIC_API_KEY. Die Befehle "
                    "funktionieren trotzdem — /hilfe zeigt sie.")

        import anthropic

        inhalt: list[dict[str, Any]] = []
        for media_type, data in bilder:
            inhalt.append({"type": "image", "source": {
                "type": "base64", "media_type": media_type, "data": data}})
        inhalt.append({"type": "text",
                       "text": f"LAGE\n{lage}\n\nFRAGE\n{frage or 'Schau dir das an.'}"})

        nachrichten = self.history[-self.settings.history_turns:] + [
            {"role": "user", "content": inhalt}
        ]

        try:
            antwort = self.client.messages.create(
                model=self.settings.model,
                max_tokens=self.settings.max_tokens,
                system=SYSTEM,
                messages=nachrichten,
                output_config={"effort": self.settings.effort},
            )
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

        if getattr(antwort, "stop_reason", None) == "refusal":
            return "Diese Anfrage hat Claude abgelehnt. Formulier sie anders."

        text = "\n".join(b.text for b in antwort.content
                         if getattr(b, "type", None) == "text").strip()
        if not text:
            return "Darauf kam keine Antwort. Frag es anders."

        # Bilder wandern nicht in den Verlauf: sie würden jedes Mal neu mitgehen.
        self.history.append({"role": "user", "content":
                             f"LAGE (gekürzt)\n\nFRAGE\n{frage}"})
        self.history.append({"role": "assistant", "content": text})
        self.history = self.history[-self.settings.history_turns:]
        return text
