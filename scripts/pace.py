# -*- coding: utf-8 -*-
"""Measure the pace of a cut, so "make it like this reel" becomes numbers to match.

  python pace.py REFERENCE.mp4
  python pace.py REFERENCE.mp4 OURS.mp4 [--words] [--sheet first6.jpg] [--json pace.json]

A contact sheet shows a reference's look, not its pace. This measures the pace:

  cuts/s         picture cuts per second (a new shot)
  hits/s         anything new on screen per second: a cut, a flash, a punch-in, a whip,
                 a graphic slamming in. Read as the frame changing far more than the
                 frames around it.
  avg shot       average shot length in seconds
  longest still  the longest stretch with no hit at all, and where it is. The
                 number viewers feel as "it dragged"
  first hit      when the first thing changes
  words/s        with --words: words per second of the whole piece, and when the first
                 word lands (faster-whisper, run on the CPU)

With two or more files the first is the reference: each other file is printed beside
it with the difference in percent, and anything more than 20 % off is marked. Match
hits/s and the longest still stretch before the cut goes to the editor; cuts/s may
differ when the reference gets its hits from moves inside one shot.

--sheet steps through the first 6 seconds of every file at 6 frames a second (12x3
tiles, one sheet per file), which is where a hook's pace is decided. Put the
reference's sheet beside ours and compare what lands on which beat.
"""
import argparse, json, os, subprocess, sys
from rs_common import find_ffmpeg

try:
    import cv2
    import numpy as np
except ImportError:
    sys.exit("needs OpenCV and numpy:  pip install opencv-python numpy")

CUT_CORR = 0.55        # HSV histogram correlation below this between frames = a new shot
DEBOUNCE = 0.15        # hits closer than this (s) are one hit


def measure(path):
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    prev_g = prev_h = None
    diff, corr, luma = [], [], []
    while True:
        ok, img = cap.read()
        if not ok:
            break
        small = cv2.resize(img, (96, int(96 * img.shape[0] / img.shape[1])), interpolation=cv2.INTER_AREA)
        g = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        h = cv2.calcHist([hsv], [0, 1], None, [32, 16], [0, 180, 0, 256])
        cv2.normalize(h, h)
        luma.append(float(g.mean()))
        if prev_g is None:
            diff.append(0.0); corr.append(1.0)
        else:
            diff.append(float(np.abs(g - prev_g).mean()))
            corr.append(float(cv2.compareHist(prev_h, h, cv2.HISTCMP_CORREL)))
        prev_g, prev_h = g, h
    cap.release()
    n = len(diff)
    if n < 2:
        sys.exit(f"{path}: no frames read")
    dur = n / fps
    d = np.array(diff)
    win = max(3, int(fps))                    # one second either side
    cuts, hits = [], []
    for i in range(1, n):
        lo, hi = max(1, i - win), min(n, i + win + 1)
        local = np.median(d[lo:hi])
        # A cut is a change of colours, or (a jump cut in the same room, where the
        # colours hardly change) a one-frame spike far above everything around it.
        # Measured on a talking head: jump cuts 57 to 73 against about 5 either
        # side; a fast hand move 33.
        is_cut = (corr[i] < CUT_CORR and d[i] > 6) or (d[i] > 40 and d[i] > 6 * local)
        is_peak = d[i] >= d[max(1, i - 1)] and d[i] >= d[min(n - 1, i + 1)] \
            and d[i] > max(10.0, 3.0 * local)
        flash = abs(luma[i] - luma[i - 1]) > 30
        t = i / fps
        if is_cut and (not cuts or t - cuts[-1] > DEBOUNCE):
            cuts.append(t)
        if (is_cut or is_peak or flash) and (not hits or t - hits[-1] > DEBOUNCE):
            hits.append(t)
    marks = [0.0] + hits + [dur]
    gaps = [(b - a, a) for a, b in zip(marks, marks[1:])]
    still, still_at = max(gaps)
    shots = len(cuts) + 1
    return dict(file=os.path.basename(path), duration=round(dur, 2), fps=round(fps, 3),
                cuts=len(cuts), hits=len(hits),
                cuts_per_s=round(len(cuts) / dur, 2), hits_per_s=round(len(hits) / dur, 2),
                avg_shot=round(dur / shots, 2), longest_still=round(still, 2),
                longest_still_at=round(still_at, 2),
                first_hit=round(hits[0], 2) if hits else None,
                cut_times=[round(t, 2) for t in cuts], hit_times=[round(t, 2) for t in hits])


