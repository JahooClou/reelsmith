# -*- coding: utf-8 -*-
"""Render caption plates as transparent PNGs for overlay.

  python captions.py captions.json --out CAPDIR --font PATH [--variation "Bold Condensed"]

captions.json:
  [{"id": "cap01", "text": "ON SCREEN TEXT", "y": 430, "align": "center"}, ...]

Uses PIL rather than ffmpeg's drawtext, for one specific reason: drawtext goes
through FreeType and renders the DEFAULT instance of a variable font. Ask it for
Bold Condensed and it gives you Regular, with no warning. PIL can select a named
instance, so what you asked for is what you get.

You also get real control over the block behind the text, padding and letter
spacing, none of which drawtext offers.

On placement: a fixed y that reads well over a wide shot lands on a face in a
close-up. Set y per caption, or render the picture clean and place text in an
editor. Keep clear of platform furniture — roughly the top 250px and bottom 320px
of a 1080x1920 frame.
"""
import argparse, json, os, sys

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("needs Pillow:  pip install Pillow")


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


def render(spec, W, H, font_path, variation, fg, bg, out):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    text = spec["text"]
    size = spec.get("size", 74)
    maxw = spec.get("maxw", W - 150)
    pad = spec.get("pad", 28)
    track = spec.get("tracking", 0)

    while size > 20:
        f = load_font(font_path, size, variation)
        w = _width(d, text, f, track)
        if w <= maxw:
            break
        size -= 2
    f = load_font(font_path, size, variation)
    tw = _width(d, text, f, track)
    th = size * 1.06
    y0 = spec.get("y", 430)
    align = spec.get("align", "center")
    x0 = {"center": (W - tw) / 2, "left": spec.get("x", 80),
          "right": W - spec.get("x", 80) - tw}[align]

    if bg:
        d.rectangle([x0 - pad, y0, x0 + tw + pad, y0 + th + pad * 1.4], fill=bg)
    _draw(d, x0, y0 + pad * 0.62, text, f, fg, track)
    im.save(out)
    return size


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
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    fg = tuple(int(v) for v in a.fg.split(",")) + (255,)
    fg = fg[:4]
    bg = None if a.bg.lower() == "none" else tuple(int(v) for v in a.bg.split(","))

    specs = json.load(open(a.captions, encoding="utf-8"))
    for s in specs:
        p = os.path.join(a.out, f"{s['id']}.png")
        size = render(s, a.width, a.height, a.font, a.variation, fg, bg, p)
        print(f"{s['id']:12} {size:3d}px  y={s.get('y', 430):4}  {s['text'][:46]}")
    print(f"\n{len(specs)} plates -> {a.out}")
    print("Overlay with: -i clip -i plate -filter_complex '[0:v][1:v]overlay=0:0'")


if __name__ == "__main__":
    main()
