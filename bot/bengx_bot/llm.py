"""Zwei Anbieter, eine Schnittstelle.

Der Assistent kann über **Gemini** von Google laufen oder über **Claude** von
Anthropic. Gemini hat ein kostenloses Kontingent und ist deshalb der Weg zum
Ausprobieren; Claude kostet, antwortet dafür gründlicher und ist der einzige,
der den Coding-Agenten antreiben kann.

    pip install google-genai        # für Gemini
    pip install anthropic           # für Claude

Welcher läuft, entscheidet sich von selbst: Es wird der genommen, für den ein
Schlüssel da ist. Sind beide da, gewinnt Claude, außer BENGX_ANBIETER sagt
etwas anderes.

Beide bekommen dieselben Werkzeuge und dieselbe Anweisung. Was der Bot kann,
hängt also nicht daran, wer antwortet — nur wie gut.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, Sequence

Bild = tuple[str, bytes]          # Medientyp und die rohen Daten


@dataclass
class LLMSettings:
    anbieter: str = "auto"                     # auto | claude | gemini
    claude_key: str = ""
    gemini_key: str = ""
    claude_model: str = "claude-opus-5-5"
    gemini_model: str = "gemini-2.5-flash"
    effort: str = "low"
    max_tokens: int = 1500
    websuche: bool = True

    @staticmethod
    def from_env(env: dict[str, str]) -> "LLMSettings":
        def an(name: str, standard: str = "1") -> bool:
            return str(env.get(name, standard)).strip().lower() not in (
                "0", "aus", "false", "nein")
        return LLMSettings(
            anbieter=env.get("BENGX_ANBIETER", "auto").strip() or "auto",
            claude_key=env.get("ANTHROPIC_API_KEY", "").strip(),
            gemini_key=(env.get("GOOGLE_API_KEY", "").strip()
                        or env.get("GEMINI_API_KEY", "").strip()),
            claude_model=env.get("BENGX_MODEL", "").strip() or "claude-opus-5-5",
            gemini_model=(env.get("BENGX_GEMINI_MODEL", "").strip()
                          or "gemini-2.5-flash"),
            effort=env.get("BENGX_EFFORT", "low").strip() or "low",
            max_tokens=int(env.get("BENGX_MAX_TOKENS", "1500") or 1500),
            websuche=an("BENGX_WEBSUCHE"),
        )

    def gewaehlt(self) -> str:
        wunsch = (self.anbieter or "auto").lower()
        if wunsch in ("claude", "anthropic"):
            return "claude"
        if wunsch in ("gemini", "google"):
            return "gemini"
        if self.claude_key:
            return "claude"
        if self.gemini_key:
            return "gemini"
        return "claude"


class Provider(Protocol):
    name: str

    def hindernis(self) -> str: ...
    def frage(self, system: str, verlauf: Sequence[dict[str, str]],
              nachricht: str, bilder: Sequence[Bild],
              werkzeuge: Sequence[Callable[..., Any]]) -> str: ...


# ---- Claude ---------------------------------------------------------------
@dataclass
class ClaudeProvider:
    s: LLMSettings
    name: str = "Claude"
    client: Any = None

    def hindernis(self) -> str:
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return ("Für Claude fehlt das Paket anthropic. "
                    "Nachinstallieren mit: pip install anthropic")
        if not self.s.claude_key:
            return "Für Claude fehlt ANTHROPIC_API_KEY."
        return ""

    def _verbinden(self) -> Any:
        if self.client is None:
            import anthropic
            self.client = anthropic.Anthropic(api_key=self.s.claude_key or None)
        return self.client

    def frage(self, system, verlauf, nachricht, bilder, werkzeuge):
        import anthropic
        from anthropic import beta_tool

        client = self._verbinden()
        inhalt: list[dict[str, Any]] = []
        for art, roh in bilder:
            inhalt.append({"type": "image", "source": {
                "type": "base64", "media_type": art,
                "data": base64.standard_b64encode(roh).decode("ascii")}})
        inhalt.append({"type": "text", "text": nachricht})

        nachrichten = [{"role": t["role"], "content": t["content"]}
                       for t in verlauf] + [{"role": "user", "content": inhalt}]

        gemeinsam = dict(model=self.s.claude_model, max_tokens=self.s.max_tokens,
                         system=system, messages=nachrichten,
                         output_config={"effort": self.s.effort})

        liste: list[Any] = [beta_tool(f) for f in werkzeuge]
        if self.s.websuche:
            liste.append({"type": "web_search_20260209", "name": "web_search",
                          "max_uses": 4})

        try:
            if liste:
                runner = client.beta.messages.tool_runner(tools=liste, **gemeinsam)
                antwort = (runner.until_done() if hasattr(runner, "until_done")
                           else _letzte(runner))
            else:
                antwort = client.messages.create(**gemeinsam)
        except anthropic.AuthenticationError:
            return "Der Anthropic-Schlüssel wird nicht angenommen."
        except anthropic.PermissionDeniedError:
            return "Der Anthropic-Schlüssel darf dieses Modell nicht benutzen."
        except anthropic.NotFoundError:
            return f"Das Modell {self.s.claude_model} gibt es so nicht."
        except anthropic.RateLimitError:
            return "Zu viele Anfragen gerade. Gleich noch einmal."
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                return "Bei Anthropic hakt es gerade. Gleich noch einmal."
            return f"Anfrage abgelehnt: {exc.message}"
        except anthropic.APIConnectionError:
            return "Keine Verbindung zu Anthropic. Netz prüfen."

        if antwort is None:
            return ""
        if getattr(antwort, "stop_reason", None) == "refusal":
            return "Diese Anfrage hat Claude abgelehnt. Formulier sie anders."
        return "\n".join(b.text for b in antwort.content
                         if getattr(b, "type", None) == "text").strip()


def _letzte(runner):
    letzte = None
    for nachricht in runner:
        letzte = nachricht
    return letzte


# ---- Gemini ---------------------------------------------------------------
@dataclass
class GeminiProvider:
    s: LLMSettings
    name: str = "Gemini"
    client: Any = None
    modell: str = ""
    ohne_suche: bool = False          # merkt sich, wenn Suche nicht mitgeht
    notizen: list[str] = field(default_factory=list)

    def hindernis(self) -> str:
        try:
            from google import genai  # noqa: F401
        except ImportError:
            return ("Für Gemini fehlt das Paket google-genai. "
                    "Nachinstallieren mit: pip install google-genai")
        if not self.s.gemini_key:
            return "Für Gemini fehlt GOOGLE_API_KEY."
        return ""

    def _verbinden(self) -> Any:
        if self.client is None:
            from google import genai
            self.client = genai.Client(api_key=self.s.gemini_key)
            self.modell = self.modell or self.s.gemini_model
        return self.client

    def _ersatzmodell(self) -> str:
        """Sucht ein verfügbares Modell, falls der eingestellte Name nicht
        mehr stimmt — Modellnamen ändern sich häufiger als dieser Code."""
        try:
            namen = []
            for m in self.client.models.list():
                name = (getattr(m, "name", "") or "").split("/")[-1]
                aktionen = getattr(m, "supported_actions", None) or []
                if name and (not aktionen or "generateContent" in aktionen):
                    namen.append(name)
        except Exception:
            return ""
        for muster in ("flash-latest", "flash", "pro"):
            for name in namen:
                if muster in name and "embedding" not in name:
                    return name
        return namen[0] if namen else ""

    def _inhalte(self, verlauf, nachricht, bilder):
        from google.genai import types
        inhalte = []
        for zug in verlauf:
            rolle = "model" if zug["role"] == "assistant" else "user"
            inhalte.append(types.Content(
                role=rolle, parts=[types.Part.from_text(text=zug["content"])]))
        teile = [types.Part.from_bytes(data=roh, mime_type=art)
                 for art, roh in bilder]
        teile.append(types.Part.from_text(text=nachricht))
        inhalte.append(types.Content(role="user", parts=teile))
        return inhalte

    def _config(self, system, werkzeuge, mit_suche):
        from google.genai import types
        liste: list[Any] = list(werkzeuge)
        if mit_suche:
            liste.append(types.Tool(google_search=types.GoogleSearch()))
        return types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=self.s.max_tokens,
            tools=liste or None,
            automatic_function_calling=(
                types.AutomaticFunctionCallingConfig(maximum_remote_calls=6)
                if werkzeuge else None),
        )

    def frage(self, system, verlauf, nachricht, bilder, werkzeuge):
        from google.genai import errors

        client = self._verbinden()
        inhalte = self._inhalte(verlauf, nachricht, bilder)
        mit_suche = self.s.websuche and not self.ohne_suche

        for versuch in range(3):
            try:
                antwort = client.models.generate_content(
                    model=self.modell, contents=inhalte,
                    config=self._config(system, werkzeuge, mit_suche))
                return (getattr(antwort, "text", "") or "").strip()
            except errors.ClientError as exc:
                text = str(exc).lower()
                if mit_suche and ("tool" in text or "search" in text):
                    # Suche und eigene Werkzeuge vertragen sich hier nicht.
                    self.ohne_suche = True
                    mit_suche = False
                    self.notizen.append("Websuche abgeschaltet: geht nicht "
                                        "zusammen mit den Werkzeugen.")
                    continue
                if versuch == 0 and ("not found" in text or "404" in text
                                     or "not supported" in text):
                    ersatz = self._ersatzmodell()
                    if ersatz and ersatz != self.modell:
                        self.notizen.append(
                            f"Modell {self.modell} gibt es nicht mehr, "
                            f"nehme {ersatz}.")
                        self.modell = ersatz
                        continue
                if "api key" in text or "permission" in text or "401" in text:
                    return "Der Google-Schlüssel wird nicht angenommen."
                if "quota" in text or "429" in text or "resource_exhausted" in text:
                    return ("Das kostenlose Kontingent ist gerade "
                            "aufgebraucht. Später noch einmal.")
                return f"Google lehnt die Anfrage ab: {exc}"
            except errors.ServerError:
                return "Bei Google hakt es gerade. Gleich noch einmal."
            except Exception as exc:
                return f"Keine Antwort von Google: {exc}"
        return ""


def anbieter_bauen(s: LLMSettings) -> Provider:
    return GeminiProvider(s) if s.gewaehlt() == "gemini" else ClaudeProvider(s)
