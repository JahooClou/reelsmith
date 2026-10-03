# -*- coding: utf-8 -*-
"""Beats, downbeats, bars and sections of a music bed, and cut points on frames.

  python beats.py MUSIC.wav --fps 25 --out beats.json
  python beats.py MUSIC.wav --fps 25 --lead 1 --every 2 --out beats.json

What it does, in order:
  1. onset envelope (spectral flux), fine tempo estimate over 60-200 BPM
  2. beat TRACKING by dynamic programming, so a track that drifts (128 -> 133 BPM
     over three minutes is common in generated music) stays on the grid; a fixed
     grid from one tempo is several frames off by the end
  3. each beat moved onto the audible transient (-20/+70 ms), because the tracker
     sits on the smoothed envelope, 30-40 ms ahead of the hit
  4. downbeats: the beat phase whose bar lines carry the kick and the section
     changes
  5. per-bar loudness and section boundaries, so the structure (intro, build,
     drop, break, outro) can be read before anything is cut
  6. cut frames = beat frame - LEAD. Picture cuts land one frame BEFORE the beat:
     audio follows video. A cut exactly on the beat reads as late.

Writes beats.json:
  beats    [{t, frame, bar, beat_in_bar, downbeat}]
  bars     [{n, t, frame, db}]          one entry per bar
  sections [{start_bar, t, db, kind}]   kind: quiet / mid / loud, from loudness
  cuts     frames to cut on (every Nth beat, minus lead)
Only numpy and ffmpeg are needed.
"""
import argparse, json, math, os, subprocess, sys, tempfile, wave
from rs_common import find_ffmpeg

try:
    import numpy as np
except ImportError:
    sys.exit("needs numpy:  pip install numpy")

SR = 12000          # analysis rate: enough for kick, snare and hats
HOP = 64            # 5.3 ms envelope resolution
NFFT = 512


def decode(ff, path, sr=SR):
    tmp = tempfile.mktemp(suffix=".wav")
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-i", path,
                    "-ac", "1", "-ar", str(sr), "-f", "wav", tmp], check=True, capture_output=True)
    with wave.open(tmp, "rb") as w:
        raw = w.readframes(w.getnframes())
    os.unlink(tmp)
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def envelopes(x):
    n = 1 + (len(x) - NFFT) // HOP
    idx = np.arange(NFFT)[None, :] + HOP * np.arange(n)[:, None]
    win = np.hanning(NFFT).astype(np.float32)
    S = np.log1p(10 * np.abs(np.fft.rfft(x[idx] * win, axis=1)))
    f = np.fft.rfftfreq(NFFT, 1 / SR)
    fl = np.diff(S, axis=0)
    fl[fl < 0] = 0
    def norm(e):
        e = e - e.mean()
        return e / (e.std() + 1e-9)
    return norm(fl.sum(1)), norm(fl[:, f < 200].sum(1))


def tempo(env, fe, lo=60, hi=200):
    """Autocorrelation with a log-normal prior centred on 120 BPM (picks the tactus
    rather than a half or double), then a fine comb search around the winner."""
    ac = np.correlate(env, env, mode="full")[len(env) - 1:]
    lags = np.arange(int(fe * 60 / hi), int(fe * 60 / lo) + 1)
    bpms = 60 * fe / lags
    w = np.exp(-0.5 * (np.log2(bpms / 120.0) / 0.9) ** 2)
    coarse = float(bpms[int(np.argmax(ac[lags] * w))])
    best = (-1e18, coarse)
    for bpm in np.arange(coarse - 4, coarse + 4, 0.05):
        per = 60 / bpm * fe
        score = max(env[np.arange(off, len(env), per).astype(int)].mean()
                    for off in np.linspace(0, per, 24, endpoint=False))
        if score > best[0]:
            best = (score, bpm)
    return best[1]


def track(env, fe, bpm, tight=400.0):
    """Ellis dynamic-programming beat tracker: follows gradual tempo drift."""
    per = 60 / bpm * fe
    k = np.exp(-0.5 * (np.arange(-6, 7) / 2.0) ** 2)
    e = np.convolve(env, k / k.sum(), "same")
    n = len(e)
    cum = np.zeros(n)
    back = -np.ones(n, int)
    lo, hi = int(per * 0.5), int(per * 2)
    for i in range(n):
        a, b = max(0, i - hi), i - lo
        if b <= a:
            cum[i] = e[i]
            continue
        prev = np.arange(a, b)
        sc = cum[prev] - tight * np.log((i - prev) / per) ** 2
        j = int(np.argmax(sc))
        cum[i] = e[i] + sc[j]
        back[i] = prev[j]
    i = n - int(per) + int(np.argmax(cum[n - int(per):]))
    out = []
    while i >= 0:
        out.append(i)
        i = back[i]
    return np.array(out[::-1]) / fe


