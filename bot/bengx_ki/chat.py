"""Chat: mit der KI schreiben wie mit einem Menschen.

Das eigene Gehirn kann einschätzen, aber nicht sprechen. Das Sprechen
übernimmt Claude (Anthropic). Claude rechnet dabei nichts selbst aus:
jede Zahl holt es sich über die Werkzeuge unten, also über dieselben
Funktionen wie die Oberfläche — das eigene Gehirn, die Indikatoren, den
Strategie-Test, den Verlauf. Was Claude damit erstellt (eine Analyse, ein
Test, ein Indikator), hängt die Oberfläche als Karte an die Antwort.

Einrichtung: einen API-Schlüssel von console.anthropic.com als
ANTHROPIC_API_KEY in die Umgebung oder in `bot/.env` legen. Ohne Schlüssel
läuft alles andere weiter, nur der Chat sagt, dass er nicht eingerichtet ist.

Jede Chat-Nachricht kostet bei Anthropic echtes Geld (meist wenige Cent).
Deshalb hat der Chat ein eigenes Kontingent je Abo (`konto.ABOS[...]["chat"]`).
Das Modell lässt sich mit BENGX_KI_CLAUDE_MODELL ändern.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .konto import Grenze, abo_von
from .modelle import MODELLE

MODELL = os.environ.get("BENGX_KI_CLAUDE_MODELL", "claude-opus-5-5")
MAX_SCHRITTE = 8          # Werkzeug-Runden je Nachricht
MAX_VERLAUF = 120         # Nachrichten je Faden, danach beginnt ein neuer

BEREICHE = {"allgemein": "Chat", "analyse": "Analyse", "indikatoren": "Indikatoren",
            "strategie": "Strategie", "verlauf": "Verlauf", "modelle": "Modelle"}

SYSTEM = """Du bist die BENGX KI, der Assistent in der BENGX-KI-Oberfläche für den Goldhandel (XAU/USD). Du sprichst Deutsch, duzt und schreibst klar und knapp, wie ein erfahrener Händler, der etwas erklärt.

Was hinter dir steckt: ein eigenes neuronales Netz (Transformer) in drei Größen: Mini, Standard und Max. Es ist auf Kerzen trainiert und schätzt für die jüngste Kerze, ob der Kurs zuerst das Ziel oben oder den Stop unten erreicht, beide je 1,5 × ATR entfernt, innerhalb von 24 Kerzen. Du selbst rechnest nichts aus dem Kopf. Kurse, Einschätzungen, Indikatorwerte und Ergebnisse holst du dir immer über die Werkzeuge. Erfinde nie Zahlen.

Kosten für den Nutzer: Analysen und Strategie-Tests verbrauchen sein Kontingent (Analyse: Mini 1, Standard 3, Max 10 Tokens; Strategie-Test das Fünffache). Starte sie nur, wenn der Nutzer danach fragt oder seine Frage ohne sie nicht zu beantworten ist. Nennt er kein Modell, nimm Standard, oder Mini, wenn Standard nicht verfügbar ist. Indikatoren, Kerzen, Verlauf und Stand zu lesen kostet nichts.

Analysen erklären: Das Werkzeug ki_analyse liefert neben der Einschätzung die Felder gruende, fokus und merkmale. Das sind Messungen am Netz: auf welche Kerzen es geachtet hat und wie stark die Wahrscheinlichkeit sinkt, wenn man ihm eine Merkmalsgruppe wegnimmt. Stütze jede Begründung darauf und auf die Kerzen selbst. Sag ehrlich, wenn die KI unsicher ist, also bei Werten nahe 50 %, und was gegen das Setup spricht.

