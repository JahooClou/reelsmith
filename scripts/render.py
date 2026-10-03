# -*- coding: utf-8 -*-
"""Render an edit list to finished vertical video.

  python render.py edl.json --out DIR
  python render.py edl.json --out DIR --luts LUTDIR --captions CAPDIR
  python render.py edl.json --source SRC --out DIR      (single-file lists)

edl.json:
{
  "fps": 25, "width": 1080, "height": 1920,
  "sources": {"CamA_014": "D:/shoot/A001C014.MOV", "Osmo_03": "D:/shoot/DJI_0003.MP4"},
  "endcard": {"image": "card.png", "dur": 1.5},
  "reels": [
    {"name": "Reel01_hook",
     "clips": [{"code": "CA12", "src": "CamA_014", "t": 104.3, "dur": 1.52, "cx": 0.42,
                "lut": "CamA", "caption": "cap01.png", "text": "ON SCREEN TEXT"},
               {"code": "OS03", "src": "Osmo_03", "t": 12.0, "dur": 1.84, "speed": "conform"}]}
  ]
}

Clips are cut from the camera originals named by `src`; `t` is seconds from the
start of that file. The same list drives premiere_xml.py, so the render and the
editor's sequence come from the same frames. `cx`/`cy`/`z` place the 9:16 window,
`speed` is a percentage or "conform" (every source frame once: true slow motion).

`lut` is optional; omit it, or pass --lut-map to pick automatically from the
clip's source timecode so colour follows a shot when you reorder (single-file lists).

What this handles that hand-rolled ffmpeg usually does not:

  durations snapped to whole frames   half frames make the concat drift off CFR
  -t placed after all inputs          between inputs it limits the wrong input
  final pass re-encoded at fixed fps  stream-copy concat yields variable rate
  segments encoded above target CRF   gives the final pass headroom
  segment sound as PCM, not AAC       AAC priming pads each segment, and the
                                      joins slip a frame every few cuts
"""
import argparse, json, os, shutil, sys
from rs_common import (find_ffmpeg, run, frames, probe, probe_source, source_path,
                       clip_key, speed_of, reframe)


def lut_for(t, lut_map):
    for m in lut_map:
        if m["start"] <= t < m["end"]:
            return m["name"]
    return lut_map[-1]["name"] if lut_map else None


