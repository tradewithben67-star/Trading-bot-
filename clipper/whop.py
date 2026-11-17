#!/usr/bin/env python3
"""Whop-Auftraege: Kriterien rein, fertige Clips raus.

Liest die Bedingungen einer Clipping-Kampagne (Text und/oder Screenshots),
sucht oeffentliches Material der Person (YouTube, Twitch, Kick ...), geht jedes
Video bzw. jeden Stream anhand des Transkripts durch, waehlt die besten
Momente aus und schneidet sie genau nach den Vorgaben (Laenge, Format,
Anzahl). Dazu kommt ein fertiger Einreichungstext mit den Quell-Links.

Beispiele:
  python whop.py --kriterien auftrag.txt --bild s1.png --bild s2.png
  python whop.py --person "Shane Gillis" --anzahl 5
  python whop.py --person "Papaplatte" --quelle https://www.twitch.tv/papaplatte
  python whop.py --issue 12           (so laeuft es in GitHub Actions)

Mit ANTHROPIC_API_KEY liest Claude die Screenshots und sucht die Momente aus.
Ohne Schluessel arbeitet das Skript mit Regeln: Lacher im Transkript und die
"meistgesehen"-Kurve von YouTube.
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import mimetypes
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlparse

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))

MODELL = os.environ.get("WHOP_MODELL", "claude-opus-5-5")

STANDARD = {
    "person": "",
    "suchbegriffe": [],
    "quellen": [],
    "anzahl": 5,
    "min_sekunden": 30,
    "max_sekunden": 60,
    "format": "mp4",
    "hochformat": False,
    "untertitel": False,
    "sprache": "en",
    "regeln": [],
    "selbst_erledigen": [],
}


def log(*a) -> None:
    print(*a, flush=True)


# --------------------------------------------------------------------------
# Claude
# --------------------------------------------------------------------------

def claude_json(inhalt: list, schema: dict, system: str, effort: str = "medium") -> dict | None:
    """Ein Aufruf mit festem JSON-Schema. None, wenn kein Schluessel da ist oder es scheitert."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    import anthropic
    client = anthropic.Anthropic()
    try:
        with client.beta.messages.stream(
            model=MODELL,
            max_tokens=32000,
            system=system,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": effort,
                           "format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": inhalt}],
        ) as stream:
            antwort = stream.get_final_message()
    except anthropic.APIStatusError as e:
        log(f"  Claude-Fehler {e.status_code}: {e.message}")
        return None
    except anthropic.APIConnectionError as e:
        log(f"  Claude nicht erreichbar: {e}")
        return None
    if antwort.stop_reason in ("refusal", "max_tokens"):
        log(f"  Claude hat abgebrochen ({antwort.stop_reason})")
        return None
    text = next((b.text for b in antwort.content if b.type == "text"), "")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        log("  Claude-Antwort war kein JSON")
        return None


def _bild_block(pfad: Path) -> dict:
    art = mimetypes.guess_type(pfad.name)[0] or "image/png"
    if art not in ("image/png", "image/jpeg", "image/gif", "image/webp"):
        art = "image/png"
    daten = base64.standard_b64encode(pfad.read_bytes()).decode()
    return {"type": "image", "source": {"type": "base64", "media_type": art, "data": daten}}


# --------------------------------------------------------------------------
# 1. Kriterien lesen
# --------------------------------------------------------------------------

KRITERIEN_SCHEMA = {
    "type": "object",
    "properties": {
        "person": {"type": "string", "description": "Wer im Clip im Mittelpunkt stehen muss"},
        "suchbegriffe": {"type": "array", "items": {"type": "string"},
                         "description": "3-6 YouTube-Suchanfragen fuer passendes Material"},
        "quellen": {"type": "array", "items": {"type": "string"},
                    "description": "Konkret genannte Links (Kanal, Video, Stream), sonst leer"},
        "anzahl": {"type": "integer"},
        "min_sekunden": {"type": "integer"},
        "max_sekunden": {"type": "integer"},
        "format": {"type": "string", "enum": ["mp4", "mov", "webm"]},
        "hochformat": {"type": "boolean", "description": "Nur true, wenn 9:16/vertikal verlangt ist"},
        "untertitel": {"type": "boolean", "description": "Nur true, wenn Untertitel verlangt sind"},
        "sprache": {"type": "string", "description": "Sprache des Materials, ISO-Code wie en oder de"},
        "regeln": {"type": "array", "items": {"type": "string"},
                   "description": "Jede inhaltliche Bedingung an einen Clip, woertlich"},
        "selbst_erledigen": {"type": "array", "items": {"type": "string"},
                             "description": "Was der Mensch selbst tun muss, z.B. ein Nachweis-Stream"},
    },
    "required": list(STANDARD),
    "additionalProperties": False,
}


def kriterien_mit_claude(text: str, bilder: list[Path]) -> dict | None:
    inhalt = [_bild_block(b) for b in bilder]
    inhalt.append({"type": "text", "text":
                   "Hier ist eine Clipping-Kampagne (Text und/oder Screenshots). "
                   "Lies alle Bedingungen heraus.\n\n" + (text or "(nur Screenshots)")})
    return claude_json(inhalt, KRITERIEN_SCHEMA, effort="low", system=(
        "Du liest Ausschreibungen fuer Clipping-Kampagnen (z.B. auf Whop) und gibst die "
        "Bedingungen als JSON zurueck. Erfinde nichts: was nicht genannt ist, bekommt einen "
        "sinnvollen Standard (30-60 Sekunden, 5 Clips, mp4, kein Hochformat, keine Untertitel). "
        "Screenshots ohne Bedingungen (z.B. ein Upload-Dialog) ignorierst du."))


