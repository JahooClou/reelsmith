# -*- coding: utf-8 -*-
"""Locate ffmpeg, report what the build can do, probe media.

  python ffmpeg_tools.py --locate
  python ffmpeg_tools.py --check /path/to/ffmpeg
  python ffmpeg_tools.py --probe FILE [FILE ...] [--ffmpeg PATH]

A minimal build (the one bundled with imageio-ffmpeg, for example) can extract
frames but usually cannot encode H.264 or apply a 3D LUT, so the colour and render
steps will fail later rather than here. --check tells you before you commit.
"""
import argparse, json, os, sys
from rs_common import find_ffmpeg, capabilities, probe, crop_9x16


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--locate", action="store_true")
    ap.add_argument("--check", metavar="FFMPEG")
    ap.add_argument("--probe", nargs="+", metavar="FILE")
    ap.add_argument("--ffmpeg")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.locate:
        ff, fp = find_ffmpeg(a.ffmpeg)
        if not ff:
            print("nie znaleziono ffmpeg / ffmpeg not found")
            print("install a full build, or: pip install imageio-ffmpeg")
            return 1
        print(f"ffmpeg : {ff}")
        print(f"ffprobe: {fp or 'MISSING'}")
        caps = capabilities(ff)
        _report_caps(caps)
        return 0

    if a.check:
        caps = capabilities(a.check)
        _report_caps(caps)
        return 0

    if a.probe:
        ff, fp = find_ffmpeg(a.ffmpeg)
        if not fp:
            print("ffprobe not found"); return 1
        rows = []
        for f in a.probe:
            if not os.path.exists(f):
                print(f"missing: {f}"); continue
            info = probe(fp, f)
            rows.append(info)
            v = info["video"]
            if not v:
                print(f"{os.path.basename(f):40} (no video stream)"); continue
            c = crop_9x16(v["w"], v["h"])
            flag = "" if c["ok"] else "  <- below 1080x1920 at 9:16"
            print(f"{os.path.basename(f):40} {v['w']}x{v['h']} {v['aspect']:>6} "
                  f"{v['fps']:>6} fps  {info['duration']:7.2f}s  "
                  f"9:16 -> {c['w']}x{c['h']}{flag}")
        if a.json:
            print(json.dumps(rows, indent=2))
        return 0

    ap.print_help()
    return 0


def _report_caps(caps):
    print("\nencoders:")
    for k, v in caps["encoders"].items():
        print(f"  {k:14} {'yes' if v else 'NO'}")
    print("filters:")
    for k, v in caps["filters"].items():
        print(f"  {k:14} {'yes' if v else 'NO'}")
    if caps["minimal_build"]:
        print("\nThis looks like a MINIMAL build. Frame extraction will work, but")
        print("encoding and 3D LUTs probably will not. Get a full build before")
        print("the colour and render steps.")
    else:
        print("\nFull build. Colour and render steps will work.")


if __name__ == "__main__":
    sys.exit(main())
