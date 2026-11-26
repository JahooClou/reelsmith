# -*- coding: utf-8 -*-
"""Render caption plates as transparent PNGs for overlay.

  python captions.py captions.json --out CAPDIR --font PATH [--variation "Bold Condensed"]
  python captions.py captions.json --out CAPDIR --font PATH --faces faces.json

captions.json:
  [{"id": "cap01", "text": "ON SCREEN TEXT", "y": 430, "align": "center"}, ...]

Uses PIL rather than ffmpeg's drawtext, for one specific reason: drawtext goes
through FreeType and renders the DEFAULT instance of a variable font. Ask it for
Bold Condensed and it gives you Regular, with no warning. PIL can select a named
instance, so what you asked for is what you get.

You also get real control over the block behind the text, padding and letter
spacing, none of which drawtext offers.

On placement: a fixed y that reads well over a wide shot lands on a face in a
close-up. Set y per caption, or let --faces place it. --faces takes the face boxes
qc.py --faces-out measured on a clean render, and places every plate whose id is in
that file and whose y is missing or "auto". The order of preference:

  1. full size, inside the interface margins, off every face: the bottom of the safe
     area, then just under the lowest chin, then just above the highest head, then
     every height up the frame
  2. the same at 85 % and then 72 % of the size
  3. still nothing: give up the margins (keep 30 px from the edge), never the face
  4. still nothing: the bottom of the safe area at 72 %, with a warning. Shorten the
     line, end the caption sooner, or reframe the clip.

A caption jumps; it never slides, because a slide can cross the face.
Interface margins are those of shortform.md: "loose" (default) or "meta".
"""
import argparse, json, math, os, sys

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("needs Pillow:  pip install Pillow")

MARGINS = {"meta": dict(top=270, bottom=670, side=65),          # same as qc.py
           "loose": dict(top=250, bottom=320, side=40)}


def load_font(path, size, variation=None):
    f = ImageFont.truetype(path, size)
    if variation:
        try:
            f.set_variation_by_name(variation)
        except Exception:
            names = []
            try:
                names = [n.decode() if isinstance(n, bytes) else n
                         for n in f.get_variation_names()]
            except Exception:
                pass
            sys.exit(f"variation '{variation}' not found. available: {names}")
    return f


def layout(d, spec, W, font_path, variation, size):
    """Fit the text to the width; return the font, its size, text width and block size."""
    text = spec["text"]
    maxw = spec.get("maxw", W - 150)
    pad = spec.get("pad", 28)
    track = spec.get("tracking", 0)
    while size > 20:
        f = load_font(font_path, size, variation)
        if _width(d, text, f, track) <= maxw:
            break
        size -= 2
    f = load_font(font_path, size, variation)
    tw = _width(d, text, f, track)
    th = size * 1.06
    return f, size, tw, th, tw + 2 * pad, th + pad * 1.4


def x_of(spec, W, tw):
    align = spec.get("align", "center")
    return {"center": (W - tw) / 2, "left": spec.get("x", 80),
            "right": W - spec.get("x", 80) - tw}[align]


def hits(box, faces):
    x, y, w, h = box
    return any(min(x + w, fx + fw) > max(x, fx) and min(y + h, fy + fh) > max(y, fy)
               for fx, fy, fw, fh in faces)


def place(d, spec, W, H, font_path, variation, faces, margins):
    """Choose size and y for one caption (see the module notes). Returns size, y, note."""
    pad = spec.get("pad", 28)
    base = spec.get("size", 74)
    k = H / 1920
    g = {s: v * k for s, v in MARGINS[margins].items()}
    edge = {"top": 30 * k, "bottom": 30 * k}
    gap = 24 * k
    tops = [fy for fx, fy, fw, fh in faces]
    bottoms = [fy + fh for fx, fy, fw, fh in faces]

    def try_at(scale, lim):
        _, size, tw, th, bw, bh = layout(d, spec, W, font_path, variation, int(base * scale))
        x = x_of(spec, W, tw) - pad
        # PIL fills a rectangle's last row too, so the plate is one pixel taller than bh
        lo, hi = math.ceil(lim["top"]), math.floor(H - lim["bottom"] - bh) - 1
        cands = [hi]
        if bottoms:
            cands.append(max(bottoms) + gap)
        if tops:
            cands.append(min(tops) - gap - bh)
        cands += list(range(int(hi), int(lo) - 1, -int(20 * k) or -1))
        for y in cands:
            if lo <= y <= hi and not hits((x, y, bw, bh), faces):
                return size, y
        return None

    for scale in (1.0, 0.85, 0.72):
        r = try_at(scale, g)
        if r:
            return r[0], r[1], "" if scale == 1.0 else f"shrunk to {int(scale * 100)} %"
    if margins != "loose":                       # the looser margins before none at all
        loose = {s: v * k for s, v in MARGINS["loose"].items()}
        r = try_at(0.72, loose)
        if r:
            return r[0], r[1], f"inside the loose margins only, to stay off the face"
    r = try_at(0.72, edge)
    if r:
        return r[0], r[1], "outside the interface margins to stay off the face"
    _, size, _, _, _, bh = layout(d, spec, W, font_path, variation, int(base * 0.72))
    return size, math.floor(H - g["bottom"] - bh) - 1, "COVERS A FACE: shorten it, end it sooner or reframe"