Eigene Indikatoren sind Formeln aus open, high, low, close, volume, hl2, hlc3, Zahlen, + - * /, den Vergleichen > < >= <=, and, or, not und den Funktionen sma(x, n), ema(x, n), rsi(x, n), atr(n), stdev(x, n), highest(x, n), lowest(x, n), change(x, n), ref(x, n), crossover(a, b), crossunder(a, b), abs(x), min(a, b), max(a, b). Eine Formel mit Vergleich ist eine Bedingung; für sie misst indikator_pruefen, wie oft sie zutraf und wohin der Kurs danach ging. Prüfe jede Formel, bevor du sie speicherst, und speichere nur, wenn der Nutzer es möchte.

Ist ein Kontingent aufgebraucht oder ein Modell nicht im Abo, sag das klar und nenne, was stattdessen geht: ein anderes Modell, der nächste Monat oder ein anderes Abo beim Inhaber.

Du gibst keine Anlageberatung und versprichst keine Gewinne. Eine Kauf- oder Verkaufsidee ist eine Einschätzung; erinnere bei solchen Ideen kurz daran, zuerst auf Papier zu testen. Spread und Gebühren sind in den Zahlen nicht enthalten.

Form: kurze Absätze, Aufzählungen mit "- " wenn es hilft, **fett** nur sparsam, keine Tabellen, keine Überschriften. Analysen, Tests und Indikatoren, die du mit Werkzeugen erstellst, zeigt die Oberfläche als Karte mit Chart unter deiner Antwort. Zähl deshalb nicht alle Zahlen auf, sondern sag, was sie bedeuten.

