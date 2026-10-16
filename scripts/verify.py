# -*- coding: utf-8 -*-
"""Render the exact frame at each in-point you intend to cut from, and lay them
out labelled so you can look at what you are actually about to use.

  python verify.py SOURCE --points points.json --out sheet.jpg
  python verify.py SOURCE --scan 106.0 124.0 --step 2 --out take.jpg
  python verify.py --edl edl.json --out check.jpg
  python verify.py --edl edl.json --repeats

points.json:
  [{"code": "CA14", "t": 116.6, "note": "child on shoulder"}, ...]
  A point may name its own file with "src" (a path), so one sheet can check
  in-points across several camera originals.

--scan samples one long take densely across its length, which is what you want
before picking a moment inside a take longer than about six seconds.

--edl checks a whole edit list the way it will be seen: for every clip, the first,
middle and last frame it will show, cut from its camera original, through its 9:16
window and at its speed. A crop that loses the subject halfway through a clip, or a
slow-motion clip that runs into the next take, shows up here and nowhere else.
Writes check_00.jpg, check_01.jpg ... beside --out, 18 clips a sheet.

--edl also lists every moment used twice: two clips from one original whose source
ranges come within 5 s of each other. Neighbouring slices of one take (a stepped
punch-in) count as one shot. --repeats runs only that test and renders nothing; it
exits 1 when it finds any.

This exists because contact sheets sample mid-shot. On a twenty-second take the
frame you liked can be ten seconds from the timecode you wrote down, and nothing
catches that until the render.
"""
import argparse, json, math, os, shutil, sys
from concurrent.futures import ThreadPoolExecutor
from rs_common import (find_ffmpeg, run, tc, probe_source, source_path, speed_of,
                       reframe, frames, find_repeats)

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("needs Pillow:  pip install Pillow")


def font(size):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        return ImageFont.load_default()


def report_repeats(edl, spans, window=5.0):
    reps = find_repeats(edl, spans, window)
    for reel, i, j, src, ti, tj in reps:
        print(f"REPEAT {reel}: clip {j} ({tj:.2f}s) shows the moment clip {i} ({ti:.2f}s) "
              f"already used, in {os.path.basename(src)}")
    print(f"{len(reps)} repeated moments" if reps else "no moment used twice")
    return reps


