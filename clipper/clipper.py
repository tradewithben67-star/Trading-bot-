#!/usr/bin/env python3
"""Clip-Fabrik: holt die besten neuen Twitch-Clips, schneidet sie ins
TikTok-Hochformat, brennt Untertitel ein und legt Video + Beschreibung ab.

Ablauf pro Streamer:
  1. Top-Clips der letzten 24 Stunden holen (nach Aufrufen sortiert).
     Die Zuschauer haben die besten Momente damit schon ausgesucht.
  2. Schon verarbeitete Clips ueberspringen (state-Datei).
  3. Clip laden, auf 1080x1920 bringen: unscharfer Hintergrund,
     Spielbild in der Mitte, Titel oben, Untertitel unten.
  4. MP4 + fertige TikTok-Beschreibung nach ausgabe/ schreiben.

Ohne Twitch-Schluessel liest das Skript die oeffentliche Clip-Liste
ueber yt-dlp. Sind TWITCH_CLIENT_ID und TWITCH_CLIENT_SECRET gesetzt,
nimmt es die offizielle Twitch-API.

Testen ohne Twitch:  python clipper.py --lokal video.mp4 --titel "Test"
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout  # noqa: E402

HIER = Path(__file__).resolve().parent
BREITE, HOEHE = 1080, 1920


# --------------------------------------------------------------------------
# Clips finden
# --------------------------------------------------------------------------

def _json_holen(url: str, headers: dict | None = None, data: bytes | None = None) -> dict:
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def _grenze(stunden: float) -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=stunden)


def clips_helix(login: str, stunden: float) -> list[dict]:
    cid, secret = os.environ["TWITCH_CLIENT_ID"], os.environ["TWITCH_CLIENT_SECRET"]
    token = _json_holen(
        "https://id.twitch.tv/oauth2/token",
        data=urllib.parse.urlencode({
            "client_id": cid, "client_secret": secret,
            "grant_type": "client_credentials"}).encode(),
    )["access_token"]
    h = {"Client-Id": cid, "Authorization": f"Bearer {token}"}
    users = _json_holen(f"https://api.twitch.tv/helix/users?login={login}", h)["data"]
    if not users:
        return []
    q = urllib.parse.urlencode({
        "broadcaster_id": users[0]["id"], "first": 100,
        "started_at": _grenze(stunden).strftime("%Y-%m-%dT%H:%M:%SZ")})
    data = _json_holen(f"https://api.twitch.tv/helix/clips?{q}", h)["data"]
    return [{"id": c["id"], "url": c["url"], "titel": c["title"],
             "aufrufe": c["view_count"], "dauer": c["duration"]} for c in data]


def clips_ytdlp(login: str, stunden: float) -> list[dict]:
    """Oeffentliche Clip-Liste (nach Aufrufen sortiert), danach auf das Alter gefiltert."""
    import yt_dlp
    bereich = "24hr" if stunden <= 24 else "7d" if stunden <= 168 else "30d"
    url = f"https://www.twitch.tv/{login}/clips?filter=clips&range={bereich}"
    opts = {"quiet": True, "extract_flat": True, "playlistend": 100, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as y:
        info = y.extract_info(url, download=False) or {}
    grenze = _grenze(stunden).timestamp()
    out = []
    for e in info.get("entries") or []:
        if not e or not e.get("url"):
            continue
        if e.get("timestamp") and e["timestamp"] < grenze:
            continue
        out.append({"id": str(e.get("id") or e["url"].rstrip("/").split("/")[-1]),
                    "url": e["url"], "titel": e.get("title") or "",
                    "aufrufe": e.get("view_count") or 0,
                    "dauer": e.get("duration") or 0})
    return out


def clips_finden(login: str, stunden: float) -> list[dict]:
    if os.environ.get("TWITCH_CLIENT_ID") and os.environ.get("TWITCH_CLIENT_SECRET"):
        try:
            return clips_helix(login, stunden)
        except Exception as e:  # faellt auf yt-dlp zurueck
            print(f"  Twitch-API fehlgeschlagen ({e}), nehme yt-dlp", flush=True)
    return clips_ytdlp(login, stunden)


def clip_laden(url: str, ziel: Path) -> Path:
    import yt_dlp
    opts = {"quiet": True, "outtmpl": str(ziel.with_suffix(".%(ext)s")),
            "format": "best[ext=mp4]/best", "noprogress": True}
    with yt_dlp.YoutubeDL(opts) as y:
        info = y.extract_info(url, download=True)
        return Path(y.prepare_filename(info))


# --------------------------------------------------------------------------
# Untertitel
# --------------------------------------------------------------------------

_modell = None


def woerter_erkennen(video: Path, modell: str, sprache: str) -> list[tuple[float, float, str]]:
    global _modell
    from faster_whisper import WhisperModel
    import numpy as np
    if _modell is None:
        _modell = WhisperModel(modell, device="cpu", compute_type="int8")
    # Ton selbst mit ffmpeg dekodieren (16 kHz mono): umgeht PyAV-Versionsprobleme
    roh = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vn", "-ac", "1",
                          "-ar", "16000", "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    audio = np.frombuffer(roh, dtype=np.float32)
    segmente, _ = _modell.transcribe(audio, language=sprache,
                                     word_timestamps=True, vad_filter=True)
    woerter = []
    for s in segmente:
        for w in s.words or []:
            t = w.word.strip()
            if t:
                woerter.append((w.start, w.end, t))
    return woerter


def in_happen(woerter, max_woerter=3, max_luecke=0.6):
    happen, akt = [], []
    for w in woerter:
        if akt and (len(akt) >= max_woerter or w[0] - akt[-1][1] > max_luecke
                    or re.search(r"[.!?]$", akt[-1][2])):
            happen.append(akt)
            akt = []
        akt.append(w)
    if akt:
        happen.append(akt)
    return [(h[0][0], max(h[-1][1], h[0][0] + 0.25), " ".join(x[2] for x in h)) for h in happen]


def _ass_zeit(s: float) -> str:
    s = max(0.0, s)
    h, rest = divmod(s, 3600)
    m, sek = divmod(rest, 60)
    return f"{int(h)}:{int(m):02d}:{sek:05.2f}"


def _ass_text(t: str) -> str:
    return t.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", " ").strip()


def _ohne_emoji(text: str) -> str:
    """Die Schrift im Video kann keine Emojis (sie erscheinen als Kaestchen)."""
    text = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]", "", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def _kanal_text(kanal: str) -> str:
    """Twitch-Login -> twitch.tv/login; alles andere (z.B. YouTube-Kanalname) bleibt, wie es ist."""
    return kanal if re.search(r"[^A-Za-z0-9_]", kanal) else f"twitch.tv/{kanal}"


def ass_schreiben(pfad: Path, dauer: float, titel: str, kanal: str, happen, lay) -> None:
    sub_ausr, sub_rand = (5, 0) if lay.sub_mitte else (8, lay.sub_y)
    kopf = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {BREITE}
PlayResY: {HOEHE}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Titel,DejaVu Sans,{lay.titel_groesse},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,2,2,60,60,{HOEHE - lay.titel_unten},1
Style: Kanal,DejaVu Sans,44,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,4,1,8,40,40,{lay.kanal_oben},1
Style: Sub,DejaVu Sans,86,&H0000F0FF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,7,3,{sub_ausr},50,50,{sub_rand},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ende = _ass_zeit(dauer + 1)
    zeilen = [f"Dialogue: 1,0:00:00.00,{ende},Titel,,0,0,0,,{_ass_text(_ohne_emoji(titel))}",
              f"Dialogue: 1,0:00:00.00,{ende},Kanal,,0,0,0,,{_ass_text(_kanal_text(kanal))}"]
    pos = rf"\pos({BREITE // 2},{lay.sub_y})" if lay.sub_mitte else ""
    for start, stop, text in happen:
        pop = r"{\fscx80\fscy80\t(0,90,\fscx105\fscy105)\t(90,160,\fscx100\fscy100)" + pos + "}"
        zeilen.append(f"Dialogue: 2,{_ass_zeit(start)},{_ass_zeit(stop)},Sub,,0,0,0,,"
                      f"{pop}{_ass_text(text).upper()}")
    pfad.write_text(kopf + "\n".join(zeilen) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------
# Schnitt
# --------------------------------------------------------------------------

def dauer_von(video: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(video)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip() or 0)


def filter_bauen(lay) -> str:
    n = len(lay.felder)
    teile = [f"[0:v]split={n + 1}[hg]" + "".join(f"[q{i}]" for i in range(n)),
             f"[hg]scale={BREITE}:{HOEHE}:force_original_aspect_ratio=increase,"
             f"crop={BREITE}:{HOEHE},boxblur=30:2,eq=brightness=-0.15[s0]"]
    for i, f in enumerate(lay.felder):
        teile.append(f"[q{i}]crop={f.w}:{f.h}:{f.x}:{f.y},scale={f.ow}:{f.oh},setsar=1[f{i}]")
        teile.append(f"[s{i}][f{i}]overlay={f.ox}:{f.oy}[s{i + 1}]")
    teile.append(f"[s{n}]ass=text.ass,fps=30[v]")
    return ";".join(teile)


def hochformat(quelle: Path, ziel: Path, titel: str, kanal: str, cfg: dict,
               max_sek: float, feste_cam=None) -> str:
    dauer = min(dauer_von(quelle), max_sek)
    lay = layout.waehlen(quelle, feste_cam)
    print(f"  Layout: {lay.art}", flush=True)
    happen = []
    if cfg.get("untertitel", True):
        try:
            happen = in_happen(woerter_erkennen(quelle, cfg.get("whisper_modell", "small"),
                                                cfg.get("sprache", "de")))
        except Exception as e:
            print(f"  Untertitel uebersprungen: {e}", flush=True)
    with tempfile.TemporaryDirectory() as tmp:
        ass_schreiben(Path(tmp) / "text.ass", dauer, titel, kanal, happen, lay)
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(quelle.resolve()),
               "-t", f"{dauer:.2f}", "-filter_complex", filter_bauen(lay),
               "-map", "[v]", "-map", "0:a?",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
               "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
               "-movflags", "+faststart", str(ziel.resolve())]
        subprocess.run(cmd, check=True, cwd=tmp)
    return lay.art


def vorschau_speichern(quelle: Path, ziel: Path) -> None:
    """Ein Originalbild aus der Clip-Mitte, um Cam-Positionen einzumessen."""
    try:
        ziel.parent.mkdir(parents=True, exist_ok=True)
        mitte = dauer_von(quelle) / 2
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{mitte:.2f}", "-i", str(quelle),
                        "-frames:v", "1", "-q:v", "3", str(ziel)], check=True)
    except Exception as e:
        print(f"  Vorschau fehlgeschlagen: {e}", flush=True)


def beschreibung(clip: dict, s: dict, cfg: dict) -> str:
    tags = cfg.get("hashtags_pro_streamer", {}).get(s["twitch"], []) + cfg.get("hashtags", [])
    titel = clip["titel"].strip() or f"{s['name']} eskaliert"
    return f"{titel} 😂\n\n🎥 Credit: twitch.tv/{s['twitch']}\n\n{' '.join(tags)}"


# --------------------------------------------------------------------------
# Hauptprogramm
# --------------------------------------------------------------------------

def _sicher(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", name)[:60].strip("-") or "clip"


def lauf(cfg: dict, state_pfad: Path, ausgabe: Path, alles_neu: bool = False) -> int:
    ausgabe.mkdir(parents=True, exist_ok=True)
    gesehen: dict = json.loads(state_pfad.read_text()) if state_pfad.exists() else {}
    grenze = (dt.date.today() - dt.timedelta(days=21)).isoformat()
    gesehen = {k: v for k, v in gesehen.items() if v >= grenze}
    heute = dt.date.today().isoformat()
    fertig = []

    # 1. Clip-Listen aller Streamer holen (schnell, nur Text)
    kandidaten = []
    for s in cfg["streamer"]:
        try:
            clips = clips_finden(s["twitch"], cfg.get("max_alter_stunden", 24))
        except Exception as e:
            print(f"== {s['name']}: Clip-Liste nicht ladbar: {e}", flush=True)
            continue
        clips = [c for c in clips if (alles_neu or c["id"] not in gesehen)
                 and c["aufrufe"] >= cfg.get("mindest_aufrufe", 0)]
        clips.sort(key=lambda c: c["aufrufe"], reverse=True)
        clips = clips[: cfg.get("clips_pro_streamer", 2)]
        print(f"== {s['name']} ({s['twitch']}): {len(clips)} neue Clips", flush=True)
        kandidaten += [(rang, s, c) for rang, c in enumerate(clips)]

    # 2. Reihum verteilen (erst der beste Clip jedes Streamers, dann der zweitbeste, ...)
    #    und auf max_clips_pro_lauf begrenzen, damit ein Lauf nicht zu lange dauert.
    kandidaten.sort(key=lambda k: (k[0], -k[2]["aufrufe"]))
    kandidaten = kandidaten[: cfg.get("max_clips_pro_lauf", 25)]
    print(f"\nSchneide {len(kandidaten)} Clips\n", flush=True)

    # 3. Schneiden
    for _, s, c in kandidaten:
        print(f"  {s['name']:<12} {c['aufrufe']:>7} Aufrufe  {c['titel']}", flush=True)
        name = f"{s['twitch']}_{_sicher(c['id'])}"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                roh = clip_laden(c["url"], Path(tmp) / "roh")
                vorschau_speichern(roh, ausgabe / "vorschau" / f"{name}.jpg")
                hochformat(roh, ausgabe / f"{name}.mp4", c["titel"] or s["name"],
                           s["twitch"], cfg, cfg.get("max_sekunden", 60),
                           s.get("facecam"))
        except Exception as e:
            print(f"  Fehler: {e}", flush=True)
            continue
        (ausgabe / f"{name}.txt").write_text(beschreibung(c, s, cfg), encoding="utf-8")
        gesehen[c["id"]] = heute
        fertig.append({"datei": f"{name}.mp4", "streamer": s["name"],
                       "titel": c["titel"], "aufrufe": c["aufrufe"], "url": c["url"]})

    state_pfad.parent.mkdir(parents=True, exist_ok=True)
    state_pfad.write_text(json.dumps(gesehen, indent=1, sort_keys=True))
    (ausgabe / "liste.json").write_text(json.dumps(fertig, indent=1, ensure_ascii=False))
    print(f"\nFertig: {len(fertig)} neue Clips in {ausgabe}", flush=True)
    return len(fertig)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, default=HIER / "config.json")
    ap.add_argument("--state", type=Path, default=HIER / "state" / "gesehen.json")
    ap.add_argument("--ausgabe", type=Path, default=HIER / "ausgabe")
    ap.add_argument("--lokal", type=Path, help="eine lokale Datei schneiden (Test)")
    ap.add_argument("--titel", default="Test-Clip")
    ap.add_argument("--kanal", default="papaplatte")
    ap.add_argument("--alles-neu", action="store_true",
                    help="auch schon gemachte Clips neu schneiden")
    a = ap.parse_args()
    cfg = json.loads(a.config.read_text(encoding="utf-8"))
    if a.lokal:
        a.ausgabe.mkdir(parents=True, exist_ok=True)
        ziel = a.ausgabe / f"test_{_sicher(a.lokal.stem)}.mp4"
        hochformat(a.lokal, ziel, a.titel, a.kanal, cfg, cfg.get("max_sekunden", 60))
        print(ziel)
        return
    lauf(cfg, a.state, a.ausgabe, a.alles_neu)


if __name__ == "__main__":
    sys.exit(main())