def words(ff, path, r):
    from faster_whisper import WhisperModel
    pcm = subprocess.run([ff, "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", "16000",
                          "-f", "f32le", "-"], capture_output=True).stdout
    audio = np.frombuffer(pcm, np.float32)
    if not len(audio):
        r.update(words=0, words_per_s=0.0, first_word=None); return
    m = WhisperModel(os.environ.get("RS_WHISPER_MODEL", "small"),
                     device=os.environ.get("RS_WHISPER_DEVICE", "cpu"), compute_type="int8")
    segs, _ = m.transcribe(audio, word_timestamps=True, vad_filter=True)
    ws = [w for s in segs for w in (s.words or [])]
    r.update(words=len(ws), words_per_s=round(len(ws) / r["duration"], 2),
             first_word=round(ws[0].start, 2) if ws else None)


def sheet(ff, path, out):
    subprocess.run([ff, "-v", "error", "-y", "-t", "6", "-i", path, "-vf",
                    "fps=6,scale=160:-1,tile=12x3", "-frames:v", "1", out], check=False)


ROWS = [("duration", "s"), ("cuts_per_s", ""), ("hits_per_s", ""), ("avg_shot", "s"),
        ("longest_still", "s"), ("first_hit", "s"), ("words_per_s", ""), ("first_word", "s")]
COMPARE = {"cuts_per_s", "hits_per_s", "avg_shot", "longest_still", "words_per_s"}


def table(results):
    ref = results[0]
    head = f"{'':16}" + "".join(f"{r['file'][:22]:>24}" for r in results)
    print(head)
    for key, unit in ROWS:
        if all(r.get(key) is None for r in results):
            continue
        line = f"{key:16}"
        for j, r in enumerate(results):
            v = r.get(key)
            cell = "-" if v is None else f"{v}{unit}"
            if j and key in COMPARE and v is not None and ref.get(key):
                pct = (v - ref[key]) / ref[key] * 100
                cell += f" ({pct:+.0f}%{' !' if abs(pct) > 20 else ''})"
            line += f"{cell:>24}"
        print(line)
    print(f"{'longest at':16}" + "".join(f"{str(r['longest_still_at']) + 's':>24}" for r in results))
    if len(results) > 1:
        print("\n! = more than 20 % from the reference. Match hits/s and the longest still first.")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("files", nargs="+", help="reference first, then the cuts to compare")
    ap.add_argument("--words", action="store_true", help="also words per second (faster-whisper)")
    ap.add_argument("--sheet", help="first 6 s at 6 fps; one sheet per file, named from this")
    ap.add_argument("--json")
    a = ap.parse_args()
    ff, _ = find_ffmpeg()
    results = []
    for f in a.files:
        r = measure(f)
        if a.words:
            try:
                words(ff, f, r)
            except Exception as e:
                print(f"{r['file']}: words not measured ({e})")
        if a.sheet and ff:
            base, ext = os.path.splitext(a.sheet)
            out = a.sheet if len(a.files) == 1 else f"{base}_{len(results)}{ext or '.jpg'}"
            sheet(ff, f, out)
            r["sheet"] = out
        results.append(r)
    table(results)
    if a.json:
        json.dump(results, open(a.json, "w", encoding="utf-8"), indent=1)
        print(f"\n-> {a.json}")


if __name__ == "__main__":
    main()
