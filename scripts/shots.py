# -*- coding: utf-8 -*-
"""Detect shots and build a labelled contact sheet.

  python shots.py SOURCE --out DIR
  python shots.py SOURCE --out DIR --segments segments.json

segments.json lets you detect per camera or per section with its own threshold,
which matters because a threshold tuned for handheld action merges cuts in slow
motion, where consecutive frames are far more alike:

  [{"name": "CamA", "code": "CA", "start": 0,   "end": 233.5, "threshold": 0.14},
   {"name": "SlowMo","code": "SL","start": 233.5,"end": 583.0, "threshold": 0.10}]

Writes shots.tsv (code, segment, in, out, duration) and contact.jpg.

IMPORTANT: the contact sheet samples ONE frame per shot, near the middle. For a
long take that frame can be many seconds from the shot's start. Never take an
in-point from this sheet alone — run verify.py on the in-points you intend to use.
"""
import argparse, json, math, os, re, shutil, sys
from rs_common import find_ffmpeg, run, tc

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("needs Pillow:  pip install Pillow")

PALETTE = [(255, 215, 80), (120, 255, 140), (255, 140, 200),
           (120, 220, 255), (255, 175, 90), (200, 180, 255)]


def detect(ff, src, a, b, thr, min_len):
    r = run([ff, "-hide_banner", "-ss", str(a), "-to", str(b), "-i", src,
             "-filter:v", f"select='gt(scene,{thr})',showinfo",
             "-an", "-f", "null", "-"])
    hits = [round(a + float(t), 2) for t in re.findall(r"pts_time:([\d.]+)", r.stderr)]
    cuts = [a]
    for t in hits:
        if t - cuts[-1] >= min_len:
            cuts.append(t)
    return cuts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--out", required=True)
    ap.add_argument("--segments", help="JSON list of segments; omit to treat whole file as one")
    ap.add_argument("--threshold", type=float, default=0.14)
    ap.add_argument("--min-len", type=float, default=0.7)
    ap.add_argument("--ffmpeg")
    ap.add_argument("--cols", type=int, default=12)
    a = ap.parse_args()

    ff, fp = find_ffmpeg(a.ffmpeg)
    if not ff:
        sys.exit("ffmpeg not found; run ffmpeg_tools.py --locate")
    os.makedirs(a.out, exist_ok=True)

    from rs_common import probe
    dur = probe(fp, a.source)["duration"] if fp else 0.0

    if a.segments:
        segs = json.load(open(a.segments, encoding="utf-8"))
    else:
        segs = [{"name": "all", "code": "SH", "start": 0.0,
                 "end": dur or 10 ** 9, "threshold": a.threshold}]

    shots = []
    for s in segs:
        thr = s.get("threshold", a.threshold)
        cuts = detect(ff, a.source, s["start"], s["end"], thr, a.min_len)
        n = 0
        for i, t in enumerate(cuts):
            e = cuts[i + 1] if i + 1 < len(cuts) else s["end"]
            if e - t < a.min_len:
                continue
            n += 1
            shots.append({"code": f"{s['code']}{n:02d}", "segment": s["name"],
                          "start": round(t, 2), "end": round(e, 2),
                          "dur": round(e - t, 2)})
        print(f"{s['name']:14} {n:3d} shots   {tc(s['start'])} - {tc(s['end'])}   thr={thr}")

    tsv = os.path.join(a.out, "shots.tsv")
    with open(tsv, "w", encoding="utf-8") as f:
        f.write("code\tsegment\tin\tout\tdur\n")
        for s in shots:
            f.write(f"{s['code']}\t{s['segment']}\t{s['start']}\t{s['end']}\t{s['dur']}\n")
    json.dump(shots, open(os.path.join(a.out, "shots.json"), "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)

    # contact sheet, sampled at 45% into each shot
    tmp = os.path.join(a.out, "_frames")
    shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp)
    for i, s in enumerate(shots):
        mid = s["start"] + (s["end"] - s["start"]) * 0.45
        run([ff, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{mid:.2f}",
             "-i", a.source, "-frames:v", "1", "-q:v", "4",
             os.path.join(tmp, f"{i:04d}.jpg")])

    first = Image.open(os.path.join(tmp, "0000.jpg"))
    vertical = first.height > first.width
    CW, CH = (158, 300) if vertical else (250, 160)
    cols = a.cols
    rows = math.ceil(len(shots) / cols)
    sheet = Image.new("RGB", (cols * CW, rows * CH), (12, 12, 12))
    dr = ImageDraw.Draw(sheet)
    try:
        fnt = ImageFont.truetype("arial.ttf", 16)
    except Exception:
        fnt = ImageFont.load_default()
    segnames = [s["name"] for s in segs]
    for i, s in enumerate(shots):
        p = os.path.join(tmp, f"{i:04d}.jpg")
        if not os.path.exists(p):
            continue
        im = Image.open(p); im.draft("RGB", (CW * 2, CH * 2))
        im.thumbnail((CW - 6, CH - 24))
        sheet.paste(im, ((i % cols) * CW + (CW - im.width) // 2,
                         (i // cols) * CH + 20))
        col = PALETTE[segnames.index(s["segment"]) % len(PALETTE)]
        dr.text(((i % cols) * CW + 4, (i // cols) * CH + 3),
                f"{s['code']} {tc(s['start'])}", fill=col, font=fnt)
    out = os.path.join(a.out, "contact.jpg")
    sheet.save(out, quality=72, optimize=True)
    shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{len(shots)} shots -> {tsv}")
    print(f"contact sheet -> {out}")
    print("\nThese frames are sampled MID-SHOT. Before cutting, run verify.py on")
    print("the in-points you plan to use and look at the actual frames.")


if __name__ == "__main__":
    main()
