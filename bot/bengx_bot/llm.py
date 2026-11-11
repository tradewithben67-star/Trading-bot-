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
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, Sequence

Bild = tuple[str, bytes]          # Medientyp und die rohen Daten


@dataclass
class LLMSettings:
    anbieter: str = "auto"                     # auto | claude | gemini
    claude_key: str = ""
    gemini_key: str = ""
    claude_model: str = "claude-opus-5-5"
    gemini_model: str = ""          # leer heißt: beim Schlüssel nachfragen
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
            gemini_model=env.get("BENGX_GEMINI_MODEL", "").strip(),
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
    versucht: set = field(default_factory=set)
    _kandidaten: list[str] = field(default_factory=list)
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
        if not self.modell:
            # Modellnamen ändern sich schneller als dieser Code. Statt einen
            # zu raten, den der Schlüssel vielleicht gar nicht darf, wird
            # gefragt — und das kleinste genommen, das es gibt.
            self.modell = (self.s.gemini_model
                           or self._naechstes_modell()
                           or "gemini-flash-lite-latest")
        return self.client

    def modelle(self) -> list[str]:
        """Welche Modelle dieser Schlüssel benutzen darf — günstigste zuerst.

        Modellnamen und Kontingente ändern sich häufiger als dieser Code,
        deshalb wird gefragt statt geraten.
        """
        try:
            namen = []
            for m in self.client.models.list():
                name = (getattr(m, "name", "") or "").split("/")[-1]
                aktionen = getattr(m, "supported_actions", None) or []
                if not name or "embedding" in name or "imagen" in name:
                    continue
                if aktionen and "generateContent" not in aktionen:
                    continue
                namen.append(name)
        except Exception:
            return []

        def rang(name: str) -> tuple[int, float, int]:
            # Erst die kleinen — die haben das großzügigste Kontingent —,
            # darunter die neueste Version zuerst.
            art = 3
            for i, muster in enumerate(("flash-lite", "flash", "pro")):
                if muster in name:
                    art = i
                    break
            version = 0.0
            for stueck in name.replace("-", " ").split():
                try:
                    version = max(version, float(stueck))
                except ValueError:
                    continue
            return (art, -version, len(name))

        return sorted(dict.fromkeys(namen), key=rang)

    def _naechstes_modell(self) -> str:
        if not self._kandidaten:
            self._kandidaten = self.modelle()
        for name in self._kandidaten:
            if name not in self.versucht:
                return name
        return ""

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
                types.AutomaticFunctionCallingConfig(maximum_remote_calls=3)
                if werkzeuge else None),
        )

    def frage(self, system, verlauf, nachricht, bilder, werkzeuge):
        from google.genai import errors

        client = self._verbinden()
        inhalte = self._inhalte(verlauf, nachricht, bilder)
        mit_suche = self.s.websuche and not self.ohne_suche
        letzter_fehler = ""

        for runde in range(3):
            self.versucht.add(self.modell)
            try:
                antwort = client.models.generate_content(
                    model=self.modell, contents=inhalte,
                    config=self._config(system, werkzeuge, mit_suche))
                return (getattr(antwort, "text", "") or "").strip()
            except errors.ClientError as exc:
                roh = str(exc)
                text = roh.lower()
                letzter_fehler = _kurz(roh)

                if mit_suche and ("tool" in text or "search" in text):
                    self.ohne_suche = True
                    mit_suche = False
                    self.notizen.append("Websuche abgeschaltet: geht hier "
                                        "nicht zusammen mit den Werkzeugen.")
                    continue

                if "api key" in text or "api_key" in text or "401" in text:
                    return ("Der Google-Schlüssel wird nicht angenommen. "
                            "Neu anlegen unter aistudio.google.com/apikey.")

                erschoepft = ("quota" in text or "429" in text
                              or "resource_exhausted" in text)
                unbekannt = ("not found" in text or "404" in text
                             or "not supported" in text)
                if erschoepft or unbekannt:
                    naechstes = self._naechstes_modell()
                    if naechstes:
                        grund = ("Kontingent erschöpft" if erschoepft
                                 else "Modell nicht verfügbar")
                        self.notizen.append(
                            f"{self.modell}: {grund} — versuche {naechstes}.")
                        self.modell = naechstes
                        if erschoepft:
                            # Nicht hetzen: sonst reißen wir das
                            # Minutenlimit erst recht.
                            time.sleep(2)
                        continue
                    if erschoepft:
                        return (
                            "Google gibt diesem Schlüssel kein Kontingent — "
                            "bei keinem Modell, das er benutzen darf.\n\n"
                            "Das heißt meist nicht „verbraucht“, sondern "
                            "„nie zugeteilt“. Nachsehen unter "
                            "https://ai.dev/rate-limit, welche Stufe dort "
                            "steht. Hilft oft: in aistudio.google.com/apikey "
                            "einen neuen Schlüssel in einem NEUEN Projekt "
                            "anlegen.\n\n"
                            f"Googles Meldung: {letzter_fehler}")
                    return ("Kein Modell gefunden, das dein Schlüssel benutzen "
                            f"darf.\n\nGoogles Meldung: {letzter_fehler}")

                return f"Google lehnt ab: {letzter_fehler}"
            except errors.ServerError as exc:
                return f"Bei Google hakt es gerade: {_kurz(str(exc))}"
            except Exception as exc:
                return f"Keine Antwort von Google: {_kurz(str(exc))}"

        return (f"Nach mehreren Versuchen keine Antwort.\n\n"
                f"Versucht: {', '.join(sorted(self.versucht)) or '—'}\n\n"
                f"Letzte Meldung: {letzter_fehler}")


def _kurz(text: str, laenge: int = 300) -> str:
    """Googles Meldungen sind lang und voller JSON — das Wesentliche reicht."""
    text = " ".join(text.split())
    for marke in ("'message': '", '"message": "'):
        if marke in text:
            rest = text.split(marke, 1)[1]
            for ende in ("', '", '", "'):
                if ende in rest:
                    rest = rest.split(ende, 1)[0]
                    break
            text = rest
            break
    return text[:laenge] + ("…" if len(text) > laenge else "")


def anbieter_bauen(s: LLMSettings) -> Provider:
    return GeminiProvider(s) if s.gewaehlt() == "gemini" else ClaudeProvider(s)
