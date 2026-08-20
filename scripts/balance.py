# -*- coding: utf-8 -*-
"""Per-shot balance plus one shared look. This is what actually matches cameras.

  python balance.py edl.json --source SRC --out GRADEDIR
  python balance.py edl.json --source SRC --out GRADEDIR --report cmp.jpg

Writes `look.cube` and `shot_params.json`. `render.py --balance GRADEDIR` consumes
both.

WHY NOT ONE LUT PER CAMERA

A camera-level LUT cannot match shots. One gamma derived from a segment median
darkens every shot above that median and lightens every one below — the opposite
of matching. Exposure, white balance and saturation vary shot to shot, often by
more than they vary between cameras, so they have to be corrected shot to shot.

The order is the order colourists use: balance first, look second.

  colorlevels   levels + white balance, per channel
  eq gamma      exposure to a common target
  lut3d         the shared look, identical on every shot
  eq saturation corrected LAST, against a measured result

Three things this gets right that are easy to get wrong:

1. eq computes x^(1/gamma), NOT x^gamma. The exponent has to be inverted or every
   shot moves the wrong way.
2. White balance is measured on near-neutral pixels only. A whole-frame average on
   footage with a strong coloured element reads that element as a cast and pushes
   the correction the opposite way.
3. Saturation is measured after the chain, not predicted from the source. Levels
   stretching and the look each raise it on their own, so a multiplier computed
   from the source overshoots.
"""
import argparse, json, math, os, subprocess, sys

try:
    import numpy as np
    from PIL import Image
except ImportError:
    sys.exit("needs numpy and Pillow:  pip install numpy Pillow")

from rs_common import find_ffmpeg, run

LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)

T_BLACK, T_MID, T_SAT = 0.012, 0.400, 0.420
SAT_MIN, SAT_MAX = 0.80, 1.30
WB_STRENGTH = 0.65          # 1.0 fully neutral; less keeps the scene's character
BLACK_FRACTION = 0.35       # black point at a fraction of measured p1, not on it
OUT_BLACK = 0.016           # lifted output floor so shadows do not sit at zero


# ------------------------------------------------------------------ measurement
def measure(ff, src, t, span=1.2, n=5, tmp="_bal", vf=None, cwd=None):
    """Average several frames across the clip. One frame lets a flash define it.

    Both passes — before and after the chain — go through here with the same
    sample times, otherwise you are comparing an average against a single frame
    and the correction chases a difference that is not real.
    """
    os.makedirs(tmp, exist_ok=True)
    px = []
    for i in range(n):
        tt = t + span * i / max(n - 1, 1)
        p = os.path.abspath(os.path.join(tmp, "_m.png"))
        cmd = [ff, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{tt:.2f}",
               "-i", src]
        if vf:
            cmd += ["-vf", vf]
        cmd += ["-frames:v", "1", p]
        run(cmd, cwd=cwd)
        im = Image.open(p).convert("RGB"); im.thumbnail((240, 240))
        px.append(np.asarray(im, np.float32) / 255.0)
    f = np.concatenate([q.reshape(-1, 3) for q in px], 0)
    l = f @ LUMA
    mx, mn = f.max(1), f.min(1)
    sat = np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0)
    neutral = f[(sat < 0.16) & (l > 0.18) & (l < 0.85)]
    wb = neutral.mean(0) if len(neutral) > 300 else f.mean(0)
    return dict(p1=float(np.percentile(l, 1)), p50=float(np.median(l)),
                p99=float(np.percentile(l, 99)), sat=float(sat.mean()),
                wb=[float(v) for v in wb], neutral_px=int(len(neutral)))


def params(m):
    lo, hi = m["p1"], m["p99"]

    wb = np.array(m["wb"], np.float32)
    g = float(wb[1])
    gain = np.array([g / max(wb[0], 1e-6), 1.0, g / max(wb[2], 1e-6)], np.float32)
    gain = np.clip(1.0 + (gain - 1.0) * WB_STRENGTH, 0.85, 1.18)

    imin = float(np.clip(lo * BLACK_FRACTION, 0.0, 0.5))
    imax = float(np.clip(hi + 0.004, 0.5, 1.0))
    ch = np.clip(imax / gain, 0.35, 1.0)

    mid = min(max((m["p50"] - imin) / max(imax - imin, 1e-6), 0.05), 0.95)
    exponent = math.log(T_MID) / math.log(mid)
    gamma = min(max(1.0 / exponent, 0.55), 1.85)      # eq does x^(1/gamma)

    return dict(imin=round(imin, 4), rimax=round(float(ch[0]), 4),
                gimax=round(float(ch[1]), 4), bimax=round(float(ch[2]), 4),
                gamma=round(gamma, 3))


def sat_correction(post):
    return round(min(max(T_SAT / max(post, 1e-6), SAT_MIN), SAT_MAX), 3)


# ------------------------------------------------------------------ filter chain
def _levels(p):
    return (f"colorlevels=rimin={p['imin']}:gimin={p['imin']}:bimin={p['imin']}"
            f":rimax={p['rimax']}:gimax={p['gimax']}:bimax={p['bimax']}"
            f":romin={OUT_BLACK}:gomin={OUT_BLACK}:bomin={OUT_BLACK},"
            f"eq=gamma={p['gamma']}")