def kriterien_mit_regeln(text: str) -> dict:
    k = json.loads(json.dumps(STANDARD))
    m = re.search(r"(\d+)\s*(?:to|bis|-|–)\s*(\d+)\s*(?:s\b|sec|second|sek)", text, re.I)
    if m:
        k["min_sekunden"], k["max_sekunden"] = int(m[1]), int(m[2])
    m = re.search(r"(\d+)\s+(?:video\s*)?(?:clips|videos)", text, re.I)
    if m:
        k["anzahl"] = int(m[1])
    formate = [(text.lower().find(f), f) for f in ("mp4", "mov", "webm") if f in text.lower()]
    if formate:
        k["format"] = min(formate)[1]
    m = re.search(r"find\s+(.+?)\s+(?:footage|clips|videos)", text, re.I) or \
        re.search(r"(?:suche|finde)\s+(.+?)\s+(?:material|clips|videos)", text, re.I)
    if m:
        k["person"] = m[1].strip()
    k["hochformat"] = bool(re.search(r"9:16|vertical|vertikal|hochformat|tiktok|shorts|reels", text, re.I))
    k["untertitel"] = bool(re.search(r"subtitle|caption|untertitel", text, re.I))
    for zeile in text.splitlines():
        z = zeile.strip()
        if z[:1] in "•-*" and len(z) > 3:
            satz = z[1:].strip()
            if re.search(r"livestream|screen.?share|record", satz, re.I):
                k["selbst_erledigen"].append(satz)
            else:
                k["regeln"].append(satz)
    return k


def kriterien_lesen(text: str, bilder: list[Path]) -> dict:
    k = None
    if os.environ.get("ANTHROPIC_API_KEY"):
        log("Lese Kriterien mit Claude ...")
        k = kriterien_mit_claude(text, bilder)
    if k is None:
        if bilder and not text.strip():
            log("Hinweis: Screenshots kann nur Claude lesen (ANTHROPIC_API_KEY fehlt). "
                "Bitte den Text der Kampagne mit einfuegen.")
        k = kriterien_mit_regeln(text)
    for feld, wert in STANDARD.items():
        k.setdefault(feld, wert)
    k["min_sekunden"] = max(1, int(k["min_sekunden"]))
    k["max_sekunden"] = max(k["min_sekunden"] + 1, int(k["max_sekunden"]))
    k["anzahl"] = max(1, min(int(k["anzahl"]), 30))
    return k


# --------------------------------------------------------------------------
# 2. Quellen sammeln
# --------------------------------------------------------------------------

def ytdlp_opts(**extra) -> dict:
    o = {"quiet": True, "no_warnings": True, "noprogress": True}
    cookies = os.environ.get("YTDLP_COOKIES_DATEI")
    if cookies and Path(cookies).is_file() and Path(cookies).stat().st_size > 0:
        o["cookiefile"] = cookies
    o.update(extra)
    return o


def _eintrag(e: dict, quelle: str = "") -> dict | None:
    if not e:
        return None
    url = e.get("webpage_url") or e.get("url") or ""
    if e.get("ie_key") == "Youtube" or "youtube" in (e.get("extractor_key") or "").lower() or \
            (e.get("id") and not url.startswith("http")):
        url = f"https://www.youtube.com/watch?v={e['id']}"
    if not url.startswith("http"):
        return None
    return {"id": str(e.get("id") or url), "url": url, "titel": e.get("title") or "",
            "kanal": e.get("channel") or e.get("uploader") or "",
            "dauer": e.get("duration") or 0, "quelle": quelle}


def youtube_suchen(begriffe: list[str], pro_begriff: int = 8) -> list[dict]:
    import yt_dlp
    listen = []
    with yt_dlp.YoutubeDL(ytdlp_opts(extract_flat=True, skip_download=True)) as y:
        for q in begriffe:
            try:
                info = y.extract_info(f"ytsearch{pro_begriff}:{q}", download=False) or {}
            except Exception as e:
                log(f"  Suche '{q}' fehlgeschlagen: {e}")
                continue
            listen.append([x for x in (_eintrag(e, f"Suche: {q}") for e in info.get("entries") or []) if x])
    # Reihum mischen: erst der beste Treffer jeder Suche, dann der zweitbeste ...
    out = []
    for rang in range(pro_begriff):
        out += [liste[rang] for liste in listen if rang < len(liste)]
    return out


def link_aufloesen(url: str, max_videos: int) -> list[dict]:
    """Ein Link kann ein einzelnes Video/Stream sein oder ein ganzer Kanal."""
    import yt_dlp
    u = url.strip()
    kanal_yt = re.match(r"https?://(www\.)?youtube\.com/(@[^/?#]+|c/[^/?#]+|channel/[^/?#]+)/?$", u)
    kanal_tw = re.match(r"https?://(www\.)?twitch\.tv/([A-Za-z0-9_]+)/?$", u)
    if kanal_yt:
        u = u.rstrip("/") + "/streams"
    elif kanal_tw and kanal_tw[2] not in ("videos", "directory"):
        u = f"https://www.twitch.tv/{kanal_tw[2]}/videos?filter=archives&sort=time"
    with yt_dlp.YoutubeDL(ytdlp_opts(extract_flat="in_playlist", skip_download=True,
                                     playlistend=max_videos)) as y:
        try:
            info = y.extract_info(u, download=False) or {}
        except Exception as e:
            if kanal_yt:  # Kanal ohne Streams: normale Videos nehmen
                info = y.extract_info(u.rsplit("/", 1)[0] + "/videos", download=False) or {}
            else:
                log(f"  Link nicht lesbar: {url} ({e})")
                return []
    eintraege = info.get("entries")
    if kanal_yt and not eintraege and u.endswith("/streams"):
        return link_aufloesen(url.rstrip("/") + "/videos", max_videos)
    if eintraege is None:
        x = _eintrag(info, url)
        return [x] if x else []
    return [x for x in (_eintrag(e, url) for e in eintraege) if x][:max_videos]


