# -*- coding: utf-8 -*-
"""Render the exact frame at each in-point you intend to cut from, and lay them
out labelled so you can look at what you are actually about to use.

  python verify.py SOURCE --points points.json --out sheet.jpg
  python verify.py SOURCE --scan 106.0 124.0 --step 2 --out take.jpg

points.json:
  [{"code": "CA14", "t": 116.6, "note": "child on shoulder"}, ...]

--scan samples one long take densely across its length, which is what you want
before picking a moment inside a take longer than about six seconds.

This exists because contact sheets sample mid-shot. On a twenty-second take the
frame you liked can be ten seconds from the timecode you wrote down, and nothing
catches that until the render.
"""
import argparse, json, math, os, shutil, sys
from rs_common import find_ffmpeg, run, tc

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("needs Pillow:  pip install Pillow")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--points", help="JSON list of {code,t,note}")
    ap.add_argument("--scan", nargs=2, type=float, metavar=("START", "END"))
    ap.add_argument("--step", type=float, default=2.0)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cols", type=int, default=10)
    ap.add_argument("--ffmpeg")
    a = ap.parse_args()

    ff, _ = find_ffmpeg(a.ffmpeg)
    if not ff:
        sys.exit("ffmpeg not found")

    if a.points:
        pts = json.load(open(a.points, encoding="utf-8"))
    elif a.scan:
        s, e = a.scan
        pts, t = [], s + 0.5
        while t < e - 0.2:
            pts.append({"code": "", "t": round(t, 2), "note": ""})
            t += a.step
    else:
        sys.exit("give --points or --scan")

    tmp = a.out + "_frames"
    shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp)
    for i, p in enumerate(pts):
        run([ff, "-hide_banner", "-loglevel", "error", "-y",
             "-ss", f"{p['t']:.2f}", "-i", a.source, "-frames:v", "1", "-q:v", "3",
             os.path.join(tmp, f"{i:03d}.jpg")])

    probe = Image.open(os.path.join(tmp, "000.jpg"))
    vertical = probe.height > probe.width
    CW, CH = (190, 350) if vertical else (280, 180)
    cols = a.cols
    rows = math.ceil(len(pts) / cols)
    sheet = Image.new("RGB", (cols * CW, rows * CH), (12, 12, 12))
    dr = ImageDraw.Draw(sheet)
    try:
        fnt = ImageFont.truetype("arial.ttf", 16)
    except Exception:
        fnt = ImageFont.load_default()

    for i, p in enumerate(pts):
        f = os.path.join(tmp, f"{i:03d}.jpg")
        if not os.path.exists(f):
            continue
        im = Image.open(f); im.draft("RGB", (CW * 2, CH * 2))
        im.thumbnail((CW - 8, CH - 26))
        sheet.paste(im, ((i % cols) * CW + (CW - im.width) // 2,
                         (i // cols) * CH + 22))
        label = f"{p.get('code','')} {tc(p['t'])}".strip()
        dr.text(((i % cols) * CW + 5, (i // cols) * CH + 4), label,
                fill=(255, 215, 80), font=fnt)

    sheet.save(a.out, quality=78, optimize=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"{len(pts)} frames -> {a.out}")
    print("Check each one shows what the edit list claims. Fix the list, not the render.")


if __name__ == "__main__":
    main()
