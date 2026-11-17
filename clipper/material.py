#!/usr/bin/env python3
"""Material-Lader fuer Kampagnen, die eigenes Footage stellen (z. B. BloxClips).

Gesteuert ueber clipper/material.json, Feld "aufgabe":

  erkunden   Seite und ihre Scripte laden, alle Adressen ins Protokoll
             schreiben (um herauszufinden, wo die Dateien liegen).
  laden      Dateien herunterladen, pro Video eine Uebersicht mit
             Vorschaubildern bauen, alles in ausgabe/ legen.
  schneiden  Clips aus dem Material zusammensetzen: Szenen in 9:16,
             Hoehepunkt zuerst, Hook oben, Wasserzeichen unten, Musik drunter.

Aufruf: python material.py material.json
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urljoin

import requests

HIER = Path(__file__).resolve().parent
AUS = HIER / "material_ausgabe"
BREITE, HOEHE = 1080, 1920
KOPF = {"User-Agent": "Mozilla/5.0 (clip-tool)"}


def log(*a):
    print(*a, flush=True)


# --------------------------------------------------------------------------
# erkunden
# --------------------------------------------------------------------------

def erkunden(auftrag: dict) -> None:
    url = auftrag["url"]
    r = requests.get(url, headers=KOPF, timeout=30)
    log(f"Seite: HTTP {r.status_code}, {len(r.text)} Zeichen")
    html = r.text
    log("--- HTML (Anfang) ---")
    log(html[:3000])
    scripte = re.findall(r'<script[^>]+src="([^"]+)"', html)
    texte = [("html", html)]
    for s in scripte[:15]:
        su = urljoin(url, s)
        try:
            t = requests.get(su, headers=KOPF, timeout=30).text
            texte.append((su, t))
            log(f"Script {su}: {len(t)} Zeichen")
        except Exception as e:
            log(f"Script {su}: {e}")
    gesehen = set()
    muster = re.compile(r"""["'`](https?://[^"'`\s]+|/[A-Za-z0-9_\-./]*(?:api|files|list|folder|footage|media|download|storage|bucket)[^"'`\s]*)["'`]""", re.I)
    log("--- Adressen ---")
    for quelle, t in texte:
        for m in muster.finditer(t):
            a = m.group(1)
            if a not in gesehen and len(a) < 300:
                gesehen.add(a)
                log(f"{a}    <- {quelle[-40:]}")
    log("--- Stellen mit fetch( ---")
    for quelle, t in texte:
        for m in re.finditer(r"fetch\(([^)]{0,200})\)", t):
            log(m.group(0)[:250])
    for probe in auftrag.get("proben", []):
        pu = urljoin(url, probe)
        try:
            p = requests.get(pu, headers=KOPF, timeout=30)
            log(f"PROBE {pu}: HTTP {p.status_code} {p.headers.get('content-type')}\n{p.text[:1500]}")
        except Exception as e:
            log(f"PROBE {pu}: {e}")


# --------------------------------------------------------------------------
# laden
# --------------------------------------------------------------------------

def dauer_von(datei: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(datei)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def uebersicht(video: Path, ziel: Path, schritt: float = 2.0) -> None:
    """Raster aus Vorschaubildern alle `schritt` Sekunden, mit Zeitstempel."""
    d = dauer_von(video)
    n = max(1, int(d // schritt))
    spalten = 8
    zeilen = (n + spalten - 1) // spalten
    vf = (f"fps=1/{schritt},scale=240:-2,"
          f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
          f"text='%{{pts\\:hms}}':x=4:y=4:fontsize=18:fontcolor=yellow:box=1:boxcolor=black@0.6,"
          f"tile={spalten}x{zeilen}")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-vf", vf,
                    "-frames:v", "1", "-q:v", "4", str(ziel)], check=True)


def laden(auftrag: dict) -> None:
    AUS.mkdir(parents=True, exist_ok=True)
    liste = []
    for d in auftrag["dateien"]:
        ziel = AUS / d["name"]
        log(f"Lade {d['name']} ...")
        with requests.get(d["url"], headers=KOPF, timeout=600, stream=True) as r:
            r.raise_for_status()
            with ziel.open("wb") as f:
                for block in r.iter_content(1 << 20):
                    f.write(block)
        info = {"name": d["name"], "mb": round(ziel.stat().st_size / 1e6, 1)}
        if ziel.suffix.lower() in (".mp4", ".mov", ".webm", ".mkv"):
            info["dauer"] = round(dauer_von(ziel), 1)
            r2 = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                 "-show_entries", "stream=width,height", "-of", "csv=p=0",
                                 str(ziel)], capture_output=True, text=True)
            info["groesse"] = r2.stdout.strip()
            uebersicht(ziel, AUS / (ziel.stem + "_uebersicht.jpg"),
                       float(auftrag.get("schritt", 2)))
        elif ziel.suffix.lower() in (".mp3", ".wav", ".m4a"):
            info["dauer"] = round(dauer_von(ziel), 1)
        log(f"  {info}")
        liste.append(info)
    (AUS / "material.json").write_text(json.dumps(liste, indent=1, ensure_ascii=False))


# --------------------------------------------------------------------------
# schneiden
# --------------------------------------------------------------------------

def _ass_zeit(s: float) -> str:
    h, rest = divmod(max(0.0, s), 3600)
    m, sek = divmod(rest, 60)
    return f"{int(h)}:{int(m):02d}:{sek:05.2f}"


def _ass_text(t: str) -> str:
    t = re.sub(r"[\U0001F000-\U0001FAFF☀-➿️‍]", "", t)
    return re.sub(r"\s{2,}", " ", t.replace("{", "(").replace("}", ")")).strip()


def ass_schreiben(pfad: Path, dauer: float, hook: str, zeile2: str, wasserzeichen: str) -> None:
    ende = _ass_zeit(dauer + 1)
    pfad.write_text(f"""[Script Info]
