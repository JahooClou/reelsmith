# -*- coding: utf-8 -*-
"""Log a shoot: sample every camera original and lay the frames out in shooting order.

  python logsheet.py /shoot/CamA /shoot/CamB /shoot/Drone --out log/
  python logsheet.py /shoot --out log/ --short 2 --mid 5 --long 15

Writes, under --out:
  clips.json      one entry per original: code, path, duration, size, fps, recorded
  thumbs/CODE/    sampled frames, named by seconds from the start of the clip
  sheets/NN.jpg   contact sheets in recording order, every tile labelled CODE m:ss
  index.md        which sheet covers which clips and times

Sampling follows clip length, because a short clip is a deliberate shot and a long
one is continuous coverage:
  up to 30 s   every --short seconds (2)
  up to 300 s  every --mid seconds (5)
  longer       every --long seconds (15)

A sheet is for FINDING moments. Before cutting from one, scan the stretch densely
(verify.py SOURCE --scan A B --step 1) and check the in-point itself: a tile is one
frame, and a twenty-second take holds many different moments.

Codes are the folder's first three letters plus a running number in recording
order, e.g. Cam007 or Dro001. Resumable: frames already extracted are skipped.
"""
import argparse, json, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from rs_common import find_ffmpeg

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("needs Pillow:  pip install Pillow")

EXT = (".mov", ".mp4", ".mxf", ".mts", ".m4v", ".avi", ".mkv")


def probe(fp, path):
    r = subprocess.run([fp, "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,r_frame_rate:stream_tags=timecode:format=duration:format_tags=creation_time",
                        "-of", "json", path], capture_output=True, text=True, errors="ignore")
    d = json.loads(r.stdout or "{}")
    s = (d.get("streams") or [{}])[0]
    n, _, den = s.get("r_frame_rate", "0/1").partition("/")
    return dict(dur=float(d.get("format", {}).get("duration") or 0), w=s.get("width"), h=s.get("height"),
                fps=round(float(n) / float(den or 1), 3) if float(den or 1) else 0,
                recorded=d.get("format", {}).get("tags", {}).get("creation_time", ""),
                tc=s.get("tags", {}).get("timecode", ""))


def font(size):
    for f in ("arialbd.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except Exception:
            pass
    return ImageFont.load_default()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", help="folders or files of camera originals")
    ap.add_argument("--out", required=True)
    ap.add_argument("--short", type=float, default=2.0)
    ap.add_argument("--mid", type=float, default=5.0)
    ap.add_argument("--long", type=float, default=15.0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--ffmpeg")
    a = ap.parse_args()
    ff, fp = find_ffmpeg(a.ffmpeg)
    if not ff or not fp:
        sys.exit("ffmpeg and ffprobe are needed")

    paths = []
    for inp in a.inputs:
        if os.path.isfile(inp):
            paths.append(inp)
        else:
            for dp, _, fs in os.walk(inp):
                paths += [os.path.join(dp, f) for f in sorted(fs) if f.lower().endswith(EXT)]
    if not paths:
        sys.exit("no video files found")
    with ThreadPoolExecutor(a.workers) as ex:
        infos = list(ex.map(lambda p: probe(fp, p), paths))
    clips = []
    for p, i in zip(paths, infos):
        if i["dur"] > 0 and i["w"]:
            clips.append(dict(path=os.path.abspath(p), file=os.path.basename(p),
                              folder=os.path.basename(os.path.dirname(os.path.abspath(p))), **i))
    clips.sort(key=lambda c: (c["recorded"] or "~", c["folder"], c["file"]))
    count = {}
    for c in clips:
        k = (c["folder"][:3] or "Clp").capitalize()
        count[k] = count.get(k, 0) + 1
        c["code"] = f"{k}{count[k]:03d}"

    os.makedirs(a.out, exist_ok=True)
    json.dump(clips, open(os.path.join(a.out, "clips.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    jobs = []
    for c in clips:
        step = a.short if c["dur"] <= 30 else (a.mid if c["dur"] <= 300 else a.long)
        t = min(1.0, c["dur"] / 2)
        while t < c["dur"] - 0.3:
            jobs.append((c, round(t, 2)))
            t += step
    print(f"{len(clips)} clips, {sum(c['dur'] for c in clips) / 3600:.1f} h, {len(jobs)} frames to sample")

    def grab(job):
        c, t = job
        d = os.path.join(a.out, "thumbs", c["code"])
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, f"{int(round(t * 100)):08d}.jpg")
        if not (os.path.exists(p) and os.path.getsize(p) > 500):
            sc = "scale=216:-2" if c["h"] > c["w"] else "scale=384:-2"
            subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.2f}", "-i", c["path"],
                            "-map", "0:v:0", "-frames:v", "1", "-vf", sc, "-q:v", "4", p],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return c, t, p

    with ThreadPoolExecutor(a.workers) as ex:
        done = [r for r in ex.map(grab, jobs) if os.path.exists(r[2])]

    # sheets in recording order; vertical and landscape clips get their own sheets
    F = font(15)
    os.makedirs(os.path.join(a.out, "sheets"), exist_ok=True)
    index, k = ["# Log\n", "| sheet | clips | first | last |", "|---|---|---|---|"], 0
    for vert in (False, True):
        group = [d for d in done if (d[0]["h"] > d[0]["w"]) == vert]
        tw, th, cols, per = (153, 272, 10, 40) if vert else (256, 144, 6, 48)
        for s in range(0, len(group), per):
            part = group[s:s + per]
            rows = (len(part) + cols - 1) // cols
            sheet = Image.new("RGB", (cols * tw, rows * th), (20, 20, 20))
            dr = ImageDraw.Draw(sheet)
            for i, (c, t, p) in enumerate(part):
                im = Image.open(p).convert("RGB"); im.thumbnail((tw, th))
                x, y = (i % cols) * tw, (i // cols) * th
                sheet.paste(im, (x + (tw - im.width) // 2, y + (th - im.height) // 2))
                lab = f"{c['code']} {int(t // 60)}:{t % 60:04.1f}"
                dr.rectangle([x, y, x + dr.textlength(lab, font=F) + 6, y + 18], fill=(0, 0, 0))
                dr.text((x + 3, y + 1), lab, font=F, fill=(255, 220, 0))
            k += 1
            name = f"{k:03d}{'_v' if vert else ''}.jpg"
            sheet.save(os.path.join(a.out, "sheets", name), quality=82)
            codes = sorted({c["code"] for c, _, _ in part})
            index.append(f"| {name} | {', '.join(codes)} | {part[0][0]['code']} {part[0][1]:.0f}s | "
                         f"{part[-1][0]['code']} {part[-1][1]:.0f}s |")
    index += ["", "| code | file | folder | length | size | fps | recorded |", "|---|---|---|---|---|---|---|"]
    index += [f"| {c['code']} | {c['file']} | {c['folder']} | {c['dur']:.1f}s | {c['w']}x{c['h']} | {c['fps']} | "
              f"{c['recorded'][:19]} |" for c in clips]
    open(os.path.join(a.out, "index.md"), "w", encoding="utf-8").write("\n".join(index) + "\n")
    print(f"{k} sheets -> {os.path.join(a.out, 'sheets')}\nindex -> {os.path.join(a.out, 'index.md')}")


if __name__ == "__main__":
    main()