def render(spec, W, H, font_path, variation, fg, bg, out, size=None, y=None):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pad = spec.get("pad", 28)
    track = spec.get("tracking", 0)
    f, size, tw, th, _, _ = layout(d, spec, W, font_path, variation, size or spec.get("size", 74))
    y0 = spec.get("y", 430) if y is None else y
    x0 = x_of(spec, W, tw)
    if bg:
        d.rectangle([x0 - pad, y0, x0 + tw + pad, y0 + th + pad * 1.4], fill=bg)
    _draw(d, x0, y0 + pad * 0.62, spec["text"], f, fg, track)
    im.save(out)
    return size, y0


def _width(d, s, f, track):
    if not track:
        return d.textlength(s, font=f)
    return sum(d.textlength(c, font=f) + track for c in s) - track


def _draw(d, x, y, s, f, fill, track):
    if not track:
        d.text((x, y), s, font=f, fill=fill); return
    for c in s:
        d.text((x, y), c, font=f, fill=fill)
        x += d.textlength(c, font=f) + track


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("captions")
    ap.add_argument("--out", required=True)
    ap.add_argument("--font", required=True)
    ap.add_argument("--variation", help='e.g. "Bold Condensed" for a variable font')
    ap.add_argument("--width", type=int, default=1080)
    ap.add_argument("--height", type=int, default=1920)
    ap.add_argument("--fg", default="251,244,232")
    ap.add_argument("--bg", default="0,0,0,235", help="block behind text; 'none' to omit")
    ap.add_argument("--faces", help="qc.py --faces-out file: place captions off the faces")
    ap.add_argument("--margins", choices=list(MARGINS), default="loose")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    fg = tuple(int(v) for v in a.fg.split(",")) + (255,)
    fg = fg[:4]
    bg = None if a.bg.lower() == "none" else tuple(int(v) for v in a.bg.split(","))
    faces = json.load(open(a.faces, encoding="utf-8")) if a.faces else {}

    specs = json.load(open(a.captions, encoding="utf-8"))
    placed = []
    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    for s in specs:
        p = os.path.join(a.out, f"{s['id']}.png")
        size = y = None; note = ""
        if s["id"] in faces and s.get("y", "auto") == "auto":
            side = MARGINS[a.margins]["side"] * a.height / 1920
            fit = int(a.width - 2 * side - 2 * s.get("pad", 28) - 2)   # the block inside the sides
            s = dict(s, maxw=min(s.get("maxw", a.width - 150), fit))
            size, y, note = place(probe, s, a.width, a.height, a.font, a.variation,
                                  faces[s["id"]]["faces"], a.margins)
        elif s.get("y") == "auto":
            note = "no face boxes for this id; y 430"
            s = dict(s, y=430)
        size, y = render(s, a.width, a.height, a.font, a.variation, fg, bg, p, size, y)
        placed.append(dict(s, y=round(y), size=size))
        print(f"{s['id']:12} {size:3d}px  y={y:6.0f}  {s['text'][:40]:40} {note}")
    if a.faces:
        out = os.path.join(a.out, "placed.json")
        json.dump(placed, open(out, "w", encoding="utf-8"), indent=1)
        print(f"\nplacements -> {out}")
    print(f"\n{len(specs)} plates -> {a.out}")
    print("Overlay with: -i clip -i plate -filter_complex '[0:v][1:v]overlay=0:0'")


if __name__ == "__main__":
    main()