def quellen_sammeln(k: dict, max_videos: int) -> list[dict]:
    kandidaten = []
    for link in k["quellen"]:
        log(f"Lese Link {link}")
        kandidaten += link_aufloesen(link, max_videos)
    if not k["quellen"]:
        begriffe = k["suchbegriffe"] or [f"{k['person']} {w}".strip()
                                         for w in ("stand up", "podcast", "interview", "")]
        log("Suche auf YouTube: " + " | ".join(begriffe))
        kandidaten += youtube_suchen(begriffe)
    gesehen, out = set(), []
    for c in kandidaten:
        if c["id"] in gesehen:
            continue
        gesehen.add(c["id"])
        # Fertige Kurzclips (Shorts) sind kein Quellmaterial
        if c["dauer"] and c["dauer"] < max(120, k["max_sekunden"] * 2):
            continue
        out.append(c)
    return out


# --------------------------------------------------------------------------
# 3. Transkript
# --------------------------------------------------------------------------

def _json3(daten: dict) -> list[tuple[float, float, str]]:
    zeilen = []
    for ev in daten.get("events", []):
        if "segs" not in ev:
            continue
        t = ev.get("tStartMs", 0) / 1000
        d = ev.get("dDurationMs", 0) / 1000
        text = "".join(s.get("utf8", "") for s in ev["segs"]).replace("\n", " ").strip()
        if text:
            zeilen.append((t, t + d, text))
    return zeilen


def _vtt(roh: str) -> list[tuple[float, float, str]]:
    def sek(z: str) -> float:
        teile = z.replace(",", ".").split(":")
        return sum(float(x) * 60 ** i for i, x in enumerate(reversed(teile)))
    zeilen, letzte = [], ""
    for block in re.split(r"\n\s*\n", roh):
        z = block.splitlines()
        i = next((n for n, l in enumerate(z) if "-->" in l), None)
        if i is None:
            continue
        m = re.search(r"([\d:.,]+)\s+-->\s+([\d:.,]+)", z[i])
        text = re.sub(r"<[^>]+>", "", " ".join(z[i + 1:])).strip()
        if m and text and text != letzte:
            zeilen.append((sek(m[1]), sek(m[2]), text))
            letzte = text
    return zeilen


def untertitel_holen(y, info: dict, sprache: str) -> list[tuple[float, float, str]]:
    for quelle in (info.get("subtitles") or {}, info.get("automatic_captions") or {}):
        sprachen = [s for s in quelle if s.split("-")[0] == sprache] or \
                   [s for s in quelle if s.endswith("-orig")] or \
                   [s for s in quelle if s.split("-")[0] == "en"]
        for s in sprachen:
            formate = {f.get("ext"): f.get("url") for f in quelle[s]}
            try:
                if formate.get("json3"):
                    zeilen = _json3(json.loads(y.urlopen(formate["json3"]).read()))
                elif formate.get("vtt"):
                    zeilen = _vtt(y.urlopen(formate["vtt"]).read().decode("utf-8", "replace"))
                else:
                    continue
            except Exception as e:
                log(f"  Untertitel {s} nicht ladbar: {e}")
                continue
            if zeilen:
                return zeilen
    return []


def per_whisper(url: str, sprache: str, max_dauer: float) -> list[tuple[float, float, str]]:
    """Kein Untertitel vorhanden (Twitch, Kick ...): Ton laden und selbst erkennen."""
    import yt_dlp
    from clipper import woerter_erkennen
    with tempfile.TemporaryDirectory() as tmp:
        opts = ytdlp_opts(format="bestaudio/worstaudio/worst", outtmpl=f"{tmp}/ton.%(ext)s")
        if max_dauer:
            from yt_dlp.utils import download_range_func
            opts["download_ranges"] = download_range_func(None, [(0, max_dauer)])
        with yt_dlp.YoutubeDL(opts) as y:
            info = y.extract_info(url, download=True)
            datei = Path(y.prepare_filename(info))
        if not datei.exists():
            datei = next(Path(tmp).glob("ton.*"))
        woerter = woerter_erkennen(datei, os.environ.get("WHOP_WHISPER", "base"), sprache)
    # Woerter zu Zeilen von ~6 Sekunden zusammenfassen
    zeilen, akt = [], []
    for w in woerter:
        if akt and w[1] - akt[0][0] > 6:
            zeilen.append((akt[0][0], akt[-1][1], " ".join(x[2] for x in akt)))
            akt = []
        akt.append(w)
    if akt:
        zeilen.append((akt[0][0], akt[-1][1], " ".join(x[2] for x in akt)))
    return zeilen


def video_lesen(c: dict, k: dict, max_stream_stunden: float) -> dict | None:
    """Holt Infos, Transkript und die 'meistgesehen'-Kurve eines Videos."""
    import yt_dlp
    with yt_dlp.YoutubeDL(ytdlp_opts(skip_download=True)) as y:
        try:
            info = y.extract_info(c["url"], download=False)
        except Exception as e:
            log(f"  nicht lesbar: {str(e)[:200]}")
            if "confirm you" in str(e) or "Sign in" in str(e):
                raise YoutubeSperre(str(e)) from e
            return None
        if info.get("is_live"):
            log("  laeuft gerade live, ueberspringe")
            return None
        zeilen = untertitel_holen(y, info, k["sprache"])
    dauer = info.get("duration") or 0
    if not zeilen:
        grenze = max_stream_stunden * 3600
        if os.environ.get("WHOP_OHNE_WHISPER"):
            log("  keine Untertitel")
        else:
            log(f"  keine Untertitel, erkenne Sprache selbst"
                f"{f' (erste {max_stream_stunden:g} h)' if dauer > grenze else ''} ...")
            try:
                zeilen = per_whisper(c["url"], k["sprache"], grenze if dauer > grenze else 0)
            except Exception as e:
                log(f"  Spracherkennung fehlgeschlagen: {e}")
    return {**c, "titel": info.get("title") or c["titel"],
            "kanal": info.get("channel") or info.get("uploader") or c["kanal"],
            "url": info.get("webpage_url") or c["url"], "dauer": dauer,
            "heatmap": info.get("heatmap") or [], "zeilen": zeilen,
            "youtube": (info.get("extractor_key") or "").lower().startswith("youtube")}