def check_bounds(edl, shots_tsv, fps):
    """A clip that runs past its shot's end pulls frames from the next shot. It
    looks like a glitch two frames long and is invisible in a contact sheet."""
    bounds = []
    for line in open(shots_tsv, encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) >= 4 and p[0] != "code":
            bounds.append((p[0], float(p[2]), float(p[3])))
    bad = []
    for reel in edl["reels"]:
        for i, c in enumerate(reel["clips"], 1):
            if c.get("src") is not None:       # shots.tsv describes one file; skip others
                continue
            end = c["t"] + frames(c["dur"], fps)
            for code, a, b in bounds:
                if a <= c["t"] < b:
                    if end > b + 0.01:
                        bad.append((reel["name"], i, code, b, end))
                    break
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edl")
    ap.add_argument("--source", help="default file for clips with no `src`")
    ap.add_argument("--out", required=True)
    ap.add_argument("--balance", help="directory from balance.py: per-shot grade + shared look")
    ap.add_argument("--shots", help="shots.tsv, to check no clip overruns its shot")
    ap.add_argument("--luts", help="directory holding .cube files (per-camera path)")
    ap.add_argument("--lut-map", help="JSON [{name,start,end}] to pick LUT by timecode")
    ap.add_argument("--captions", help="directory holding caption PNGs")
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--seg-crf", type=int, default=16)
    ap.add_argument("--ffmpeg")
    a = ap.parse_args()

    ff, fp = find_ffmpeg(a.ffmpeg)
    if not ff:
        sys.exit("ffmpeg not found")
    edl = json.load(open(a.edl, encoding="utf-8"))
    fps = edl.get("fps", 25)
    W, H = edl.get("width", 1080), edl.get("height", 1920)
    lut_map = json.load(open(a.lut_map, encoding="utf-8")) if a.lut_map else []
    os.makedirs(a.out, exist_ok=True)
    tmp = os.path.join(a.out, "_seg")

    if a.shots:
        bad = check_bounds(edl, a.shots, fps)
        if bad:
            print("CLIPS OVERRUNNING THEIR SHOT:")
            for name, i, code, end_shot, end_clip in bad:
                print(f"  {name} clip{i}: {code} ends {end_shot:.2f}, "
                      f"clip runs to {end_clip:.2f}  (+{end_clip-end_shot:.2f}s)")
            print("Shorten the clip or move the in-point earlier, then re-run.\n")
        else:
            print("bounds ok: no clip overruns its shot\n")

    bal = None
    if a.balance:
        bal = json.load(open(os.path.join(a.balance, "shot_params.json"),
                             encoding="utf-8"))
        print(f"per-shot balance from {a.balance} ({len(bal['clips'])} clips)\n")

    infos = {}

    def info_for(path):
        if path not in infos:
            if not path or not os.path.exists(path):
                sys.exit(f"source not found: {path}")
            infos[path] = probe_source(fp, path)
        return infos[path]

    manifest = []
    for reel in edl["reels"]:
        shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp)
        parts, used, total = [], [], 0.0

        for i, c in enumerate(reel["clips"]):
            path = source_path(edl, c, a.source)
            si = info_for(path)
            dur = frames(c["dur"], fps)
            total += dur
            sp = speed_of(c, si["fps"], fps)
            # retime first, so the colour and crop see the frames that will be shown
            vf = [f"setpts=(PTS-STARTPTS)/{sp:.6f}"] if abs(sp - 1) > 1e-6 else []
            lut = None
            if bal is not None:
                # per-shot balance wins over any per-camera LUT
                from balance import vf_full
                e = bal["clips"].get(clip_key(c))
                if e is None:
                    sys.exit(f"no balance entry for {clip_key(c)}; re-run balance.py")
                vf.append(vf_full(e["params"], bal["look"], e["sat"]))
                used.append("balanced")
            else:
                lut = c.get("lut") or (lut_for(c["t"], lut_map) if lut_map else None)
                if lut and a.luts:
                    vf.append(f"lut3d=file={lut}.cube")
                used.append(lut or "-")
            # the same window premiere_xml.py writes as Motion Scale and Position
            x0, y0, cw, ch, _ = reframe(si["w"], si["h"], W, H, c.get("cx", 0.5),
                                        c.get("cy", 0.5), c.get("z", 1.0))
            if (round(cw), round(ch)) != (si["w"], si["h"]):
                vf.append(f"crop={int(round(cw))}:{int(round(ch))}:{int(round(x0))}:{int(round(y0))}")
            vf.append(f"scale={W}:{H}:flags=lanczos")

            cmd = [ff, "-hide_banner", "-loglevel", "error", "-y",
                   "-ss", f"{c['t']:.3f}", "-i", path]
            # camera sound for real-time clips; silence for retimed ones and for
            # files without audio, so every segment has the same streams for concat
            real_sound = si["audio_ch"] and abs(sp - 1) < 1e-6
            if not real_sound:
                cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
            amap = "0:a:0" if real_sound else "1:a"
            cap = c.get("caption")
            if cap and a.captions:
                cmd += ["-i", os.path.join(a.captions, cap)]
                ci = 1 if real_sound else 2
                chain = "[0:v:0]" + ",".join(vf) + f"[v0];[v0][{ci}:v]overlay=0:0[v]"
                cmd += ["-filter_complex", chain, "-map", "[v]", "-map", amap]
            else:
                # 0:v:0, not 0:v: DJI files carry a second video stream (a thumbnail)
                cmd += ["-vf", ",".join(vf), "-map", "0:v:0", "-map", amap]

            seg = os.path.join(tmp, f"s{i:03d}.mov")
            # -t AFTER all inputs. Between them it limits the wrong input and
            # silently produces a file running to the end of the source.
            cmd += ["-t", f"{dur:.3f}", "-r", str(fps),
                    "-c:v", "libx264", "-preset", "medium", "-crf", str(a.seg_crf),
                    "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le",
                    "-ar", "48000", "-ac", "2", "-map_metadata", "-1", seg]
            cwd = a.balance if bal is not None else (a.luts if (lut and a.luts) else None)
            run(cmd, cwd=cwd)
            parts.append(seg)

        card = edl.get("endcard")
        if card and os.path.exists(card.get("image", "")):
            cd = frames(card.get("dur", 1.5), fps)
            seg = os.path.join(tmp, "s999.mov")
            run([ff, "-hide_banner", "-loglevel", "error", "-y",
                 "-loop", "1", "-i", card["image"],
                 "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                 "-t", f"{cd:.3f}", "-r", str(fps),
                 "-c:v", "libx264", "-preset", "medium", "-crf", str(a.seg_crf),
                 "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", seg])
            parts.append(seg); total += cd

        lst = os.path.join(tmp, "list.txt")
        with open(lst, "w", encoding="utf-8") as f:
            for p in parts:
                f.write(f"file '{p}'\n")

        final = os.path.join(a.out, f"{reel['name']}_{W}x{H}.mp4")
        # Re-encode on concat. Stream copy keeps each segment's timing and the
        # joins land between frames, giving variable frame rate.
        run([ff, "-hide_banner", "-loglevel", "error", "-y",
             "-f", "concat", "-safe", "0", "-i", lst,
             "-r", str(fps), "-fps_mode", "cfr",
             "-c:v", "libx264", "-preset", "slow", "-crf", str(a.crf),
             "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1",
             "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
             "-movflags", "+faststart", final])

        v = probe(fp, final)["video"] if fp else {}
        print(f"{reel['name']:34} {len(reel['clips']):2d} clips  {total:6.2f}s  "
              f"{os.path.getsize(final)//1024//1024:3d} MB  {v.get('fps')} fps")
        if v.get("fps") and abs(v["fps"] - fps) > 0.01:
            print(f"   WARNING: {v['fps']} fps, expected {fps}. Check clip durations "
                  f"are multiples of {1/fps:.3f}s.")
        manifest.append({"name": reel["name"], "file": final,
                         "clips": len(reel["clips"]), "duration": round(total, 2),
                         "luts": used})

    shutil.rmtree(tmp, ignore_errors=True)
    mf = os.path.join(a.out, "render_manifest.json")
    json.dump(manifest, open(mf, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"\n{len(manifest)} reels -> {a.out}\nmanifest -> {mf}")


if __name__ == "__main__":
    main()
