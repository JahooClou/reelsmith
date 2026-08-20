# -*- coding: utf-8 -*-
"""Measure footage, generate .cube look LUTs from what was measured, prove them.

  python color.py --measure SRC --groups groups.json
  python color.py --make-luts config.json --out LUTDIR
  python color.py --compare SRC --luts LUTDIR --points points.json --out cmp.jpg

groups.json / config.json share a shape:
  [{"name": "CamA", "start": 0, "end": 233.5}, ...]

--measure prints black point, white point, median, saturation and channel means
per group, and suggests blk / gamma / sat values. Read them before deciding:

  black near 0, white near 1     -> display-referred, already converted
  black 0.10-0.20, white 0.7-0.8 -> genuine log, needs the maker's conversion first
  low saturation, full range     -> weather, not white balance

These are LOOK LUTs for display-referred footage, not log conversions. Applying a
log expansion to already-converted footage crushes shadows and clips highlights,
and the export cannot be recovered.

LUTs are built deliberately conservative: black point at half the measured floor.
Colour tools scale a LUT's strength down, never up, so one that clips at full
strength is unrecoverable while one that is slightly weak can be reinforced.
"""
import argparse, json, math, os, shutil, subprocess, sys
from rs_common import find_ffmpeg, run, tc

try:
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("needs numpy and Pillow:  pip install numpy Pillow")

LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
SIZE = 33


# ---------------------------------------------------------------- measurement
def sample(ff, src, a, b, n, tmp):
    px = []
    for i in range(n):
        t = a + (b - a) * (i + 0.5) / n
        p = os.path.join(tmp, f"{i:03d}.jpg")
        run([ff, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.2f}",
             "-i", src, "-frames:v", "1", "-q:v", "2", p])
        if os.path.exists(p):
            im = Image.open(p).convert("RGB")
            im.thumbnail((256, 256))
            px.append(np.asarray(im, dtype=np.float32) / 255.0)
    return np.concatenate([q.reshape(-1, 3) for q in px], axis=0)


def stats(flat):
    l = flat @ LUMA
    p1, p50, p99 = np.percentile(l, [1, 50, 99])
    mx, mn = flat.max(axis=1), flat.min(axis=1)
    sat = float(np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0).mean())
    return dict(p1=float(p1), p50=float(p50), p99=float(p99), sat=sat,
                rgb=[float(x) for x in flat.mean(axis=0)])


def suggest(s, target_median=0.42, target_sat=0.40):
    blk = s["p1"] * 0.5                     # half the floor: headroom, not clipping
    m = (s["p50"] - blk) / max(s["p99"] - blk, 1e-6)
    gamma = math.log(target_median) / math.log(max(m, 1e-6))
    sat = min(1.45, max(1.05, target_sat / max(s["sat"], 1e-6)))
    contrast = 0.15 if s["p99"] > 0.985 else 0.18   # near-clipped whites: go gentle
    return dict(blk=round(blk, 4), wht=round(s["p99"], 4), gamma=round(gamma, 3),
                contrast=contrast, sat=round(sat, 2), cool=0.030, redguard=0.80)


def kind(s):
    if s["p1"] > 0.08 and s["p99"] < 0.85:
        return "LOG (needs maker's conversion LUT first)"
    if s["p1"] < 0.08 and s["p99"] > 0.88:
        return "display-referred"
    return "unclear, inspect manually"


# ---------------------------------------------------------------------- LUTs
def scurve(x, amt, pivot=0.45):
    return np.where(x < pivot,
                    pivot * (x / pivot) ** (1 + amt),
                    1 - (1 - pivot) * ((1 - x) / (1 - pivot)) ** (1 + amt))


def look(rgb, c):
    x = np.clip((rgb - c["blk"]) / (c["wht"] - c["blk"]), 0, 1)
    x = np.power(np.clip(x, 1e-6, 1), c["gamma"])
    x = scurve(x, c["contrast"])
    l = (x * LUMA).sum(axis=-1, keepdims=True)
    hi = np.clip((x - c["redguard"]) / (1 - c["redguard"]), 0, 1)
    boost = c["sat"] - (c["sat"] - 1.0) * hi          # roll off before clipping
    x = l + (x - l) * boost
    w = np.clip(1 - l, 0, 1) ** 2
    x[..., 2:3] += c["cool"] * w
    x[..., 0:1] -= c["cool"] * w * 0.55
    return np.clip(x, 0, 1)


def write_cube(path, name, c, note=""):
    g = np.linspace(0, 1, SIZE, dtype=np.float32)
    R, G, B = np.meshgrid(g, g, g, indexing="ij")
    grid = np.stack([R, G, B], -1).transpose(2, 1, 0, 3).reshape(-1, 3)
    out = look(grid, c)
    with open(path, "w", encoding="ascii") as f:
        f.write(f'TITLE "{name}"\n')
        if note:
            f.write(f"# {note}\n")
        f.write("# Look LUT for display-referred footage. Not a log conversion.\n")
        f.write(f"LUT_3D_SIZE {SIZE}\nDOMAIN_MIN 0.0 0.0 0.0\nDOMAIN_MAX 1.0 1.0 1.0\n\n")
        for v in out:
            f.write(f"{v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")


