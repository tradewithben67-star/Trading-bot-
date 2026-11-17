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
    ox: int = 0           # x im Hochformat (nur bei zwei Cams nebeneinander)
    ow: int = BREITE      # Breite im Hochformat


@dataclass
class Layout:
    art: str
    felder: list
    titel_unten: int      # y der Unterkante des Titels
    titel_groesse: int
    kanal_oben: int       # y der Oberkante von "twitch.tv/..."
    sub_mitte: bool       # True: Untertitel mittig auf sub_y (an der Naht)
    sub_y: int
    sub_groesse: int = 86


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
    det = cv2.FaceDetectorYN.create(str(MODELL), "", (sw, sh), 0.6)
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


def _gruppen(bilder):
    """Fasst Gesichter zusammen, die ueber mehrere Bilder an derselben Stelle auftauchen."""
    gruppen = []
    for i, b in enumerate(bilder):
        for g in b:
            for gr in gruppen:
                cx, cy, fw, fh = (statistics.median(t[1][k] for t in gr) for k in range(4))
                if abs(g[0] - cx) < max(1.5 * fw, 0.06) and abs(g[1] - cy) < max(1.2 * fh, 0.08):
                    gr.append((i, g))
                    break
            else:
                gruppen.append([(i, g)])
    return gruppen


def _facecam(bilder):
    """Stellen am Bildrand, an denen fast immer ein Gesicht ist = Facecam(s). Max. zwei.

    Sind dagegen oft groessere Gesichter in der Bildmitte, ist es IRL -> kein Facecam-Layout.
    """
    n = len(bilder)
    mitte = sum(1 for b in bilder if any(abs(g[0] - 0.5) < 0.25 and abs(g[1] - 0.5) < 0.3
                                         and g[3] >= 0.05 for g in b))
    if mitte >= 0.3 * n:
        return []
    cams = []
    for gr in _gruppen(bilder):
        anzahl = len({i for i, _ in gr})
        cx, cy, fw, fh = (statistics.median(t[1][k] for t in gr) for k in range(4))
        am_rand = cx < 0.3 or cx > 0.7 or cy < 0.3 or cy > 0.7
        if am_rand and fh < 0.3 and anzahl >= 0.25 * n:
            xs = [t[1][0] for t in gr]
            cams.append((anzahl, (cx, cy, fw, fh, max(xs) - min(xs))))
    cams.sort(key=lambda c: -c[0])
    if not cams:
        return []
    erste = cams[0][1]
    # zweite Cam nur, wenn sie deutlich woanders sitzt (andere Bildseite)
    zweite = next((c[1] for c in cams[1:] if abs(c[1][0] - erste[0]) > 0.3), None)
    return [erste] + ([zweite] if zweite else [])