def to_transient(x, t, before=0.02, after=0.07):
    """Move a beat onto the steepest rise of the waveform envelope nearby.

    The tracker works on a smoothed envelope and lands 30-40 ms BEFORE the audible
    hit, so the search window looks mostly forward."""
    a = max(0, int((t - before) * SR))
    seg = np.abs(x[a:int((t + after) * SR)])
    k = max(1, int(0.003 * SR))
    if len(seg) <= 2 * k:
        return t
    env = np.convolve(seg, np.ones(k) / k, "same")
    d = env[k:] - env[:-k]
    return (a + int(np.argmax(d)) + k // 2) / SR


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("music")
    ap.add_argument("--fps", type=float, default=25.0)
    ap.add_argument("--every", type=int, default=1, help="cut grid on every Nth beat")
    ap.add_argument("--lead", type=int, default=1,
                    help="frames the picture cut leads the beat (audio follows video)")
    ap.add_argument("--bpm", type=float, help="tempo hint, if the estimate halves or doubles")
    ap.add_argument("--out")
    ap.add_argument("--ffmpeg")
    a = ap.parse_args()

    ff, _ = find_ffmpeg(a.ffmpeg)
    if not ff:
        sys.exit("ffmpeg not found")
    x = decode(ff, a.music)
    dur = len(x) / SR
    fe = SR / HOP
    env, envl = envelopes(x)
    bpm = a.bpm or tempo(env, fe)
    raw = track(env, fe, bpm)
    # per-beat transient offsets are noisy (a vocal or a hat can win), so apply a
    # rolling median of them: every cut keeps the same lead against the drums
    off = np.array([to_transient(x, t) - t for t in raw])
    sm = np.array([np.median(off[max(0, i - 4):i + 5]) for i in range(len(off))])
    beats = [float(b) for b in raw + sm if b >= 0]
    ib = np.diff(beats)

    # downbeat phase: low-band onset strength on the bar lines plus loudness jumps there
    rms = np.array([math.sqrt(float(np.mean(x[int(beats[i] * SR):int(beats[i + 1] * SR)] ** 2)) + 1e-12)
                    for i in range(len(beats) - 1)] + [1e-6])
    db = 20 * np.log10(rms)
    jump = np.maximum(np.diff(np.concatenate([[db[0]], db])), 0)
    def at(e, t):
        i = int(t * fe)
        return float(e[max(0, i - 3):i + 4].max()) if i < len(e) else 0.0
    score = [sum(at(envl, beats[i]) + 0.5 * jump[i] for i in range(ph, len(beats), 4)) for ph in range(4)]
    phase = int(np.argmax(score))

    fr = lambda t: int(round(t * a.fps))
    out_beats = []
    for i, t in enumerate(beats):
        bar = (i - phase) // 4 + 1
        out_beats.append({"t": round(t, 4), "frame": fr(t), "bar": bar,
                          "beat_in_bar": (i - phase) % 4 + 1, "downbeat": (i - phase) % 4 == 0})
    bars = []
    for i in range(phase, len(beats) - 4, 4):
        seg = x[int(beats[i] * SR):int(beats[i + 4] * SR)]
        bars.append({"n": len(bars) + 1, "t": round(beats[i], 4), "frame": fr(beats[i]),
                     "db": round(20 * math.log10(math.sqrt(float(np.mean(seg ** 2))) + 1e-12), 1)})

    # sections: a bar whose loudness steps by 2.5 dB or more starts a new section
    sections = []
    lv = [b["db"] for b in bars]
    hi_db, lo_db = (max(lv), min(lv)) if lv else (0, 0)
    def kind(v):
        r = (v - lo_db) / max(hi_db - lo_db, 1e-6)
        return "loud" if r > 0.75 else ("mid" if r > 0.4 else "quiet")
    for j, b in enumerate(bars):
        if j == 0 or abs(b["db"] - bars[j - 1]["db"]) >= 2.5:
            sections.append({"start_bar": b["n"], "t": b["t"], "db": b["db"], "kind": kind(b["db"])})

    cuts = sorted({max(0, b["frame"] - a.lead) for b in out_beats[phase::a.every]})
    res = {"file": os.path.abspath(a.music), "duration": round(dur, 3), "fps": a.fps,
           "bpm": round(60 / float(np.median(ib)), 2), "bpm_start": round(60 / float(np.median(ib[:16])), 2),
           "bpm_end": round(60 / float(np.median(ib[-16:])), 2), "lead_frames": a.lead,
           "beats": out_beats, "bars": bars, "sections": sections, "cuts": cuts}
    out = a.out or "beats.json"
    json.dump(res, open(out, "w", encoding="utf-8"), indent=1)

    print(f"duration   {dur:.2f}s")
    print(f"tempo      {res['bpm']} BPM (start {res['bpm_start']}, end {res['bpm_end']})"
          + ("   DRIFTS: use the tracked beats, not a fixed grid" if abs(res['bpm_end'] - res['bpm_start']) > 1 else ""))
    print(f"beats      {len(beats)}, bars {len(bars)}, first downbeat {beats[phase]:.3f}s")
    print("sections:")
    for s in sections:
        print(f"  bar {s['start_bar']:3d}  {s['t']:7.2f}s  {s['db']:6.1f} dB  {s['kind']}")
    print(f"cuts       {len(cuts)} on every {a.every} beat(s), {a.lead} frame(s) before the beat")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