class YoutubeSperre(Exception):
    pass


# --------------------------------------------------------------------------
# 4. Momente finden
# --------------------------------------------------------------------------

MOMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "video_passt": {"type": "boolean",
                        "description": "Ist die Person wirklich in diesem Video und spricht selbst?"},
        "momente": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "start": {"type": "number", "description": "Sekunde, an der der Clip beginnt"},
                "ende": {"type": "number", "description": "Sekunde, an der der Clip endet"},
                "titel": {"type": "string", "description": "Kurzer TikTok-Hook in der Sprache des Videos, neugierig machend, z.B. \"bro bought a $3.5m car and can't fit in it\""},
                "warum": {"type": "string", "description": "Ein Satz, warum der Moment funktioniert"},
                "punkte": {"type": "integer", "description": "1-10, wie stark der Moment ist"},
            },
            "required": ["start", "ende", "titel", "warum", "punkte"],
            "additionalProperties": False,
        }},
    },
    "required": ["video_passt", "momente"],
    "additionalProperties": False,
}


def _mmss(s: float) -> str:
    s = int(max(0, s))
    h, r = divmod(s, 3600)
    return f"{h}:{r // 60:02d}:{r % 60:02d}" if h else f"{r // 60}:{r % 60:02d}"


def transkript_text(zeilen, max_zeichen: int = 600_000) -> str:
    """Zeilen zu Bloecken von ~8 s: '[754] text' (Sekunden als Zahl)."""
    out, start, akt, letzte = [], None, [], ""
    for a, _, t in zeilen:
        if t == letzte:
            continue
        letzte = t
        if start is None:
            start = a
        akt.append(t)
        if a - start >= 8:
            out.append(f"[{int(start)}] {' '.join(akt)}")
            start, akt = None, []
    if akt:
        out.append(f"[{int(start)}] {' '.join(akt)}")
    text = "\n".join(out)
    return text[:max_zeichen]


def heatmap_spitzen(heatmap: list, n: int = 8) -> list[tuple[float, float, float]]:
    beste = sorted(heatmap, key=lambda h: h.get("value", 0), reverse=True)[:n]
    return sorted((h["start_time"], h["end_time"], h.get("value", 0)) for h in beste)


def momente_mit_claude(v: dict, k: dict, wie_viele: int) -> list[dict] | None:
    spitzen = heatmap_spitzen(v["heatmap"])
    hinweis = ("Stellen, die Zuschauer besonders oft wiederholen (Sekunden): " +
               ", ".join(f"{int(a)}-{int(b)}" for a, b, _ in spitzen)) if spitzen else ""
    regeln = "\n".join(f"- {r}" for r in k["regeln"]) or "- lustig und fuer sich allein verstaendlich"
    text = (
        f"Person: {k['person'] or 'die Hauptperson des Videos'}\n"
        f"Video: {v['titel']} (Kanal: {v['kanal']}, Laenge {_mmss(v['dauer'])})\n"
        f"Clip-Laenge: {k['min_sekunden']} bis {k['max_sekunden']} Sekunden\n"
        f"Bedingungen der Kampagne:\n{regeln}\n\n{hinweis}\n\n"
        f"Finde die bis zu {wie_viele} besten Momente. Jeder Clip beginnt kurz vor dem "
        f"Aufbau (nicht mitten im Satz) und endet nach der Pointe und dem Lacher. "
        f"Die Person muss im Mittelpunkt stehen und selbst sprechen, nicht ein Gast. "
        f"Lieber weniger, dafuer starke Momente; ist nichts Gutes dabei, gib eine leere Liste.\n\n"
        f"Transkript (Zahl in Klammern = Sekunde):\n{transkript_text(v['zeilen'])}")
    r = claude_json([{"type": "text", "text": text}], MOMENT_SCHEMA, system=(
        "Du bist ein erfahrener Clipper fuer Kurzvideos. Du findest in Transkripten die "
        "Momente, die als eigenstaendiger Clip funktionieren, und haeltst dich exakt an die "
        "Bedingungen der Kampagne. Zeiten nimmst du aus dem Transkript, du erfindest keine."))
    if r is None:
        return None
    if not r.get("video_passt", True):
        log("  Person spielt in diesem Video keine Hauptrolle, ueberspringe")
        return []
    return r.get("momente") or []


LACHER = re.compile(r"\[(laughter|laughing|laughs|applause|cheering|lachen|gel[aä]chter|applaus)\]"
                    r"|\((laughs?|laughter|lacht)\)|\bha(ha)+\b", re.I)


