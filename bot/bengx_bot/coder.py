"""Der Coding-Agent: baut wirklich am Repository weiter.

Sagt Ben in Telegram „baue an der Website weiter“, läuft auf derselben
Maschine ein Claude-Code-Agent los, liest die Dateien, ändert sie, führt die
Tests aus und committet. Dafür gibt es das Claude-Agent-SDK:

    pip install claude-agent-sdk

Das bleibt freiwillig. Fehlt das Paket oder steht der Schalter aus, sagt der
Bot das und notiert stattdessen eine Aufgabe.

Vier Grenzen sind eingebaut, weil hier niemand danebensitzt:

* **Aus, bis es eingeschaltet wird** — BENGX_CODER=1 in der .env.
* **Nur ein Ordner** — der Agent arbeitet in dem Verzeichnis aus der
  Konfiguration, sonst nirgends.
* **Zugkraft begrenzt** — höchstens so viele Schritte und so viele Dollar,
  wie eingestellt sind; danach bricht das SDK selbst ab.
* **Kein Push** — er darf committen, aber nichts nach außen schieben, außer
  der Auftrag sagt es ausdrücklich.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

ANWEISUNG = """Du arbeitest am Repository von BENGX: eine Website (index.html,
konsole.html) und ein Handelsbot in Python unter bot/.

So arbeitest du:
- Lies zuerst, was es gibt, bevor du etwas änderst.
- Halte dich an den vorhandenen Stil: Deutsch in Texten und Kommentaren,
  keine neuen Abhängigkeiten ohne Not.
- Nach jeder Änderung am Bot: python3 -m unittest discover -s tests -t .
  im Ordner bot/ ausführen. Schlägt ein Test fehl, repariere es.
- Committe mit einer aussagekräftigen Nachricht auf Deutsch.
- Schiebe NICHTS nach außen (kein git push), außer der Auftrag verlangt es.
- Ändere keine Zugangsdaten, keine .env und nichts unter state/.

Antworte am Ende mit drei bis fünf Sätzen auf Deutsch: was du geändert hast,
ob die Tests laufen, und was offen bleibt. Keine Aufzählung, keine
Überschriften — das geht direkt als Telegram-Nachricht raus."""


@dataclass
class CoderSettings:
    enabled: bool = False
    repo: str = ".."
    max_turns: int = 40
    max_budget_usd: float = 2.0
    timeout_seconds: float = 900.0
    permission_mode: str = "acceptEdits"
    model: str = ""

    @staticmethod
    def from_env(env: dict[str, str]) -> "CoderSettings":
        an = str(env.get("BENGX_CODER", "0")).strip().lower()
        return CoderSettings(
            enabled=an in ("1", "an", "true", "ja"),
            repo=env.get("BENGX_REPO", "..").strip() or "..",
            max_turns=int(env.get("BENGX_CODER_TURNS", "40") or 40),
            max_budget_usd=float(env.get("BENGX_CODER_BUDGET", "2.0") or 2.0),
            timeout_seconds=float(env.get("BENGX_CODER_TIMEOUT", "900") or 900),
            model=env.get("BENGX_CODER_MODEL", "").strip(),
        )


@dataclass
class Coder:
    settings: CoderSettings
    runner: Callable[[str, "CoderSettings"], str] | None = None
    verlauf: list[str] = field(default_factory=list)

    @staticmethod
    def sdk_available() -> bool:
        try:
            import claude_agent_sdk  # noqa: F401
        except ImportError:
            return False
        return True

    def status(self) -> str:
        if not self.settings.enabled:
            return ("Das Weiterbauen ist ausgeschaltet. Zum Einschalten "
                    "BENGX_CODER=1 in bot/.env setzen und mich neu starten.")
        if self.runner is None and not self.sdk_available():
            return ("Dafür fehlt das Paket claude-agent-sdk. "
                    "Nachinstallieren mit: pip install claude-agent-sdk")
        ordner = Path(self.settings.repo).resolve()
        if not ordner.is_dir():
            return f"Den Ordner {ordner} gibt es nicht."
        return ""

    def ready(self) -> bool:
        return self.status() == ""

    # ---- Ausführen -------------------------------------------------------
    def run(self, auftrag: str) -> str:
        hindernis = self.status()
        if hindernis:
            raise RuntimeError(hindernis)
        auftrag = (auftrag or "").strip()
        if not auftrag:
            raise ValueError("Ohne Auftrag kann ich nichts bauen.")

        self.verlauf.append(auftrag)
        if self.runner is not None:
            return self.runner(auftrag, self.settings)
        return _run_sdk(auftrag, self.settings)


def _run_sdk(auftrag: str, s: CoderSettings) -> str:
    from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions,  # type: ignore
                                  ResultMessage, TextBlock, query)

    optionen: dict[str, Any] = dict(
        cwd=str(Path(s.repo).resolve()),
        system_prompt={"type": "preset", "preset": "claude_code",
                       "append": ANWEISUNG},
        permission_mode=s.permission_mode,
        allowed_tools=["Read", "Grep", "Glob", "Edit", "Write", "Bash",
                       "TodoWrite"],
        max_turns=s.max_turns,
        max_budget_usd=s.max_budget_usd,
        setting_sources=["project"],
    )
    if s.model:
        optionen["model"] = s.model

    async def arbeiten() -> str:
        letzter_text = ""
        ergebnis = ""
        async for nachricht in query(prompt=auftrag,
                                     options=ClaudeAgentOptions(**optionen)):
            if isinstance(nachricht, ResultMessage):
                if nachricht.subtype == "success":
                    ergebnis = nachricht.result or ""
                else:
                    ergebnis = (f"Der Agent hat abgebrochen "
                                f"({nachricht.subtype}).")
            elif isinstance(nachricht, AssistantMessage):
                for block in nachricht.content:
                    if isinstance(block, TextBlock) and block.text.strip():
                        letzter_text = block.text.strip()
        return ergebnis or letzter_text or "Der Agent hat nichts zurückgemeldet."

    async def mit_frist() -> str:
        return await asyncio.wait_for(arbeiten(), timeout=s.timeout_seconds)

    try:
        return asyncio.run(mit_frist())
    except asyncio.TimeoutError:
        return (f"Abgebrochen: der Agent lief länger als "
                f"{int(s.timeout_seconds / 60)} Minuten. Was bis dahin "
                "geändert wurde, steht im Repository — bitte nachsehen.")
    except Exception as exc:                      # pragma: no cover - Umgebung
        return f"Der Agent ist gescheitert: {exc}"