def vf_base(p, look=None):
    f = _levels(p)
    return f + (f",lut3d=file={look}" if look else "")


def vf_full(p, look, sat):
    return vf_base(p, look) + f",eq=saturation={sat:.3f}"


# ------------------------------------------------------------------- shared look
def build_look(path, contrast=0.10, cool=0.018):
    """Gentle by design. The per-shot balance already did the heavy lifting; this
    only adds character, and anything stronger fights the matching."""
    N = 33
    g = np.linspace(0, 1, N, np.float32)
    R, G, B = np.meshgrid(g, g, g, indexing="ij")
    x = np.stack([R, G, B], -1).transpose(2, 1, 0, 3).reshape(-1, 3).copy()
    piv = 0.46
    x = np.where(x < piv, piv * (x / piv) ** (1 + contrast),
                 1 - (1 - piv) * ((1 - x) / (1 - piv)) ** (1 + contrast))
    l = (x * LUMA).sum(-1, keepdims=True)
    w = np.clip(1 - l, 0, 1) ** 2
    x[..., 2:3] += cool * w
    x[..., 0:1] -= cool * 0.55 * w
    x = np.clip(x, 0, 1)
    with open(path, "w", encoding="ascii") as f:
        f.write('TITLE "look"\n')
        f.write("# Shared look. Applied AFTER per-shot balance, never instead of it.\n")
        f.write("# Saturation is deliberately absent: it is corrected per shot,\n")
        f.write("# measured after this LUT rather than predicted before it.\n")
        f.write(f"LUT_3D_SIZE {N}\nDOMAIN_MIN 0.0 0.0 0.0\nDOMAIN_MAX 1.0 1.0 1.0\n\n")
        for v in x:
            f.write(f"{v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")


# --------------------------------------------------------------------------- cli
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edl")
    ap.add_argument("--source", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--contrast", type=float, default=0.10)
    ap.add_argument("--cool", type=float, default=0.018)
    ap.add_argument("--target-mid", type=float, default=0.40)
    ap.add_argument("--target-sat", type=float, default=0.42)
    ap.add_argument("--ffmpeg")
    a = ap.parse_args()

    global T_MID, T_SAT
    T_MID, T_SAT = a.target_mid, a.target_sat

    ff, _ = find_ffmpeg(a.ffmpeg)
    if not ff:
        sys.exit("ffmpeg not found")
    os.makedirs(a.out, exist_ok=True)
    look_name = "look.cube"
    build_look(os.path.join(a.out, look_name), a.contrast, a.cool)

    edl = json.load(open(a.edl, encoding="utf-8"))
    clips = [(c["t"], c.get("dur", 1.2), c.get("code", ""))
             for r in edl["reels"] for c in r["clips"]]
    uniq = sorted({round(t, 2) for t, _, _ in clips})
    span = {round(t, 2): d for t, d, _ in clips}
    code = {round(t, 2): c for t, _, c in clips}

    print(f"{len(uniq)} unique clips   source -> after chain -> corrected")
    print(f"{'code':8}{'t':>9}{'median':>18}{'saturation':>28}{'gamma':>8}")
    print("-" * 74)
    cache = {}
    for t in uniq:
        sp = min(span[t], 2.0)
        m = measure(ff, a.source, t, span=sp)
        p = params(m)
        # same sample times, now through the chain, so the two are comparable
        after = measure(ff, a.source, t, span=sp,
                        tmp=os.path.join(a.out, "_probe"),
                        vf=vf_base(p, look_name), cwd=a.out)
        post, mid_after = after["sat"], after["p50"]
        sat = sat_correction(post)
        cache[f"{t:.2f}"] = {"measured": m, "params": p,
                             "post_sat": round(post, 3), "sat": sat}
        flag = "  capped" if sat in (SAT_MIN, SAT_MAX) else ""
        print(f"{code[t][:7]:8}{t:9.2f}  {m['p50']:.3f}->{mid_after:.3f}   "
              f"{m['sat']:.3f}->{post:.3f} x{sat:.2f} ->{post*sat:.3f}   "
              f"{p['gamma']:6.2f}{flag}")

    import shutil as _sh
    for d in ("_bal", os.path.join(a.out, "_probe")):
        _sh.rmtree(d, ignore_errors=True)

    json.dump({"look": look_name, "target_mid": T_MID, "target_sat": T_SAT,
               "clips": cache},
              open(os.path.join(a.out, "shot_params.json"), "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)

    mids = [c["measured"]["p50"] for c in cache.values()]
    print(f"\nsource medians spanned {min(mids):.3f} to {max(mids):.3f}")
    print(f"-> {a.out}\\shot_params.json  and  {a.out}\\{look_name}")
    print("Then: render.py edl.json --source SRC --out DIR --balance " + a.out)
    print("\nCapped shots are ones the targets could not reach without looking")
    print("artificial. A genuinely grey shot should stay grey.")


if __name__ == "__main__":
    main()