def momente_mit_regeln(v: dict, k: dict, wie_viele: int) -> list[dict]:
    """Ohne Claude: Lacher im Transkript + Zuschauer-Kurve."""
    laenge = (k["min_sekunden"] + k["max_sekunden"]) / 2
    def kurve(t: float) -> float:
        for h in v["heatmap"]:
            if h["start_time"] <= t < h["end_time"]:
                return h.get("value", 0)
        return 0.0
    lacher = [a for a, _, t in v["zeilen"] if LACHER.search(t)]
    kandidaten = []
    for t in lacher:
        ende = t + 3
        start = ende - laenge
        n = sum(1 for x in lacher if start <= x <= ende)
        kandidaten.append((n + 3 * kurve(t), start, ende))
    if not kandidaten:
        for a, b, wert in heatmap_spitzen(v["heatmap"], wie_viele * 2):
            mitte = (a + b) / 2
            kandidaten.append((wert * 3, mitte - laenge / 2, mitte + laenge / 2))
    kandidaten.sort(reverse=True)
    out = []
    for wert, a, b in kandidaten:
        if any(a < m["ende"] and b > m["start"] for m in out):
            continue
        satz = " ".join(t for s, _, t in v["zeilen"] if a <= s <= b)
        satz = LACHER.sub("", satz).strip()
        out.append({"start": a, "ende": b, "titel": v["titel"] or " ".join(satz.split()[:8]),
                    "warum": "viele Lacher" if lacher else "oft wiederholte Stelle",
                    "punkte": min(10, 5 + int(wert))})
        if len(out) >= wie_viele:
            break
    return out


def zurechtruecken(m: dict, v: dict, k: dict) -> dict | None:
    """Laenge in die Vorgaben bringen und an Satzanfaenge legen."""
    start, ende = float(m["start"]), float(m["ende"])
    anfaenge = [a for a, _, _ in v["zeilen"] if start - 4 <= a <= start + 1]
    if anfaenge:
        start = min(anfaenge, key=lambda a: abs(a - start))
    dauer = ende - start
    ziel_min, ziel_max = k["min_sekunden"] + 1, k["max_sekunden"] - 1
    if dauer < ziel_min:
        fehlt = ziel_min - dauer
        start -= fehlt * 0.4
        ende += fehlt * 0.6
    elif dauer > ziel_max:
        ende = start + ziel_max
    if start < 0:
        ende -= start
        start = 0
    if v["dauer"] and ende > v["dauer"]:
        start -= ende - v["dauer"]
        ende = v["dauer"]
    if start < 0 or ende - start < k["min_sekunden"]:
        return None
    return {**m, "start": round(start, 2), "ende": round(ende, 2)}


def ueberlappt(a: dict, liste: list[dict]) -> bool:
    return any(x["id"] == a["id"] and a["start"] < x["ende"] and a["ende"] > x["start"] for x in liste)


def twitch_clips(k: dict, alte: list[dict]) -> list[dict]:
    """Bei Twitch-Kanaelen: die meistgesehenen Clips der letzten 7 Tage.
    Die Zuschauer haben die besten Momente damit schon markiert."""
    from clipper import clips_finden
    out = []
    for link in k["quellen"]:
        m = re.match(r"https?://(www\.)?twitch\.tv/([A-Za-z0-9_]+)/?$", link.strip())
        if not m or m[2] in ("videos", "directory"):
            continue
        try:
            clips = clips_finden(m[2], 24 * 7)
        except Exception as e:
            log(f"Twitch-Clips von {m[2]} nicht ladbar: {e}")
            continue
        clips = [c for c in clips if (c["dauer"] or 0) >= k["min_sekunden"] - 0.5]
        clips.sort(key=lambda c: -c["aufrufe"])
        log(f"Twitch {m[2]}: {len(clips)} Clips mit passender Laenge")
        for rang, c in enumerate(clips[: k["anzahl"] * 2]):
            moment = {"id": c["id"], "url": c["url"], "start": 0.0,
                      "ende": float(min(c["dauer"], k["max_sekunden"] - 0.5)),
                      "titel": c["titel"] or m[2], "warum": f"{c['aufrufe']} Aufrufe auf Twitch",
                      "punkte": 9 if rang < 3 else 8, "video": c["titel"], "kanal": m[2],
                      "youtube": False}
            if not ueberlappt(moment, alte):
                out.append(moment)
    return out


def momente_finden(kandidaten: list[dict], k: dict, benutzt: dict, max_pro_video: int,
                   max_videos: int, max_stream_stunden: float) -> list[dict]:
    gesucht = k["anzahl"]
    alte = [{"id": vid, "start": a, "ende": b} for vid, l in benutzt.items() for a, b in l]
    gefunden: list[dict] = twitch_clips(k, alte)
    geprueft = 0
    for c in kandidaten:
        if geprueft >= max_videos:
            break
        starke = [m for m in gefunden if m["punkte"] >= 7]
        if len(starke) >= gesucht * 2:
            break
        log(f"\n[{geprueft + 1}] {c['titel'] or c['url']}")
        v = video_lesen(c, k, max_stream_stunden)
        geprueft += 1
        if not v or (not v["zeilen"] and not v["heatmap"]):
            log("  kein Transkript, ueberspringe")
            continue
        momente = momente_mit_claude(v, k, max_pro_video + 1)
        if momente is None:
            momente = momente_mit_regeln(v, k, max_pro_video + 1)
        for m in sorted(momente, key=lambda m: -m["punkte"]):
            m = zurechtruecken(m, v, k)
            if not m:
                continue
            m.update(id=v["id"], url=v["url"], video=v["titel"], kanal=v["kanal"],
                     youtube=v["youtube"])
            if ueberlappt(m, gefunden) or ueberlappt(m, alte):
                continue
            gefunden.append(m)
            log(f"  {m['punkte']:>2}/10  {_mmss(m['start'])}-{_mmss(m['ende'])}  {m['titel']}")
    # Beste zuerst, hoechstens max_pro_video aus demselben Video
    gefunden.sort(key=lambda m: -m["punkte"])
    auswahl, je_video = [], {}
    for m in gefunden:
        if je_video.get(m["id"], 0) >= max_pro_video:
            continue
        je_video[m["id"]] = je_video.get(m["id"], 0) + 1
        auswahl.append(m)
    return auswahl


