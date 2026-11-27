#!/usr/bin/env python3
"""Baut den Ton fuer welt.html: ruhige Lo-Fi-Musik plus Effekte an den
Stellen, die die Szene in ihrer Ereignisliste meldet.

    python3 tools/videos/ton.py ereignisse.json ziel.wav

Alles wird hier synthetisiert (nur numpy), damit keine fremden Klaenge
mit unklarer Lizenz im Video landen.
"""
import json
import sys
import wave

import numpy as np

RATE = 44100
rng = np.random.default_rng(11)


def t_achse(dauer):
    return np.arange(int(dauer * RATE)) / RATE


def hz(note):
    """MIDI-Nummer -> Frequenz."""
    return 440.0 * 2 ** ((note - 69) / 12)


def huelle(n, an=0.005, ab=0.3):
    t = np.arange(n) / RATE
    return np.minimum(1, t / max(an, 1e-4)) * np.exp(-t / ab)


def tiefpass(x, breite):
    k = np.ones(breite) / breite
    return np.convolve(x, k, mode="same")


def bandpass(x, lo, hi):
    f = np.fft.rfft(x)
    fr = np.fft.rfftfreq(len(x), 1 / RATE)
    f[(fr < lo) | (fr > hi)] = 0
    return np.fft.irfft(f, len(x))


class Spur:
    def __init__(self, dauer):
        self.l = np.zeros(int(dauer * RATE) + RATE)
        self.r = np.zeros_like(self.l)

    def add(self, zeit, klang, laut=1.0, pan=0.0):
        i = int(zeit * RATE)
        if i >= len(self.l):
            return
        n = min(len(klang), len(self.l) - i)
        self.l[i:i + n] += klang[:n] * laut * np.sqrt((1 - pan) / 2)
        self.r[i:i + n] += klang[:n] * laut * np.sqrt((1 + pan) / 2)


# ---------------- Instrumente ----------------
def epiano(note, dauer=1.6):
    t = t_achse(dauer)
    f = hz(note)
    x = (np.sin(2 * np.pi * f * t) + .35 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t / .25)
         + .12 * np.sin(2 * np.pi * 3.01 * f * t) * np.exp(-t / .12))
    x *= 1 + .12 * np.sin(2 * np.pi * 4.5 * t)          # leichtes Tremolo
    return x * huelle(len(t), .006, .9)


def flaeche(note, dauer):
    """Weiche Synth-Flaeche: verstimmte Obertoene, langsam ein- und ausgeblendet."""
    t = t_achse(dauer)
    f = hz(note)
    x = np.zeros_like(t)
    for verstimmt in (-0.12, 0.0, 0.13):
        g = f * 2 ** (verstimmt / 12)
        for n, a in ((1, 1), (2, .3), (3, .12)):
            x += a * np.sin(2 * np.pi * g * n * t + verstimmt * 7)
    an = np.minimum(1, t / .6)
    ab = np.minimum(1, (dauer - t) / .8)
    return x / 4.3 * an * np.clip(ab, 0, 1)


def bass(note, dauer=.8):
    t = t_achse(dauer)
    f = hz(note)
    x = np.sin(2 * np.pi * f * t) + .25 * np.sin(2 * np.pi * 2 * f * t)
    return x * huelle(len(t), .01, .45)


def kick():
    t = t_achse(.35)
    f = 48 + 90 * np.exp(-t / .04)
    return np.sin(2 * np.pi * np.cumsum(f) / RATE) * huelle(len(t), .002, .12)


def snare():
    n = int(.18 * RATE)
    x = tiefpass(rng.standard_normal(n), 6) * huelle(n, .001, .05)
    t = np.arange(n) / RATE
    return x * .6 + np.sin(2 * np.pi * 190 * t) * huelle(n, .001, .03) * .4


def hat():
    n = int(.05 * RATE)
    x = rng.standard_normal(n)
    x = np.diff(x, prepend=0)
    return x * huelle(n, .0005, .012)


# ---------------- Effekte ----------------
def plopp():
    t = t_achse(.12)
    f = 760 + 700 * (1 - np.exp(-t / .02))
    return np.sin(2 * np.pi * np.cumsum(f) / RATE) * huelle(len(t), .002, .035)


def tick():
    t = t_achse(.06)
    return np.sin(2 * np.pi * 1850 * t) * huelle(len(t), .001, .012)


def kerze(stufe):
    skala = [72, 74, 76, 79, 81, 84, 86, 88, 91, 93, 96, 98]
    t = t_achse(.5)
    f = hz(skala[stufe % len(skala)])
    x = np.sin(2 * np.pi * f * t) + .3 * np.sin(2 * np.pi * 4 * f * t) * np.exp(-t / .03)
    return x * huelle(len(t), .002, .14)


def wusch(dauer):
    dauer = max(.5, dauer)
    n = int((dauer + .25) * RATE)
    x = bandpass(rng.standard_normal(n), 300, 5200)
    s = np.linspace(0, 1, n)
    env = np.sin(np.pi * np.clip(s * 1.1, 0, 1)) ** 2
    x = x * env
    return x / (np.abs(x).max() + 1e-9)


