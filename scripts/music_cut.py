# -*- coding: utf-8 -*-
"""Shorten a music bed by splicing on downbeats, and propose where to splice.

  python music_cut.py MUSIC.wav --beats beats.json --suggest 95 120
  python music_cut.py MUSIC.wav --beats beats.json --keep bar:1-45,bar:105-end --out cut.wav
  python music_cut.py MUSIC.wav --beats beats.json --keep 0-82.68,192.09-end --out cut.wav

beats.json comes from beats.py run on the SAME file.

How a good splice is chosen. Remove whole sections, never trim inside a phrase:
jump from a downbeat to a downbeat, ideally where both are section starts, and
where the bar you land on resembles the bar you skipped, so the ear hears a
continuation rather than a seam. The classic move: cut from the end of the build
straight into the last chorus. That keeps the intro and the real ending, and loses
a repeat the picture rarely needs. --suggest ranks every single splice that hits
the target length on exactly those terms.

The crossfade is equal-power and centred on the downbeat (default 0.96 s, about two
beats), the way an editor lays a cross-fade over a music edit in the timeline.

After cutting, run beats.py again on the new file: its beat map is what the picture
gets cut to.
"""
import argparse, json, math, os, subprocess, sys, tempfile, wave
from rs_common import find_ffmpeg

try:
    import numpy as np
except ImportError:
    sys.exit("needs numpy:  pip install numpy")


def decode(ff, path, sr, ch):
    tmp = tempfile.mktemp(suffix=".wav")
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-i", path, "-ac", str(ch),
                    "-ar", str(sr), "-c:a", "pcm_s16le", tmp], check=True, capture_output=True)
    with wave.open(tmp, "rb") as w:
        raw = w.readframes(w.getnframes())
    os.unlink(tmp)
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32).reshape(-1, ch) / 32768.0


def chroma(x, sr, a, b):
    seg = x[int(a * sr):int(b * sr)]
    if len(seg) < 256:
        return np.zeros(12)
    sp = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
    f = np.fft.rfftfreq(len(seg), 1 / sr)
    ok = (f > 60) & (f < 2000)
    pc = (np.round(12 * np.log2(f[ok] / 440.0)) + 9).astype(int) % 12
    c = np.zeros(12)
    np.add.at(c, pc, sp[ok])
    return c / (c.sum() + 1e-12)


def mmss(t):
    return f"{int(t // 60)}:{t % 60:05.2f}"