# --------------------------------------------------------------------------
# 5. Schneiden
# --------------------------------------------------------------------------

def abschnitt_laden(url: str, start: float, ende: float, ziel: Path) -> Path:
    """Laedt nur den Ausschnitt. Geht das bei einer Quelle nicht, wird ganz geladen
    und selbst geschnitten."""
    import yt_dlp
    from yt_dlp.utils import download_range_func
    basis = dict(
        format="bv*[height<=1080][ext=mp4]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]/b",
        merge_output_format="mp4")

    def laden(name: str, **extra) -> Path:
        with yt_dlp.YoutubeDL(ytdlp_opts(**basis, outtmpl=str(ziel.parent / name) + ".%(ext)s",
                                         **extra)) as y:
            y.extract_info(url, download=True)
        treffer = sorted(p for p in ziel.parent.glob(name + ".*") if not p.name.endswith(".part"))
        if not treffer:
            raise RuntimeError("Download lieferte keine Datei")
        return treffer[0]

    try:
        return laden(ziel.name, download_ranges=download_range_func(None, [(start, ende)]),
                     force_keyframes_at_cuts=True)
    except Exception as e:
        if "partially" not in str(e):
            raise
    log("  Quelle erlaubt keinen Teil-Download, lade ganz und schneide selbst")
    ganz = laden(ziel.name + "_ganz")
    aus = ziel.with_suffix(".mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.2f}", "-i", str(ganz),
                    "-t", f"{ende - start:.2f}", "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "18", "-c:a", "aac", "-b:a", "192k", str(aus)], check=True)
    ganz.unlink(missing_ok=True)
    return aus


def dauer_von(datei: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(datei)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def groesse(datei: Path) -> tuple[int, int]:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height", "-of", "csv=p=0", str(datei)],
                       capture_output=True, text=True)
    try:
        w, h = r.stdout.strip().split(",")[:2]
        return int(w), int(h)
    except ValueError:
        return 0, 0


def exportieren(quelle: Path, ziel: Path, fmt: str, max_dauer: float) -> None:
    if fmt == "webm":
        codec = ["-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", "-row-mt", "1",
                 "-deadline", "good", "-cpu-used", "4", "-c:a", "libopus", "-b:a", "128k"]
    else:
        codec = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                 "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart"]
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(quelle), "-t", f"{max_dauer:.2f}",
                    "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-map", "0:v:0", "-map", "0:a:0?",
                    *codec, str(ziel)], check=True)


def _dateiname(text: str) -> str:
    t = re.sub(r"[^A-Za-z0-9äöüÄÖÜß]+", "-", text).strip("-")
    return t[:40].strip("-") or "clip"


def clips_schneiden(momente: list[dict], k: dict, ausgabe: Path) -> list[dict]:
    """Ein Eintrag pro Moment. Mit k["beide_varianten"] gibt es jeden Clip zweimal:
    mit und ohne eingebrannte Untertitel (beide im Hochformat)."""
    fertig = []
    fmt = k["format"]
    if k.get("beide_varianten"):
        varianten = [("_mit_untertitel", True), ("_ohne_untertitel", False)]
        hoch_noetig = True
    else:
        varianten = [("", k["untertitel"])]
        hoch_noetig = k["hochformat"]
    for m in momente:
        if len(fertig) >= k["anzahl"]:
            break
        nr = len(fertig) + 1
        basis = f"clip_{nr:02d}_{_dateiname(m['titel'])}"
        log(f"\nSchneide {basis}  ({_mmss(m['start'])}-{_mmss(m['ende'])} aus {m['url']})")
        dateien = []
        try:
            with tempfile.TemporaryDirectory() as tmp:
                roh = abschnitt_laden(m["url"], m["start"], m["ende"], Path(tmp) / "roh")
                for zusatz, untertitel in varianten:
                    name = f"{basis}{zusatz}.{fmt}"
                    quelle = roh
                    if hoch_noetig:
                        from clipper import hochformat
                        quelle = Path(tmp) / f"hoch{zusatz}.mp4"
                        cfg = {"untertitel": untertitel, "sprache": k["sprache"],
                               "whisper_modell": os.environ.get("WHOP_WHISPER", "small")}
                        kanal = m["kanal"] if "twitch.tv" in m["url"] else \
                            f"{'YouTube' if m['youtube'] else 'Quelle'}: {m['kanal'] or k['person']}"
                        hochformat(roh, quelle, m["titel"], kanal, cfg, k["max_sekunden"])
                    exportieren(quelle, ausgabe / name, fmt, k["max_sekunden"])
                    dateien.append((name, untertitel))
        except Exception as e:
            log(f"  Fehler: {str(e)[:300]}")
            for name, _ in dateien:
                (ausgabe / name).unlink(missing_ok=True)
            continue
        d = dauer_von(ausgabe / dateien[0][0])
        if d < k["min_sekunden"] - 0.5:
            log(f"  nur {d:.1f} s lang, verworfen")
            for name, _ in dateien:
                (ausgabe / name).unlink(missing_ok=True)
            continue
        w, h = groesse(ausgabe / dateien[0][0])
        link = m["url"]
        if m["youtube"]:
            link = re.sub(r"[&?]t=\d+s?", "", link)
            link += ("&" if "?" in link else "?") + f"t={int(m['start'])}s"
        fertig.append({**m, "nr": nr, "datei": dateien[0][0], "varianten": dateien,
                       "dauer_clip": round(d, 1), "link": link, "breite": w, "hoehe": h})
        log(f"  fertig: {d:.1f} s, {w}x{h}, {len(dateien)} Datei(en)")
    return fertig