def check_edl(ff, fp, edl_path, out, source=None, repeats_only=False):
    edl = json.load(open(edl_path, encoding="utf-8"))
    from rs_common import resolve_beats
    resolve_beats(edl, edl_path)
    fps = edl.get("fps", 25)
    W, H = edl.get("width", 1080), edl.get("height", 1920)
    TW, TH = 176, int(176 * H / W)
    tmp = out + "_frames"
    if not repeats_only:
        shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp)
    infos, jobs, shots, spans = {}, [], [], {}
    for r in edl["reels"]:
        for c in r["clips"]:
            path = source_path(edl, c, source)
            if path not in infos:
                infos[path] = probe_source(fp, path)
            si = infos[path]
            sp = speed_of(c, si["fps"], fps)
            span = frames(c["dur"], fps) * sp                 # source seconds shown
            spans[id(c)] = span
            x0, y0, cw, ch, _ = reframe(si["w"], si["h"], W, H, c.get("cx", 0.5),
                                        c.get("cy", 0.5), c.get("z", 1.0))
            vf = (f"crop={int(round(cw))}:{int(round(ch))}:{int(round(x0))}:{int(round(y0))},"
                  f"scale={TW}:{TH}")
            n = len(shots)
            for j, f in enumerate((0.0, 0.5, 1.0)):
                t = c["t"] + f * max(span - 1 / si["fps"], 0)
                jobs.append([ff, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.3f}",
                             "-i", path, "-frames:v", "1", "-vf", vf, "-q:v", "3",
                             os.path.join(tmp, f"{n:03d}_{j}.jpg")])
            shots.append((r["name"], c, sp, os.path.basename(path)))
    reps = report_repeats(edl, spans)
    if repeats_only:
        return 1 if reps else 0
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(run, jobs))

    fnt = font(13)
    per, outs = 18, []
    base, ext = os.path.splitext(out)
    for k in range(0, len(shots), per):
        grp = shots[k:k + per]
        rows = math.ceil(len(grp) / 3)
        sheet = Image.new("RGB", (9 * TW + 16, rows * (TH + 22)), (12, 12, 12))
        dr = ImageDraw.Draw(sheet)
        for i, (reel, c, sp, fname) in enumerate(grp):
            n = k + i
            x, y = (i % 3) * (3 * TW + 8), (i // 3) * (TH + 22)
            lab = (f"#{n + 1} {c.get('code') or fname} {c['t']:.2f}s {frames(c['dur'], fps):.2f}s"
                   + ("" if abs(sp - 1) < 1e-6 else f" @{sp * 100:.0f}%"))
            dr.text((x + 3, y + 4), lab, fill=(255, 215, 80), font=fnt)
            for j in range(3):
                p = os.path.join(tmp, f"{n:03d}_{j}.jpg")
                if os.path.exists(p):
                    sheet.paste(Image.open(p), (x + j * TW, y + 22))
        o = f"{base}_{k // per:02d}{ext or '.jpg'}"
        sheet.save(o, quality=82); outs.append(o)
    shutil.rmtree(tmp, ignore_errors=True)
    print("\n".join(outs))
    print(f"{len(shots)} clips: first, middle and last frame each, cropped and timed as cut.")
    print("Check every one keeps its subject from first frame to last. Fix the list, not the render.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", nargs="?")
    ap.add_argument("--points", help="JSON list of {code,t,note[,src]}")
    ap.add_argument("--scan", nargs=2, type=float, metavar=("START", "END"))
    ap.add_argument("--step", type=float, default=2.0)
    ap.add_argument("--edl", help="check every clip of an edit list, cropped and timed")
    ap.add_argument("--repeats", action="store_true",
                    help="with --edl: only list moments used twice, render nothing")
    ap.add_argument("--out")
    ap.add_argument("--cols", type=int, default=10)
    ap.add_argument("--ffmpeg")
    a = ap.parse_args()

    ff, fp = find_ffmpeg(a.ffmpeg)
    if not ff:
        sys.exit("ffmpeg not found")
    if a.edl:
        if not (a.out or a.repeats):
            sys.exit("give --out, or --repeats")
        return check_edl(ff, fp, a.edl, a.out or "", a.source, a.repeats)
    if not a.out:
        sys.exit("give --out")

    if a.points:
        pts = json.load(open(a.points, encoding="utf-8"))
    elif a.scan:
        s, e = a.scan
        pts, t = [], s + 0.5
        while t < e - 0.2:
            pts.append({"code": "", "t": round(t, 2), "note": ""})
            t += a.step
    else:
        sys.exit("give --points, --scan or --edl")
    if not a.source and any("src" not in p for p in pts):
        sys.exit("give SOURCE, or a \"src\" path on every point")

    tmp = a.out + "_frames"
    shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp)
    for i, p in enumerate(pts):
        run([ff, "-hide_banner", "-loglevel", "error", "-y",
             "-ss", f"{p['t']:.2f}", "-i", p.get("src") or a.source, "-frames:v", "1", "-q:v", "3",
             os.path.join(tmp, f"{i:03d}.jpg")])

    probe = Image.open(os.path.join(tmp, "000.jpg"))
    vertical = probe.height > probe.width
    CW, CH = (190, 350) if vertical else (280, 180)
    cols = a.cols
    rows = math.ceil(len(pts) / cols)
    sheet = Image.new("RGB", (cols * CW, rows * CH), (12, 12, 12))
    dr = ImageDraw.Draw(sheet)
    fnt = font(16)

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
    sys.exit(main())
