"""Genera i brani originali CRMEvent per Event Map (sintesi locale, nessuna licenza esterna). Uso: python make_music.py"""
import os
import subprocess
import wave

import numpy as np

SR = 44100
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "eventmap_assets", "music")
PUB = "/app/frontend/public/media/music"


def note(f, d, kind="saw", amp=0.2):
    t = np.arange(int(SR * d)) / SR
    if kind == "saw":
        w = 2 * (t * f % 1) - 1
    elif kind == "sq":
        w = np.sign(np.sin(2 * np.pi * f * t))
    elif kind == "pluck":
        w = np.sin(2 * np.pi * f * t) * np.exp(-t * 6)
    else:
        w = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t)
    env = np.minimum(1, t / 0.01) * np.minimum(1, (d - t) / 0.05)
    return w * env * amp


def kick(d=0.25):
    t = np.arange(int(SR * d)) / SR
    return np.sin(2 * np.pi * (50 + 120 * np.exp(-t * 30)) * t) * np.exp(-t * 9) * 0.9


def hat(d=0.06):
    t = np.arange(int(SR * d)) / SR
    return np.random.default_rng(1).uniform(-1, 1, len(t)) * np.exp(-t * 60) * 0.15


def mix(buf, s, at):
    i = int(at * SR)
    e = min(len(buf), i + len(s))
    buf[i:e] += s[: e - i]


def midi(n):
    return 440 * 2 ** ((n - 69) / 12)


def track(bpm, prog, style):
    beat = 60 / bpm
    bars = 16
    buf = np.zeros(int(SR * beat * 4 * bars) + SR)
    for b in range(bars):
        root = prog[b % len(prog)]
        t0 = b * 4 * beat
        chord = [root, root + (3 if style in ("emo", "cine") else 4), root + 7]
        if style == "sport":
            for k in range(4):
                mix(buf, kick(), t0 + k * beat)
                mix(buf, hat(), t0 + k * beat + beat / 2)
            for k in range(8):
                mix(buf, note(midi(root - 24), beat / 2 * 0.9, "saw", 0.18), t0 + k * beat / 2)
            for n in chord:
                mix(buf, note(midi(n), beat * 4, "saw", 0.05), t0)
        elif style == "elettro":
            for k in range(4):
                mix(buf, kick(0.2), t0 + k * beat)
            for k in range(16):
                mix(buf, note(midi(chord[k % 3] + 12), beat / 4 * 0.8, "sq", 0.05), t0 + k * beat / 4)
            mix(buf, note(midi(root - 12), beat * 4, "sine", 0.2), t0)
        elif style == "emo":
            for n in chord:
                mix(buf, note(midi(n), beat * 4, "sine", 0.09), t0)
            for k in range(8):
                mix(buf, note(midi(chord[k % 3] + 12), beat * 1.5, "pluck", 0.16), t0 + k * beat / 2)
        else:
            for n in chord + [root - 12]:
                mix(buf, note(midi(n), beat * 4, "saw", 0.04), t0)
                mix(buf, note(midi(n), beat * 4, "sine", 0.06), t0)
            if b % 2 == 0:
                mix(buf, kick(0.6) * 0.8, t0)
                mix(buf, kick(0.6) * 0.6, t0 + 2.5 * beat)
    buf = buf[: int(SR * beat * 4 * bars)]
    if style in ("emo", "cine"):  # riverbero semplice
        for dly, g in ((0.11, 0.35), (0.23, 0.25), (0.37, 0.15)):
            buf[int(dly * SR):] += buf[: -int(dly * SR)] * g
    return buf / (np.max(np.abs(buf)) + 1e-9) * 0.85


TRACKS = {"sportiva": (128, [57, 53, 60, 55], "sport"), "emozionale": (72, [57, 53, 48, 55], "emo"),
          "elettronica": (122, [52, 52, 48, 50], "elettro"), "cinematografica": (84, [45, 41, 43, 40], "cine")}

if __name__ == "__main__":
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(PUB, exist_ok=True)
    for name, (bpm, prog, st) in TRACKS.items():
        wav = f"/tmp/{name}.wav"
        with wave.open(wav, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes((track(bpm, prog, st) * 32767).astype(np.int16).tobytes())
        for dst in (os.path.join(OUT, f"{name}.mp3"), os.path.join(PUB, f"{name}.mp3")):
            subprocess.run([ff, "-y", "-loglevel", "error", "-i", wav, "-ac", "2", "-b:a", "160k", dst], check=True)
        print(name, "ok")
