# -*- coding: utf-8 -*-
"""Estimate tempo and a beat grid from a music bed, snapped to frame boundaries.

  python beats.py MUSIC.mp3 --fps 25
  python beats.py MUSIC.wav --fps 25 --every 4 --out beats.json

Uses spectral flux onset detection and autocorrelation for tempo, so it needs only
numpy and ffmpeg — no audio library to install.

--every N returns a cut grid on every Nth beat, which is the usual working unit:
every 2 beats for fast montage, every 4 for a calmer pace.

Cutting on every single beat for a whole reel reads as mechanical. Vary it, and
hold one shot through a beat where the picture earns it — the held shot is what
makes the pattern legible.
"""
import argparse, json, os, subprocess, sys, tempfile
from rs_common import find_ffmpeg

try:
    import numpy as np
except ImportError:
    sys.exit("needs numpy:  pip install numpy")

SR = 22050
HOP = 512
NFFT = 1024


def decode(ff, path):
    """Mono float32 at SR, via a temp WAV so we do not depend on pipe behaviour."""
    tmp = tempfile.mktemp(suffix=".wav")
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-i", path,
                    "-ac", "1", "-ar", str(SR), "-f", "wav", tmp],
                   check=True, capture_output=True)
    import wave
    with wave.open(tmp, "rb") as w:
        n = w.getnframes()
        raw = w.readframes(n)
        width = w.getsampwidth()
    os.unlink(tmp)
    dt = {1: np.int8, 2: np.int16, 4: np.int32}.get(width, np.int16)
    x = np.frombuffer(raw, dtype=dt).astype(np.float32)
    return x / float(np.iinfo(dt).max)


def onset_envelope(x):
    win = np.hanning(NFFT).astype(np.float32)
    n = 1 + (len(x) - NFFT) // HOP
    if n < 4:
        sys.exit("audio too short")
    spec = np.empty((n, NFFT // 2 + 1), dtype=np.float32)
    for i in range(n):
        seg = x[i * HOP:i * HOP + NFFT] * win
        spec[i] = np.abs(np.fft.rfft(seg))
    spec = np.log1p(spec * 10.0)
    flux = np.diff(spec, axis=0)
    flux[flux < 0] = 0.0                    # rising energy only
    env = flux.sum(axis=1)
    env -= env.mean()
    return env / (env.std() + 1e-9)


def tempo(env, lo=70, hi=180):
    """Autocorrelate the onset envelope; peak inside a plausible BPM band."""
    fps_env = SR / HOP
    ac = np.correlate(env, env, mode="full")[len(env) - 1:]
    lag_lo = int(fps_env * 60.0 / hi)
    lag_hi = int(fps_env * 60.0 / lo)
    band = ac[lag_lo:lag_hi]
    if band.size == 0:
        return 120.0
    lag = lag_lo + int(np.argmax(band))
    return float(60.0 * fps_env / lag)


def phase(env, bpm):
    """Best offset for a pulse train at this tempo."""
    fps_env = SR / HOP
    period = 60.0 / bpm * fps_env
    best, best_score = 0.0, -1e18
    for off in np.arange(0, period, max(period / 48.0, 1.0)):
        idx = np.arange(off, len(env), period).astype(int)
        idx = idx[idx < len(env)]
        score = env[idx].sum()
        if score > best_score:
            best_score, best = score, off
    return best / fps_env


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("music")
    ap.add_argument("--fps", type=float, default=25.0)
    ap.add_argument("--every", type=int, default=2, help="cut every Nth beat")
    ap.add_argument("--limit", type=float, default=0.0, help="stop after N seconds")
    ap.add_argument("--out")
    ap.add_argument("--ffmpeg")
    a = ap.parse_args()

    ff, _ = find_ffmpeg(a.ffmpeg)
    if not ff:
        sys.exit("ffmpeg not found")

    x = decode(ff, a.music)
    dur = len(x) / SR
    env = onset_envelope(x)
    bpm = tempo(env)
    off = phase(env, bpm)
    period = 60.0 / bpm

    end = a.limit if a.limit > 0 else dur
    beats, t = [], off
    while t < end:
        beats.append(round(t, 4))
        t += period

    frame = 1.0 / a.fps
    cuts = [round(round(b / frame) * frame, 4) for b in beats[::a.every]]
    gaps = [round(cuts[i + 1] - cuts[i], 3) for i in range(len(cuts) - 1)]

    print(f"duration   {dur:.2f}s")
    print(f"tempo      {bpm:.1f} BPM   (beat every {period:.3f}s)")
    print(f"first beat {off:.3f}s")
    print(f"beats      {len(beats)}")
    print(f"cuts every {a.every} beats -> {len(cuts)}, spacing ~{period*a.every:.3f}s")
    print(f"snapped to {a.fps} fps, so each cut lands on a whole frame")
    print("\nfirst cuts: " + ", ".join(f"{c:.2f}" for c in cuts[:12]))

    res = {"file": a.music, "duration": round(dur, 3), "bpm": round(bpm, 2),
           "first_beat": round(off, 4), "beat_period": round(period, 4),
           "fps": a.fps, "every": a.every, "beats": beats, "cuts": cuts,
           "clip_durations": gaps}
    out = a.out or "beats.json"
    json.dump(res, open(out, "w", encoding="utf-8"), indent=2)
    print(f"\n-> {out}")
    print("clip_durations feeds straight into an edit list; they are already")
    print("frame-aligned, so the concat will hold constant frame rate.")


if __name__ == "__main__":
    main()