ScriptType: v4.00+
PlayResX: {BREITE}
PlayResY: {HOEHE}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Hook,DejaVu Sans,66,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,7,2,8,70,70,230,1
Style: Zeile2,DejaVu Sans,50,&H0000F0FF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,2,8,70,70,0,1
Style: Marke,DejaVu Sans,46,&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,-1,0,0,0,100,100,0,0,3,10,0,2,60,60,150,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 1,0:00:00.00,{ende},Hook,,0,0,0,,{_ass_text(hook)}
""" + (f"Dialogue: 1,0:00:00.00,{ende},Zeile2,,0,0,0,,{{\\pos({BREITE // 2},430)}}{_ass_text(zeile2)}\n" if zeile2 else "")
      + (f"Dialogue: 1,0:00:00.00,{ende},Marke,,0,0,0,,{_ass_text(wasserzeichen)}\n" if wasserzeichen else ""),
      encoding="utf-8")


def szene_9x16(quelle: Path, start: float, ende: float, ziel: Path, x_mitte: float = 0.5) -> None:
    """Szene ausschneiden und randlos auf 1080x1920 bringen (Ausschnitt um x_mitte)."""
    vf = (f"scale=-2:{HOEHE}:flags=lanczos,"
          f"crop={BREITE}:{HOEHE}:(iw-{BREITE})*{x_mitte:.3f}:0,"
          f"setsar=1,fps=30,format=yuv420p")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.2f}", "-i", str(quelle),
                    "-t", f"{ende - start:.2f}", "-vf", vf, "-an",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", str(ziel)], check=True)


def clip_bauen(c: dict, auftrag: dict, nr: int) -> Path:
    name = f"clip_{nr:02d}_{re.sub(r'[^A-Za-z0-9]+', '-', c['hook'])[:40].strip('-')}.mp4"
    ziel = AUS / "clips" / name
    ziel.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        teile = []
        for i, s in enumerate(c["szenen"]):
            t = tmp / f"s{i}.mp4"
            szene_9x16(AUS / s["datei"], s["von"], s["bis"], t, s.get("x", 0.5))
            teile.append(t)
        (tmp / "liste.txt").write_text("".join(f"file '{t}'\n" for t in teile))
        bild = tmp / "bild.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                        "-i", str(tmp / "liste.txt"), "-c", "copy", str(bild)], check=True)
        dauer = dauer_von(bild)
        ass_schreiben(tmp / "text.ass", dauer, c["hook"], c.get("zeile2", ""),
                      auftrag.get("wasserzeichen", ""))
        musik = AUS / auftrag["musik"]
        ab = float(c.get("musik_ab", 0))
        aus = max(0.0, dauer - 1.0)
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error", "-i", str(bild), "-ss", f"{ab:.2f}", "-i", str(musik),
            "-filter_complex",
            f"[0:v]ass=text.ass[v];[1:a]afade=t=in:d=0.15,afade=t=out:st={aus:.2f}:d=1,volume=1.0[a]",
            "-map", "[v]", "-map", "[a]", "-t", f"{dauer:.2f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(ziel.resolve())],
            check=True, cwd=tmp)
    (ziel.with_suffix(".txt")).write_text(c["beschreibung"], encoding="utf-8")
    log(f"  fertig: {name} ({dauer:.1f} s)")
    return ziel


def schneiden(auftrag: dict) -> None:
    liste = []
    for nr, c in enumerate(auftrag["clips"], 1):
        log(f"Clip {nr}: {c['hook']}")
        z = clip_bauen(c, auftrag, nr)
        liste.append({"datei": z.name, "titel": c["hook"], "breite": BREITE, "hoehe": HOEHE})
    (AUS / "clips" / "liste.json").write_text(json.dumps(liste, indent=1, ensure_ascii=False))


def main() -> int:
    auftrag = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    aufgabe = auftrag["aufgabe"]
    if aufgabe == "erkunden":
        erkunden(auftrag)
    elif aufgabe == "laden":
        laden(auftrag)
    elif aufgabe == "schneiden":
        schneiden(auftrag)
    else:
        log(f"unbekannte Aufgabe {aufgabe}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