def beschreibung(c: dict, k: dict) -> str:
    """Fertige TikTok-Beschreibung: Hook, Credit, Hashtags."""
    tags = k.get("hashtags") or ""
    if not tags:
        name = re.sub(r"[^a-z0-9]", "", (k["person"] or c["kanal"] or "").lower())
        tags = " ".join(t for t in (f"#{name}" if name else "", "#fyp", "#viral", "#funny") if t)
    credit = k.get("credit") or c["kanal"] or k["person"]
    return f"{c['titel']} 💀\n\n🎥 Credit: {credit}\n\n{tags}"


# --------------------------------------------------------------------------
# 6. Einreichung
# --------------------------------------------------------------------------

def einreichung_schreiben(clips: list[dict], k: dict, ausgabe: Path) -> str:
    kopf = (f"{len(clips)} von {k['anzahl']} Clips · {k['person'] or 'Clips'} · "
            f"{k['min_sekunden']}–{k['max_sekunden']} s · {k['format'].upper()}"
            f"{' · 9:16' if k['hochformat'] else ''}")
    links = "\n".join(c["link"] for c in clips)
    notizen = "\n\n".join(
        f"Clip {c['nr']} – {c['datei']} ({c['dauer_clip']:.0f}s): {c['titel']}\n"
        f"Source: {c['link']} ({_mmss(c['start'])}–{_mmss(c['ende'])}, \"{c['video']}\")"
        for c in clips)
    selbst = "\n".join(f"- {s}" for s in k["selbst_erledigen"]) or "- nichts"
    text = (f"{kopf}\n\n"
            f"=== LINKS (je einen ins Feld „Links“, weitere über „Weiteren Link hinzufügen“) ===\n"
            f"{links}\n\n"
            f"=== HINWEISE FÜR PRÜFER (ins Textfeld kopieren) ===\n{notizen}\n\n"
            f"=== MUSST DU SELBST MACHEN ===\n{selbst}\n")
    (ausgabe / "einreichung.txt").write_text(text, encoding="utf-8")
    # Pro Datei eine Beschreibung (fuer Telegram) und die Liste
    liste = []
    for c in clips:
        text_tiktok = beschreibung(c, k)
        for i, (name, untertitel) in enumerate(c.get("varianten") or [(c["datei"], None)]):
            if untertitel is None:
                text = text_tiktok
            elif i == 0:
                text = f"{text_tiktok}\n\n(Clip {c['nr']} · {'mit' if untertitel else 'ohne'} Untertitel)"
            else:
                text = (f"⬆️ Clip {c['nr']} {'mit' if untertitel else 'ohne'} Untertitel – "
                        f"Beschreibung steht beim Video darüber")
            (ausgabe / name).with_suffix(".txt").write_text(text, encoding="utf-8")
            liste.append({"datei": name, "titel": c["titel"], "url": c["link"],
                          "breite": c["breite"], "hoehe": c["hoehe"], "punkte": c["punkte"],
                          "warum": c["warum"]})
    (ausgabe / "liste.json").write_text(json.dumps(liste, indent=1, ensure_ascii=False),
                                        encoding="utf-8")
    with zipfile.ZipFile(ausgabe / "alle_clips.zip", "w", zipfile.ZIP_STORED) as z:
        for eintrag in liste:
            z.write(ausgabe / eintrag["datei"], eintrag["datei"])
        z.write(ausgabe / "einreichung.txt", "einreichung.txt")
    return text


# --------------------------------------------------------------------------
# GitHub-Issue als Eingabe
# --------------------------------------------------------------------------

def _formular(body: str) -> dict[str, str]:
    felder, name = {}, None
    for zeile in body.splitlines():
        m = re.match(r"^###\s+(.+?)\s*$", zeile)
        if m:
            name = m[1].lower()
            felder[name] = ""
        elif name:
            felder[name] += zeile + "\n"
    return {n: ("" if v.strip() == "_No response_" else v.strip()) for n, v in felder.items()}


def _feld(felder: dict, *woerter: str) -> str:
    for name, wert in felder.items():
        if any(w in name for w in woerter):
            return wert
    return ""


def issue_laden(nr: int, ordner: Path) -> tuple[str, list[Path], dict]:
    import requests
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
    kopf = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.full+json"}
    j = requests.get(f"https://api.github.com/repos/{repo}/issues/{nr}", headers=kopf, timeout=30).json()
    body, body_html = j.get("body") or "", j.get("body_html") or ""
    # Bilder: im HTML stehen (auch bei privaten Repos) direkt ladbare Adressen
    urls = [html.unescape(u) for u in re.findall(r'<img[^>]+src="([^"]+)"', body_html)]
    urls += re.findall(r"!\[[^\]]*\]\((https://[^)\s]+)\)", body)
    urls += re.findall(r'src="(https://github\.com/user-attachments/[^"]+)"', body)
    bilder, gesehen = [], set()
    ordner.mkdir(parents=True, exist_ok=True)
    for u in urls:
        if u in gesehen:
            continue
        gesehen.add(u)
        h = {"Authorization": f"Bearer {token}"} if urlparse(u).hostname == "github.com" else {}
        try:
            r = requests.get(u, headers=h, timeout=60)
        except Exception:
            continue
        art = r.headers.get("content-type", "")
        if r.ok and art.startswith("image/"):
            p = ordner / f"bild_{len(bilder) + 1}{mimetypes.guess_extension(art.split(';')[0]) or '.png'}"
            p.write_bytes(r.content)
            bilder.append(p)
    felder = _formular(body)
    text = _feld(felder, "kriterien", "bedingung") or body
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)|<img[^>]*>", "", text).strip()
    extra = {"person": _feld(felder, "person"),
             "anzahl": _feld(felder, "anzahl"),
             "quellen": re.findall(r"https?://\S+", _feld(felder, "bestimmte", "quelle", "link"))}
    log(f"Issue #{nr}: {len(text)} Zeichen Text, {len(bilder)} Bild(er)")
    return text, bilder, extra


