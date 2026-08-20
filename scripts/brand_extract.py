# -*- coding: utf-8 -*-
"""Extract brand values from what already exists, rather than guessing them.

  python brand_extract.py --images logo.png poster.jpg --out brand.json
  python brand_extract.py --psd artwork.psd --out brand.json

Images: dominant colours by k-means-ish quantisation, reported as hex with the
share of pixels each covers, so you can tell a brand colour from an accident.

PSD: canvas size, the layer tree, text layer contents, and the FONT NAMES the
designer actually used. That last one is usually the fastest way to answer "what
typeface is this" without asking anyone.

Sample real pixels. A hex value read off a screenshot is a hex value read off a
screenshot with someone's display profile baked into it.
"""
import argparse, collections, json, os, sys, warnings

warnings.filterwarnings("ignore", category=DeprecationWarning, module="PIL")

try:
    from PIL import Image
except ImportError:
    sys.exit("needs Pillow:  pip install Pillow")


def hexof(rgb):
    return "#{:02X}{:02X}{:02X}".format(*[int(c) for c in rgb[:3]])


def palette(path, n=6, ignore_near_white=False):
    im = Image.open(path).convert("RGBA")
    im.thumbnail((400, 400))
    px = [p for p in im.getdata() if p[3] > 200]
    if not px:
        return []
    if ignore_near_white:
        px = [p for p in px if not (p[0] > 245 and p[1] > 245 and p[2] > 245)] or px
    q = Image.new("RGB", (len(px), 1))
    q.putdata([p[:3] for p in px])
    q = q.quantize(colors=n, method=Image.MEDIANCUT)
    pal = q.getpalette()[: n * 3]
    counts = collections.Counter(q.getdata())
    total = sum(counts.values())
    out = []
    for idx, cnt in counts.most_common(n):
        rgb = tuple(pal[idx * 3: idx * 3 + 3])
        out.append({"hex": hexof(rgb), "rgb": list(rgb),
                    "share": round(cnt / total, 4)})
    return out


def read_psd(path):
    try:
        from psd_tools import PSDImage
    except ImportError:
        sys.exit("PSD support needs psd-tools:  pip install psd-tools")
    psd = PSDImage.open(path)
    info = {"file": os.path.basename(path), "width": psd.width,
            "height": psd.height, "layers": [], "text": [], "fonts": set()}
    for lyr in psd.descendants():
        entry = {"name": lyr.name, "kind": str(lyr.kind), "visible": lyr.visible,
                 "bbox": list(lyr.bbox) if lyr.bbox != (0, 0, 0, 0) else None}
        info["layers"].append(entry)
        if lyr.kind == "type":
            txt = (lyr.text or "").replace("\r", " / ").replace("\n", " / ")
            fonts, sizes = [], []
            try:
                rd, ed = lyr.resource_dict, lyr.engine_dict
                # psd-tools returns its own String type, not str
                names = [str(f["Name"]) for f in rd["FontSet"]]
                for r in ed["StyleRun"]["RunArray"]:
                    sd = r.get("StyleSheet", {}).get("StyleSheetData", {})
                    i = sd.get("Font")
                    if i is not None and int(i) < len(names):
                        fonts.append(names[int(i)])
                    if sd.get("FontSize"):
                        sizes.append(round(float(sd["FontSize"]), 1))
            except Exception:
                pass
            info["fonts"].update(fonts)
            info["text"].append({"layer": lyr.name, "text": txt,
                                 "fonts": sorted(set(fonts)),
                                 "sizes": sorted(set(sizes))})
    info["fonts"] = sorted(info["fonts"])
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", nargs="*", default=[])
    ap.add_argument("--psd")
    ap.add_argument("--colors", type=int, default=6)
    ap.add_argument("--out", default="brand.json")
    a = ap.parse_args()

    brand = {"sources": [], "palette": {}, "fonts": [], "psd": None}

    for img in a.images:
        if not os.path.exists(img):
            print(f"missing: {img}"); continue
        pal = palette(img, a.colors)
        brand["sources"].append(img)
        print(f"\n{os.path.basename(img)}")
        for c in pal:
            bar = "#" * max(1, int(c["share"] * 40))
            print(f"  {c['hex']}  {c['share']*100:5.1f}%  {bar}")
        brand["palette"][os.path.basename(img)] = pal

    if a.psd:
        info = read_psd(a.psd)
        brand["psd"] = info
        brand["fonts"] = info["fonts"]
        print(f"\n{info['file']}  {info['width']}x{info['height']}  "
              f"{len(info['layers'])} layers")
        if info["fonts"]:
            print("fonts used: " + ", ".join(info["fonts"]))
        for t in info["text"]:
            print(f"  [{t['layer']}] {t['text'][:60]!r}  "
                  f"{'/'.join(t['fonts'])} {t['sizes']}")
        print("\nsmart objects and pixel layers worth exporting:")
        for l in info["layers"]:
            if l["kind"] in ("smartobject", "pixel") and l["bbox"]:
                print(f"  {l['name']:34} {l['kind']:12} {l['bbox']}")

    json.dump(brand, open(a.out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"\n-> {a.out}")
    print("Confirm these values with whoever owns the brand before they propagate.")


if __name__ == "__main__":
    main()