def parse_keep(spec, bars, dur):
    """'bar:1-45,bar:105-end' or '0-82.68,192.09-end' -> [(start_s, end_s)]."""
    bt = {b["n"]: b["t"] for b in bars}
    out = []
    for part in spec.split(","):
        part = part.strip()
        isbar = part.startswith("bar:")
        a, b = (part[4:] if isbar else part).split("-")
        def val(v, end):
            if v == "end":
                return dur
            if isbar:
                n = int(v) + (1 if end else 0)     # bar ranges are inclusive
                if n == 1 and not end:
                    return 0.0                     # keep the pickup before the first downbeat
                return bt.get(n, dur)
            return float(v)
        out.append((val(a, False), val(b, True)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("music")
    ap.add_argument("--beats", required=True, help="beats.json from beats.py on this file")
    ap.add_argument("--suggest", nargs=2, type=float, metavar=("MIN", "MAX"))
    ap.add_argument("--keep", help="segments to keep, e.g. bar:1-44,bar:105-end")
    ap.add_argument("--snap", action="store_true", default=True,
                    help="snap segment edges to the nearest downbeat (default on)")
    ap.add_argument("--xfade", type=float, default=0.96, help="crossfade seconds, centred on the splice")
    ap.add_argument("--out")
    ap.add_argument("--ffmpeg")
    a = ap.parse_args()

    ff, _ = find_ffmpeg(a.ffmpeg)
    bj = json.load(open(a.beats, encoding="utf-8"))
    bars, dur = bj["bars"], bj["duration"]
    downs = [b["t"] for b in bars]
    starts = {s["start_bar"] for s in bj.get("sections", [])}
    db = {b["n"]: b["db"] for b in bars}

    if a.suggest:
        lo, hi = a.suggest
        sr = 22050
        x = decode(ff, a.music, sr, 1)[:, 0]
        ch = {b["n"]: chroma(x, sr, b["t"], bars[i + 1]["t"] if i + 1 < len(bars) else dur)
              for i, b in enumerate(bars)}
        cands = []
        for i, A in enumerate(bars[1:-1], 1):
            for B in bars[i + 1:]:
                L = dur - (B["t"] - A["t"])
                if not (lo <= L <= hi):
                    continue
                sim = float(np.corrcoef(ch[A["n"]], ch[B["n"]])[0, 1])
                score = sim + 0.35 * (A["n"] in starts) + 0.35 * (B["n"] in starts) \
                    - 0.03 * abs(db[A["n"]] - db[B["n"]]) \
                    + 0.15 * (db[B["n"]] >= db[A["n"]] - 1)          # land on equal or more energy
                cands.append((score, A, B, L, sim))
        cands.sort(key=lambda c: -c[0])
        print(f"{len(cands)} single splices give {lo:g}-{hi:g} s. Best:")
        print(" score  keep up to (bar)   jump to (bar)      length  similarity")
        for sc, A, B, L, sim in cands[:10]:
            tag = []
            if A["n"] in starts: tag.append("leaves at a section start")
            if B["n"] in starts: tag.append("lands on a section start")
            print(f" {sc:5.2f}  {mmss(A['t']):>8} ({A['n']:3d})  {mmss(B['t']):>8} ({B['n']:3d})  {L:6.1f}s  "
                  f"{sim:5.2f}   {', '.join(tag)}")
        if cands:
            A, B = cands[0][1], cands[0][2]
            print(f"\nrender the best:  --keep bar:1-{A['n'] - 1},bar:{B['n']}-end --out cut.wav")
        if not a.keep:
            return

    if not a.keep:
        sys.exit("give --suggest MIN MAX or --keep SEGMENTS")
    segs = parse_keep(a.keep, bars, dur)
    if a.snap:
        snap = lambda t: t if t in (0.0, dur) else min(downs, key=lambda d: abs(d - t))
        segs = [(snap(s), snap(e)) for s, e in segs]
    sr, chn = 48000, 2
    x = decode(ff, a.music, sr, chn)
    h = max(1, int(a.xfade * sr / 2))
    n = 2 * h
    S = lambda t: min(max(int(round(t * sr)), 0), len(x))
    # overlap-add: every segment carries h samples of handle either side of its
    # edges, and neighbours cross-fade over the 2h samples centred on each splice
    last = len(segs) - 1
    out = x[S(segs[0][0]):S(segs[0][1]) + (h if last else 0)]
    mapping, pos = [{"src_start": segs[0][0], "src_end": segs[0][1], "dst_start": 0.0}], segs[0][1] - segs[0][0]
    for i, (s0, e0) in enumerate(segs[1:], 1):
        piece = x[S(s0) - h:S(e0) + (h if i < last else 0)]
        r = np.linspace(0, 1, n)[:, None]
        mix = out[-n:] * np.cos(r * np.pi / 2) + piece[:n] * np.sin(r * np.pi / 2)
        out = np.concatenate([out[:-n], mix, piece[n:]])
        mapping.append({"src_start": s0, "src_end": e0, "dst_start": round(pos, 4)})
        pos += e0 - s0
    f = int(0.05 * sr)
    out[-f:] *= np.linspace(1, 0, f)[:, None]
    outp = a.out or os.path.splitext(a.music)[0] + "_cut.wav"
    pcm = (np.clip(out, -1, 1) * 32767).astype(np.int16)
    with wave.open(outp, "wb") as w:
        w.setnchannels(chn); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm.tobytes())
    json.dump({"source": os.path.abspath(a.music), "out": os.path.abspath(outp), "duration": round(len(out) / sr, 3),
               "xfade": a.xfade, "segments": mapping},
              open(os.path.splitext(outp)[0] + "_map.json", "w", encoding="utf-8"), indent=1)
    print(f"{len(segs)} segment(s), {len(out) / sr:.2f} s -> {outp}")
    for m in mapping:
        print(f"  {mmss(m['src_start'])}-{mmss(m['src_end'])} of the source at {mmss(m['dst_start'])}")
    print("Now run beats.py on the cut file; cut the picture to that beat map.")


if __name__ == "__main__":
    main()