# --------------------------------------------------------------------------
# Hauptprogramm
# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Whop-Auftrag: Kriterien rein, Clips raus.")
    ap.add_argument("--kriterien", type=Path, help="Textdatei mit dem Auftragstext")
    ap.add_argument("--text", default="", help="Auftragstext direkt")
    ap.add_argument("--bild", type=Path, action="append", default=[], help="Screenshot (mehrfach)")
    ap.add_argument("--issue", type=int, help="GitHub-Issue als Auftrag lesen")
    ap.add_argument("--person", default="", help="Streamer/Person (ueberschreibt die Kriterien)")
    ap.add_argument("--anzahl", type=int, help="Anzahl Clips (ueberschreibt die Kriterien)")
    ap.add_argument("--quelle", action="append", default=[],
                    help="Kanal-, Stream- oder Video-Link (mehrfach). Ohne: YouTube-Suche")
    ap.add_argument("--beide-varianten", action="store_true",
                    help="jeden Clip zweimal: mit und ohne Untertitel (Hochformat)")
    ap.add_argument("--hashtags", default="", help='z.B. "#tjr #trading #fyp"')
    ap.add_argument("--credit", default="", help='z.B. "@TJRTrades"')
    ap.add_argument("--auftrag-json", type=Path, help="alle Angaben als JSON-Datei")
    ap.add_argument("--ausgabe", type=Path, default=HIER / "whop_ausgabe")
    ap.add_argument("--benutzt", type=Path, default=HIER / "state" / "whop_benutzt.json",
                    help="merkt sich verwendete Stellen, damit kein Clip doppelt eingereicht wird")
    ap.add_argument("--max-videos", type=int, default=int(os.environ.get("WHOP_MAX_VIDEOS", 12)))
    ap.add_argument("--max-pro-video", type=int, default=2)
    ap.add_argument("--max-stream-stunden", type=float, default=3.0,
                    help="bei Streams ohne Untertitel nur so viel vom Anfang anhoeren")
    a = ap.parse_args()

    if a.auftrag_json:
        j = json.loads(a.auftrag_json.read_text(encoding="utf-8"))
        a.text = a.text or j.get("text", "")
        a.person = a.person or j.get("person", "")
        a.anzahl = a.anzahl or j.get("anzahl")
        a.quelle = a.quelle or j.get("quellen", [])
        a.beide_varianten = a.beide_varianten or j.get("beide_varianten", False)
        a.hashtags = a.hashtags or j.get("hashtags", "")
        a.credit = a.credit or j.get("credit", "")
    text, bilder, extra = a.text, list(a.bild), {}
    if a.kriterien:
        text += "\n" + a.kriterien.read_text(encoding="utf-8")
    if a.issue:
        t, b, extra = issue_laden(a.issue, a.ausgabe / "_eingang")
        text, bilder = text + "\n" + t, bilder + b

    k = kriterien_lesen(text, bilder)
    if a.person or extra.get("person"):
        k["person"] = a.person or extra["person"]
    if a.anzahl or (extra.get("anzahl") or "").strip().isdigit():
        k["anzahl"] = a.anzahl or int(extra["anzahl"].strip())
    if a.quelle or extra.get("quellen"):
        k["quellen"] = a.quelle or extra["quellen"]
    k["beide_varianten"] = a.beide_varianten
    k["hashtags"], k["credit"] = a.hashtags, a.credit
    if a.beide_varianten:
        k["hochformat"] = True
    log("\nKriterien:\n" + json.dumps(k, indent=1, ensure_ascii=False))

    a.ausgabe.mkdir(parents=True, exist_ok=True)
    kommentar = a.ausgabe / "kommentar.md"
    if not k["person"] and not k["quellen"]:
        kommentar.write_text("❌ Ich weiß nicht, von wem die Clips sein sollen. Trag im Feld "
                             "„Streamer / Person“ einen Namen ein oder füge einen Kanal-Link ein.",
                             encoding="utf-8")
        log("Keine Person und keine Quelle gefunden.")
        return 1

    benutzt = json.loads(a.benutzt.read_text()) if a.benutzt.exists() else {}
    try:
        kandidaten = quellen_sammeln(k, a.max_videos)
        log(f"\n{len(kandidaten)} moegliche Videos/Streams")
        momente = momente_finden(kandidaten, k, benutzt, a.max_pro_video, a.max_videos,
                                 a.max_stream_stunden)
        clips = clips_schneiden(momente, k, a.ausgabe)
    except YoutubeSperre:
        kommentar.write_text(
            "❌ YouTube blockiert gerade die GitHub-Server („Sign in to confirm you're not a bot“).\n\n"
            "Abhilfe: einmal YouTube-Cookies als Secret `YOUTUBE_COOKIES` hinterlegen "
            "(Anleitung in `clipper/WHOP.md`), oder einen Twitch-/Kick-Kanal als Quelle angeben.",
            encoding="utf-8")
        return 1

    for c in clips:
        benutzt.setdefault(c["id"], []).append([c["start"], c["ende"]])
    a.benutzt.parent.mkdir(parents=True, exist_ok=True)
    a.benutzt.write_text(json.dumps(benutzt, indent=1))

    if not clips:
        kommentar.write_text("❌ Keine passenden Momente gefunden. Gib im Feld „Bestimmte Streams "
                             "oder Videos“ einen Kanal- oder Video-Link an und starte neu.",
                             encoding="utf-8")
        return 1
    text = einreichung_schreiben(clips, k, a.ausgabe)
    log("\n" + text)
    kommentar.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