def standard(w: int, h: int) -> Layout:
    cw = min(w, _gerade(h * 4 / 3))
    return Layout("standard", [Feld((w - cw) // 2, 0, cw, h, 555, 810)],
                  titel_unten=505, titel_groesse=72, kanal_oben=1395,
                  sub_mitte=False, sub_y=1495)


def _zwei_cams_layout(w, h, cams) -> Layout:
    cam_oy, cam_oh, halb = 180, 640, BREITE // 2
    spiel_oy, spiel_oh = cam_oy + cam_oh, 960
    felder = []
    for i, (cx, cy, fw, fh, _) in enumerate(sorted(cams, key=lambda c: c[0])):
        bh = min(max(fh * h * 2.8, 0.2 * h), 0.6 * h)
        bw = bh * halb / cam_oh
        x = min(max(cx * w - bw / 2, 0), w - bw)
        y = min(max(cy * h - bh * 0.45, 0), h - bh)
        felder.append(Feld(_gerade(x), _gerade(y), _gerade(bw), _gerade(bh), cam_oy, cam_oh,
                           ox=i * halb, ow=halb))
    gw = min(w, _gerade(h * BREITE / spiel_oh))
    felder.append(Feld((w - gw) // 2, 0, gw, h, spiel_oy, spiel_oh))
    return Layout("zwei-cams", felder, titel_unten=cam_oy - 16, titel_groesse=54,
                  kanal_oben=spiel_oy + spiel_oh + 12, sub_mitte=True, sub_y=spiel_oy)


def _facecam_layout(w, h, cam) -> Layout:
    cx, cy, fw, _, streuung = cam
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


def _feste_cam(w, h, box) -> Layout:
    """Cam-Position aus der Konfiguration: [x, y, breite, hoehe], relativ zur Bildgroesse."""
    x, y, bw, bh = box
    return _facecam_layout(w, h, (x + bw / 2, y + bh / 2 - 0.05 * bh, bw / 3.4, 0.0, 0.0))


# --------------------------------------------------------------------------
# Randlos: das ganze Hochformat ist Bild, kein unscharfer Rand, keine Balken.
# Gesicht oben, Spiel darunter; Untertitel Wort fuer Wort an der Naht.
# --------------------------------------------------------------------------

CAM_H = 820               # Hoehe des Gesichts-Streifens oben
TITEL_RANDLOS = dict(titel_unten=250, titel_groesse=60, kanal_oben=HOEHE - 70,
                     sub_groesse=100)


def _randlos_cam(w, h, cx, cy, fw, streuung, ox=0, ow=BREITE) -> Feld:
    bw = min(max(fw * w * 2.7, (streuung + 1.8 * fw) * w, 0.16 * w), 0.45 * w) * ow / BREITE
    bh = bw * CAM_H / ow
    if bh > h:
        bh, bw = h, h * ow / CAM_H
    x = min(max(cx * w - bw / 2, 0), w - bw)
    y = min(max(cy * h - bh * 0.45, 0), h - bh)
    return Feld(_gerade(x), _gerade(y), _gerade(bw), _gerade(bh), 0, CAM_H, ox=ox, ow=ow)


def _randlos_spiel(w, h) -> Feld:
    spiel_h = HOEHE - CAM_H
    gw = min(w, _gerade(h * BREITE / spiel_h))
    gh = min(h, _gerade(gw * spiel_h / BREITE))
    return Feld((w - gw) // 2, (h - gh) // 2, gw, gh, CAM_H, spiel_h)


def _randlos_ganz(w, h, mitte_x=0.5) -> Feld:
    """Ein 9:16-Ausschnitt ueber die volle Hoehe."""
    cw = min(w, _gerade(h * BREITE / HOEHE))
    x = int(min(max(mitte_x * w - cw / 2, 0), w - cw))
    return Feld(x, 0, cw, h, 0, HOEHE)


def randlos_waehlen(w, h, bilder) -> Layout:
    cams = _facecam(bilder) if bilder else []
    if len(cams) == 2:
        halb = BREITE // 2
        felder = [_randlos_cam(w, h, c[0], c[1], c[2], c[4], ox=i * halb, ow=halb)
                  for i, c in enumerate(sorted(cams, key=lambda c: c[0]))]
        return Layout("randlos-zwei-cams", felder + [_randlos_spiel(w, h)],
                      sub_mitte=True, sub_y=CAM_H, **TITEL_RANDLOS)
    if cams:
        cx, cy, fw, _, streuung = cams[0]
        return Layout("randlos-facecam", [_randlos_cam(w, h, cx, cy, fw, streuung),
                                          _randlos_spiel(w, h)],
                      sub_mitte=True, sub_y=CAM_H, **TITEL_RANDLOS)
    gesichter = [g for b in bilder for g in b] if bilder else []
    if bilder and sum(1 for b in bilder if b) >= 0.4 * len(bilder):
        mitte = statistics.median(g[0] for g in gesichter)
        return Layout("randlos-zoom", [_randlos_ganz(w, h, mitte)],
                      sub_mitte=True, sub_y=int(HOEHE * 0.62), **TITEL_RANDLOS)
    return Layout("randlos-mitte", [_randlos_ganz(w, h)],
                  sub_mitte=True, sub_y=int(HOEHE * 0.62), **TITEL_RANDLOS)


def waehlen(quelle: Path, feste_cam=None, randlos: bool = False) -> Layout:
    w, h = groesse_von(quelle)
    if feste_cam and not randlos:
        return _feste_cam(w, h, feste_cam)
    try:
        bilder = gesichter_finden(quelle)
    except Exception as e:
        print(f"  Gesichtserkennung fehlgeschlagen ({e}), Standard-Layout", flush=True)
        return randlos_waehlen(w, h, []) if randlos else standard(w, h)
    if randlos:
        return randlos_waehlen(w, h, bilder)
    if not bilder:
        return standard(w, h)
    cams = _facecam(bilder)
    if len(cams) == 2:
        return _zwei_cams_layout(w, h, cams)
    if cams:
        return _facecam_layout(w, h, cams[0])
    mit_gesicht = sum(1 for b in bilder if b)
    if mit_gesicht >= 0.4 * len(bilder):
        return _zoom_layout(w, h, bilder)
    return standard(w, h)