Jede Nachricht des Nutzers beginnt mit einer Zeile in eckigen Klammern: auf welcher Seite er gerade ist und sein Abo. Diese Zeile kommt von der Oberfläche, nicht vom Nutzer. Den Namen des Nutzers kennst du nicht; frag nicht danach."""


def _werkzeug(name: str, beschreibung: str, felder: dict) -> dict:
    return {"name": name, "description": beschreibung, "strict": True,
            "input_schema": {"type": "object", "properties": felder,
                             "required": list(felder), "additionalProperties": False}}


_MODELL_FELD = {"type": "string", "enum": list(MODELLE),
                "description": "mini, standard oder max"}

WERKZEUGE = [
    _werkzeug("ki_analyse",
              "Lässt das eigene Netz die jüngste Kerze einschätzen: Wahrscheinlichkeiten für hoch, "
              "seitwärts und runter, eine Kauf- oder Verkaufsidee mit Stop und Ziel, dazu die Begründung "
              "(gruende, fokus, merkmale). Verbraucht das Kontingent des Nutzers.",
              {"modell": _MODELL_FELD,
               "schwelle": {"type": "number", "description": "ab welcher Sicherheit eine Idee entsteht, 0.5 bis 0.8; üblich 0.5"}}),
    _werkzeug("strategie_testen",
              "Prüft ein Modell auf allen Kerzen nach seinem Lernzeitraum: Trefferquote gegen Raten und "
              "Handelsergebnis in R je Sicherheitsstufe, verglichen mit 'immer kaufen'. Verbraucht das Kontingent.",
              {"modell": _MODELL_FELD}),
    _werkzeug("indikatoren_lesen",
              "Liest die klassischen Indikatoren auf den aktuellen Kerzen: EMA 50/200, RSI, ADX, ATR, "
              "20er-Kanal, mit Deutung. Kostenlos.", {}),
    _werkzeug("indikator_pruefen",
              "Rechnet eine Indikator-Formel aus. Bei einer Bedingung zusätzlich: wie oft sie zutraf und wie "
              "oft danach zuerst das Ziel oben oder der Stop unten kam, verglichen mit allen Kerzen. Kostenlos.",
              {"formel": {"type": "string", "description": "z. B. rsi(close, 14) < 30"}}),
    _werkzeug("indikator_speichern",
              "Speichert einen eigenen Indikator für den Nutzer; er erscheint dann unter Indikatoren im Chart. "
              "Gleicher Name überschreibt. Nur auf Wunsch des Nutzers.",
              {"name": {"type": "string", "description": "kurzer Name, z. B. RSI 21"},
               "formel": {"type": "string"},
               "anzeige": {"type": "string", "enum": ["chart", "unten"],
                           "description": "chart: im Kurschart (Linien auf Kursniveau, Bedingungen); unten: eigenes Feld (Oszillatoren wie RSI, MACD)"}}),
    _werkzeug("eigene_indikatoren",
              "Listet die gespeicherten eigenen Indikatoren des Nutzers mit Formel und aktuellem Wert. Kostenlos.", {}),
    _werkzeug("kerzen_lesen",
              "Liest die jüngsten Kerzen (Zeit in UTC, Open, High, Low, Close). Kostenlos.",
              {"anzahl": {"type": "integer", "description": "1 bis 120"}}),
    _werkzeug("stand_lesen",
              "Stand der drei Modelle (trainiert, Prüfergebnis) und das Kontingent des Nutzers je Modell "
              "und für den Chat. Kostenlos.", {}),
    _werkzeug("verlauf_lesen",
              "Die letzten Aktionen im Verlauf des Nutzers (Analysen, Tests, Trainings), neueste zuerst. Kostenlos.",
              {"bereich": {"type": "string", "enum": ["alle", "analyse", "strategie", "indikatoren", "training"]},
               "anzahl": {"type": "integer", "description": "1 bis 30"}}),
]


def _jetzt() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _r(x, n=4):
    return round(x, n) if isinstance(x, float) else x


class Werkzeuge:
    """Führt die Werkzeuge im Namen eines Nutzers aus."""

    def __init__(self, app, nutzer: dict) -> None:
        self.app = app
        self.n = nutzer
        self.anhaenge: list[dict] = []

    def ki_analyse(self, modell: str, schwelle: float) -> dict:
        e = self.app.analyse(self.n, {"modell": modell, "schwelle": schwelle})
        self.anhaenge.append({"art": "verlauf", "id": e["id"]})
        d = e["daten"]
        return {"modell": MODELLE[modell]["name"], "tokens_verbraucht": e["tokens"],
                "kerze": d["kerze"], "schluss": d["schluss"],
                "wahrscheinlichkeiten": {k: _r(v, 3) for k, v in d["wahrscheinlichkeiten"].items()},
                "idee": d["idee"] and {k: _r(v, 2) if k != "richtung" else v for k, v in d["idee"].items()},
                "schwelle": d["schwelle"], "horizont_kerzen": d["horizont"],
                "gruende": d["gruende"],
                "fokus": [{"kerzen_zurueck": f["vor"], "form": f["form"], "aufmerksamkeit": _r(f["gewicht"], 3)}
                          for f in d["fokus"]],
                "merkmale_prozentpunkte": {b["gruppe"]: round(b["beitrag"] * 100, 1) for b in d["merkmale"]}}

    def strategie_testen(self, modell: str) -> dict:
        e = self.app.strategie(self.n, {"modell": modell})
        self.anhaenge.append({"art": "verlauf", "id": e["id"]})
        d = e["daten"]
        return {"modell": MODELLE[modell]["name"], "tokens_verbraucht": e["tokens"],
                "test_ab": d.get("ab"), "kerzen": d["kerzen"],
                "treffer": _r(d["treffer"], 3), "raten": _r(d["raten"], 3),
                "schwellen": [{k: _r(v, 3) for k, v in s.items()} for s in d["schwellen"]],
                "immer_kaufen": {k: _r(v, 3) for k, v in d["immer_kaufen"].items()}}

    def indikatoren_lesen(self) -> dict:
        e = self.app.indikatoren(self.n, {})
        self.anhaenge.append({"art": "verlauf", "id": e["id"]})
        d = e["daten"]
        return {"gesamt": d["gesamt"],
                "werte": [{"name": x["name"], "wert": _r(x["wert"], 2), "deutung": x["deutung"]} for x in d["liste"]]}

    def indikator_pruefen(self, formel: str) -> dict:
        from .eigene import auswerten
        d = auswerten(self.app.quelle.kerzen(), formel)
        raus = {"formel": formel, "bedingung": d["bedingung"], "aktuell": _r(d["aktuell"], 4)}
        if d["bedingung"]:
            raus["statistik"] = {k: _r(v, 3) for k, v in d["statistik"].items()}
        self.anhaenge.append({"art": "formel", "name": formel, "formel": formel,
                              "anzeige": "unten" if not d["bedingung"] and _oszillator(formel) else "chart"})
        return raus

    def indikator_speichern(self, name: str, formel: str, anzeige: str) -> dict:
        from .eigene import auswerten
        auswerten(self.app.quelle.kerzen(), formel)        # erst prüfen
        i = self.app.eigene.speichern(self.n["id"], name, formel, anzeige)
        self.anhaenge.append({"art": "formel", "name": i["name"], "formel": i["formel"],
                              "anzeige": i["anzeige"], "gespeichert": True})
        return {"gespeichert": True, **i}

    def eigene_indikatoren(self) -> dict:
        from .eigene import auswerten
        kerzen = self.app.quelle.kerzen()
        raus = []
        for i in self.app.eigene.liste(self.n["id"]):
            try:
                a = auswerten(kerzen, i["formel"])["aktuell"]
            except ValueError as exc:
                a = f"Fehler: {exc}"
            raus.append({**i, "aktuell": _r(a, 4)})
        return {"indikatoren": raus}

    def kerzen_lesen(self, anzahl: int) -> dict:
        k = self.app.quelle.kerzen()[-max(1, min(int(anzahl), 120)):]
        return {"kerzen": [[x.ts.strftime("%Y-%m-%d %H:%M"), x.open, x.high, x.low, x.close] for x in k],
                "spalten": ["zeit_utc", "open", "high", "low", "close"]}

    def stand_lesen(self) -> dict:
        m = self.app.modelle.info()
        s = self.app.nutzung.stand(self.n)
        return {"abo": s["abo_name"], "unbegrenzt": s["unbegrenzt"], "frei_ab": s["auffuellung"],
                "modelle": {k: {"trainiert": v["vorhanden"],
                                "pruefung_treffer": _r(v["ergebnis"]["treffer"], 3) if v.get("ergebnis") else None,
                                "pruefung_raten": _r(v["ergebnis"]["raten"], 3) if v.get("ergebnis") else None,
                                "kontingent": {x: s["modelle"][k][x] for x in ("limit", "verbraucht", "rest", "gesperrt")}}
                            for k, v in m.items()},
                "chat": s["chat"]}

    def verlauf_lesen(self, bereich: str, anzahl: int) -> dict:
        wer = None if self.n["rolle"] == "inhaber" else self.n["id"]
        liste = self.app.verlauf.liste(None if bereich == "alle" else bereich,
                                       anzahl=max(1, min(int(anzahl), 30)), nutzer=wer)
        return {"eintraege": [{k: e.get(k) for k in ("zeit", "titel", "kurz", "modell", "nutzer_name")} for e in liste]}

    def ausfuehren(self, name: str, eingabe: dict) -> tuple[str, bool]:
        f = getattr(self, name, None) if name in {w["name"] for w in WERKZEUGE} else None
        if f is None:
            return f"Unbekanntes Werkzeug: {name}", True
        try:
            return json.dumps(f(**eingabe), ensure_ascii=False, default=str), False
        except Grenze as exc:
            return f"Grenze: {exc}", True
        except (ValueError, FileNotFoundError, TypeError, RuntimeError) as exc:
            return f"Fehler: {exc}", True


def _oszillator(formel: str) -> bool:
    f = formel.replace(" ", "").lower()
    return f.startswith(("rsi(", "atr(", "stdev(", "change(")) or ("ema(" in f and "-ema(" in f)


class Speicher:
    """Die Gespräche eines Nutzers: was Claude sieht (api) und was die Seite zeigt (anzeige)."""

    def __init__(self, ordner: str | Path) -> None:
        self.ordner = Path(ordner)
        self._sperre = threading.Lock()

    def _pfad(self, nid: str) -> Path:
        return self.ordner / f"{nid}.json"

    def laden(self, nid: str) -> dict:
        p = self._pfad(nid)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"faeden": {}}

    def sichern(self, nid: str, d: dict) -> None:
        p = self._pfad(nid)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, p)

    def faden(self, d: dict, bereich: str) -> dict:
        return d["faeden"].setdefault(bereich, {"api": [], "anzeige": []})


class Chat:
    def __init__(self, app, ordner: str | Path, client: Any = None) -> None:
        self.app = app
        self.speicher = Speicher(ordner)
        self._client = client
        self._sperren: dict[str, threading.Lock] = {}

    # -- Einrichtung ------------------------------------------------------

    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    def bereit(self) -> tuple[bool, str]:
        if self._client is not None:
            return True, ""
        import importlib.util
        if importlib.util.find_spec("anthropic") is None:
            return False, "Für den Chat fehlt das Paket anthropic (pip install anthropic)."
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            return False, "Der Chat ist noch nicht eingerichtet: ANTHROPIC_API_KEY fehlt (in bot/.env eintragen)."
        return True, ""

    # -- Lesen ------------------------------------------------------------

    def verlauf(self, n: dict, bereich: str) -> list[dict]:
        return list(self.speicher.faden(self.speicher.laden(n["id"]), bereich)["anzeige"])

    def neu(self, n: dict, bereich: str) -> None:
        with self._sperre_fuer(n["id"]):
            d = self.speicher.laden(n["id"])
            d["faeden"].pop(bereich, None)
            self.speicher.sichern(n["id"], d)

    def alles(self, n: dict) -> dict:
        """Alle Gespräche eines Nutzers, wie die Seite sie zeigt (für den Datenexport)."""
        return {b: f["anzeige"] for b, f in self.speicher.laden(n["id"])["faeden"].items()}

    def vergessen(self, nid: str) -> None:
        p = self.speicher._pfad(nid)
        if p.exists():
            p.unlink()

    def bereinigen(self, tage: int) -> None:
        """Gesprächsfäden, die seit `tage` Tagen ruhen, löschen."""
        from datetime import timedelta
        grenze = (datetime.now(timezone.utc) - timedelta(days=tage)).isoformat(timespec="seconds")
        if not self.speicher.ordner.exists():
            return
        for p in self.speicher.ordner.glob("*.json"):
            d = json.loads(p.read_text(encoding="utf-8"))
            alt = [b for b, f in d["faeden"].items() if not f["anzeige"] or f["anzeige"][-1].get("zeit", "") < grenze]
            for b in alt:
                del d["faeden"][b]
            if alt:
                self.speicher.sichern(p.stem, d)

    def _sperre_fuer(self, nid: str) -> threading.Lock:
        return self._sperren.setdefault(nid, threading.Lock())

    # -- Schreiben --------------------------------------------------------

    def senden(self, n: dict, bereich: str, text: str) -> dict:
        text = (text or "").strip()
        if not text:
            raise ValueError("Die Nachricht ist leer.")
        if len(text) > 4000:
            raise ValueError("Die Nachricht ist zu lang (höchstens 4000 Zeichen).")
        if bereich not in BEREICHE:
            raise ValueError("Unbekannter Bereich.")
        ok, grund = self.bereit()
        if not ok:
            raise RuntimeError(grund)
        sperre = self._sperre_fuer(n["id"])
        if not sperre.acquire(blocking=False):
            raise RuntimeError("Die KI antwortet noch auf deine letzte Nachricht.")
        try:
            self.app.nutzung.chat_abbuchen(n)
            try:
                return self._senden(n, bereich, text)
            except Exception as exc:
                self.app.nutzung.chat_erstatten(n, type(exc).__name__)
                raise
        finally:
            sperre.release()

    def _senden(self, n: dict, bereich: str, text: str) -> dict:
        d = self.speicher.laden(n["id"])
        faden = self.speicher.faden(d, bereich)
        if len(faden["api"]) > MAX_VERLAUF:
            # Zu lang: neuer Faden statt Kürzen, damit nichts Halbes an Claude geht.
            faden["api"] = []
            faden["anzeige"].append({"rolle": "hinweis", "text": "Neuer Gesprächsfaden. Ältere Nachrichten kennt die KI nicht mehr.", "zeit": _jetzt()})

        # Der Name geht nicht an Anthropic: Claude braucht ihn nicht (Datensparsamkeit).
        kontext = f"[Seite: {BEREICHE[bereich]} · Abo: {abo_von(n)['name']}]"
        neu = [{"role": "user", "content": f"{kontext}\n{text}"}]
        werkzeuge = Werkzeuge(self.app, n)
        antwort_text: list[str] = []

        for _ in range(MAX_SCHRITTE):
            r = self._anfrage(faden["api"] + neu)
            inhalt = [b.to_dict() for b in r.content]
            neu.append({"role": "assistant", "content": inhalt})
            antwort_text += [b.text for b in r.content if b.type == "text" and b.text.strip()]
            if r.stop_reason == "refusal":
                antwort_text.append("Dazu kann ich nichts sagen.")
                break
            if r.stop_reason == "pause_turn":
                continue
            aufrufe = [b for b in r.content if b.type == "tool_use"]
            if r.stop_reason != "tool_use" or not aufrufe:
                if r.stop_reason == "max_tokens":
                    antwort_text.append("(Die Antwort wurde hier abgeschnitten.)")
                break
            ergebnisse = []
            for b in aufrufe:
                inhalt_text, fehler = werkzeuge.ausfuehren(b.name, dict(b.input))
                ergebnisse.append({"type": "tool_result", "tool_use_id": b.id,
                                   "content": inhalt_text, "is_error": fehler})
            neu.append({"role": "user", "content": ergebnisse})
        else:
            antwort_text.append("Ich habe für diese Frage zu viele Schritte gebraucht und höre hier auf.")
            if neu[-1]["role"] == "user":
                # Offene Werkzeug-Ergebnisse brauchen eine Antwort, sonst ist der Faden kaputt.
                neu.append({"role": "assistant", "content": [{"type": "text", "text": antwort_text[-1]}]})

        jetzt = _jetzt()
        faden["api"] += neu
        eintrag_nutzer = {"rolle": "nutzer", "text": text, "zeit": jetzt}
        eintrag_ki = {"rolle": "ki", "text": "\n\n".join(antwort_text) or "…", "zeit": _jetzt(),
                      "anhaenge": werkzeuge.anhaenge}
        faden["anzeige"] += [eintrag_nutzer, eintrag_ki]
        del faden["anzeige"][:-400]
        self.speicher.sichern(n["id"], d)
        return eintrag_ki

    def _anfrage(self, nachrichten: list[dict]):
        import anthropic
        try:
            return self.client().beta.messages.create(
                model=MODELL,
                max_tokens=16000,
                system=SYSTEM,
                tools=WERKZEUGE,
                messages=nachrichten,
                cache_control={"type": "ephemeral"},
                output_config={"effort": "medium"},
                # Lehnt das Modell aus Sicherheitsgründen ab, springt ein anderes ein.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.AuthenticationError:
            raise RuntimeError("Der API-Schlüssel für den Chat stimmt nicht.") from None
        except anthropic.RateLimitError:
            raise RuntimeError("Die KI ist gerade ausgelastet. Bitte gleich noch einmal.") from None
        except anthropic.APIConnectionError:
            raise RuntimeError("Keine Verbindung zur KI. Ist der Rechner online?") from None
        except anthropic.APIStatusError as exc:
            raise RuntimeError(f"Die KI hat einen Fehler gemeldet ({exc.status_code}).") from None