def alarm():
    out = []
    for f in (740, 520):
        t = t_achse(.16)
        x = np.tanh(2.2 * np.sin(2 * np.pi * f * t)) * huelle(len(t), .004, .12)
        out.append(np.concatenate([x, np.zeros(int(.03 * RATE))]))
    x = np.concatenate(out)
    k = kick()
    x[:len(k)] += k * .8
    return x


def klang():
    t = t_achse(2.8)
    x = np.zeros_like(t)
    for i, note in enumerate((84, 88, 91, 96)):
        st = int(i * .09 * RATE)
        f = hz(note)
        teil = sum(a * np.sin(2 * np.pi * f * r * t[:len(t) - st]) * np.exp(-t[:len(t) - st] / d)
                   for r, a, d in ((1, 1, 1.4), (2.76, .35, .5), (5.4, .15, .2)))
        x[st:] += teil * huelle(len(t) - st, .002, 10)
    return x / 3


def hall(x, staerke=.22):
    y = x.copy()
    for ms, g in ((47, .5), (83, .38), (131, .28), (197, .2), (283, .12)):
        d = int(ms / 1000 * RATE)
        y[d:] += x[:-d] * g * staerke * 2
    return y


# ---------------- Zusammenbau ----------------
def main():
    quelle, ziel = sys.argv[1], sys.argv[2]
    daten = json.load(open(quelle))
    fps, laenge = daten["fps"], daten["laenge"]
    dauer = laenge / fps
    musik, fx = Spur(dauer), Spur(dauer)

    bpm = 88
    schlag = 60 / bpm
    akkorde = [  # Am9, Fmaj7, Cmaj7, G6 - dunkel, ruhig, modern
        (33, [57, 60, 64, 71]), (29, [57, 60, 64, 65]),
        (36, [55, 60, 64, 71]), (31, [55, 59, 62, 64])]
    takt = 0
    while takt * 4 * schlag < dauer:
        b0 = takt * 4 * schlag
        wurzel, toene = akkorde[takt % 4]
        for i, n in enumerate(toene):
            musik.add(b0, flaeche(n, 4 * schlag + .9), .07, pan=(i - 1.5) * .35)
            musik.add(b0 + i * .018, epiano(n + 12), .1, pan=(i - 1.5) * .25)
            musik.add(b0 + 2.5 * schlag + i * .018, epiano(n + 12 if i == 3 else n, 1.0), .09, pan=(i - 1.5) * .25)
        musik.add(b0, bass(wurzel + 12), .42)
        musik.add(b0 + 2.5 * schlag, bass(wurzel + 12, .5), .26)
        if b0 > 0.5:  # die Trommeln setzen nach dem ersten Takt ein
            for s in (0, 2):
                musik.add(b0 + s * schlag, kick(), .42)
            for s in (1, 3):
                musik.add(b0 + s * schlag, snare(), .12)
            for a in range(8):
                musik.add(b0 + a * schlag / 2 + (0.02 if a % 2 else 0), hat(), .05 if a % 2 else .08, pan=.3)
        takt += 1

    kz = 0
    for e in daten["ereignisse"]:
        zeit = e["b"] / fps
        typ = e["typ"]
        if typ == "plopp":
            fx.add(zeit, plopp(), .32)
        elif typ == "tick":
            fx.add(zeit, tick(), .14, pan=.2)
        elif typ == "kerze":
            fx.add(zeit, kerze(kz), .09, pan=-.5 + (kz % 12) / 11)
            kz += 1
        elif typ == "wusch":
            w = wusch(e.get("dauer", 30) / fps)
            n = len(w)
            pan = np.linspace(-.7, .7, n)
            i = int(zeit * RATE)
            n = min(n, len(fx.l) - i)
            fx.l[i:i + n] += w[:n] * .2 * np.sqrt((1 - pan[:n]) / 2)
            fx.r[i:i + n] += w[:n] * .2 * np.sqrt((1 + pan[:n]) / 2)
        elif typ == "alarm":
            fx.add(zeit, alarm(), .3)
        elif typ == "klang":
            fx.add(zeit, klang(), .5)

    n = int(dauer * RATE)
    l = hall(musik.l[:n]) + hall(fx.l[:n], .15)
    r = hall(musik.r[:n]) + hall(fx.r[:n], .15)
    t = np.arange(n) / RATE
    blende = np.minimum(1, t / .25) * np.minimum(1, (dauer - t) / 1.6)
    st = np.stack([l, r], 1) * blende[:, None]
    st = np.tanh(st * 1.1)  # sanft begrenzen
    st *= .89 / np.abs(st).max()
    pcm = (st * 32767).astype(np.int16)
    with wave.open(ziel, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    print("Ton:", ziel, f"{dauer:.1f} s")


if __name__ == "__main__":
    main()
