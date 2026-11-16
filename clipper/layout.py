"""Waehlt pro Clip das Hochformat-Layout anhand der erkannten Gesichter.

  facecam   Gaming mit Facecam in einer Ecke: oben die Cam gross, unten das Spiel.
  zoom      IRL / Just Chatting: Ausschnitt eng um die Gesichter, fast bildfuellend.
  standard  Keine Gesichter: Spielbild (4:3) mittig auf unscharfem Hintergrund.

Gesichtserkennung: YuNet (OpenCV, MIT-Lizenz), Modell liegt in modelle/.
"""
from __future__ import annotations

import statistics
import subprocess
from dataclasses import dataclass
from pathlib import Path

MODELL = Path(__file__).resolve().parent / "modelle" / "face_detection_yunet_2023mar.onnx"
BREITE, HOEHE = 1080, 1920


@dataclass
class Feld:
    """Ausschnitt der Quelle (x, y, w, h in Pixeln) -> Streifen im Hochformat (oy, oh)."""
    x: int
    y: int
    w: int
    h: int
    oy: int
    oh: int


@dataclass
class Layout:
    art: str
    felder: list
    titel_unten: int      # y der Unterkante des Titels
    titel_groesse: int
    kanal_oben: int       # y der Oberkante von "twitch.tv/..."
    sub_mitte: bool       # True: Untertitel mittig auf sub_y (an der Naht)
    sub_y: int


def _gerade(v: float) -> int:
    return max(2, int(round(v / 2)) * 2)


def groesse_von(quelle: Path) -> tuple[int, int]:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height", "-of", "csv=p=0",
                        str(quelle)], capture_output=True, text=True, check=True)
    w, h = r.stdout.strip().split(",")[:2]
    return int(w), int(h)


def gesichter_finden(quelle: Path, proben: int = 16):
    """Liefert pro Probebild eine Liste (cx, cy, w, h), alles relativ zur Bildgroesse."""
    import cv2
    import numpy as np
    cap = cv2.VideoCapture(str(quelle))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if n <= 0 or w <= 0:
        return []
    skala = min(1.0, 960 / w)
    sw, sh = int(w * skala), int(h * skala)
    det = cv2.FaceDetectorYN.create(str(MODELL), "", (sw, sh), 0.75)
    bilder = []
    for i in np.linspace(0, n - 1, proben).astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, bild = cap.read()
        if not ok:
            continue
        _, f = det.detect(cv2.resize(bild, (sw, sh)))
        bilder.append([] if f is None else
                      [((x + fw / 2) / sw, (y + fh / 2) / sh, fw / sw, fh / sh)
                       for x, y, fw, fh, *_ in f])
    cap.release()
    return bilder


def _facecam(bilder):
    """Meist genau ein Gesicht, das ungefaehr an derselben Stelle am Rand bleibt = Facecam."""
    mit = [b for b in bilder if b]
    if len(mit) < 0.25 * len(bilder):
        return None
    if sum(len(b) for b in mit) / len(mit) > 1.6:   # mehrere Leute gleichzeitig -> IRL
        return None
    haupt = [max(b, key=lambda g: g[3]) for b in mit]
    cx, cy, fw, fh = (statistics.median(g[i] for g in haupt) for i in range(4))
    nah = [g for g in haupt if abs(g[0] - cx) < max(1.5 * fw, 0.08)
           and abs(g[1] - cy) < max(1.2 * fh, 0.1)]
    if len(nah) < 0.7 * len(haupt):
        return None
    am_rand = cx < 0.3 or cx > 0.7 or cy < 0.3 or cy > 0.7
    if not am_rand or fh >= 0.25:
        return None
    streuung = max(g[0] for g in nah) - min(g[0] for g in nah)
    return cx, cy, fw, streuung


def standard(w: int, h: int) -> Layout:
    cw = min(w, _gerade(h * 4 / 3))
    return Layout("standard", [Feld((w - cw) // 2, 0, cw, h, 555, 810)],
                  titel_unten=505, titel_groesse=72, kanal_oben=1395,
                  sub_mitte=False, sub_y=1495)


def _facecam_layout(w, h, cam) -> Layout:
    cx, cy, fw, streuung = cam
    cam_oy, cam_oh = 180, 640
    spiel_oy, spiel_oh = cam_oy + cam_oh, 960
    bw = min(max(fw * w * 3.4, (streuung + 2.2 * fw) * w, 0.18 * w), 0.5 * w)
    bh = bw * cam_oh / BREITE
    x = min(max(cx * w - bw / 2, 0), w - bw)
    y = min(max(cy * h - bh * 0.45, 0), h - bh)
    gw = min(w, _gerade(h * BREITE / spiel_oh))
    return Layout("facecam",
                  [Feld(_gerade(x), _gerade(y), _gerade(bw), _gerade(bh), cam_oy, cam_oh),
                   Feld((w - gw) // 2, 0, gw, h, spiel_oy, spiel_oh)],
                  titel_unten=cam_oy - 16, titel_groesse=54, kanal_oben=spiel_oy + spiel_oh + 12,
                  sub_mitte=True, sub_y=spiel_oy)


def _zoom_layout(w, h, bilder) -> Layout:
    gesichter = [g for b in bilder for g in b]
    # Bereich, in dem die Gesichter liegen (nach Groesse gewichtet, Ausreisser raus)
    gesichter.sort(key=lambda g: g[0])
    gewicht = [g[2] * g[3] for g in gesichter]
    summe, lauf, lo, hi = sum(gewicht), 0.0, None, None
    for g, gw in zip(gesichter, gewicht):
        lauf += gw
        if lo is None and lauf >= 0.1 * summe:
            lo = g[0]
        if hi is None and lauf >= 0.9 * summe:
            hi = g[0]
    mitte = (lo + hi) / 2
    breite_noetig = (hi - lo) * w + 2.5 * statistics.median(g[2] for g in gesichter) * w
    cw = min(max(breite_noetig, 0.8 * h), 4 / 3 * h, w)
    cw = _gerade(cw)
    x = int(min(max(mitte * w - cw / 2, 0), w - cw))
    oh = _gerade(min(BREITE * h / cw, 1350))
    oy = _gerade(max(250, (HOEHE - oh) / 2 - 40))
    unten = oy + oh
    sub_y = unten + 85 if HOEHE - (unten + 85) >= 110 else unten - 230
    return Layout("zoom", [Feld(x, 0, cw, h, oy, oh)],
                  titel_unten=oy - 30, titel_groesse=64 if oh > 1100 else 72,
                  kanal_oben=unten + 20, sub_mitte=False, sub_y=sub_y)


def waehlen(quelle: Path) -> Layout:
    w, h = groesse_von(quelle)
    try:
        bilder = gesichter_finden(quelle)
    except Exception as e:
        print(f"  Gesichtserkennung fehlgeschlagen ({e}), Standard-Layout", flush=True)
        return standard(w, h)
    if not bilder:
        return standard(w, h)
    cam = _facecam(bilder)
    if cam:
        return _facecam_layout(w, h, cam)
    mit_gesicht = sum(1 for b in bilder if b)
    if mit_gesicht >= 0.4 * len(bilder):
        return _zoom_layout(w, h, bilder)
    return standard(w, h)