# ------------------------------------------------------------------------ cli
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--measure"); ap.add_argument("--groups")
    ap.add_argument("--make-luts"); ap.add_argument("--out")
    ap.add_argument("--compare"); ap.add_argument("--luts"); ap.add_argument("--points")
    ap.add_argument("--samples", type=int, default=14)
    ap.add_argument("--ffmpeg")
    a = ap.parse_args()
    ff, _ = find_ffmpeg(a.ffmpeg)

    if a.measure:
        groups = json.load(open(a.groups, encoding="utf-8"))
        tmp = "_cmeas"; shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp)
        cfg = []
        print(f"{'group':16}{'p1':>8}{'p50':>8}{'p99':>8}{'sat':>8}   kind")
        print("-" * 74)
        for g in groups:
            s = stats(sample(ff, a.measure, g["start"], g["end"], a.samples, tmp))
            sug = suggest(s)
            print(f"{g['name']:16}{s['p1']:8.3f}{s['p50']:8.3f}{s['p99']:8.3f}"
                  f"{s['sat']:8.3f}   {kind(s)}")
            print(f"{'':16}-> blk={sug['blk']} wht={sug['wht']} gamma={sug['gamma']} "
                  f"sat={sug['sat']} contrast={sug['contrast']}")
            cfg.append({"name": g["name"], "start": g["start"], "end": g["end"], **sug})
        shutil.rmtree(tmp, ignore_errors=True)
        out = (a.out or "lut_config.json")
        json.dump(cfg, open(out, "w", encoding="utf-8"), indent=2)
        print(f"\nsuggested config -> {out}   (edit before --make-luts if you like)")
        return

    if a.make_luts:
        cfg = json.load(open(a.make_luts, encoding="utf-8"))
        os.makedirs(a.out, exist_ok=True)
        for c in cfg:
            p = os.path.join(a.out, f"{c['name']}.cube")
            write_cube(p, c["name"], c, c.get("note", ""))
            print(f"{c['name']:20} {os.path.getsize(p)//1024:5d} KB -> {p}")
        json.dump(cfg, open(os.path.join(a.out, "lut_config.json"), "w",
                            encoding="utf-8"), indent=2)
        print("\nApply at full strength first and re-measure with --compare.")
        return

    if a.compare:
        cfg = json.load(open(os.path.join(a.luts, "lut_config.json"), encoding="utf-8"))
        pts = json.load(open(a.points, encoding="utf-8")) if a.points else None
        if not pts:
            pts = [{"code": c["name"], "t": (c["start"] + c["end"]) / 2,
                    "lut": c["name"]} for c in cfg]
        # absolute: the LUT pass runs with cwd set to the LUT dir, so a relative
        # temp path would resolve against that instead of here
        tmp = os.path.abspath("_ccmp")
        shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp)
        pairs = []
        print(f"{'frame':22}{'p1':>18}{'median':>18}{'sat':>18}")
        for i, p in enumerate(pts):
            lut = p.get("lut") or _lut_for(cfg, p["t"])
            raw = os.path.join(tmp, f"{i}r.png"); grd = os.path.join(tmp, f"{i}g.png")
            run([ff, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{p['t']:.2f}",
                 "-i", a.compare, "-frames:v", "1", raw])
            run([ff, "-hide_banner", "-loglevel", "error", "-y", "-i", raw,
                 "-vf", f"lut3d=file={lut}.cube", "-frames:v", "1", grd], cwd=a.luts)
            sa = stats(np.asarray(Image.open(raw).convert("RGB"), np.float32).reshape(-1, 3) / 255)
            sb = stats(np.asarray(Image.open(grd).convert("RGB"), np.float32).reshape(-1, 3) / 255)
            warn = "  <- CLIPPED" if sb["p1"] < 0.004 else ""
            print(f"{p.get('code', lut):22}{sa['p1']:.3f}->{sb['p1']:.3f}   "
                  f"{sa['p50']:.3f}->{sb['p50']:.3f}   {sa['sat']:.3f}->{sb['sat']:.3f}{warn}")
            pairs.append((raw, grd, p.get("code", lut)))
        _sheet(pairs, a.out or "lut_compare.jpg")
        shutil.rmtree(tmp, ignore_errors=True)
        print("\nIf a black point lands under 0.004 the LUT is clipping. Lower")
        print("contrast or raise blk, regenerate, and compare again.")
        return

    ap.print_help()


def _lut_for(cfg, t):
    for c in cfg:
        if c["start"] <= t < c["end"]:
            return c["name"]
    return cfg[-1]["name"]


def _sheet(pairs, out):
    im0 = Image.open(pairs[0][0])
    vert = im0.height > im0.width
    CW, CH = (216, 384) if vert else (320, 200)
    sheet = Image.new("RGB", (len(pairs) * CW, 2 * CH + 28), (14, 14, 14))
    dr = ImageDraw.Draw(sheet)
    try:
        fnt = ImageFont.truetype("arial.ttf", 16)
    except Exception:
        fnt = ImageFont.load_default()
    for i, (raw, grd, code) in enumerate(pairs):
        for row, p in ((0, raw), (1, grd)):
            sheet.paste(Image.open(p).convert("RGB").resize((CW, CH)), (i * CW, 24 + row * CH))
        dr.text((i * CW + 5, 4), code, fill=(255, 215, 80), font=fnt)
    dr.text((5, 24 + 2 * CH + 4), "top: original    bottom: with LUT",
            fill=(200, 200, 200), font=fnt)
    sheet.save(out, quality=80)
    print(f"\ncomparison -> {out}")


if __name__ == "__main__":
    main()
