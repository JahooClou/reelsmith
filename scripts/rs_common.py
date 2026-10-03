# -*- coding: utf-8 -*-
"""Shared helpers for reelsmith scripts: locating ffmpeg, probing, frame maths."""
import json, os, re, shutil, subprocess, sys

# Common install locations, checked after PATH. Set FFMPEG_PATH to skip the search.
CANDIDATES = [
    r"C:\ffmpeg\bin\ffmpeg.exe",
    r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
    r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
    "/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/opt/homebrew/bin/ffmpeg",
]


def find_ffmpeg(explicit=None):
    """Return (ffmpeg, ffprobe). Prefers a full build over a bundled minimal one."""
    if explicit and os.path.exists(explicit):
        return explicit, _probe_beside(explicit)
    env = os.environ.get("FFMPEG_PATH")
    if env and os.path.exists(env):
        return env, _probe_beside(env)
    p = shutil.which("ffmpeg")
    if p:
        return p, shutil.which("ffprobe") or _probe_beside(p)
    for c in CANDIDATES:
        if os.path.exists(c):
            return c, _probe_beside(c)
    try:                                  # last resort: minimal bundled build
        import imageio_ffmpeg
        p = imageio_ffmpeg.get_ffmpeg_exe()
        return p, _probe_beside(p)
    except Exception:
        return None, None


def _probe_beside(ffmpeg):
    cand = os.path.join(os.path.dirname(ffmpeg), "ffprobe.exe")
    if os.path.exists(cand):
        return cand
    cand = os.path.join(os.path.dirname(ffmpeg), "ffprobe")
    return cand if os.path.exists(cand) else None


def capabilities(ffmpeg):
    """Which encoders and filters this build actually has. Do not assume."""
    def has(kind, names):
        out = subprocess.run([ffmpeg, "-hide_banner", f"-{kind}"],
                             capture_output=True, text=True, errors="ignore")
        blob = out.stdout + out.stderr
        return {n: (f" {n} " in blob) for n in names}
    enc = has("encoders", ["libx264", "libx265", "prores_ks", "aac",
                           "h264_nvenc", "hevc_nvenc"])
    flt = has("filters", ["lut3d", "drawtext", "overlay", "scale", "crop",
                          "xfade", "zscale"])
    return {"encoders": enc, "filters": flt,
            "minimal_build": not enc.get("libx264") or not flt.get("lut3d")}


def probe(ffprobe, path):
    """Resolution, fps, duration, codecs. Everything downstream depends on these."""
    out = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries",
         "stream=index,codec_type,codec_name,width,height,avg_frame_rate,channels",
         "-show_entries", "format=duration,size,bit_rate",
         "-of", "json", path], capture_output=True, text=True, errors="ignore")
    d = json.loads(out.stdout or "{}")
    info = {"path": path, "video": None, "audio": None,
            "duration": float(d.get("format", {}).get("duration") or 0)}
    for s in d.get("streams", []):
        if s.get("codec_type") == "video" and info["video"] is None:
            fr = s.get("avg_frame_rate", "0/1")
            n, _, den = fr.partition("/")
            fps = float(n) / float(den) if den and float(den) else 0.0
            info["video"] = {"codec": s.get("codec_name"), "w": s.get("width"),
                             "h": s.get("height"), "fps": round(fps, 3),
                             "aspect": _aspect(s.get("width"), s.get("height"))}
        elif s.get("codec_type") == "audio" and info["audio"] is None:
            info["audio"] = {"codec": s.get("codec_name"),
                             "channels": s.get("channels")}
    return info


def _aspect(w, h):
    if not w or not h:
        return "?"
    r = w / h
    for name, val in (("9:16", 0.5625), ("1:1", 1.0), ("4:5", 0.8),
                      ("16:9", 1.7778), ("3:2", 1.5), ("2:3", 0.6667)):
        if abs(r - val) < 0.02:
            return name
    return f"{r:.3f}"


def crop_9x16(w, h):
    """What a 9:16 crop yields, and whether it clears a 1080x1920 delivery."""
    cw = round(h * 9 / 16)
    if cw <= w:
        return {"w": cw, "h": h, "ok": cw >= 1080, "mode": "crop sides"}
    ch = round(w * 16 / 9)
    return {"w": w, "h": ch, "ok": w >= 1080, "mode": "crop top/bottom"}


def frames(d, fps=25):
    """Snap a duration to a whole frame. Half frames drift the concat."""
    return round(d * fps) / fps


# ------------------------------------------------------------ camera originals
def probe_source(ffprobe, path):
    """What the XML and the renderer need from a camera original: exact frame rate,
    size, duration, audio, and the embedded start timecode with the rate it counts at.

    The timecode track does not always count at the video rate: DJI writes 59.94p
    video with a 29.97 timecode track, Canon writes 50p with a 50 fps one.
    """
    def q(args):
        r = subprocess.run([ffprobe, "-v", "error"] + args + ["-of", "json", path],
                           capture_output=True, text=True, errors="ignore")
        return json.loads(r.stdout or "{}")

    d = q(["-show_entries", "stream=index,codec_type,codec_tag_string,width,height,"
           "r_frame_rate,avg_frame_rate,channels:stream_tags=timecode:format=duration"])
    info = {"path": path, "w": None, "h": None, "fps": 0.0, "fps_str": "0/1",
            "dur": float(d.get("format", {}).get("duration") or 0), "audio_ch": 0,
            "tc": "", "tc_rate": 0.0}
    for s in d.get("streams", []):
        t = s.get("codec_type")
        if t == "video" and info["w"] is None and s.get("width"):
            info["fps_str"] = s.get("r_frame_rate", "0/1")
            n, _, den = info["fps_str"].partition("/")
            info["fps"] = float(n) / float(den or 1) if float(den or 1) else 0.0
            info["w"], info["h"] = s.get("width"), s.get("height")
            info["tc"] = info["tc"] or s.get("tags", {}).get("timecode", "")
        elif t == "audio" and not info["audio_ch"]:
            info["audio_ch"] = int(s.get("channels") or 0)
        elif t == "data" and s.get("codec_tag_string") == "tmcd":
            n, _, den = s.get("avg_frame_rate", "0/1").partition("/")
            if float(den or 0):
                info["tc_rate"] = float(n) / float(den)
            info["tc"] = info["tc"] or s.get("tags", {}).get("timecode", "")
    if not info["tc_rate"]:
        info["tc_rate"] = info["fps"]
    info["ntsc"] = abs(info["fps"] - round(info["fps"])) > 1e-3
    return info


def looks_derived(info, W, H, path, out_dirs=()):
    """Reasons to think a source is a render or an export rather than a camera original.

    A file already at the delivery size, or one sitting in a render folder, came out
    of an edit. Handing an editor that file instead of the original throws away the
    handles, the full frame for reframing, and the full frame rate for slow motion.
    """
    why = []
    if (info.get("w"), info.get("h")) == (W, H):
        why.append(f"already at the delivery size {W}x{H}")
    p = os.path.abspath(path).replace("\\", "/").lower()
    if "/_seg/" in p:
        why.append("inside a render segment folder")
    for d in out_dirs:
        if d and p.startswith(os.path.abspath(d).replace("\\", "/").lower() + "/"):
            why.append(f"inside the render output folder {d}")
    return why


def source_path(edl, clip, default=None):
    """A clip's source: `src` as a key into edl["sources"], or `src` as a path, else
    the edit list's single `source`, else the --source given on the command line."""
    s = clip.get("src")
    if s is not None:
        srcs = edl.get("sources", {})
        if s in srcs:
            v = srcs[s]
            return v["path"] if isinstance(v, dict) else v
        return s
    return default or edl.get("source")


def clip_key(clip):
    """Identity of a clip for per-shot grade values. The in-point alone is not unique
    once a cut draws on many files: two cameras can both be cut at 104.30."""
    return f"{clip['src']}@{clip['t']:.2f}" if clip.get("src") is not None else f"{clip['t']:.2f}"


def speed_of(clip, src_fps, fps):
    """Source seconds per timeline second.

    `speed` is a percentage (100 = real time, 50 = half speed), or "conform": every
    source frame shown once on the timeline, which is true slow motion with no frame
    blending (50p on a 25p timeline = 50%, 59.94p = 41.71%)."""
    sp = clip.get("speed", 100)
    if sp == "conform":
        return fps / src_fps
    return float(sp) / 100.0


def reframe(sw, sh, W, H, cx=0.5, cy=0.5, z=1.0):
    """Crop window that fills a W x H delivery from a sw x sh source.

    cx, cy  centre of the window as fractions of the source frame (0.5 = centre)
    z       1.0 = as large as the source allows; 0.8 = tighter (a punch-in)
    Returns x0, y0, cw, ch in source pixels and k, the scale from source to delivery.
    The window is clamped inside the frame, so an extreme cx stops at the edge.
    """
    if sw / sh >= W / H:
        ch = sh * z; cw = ch * W / H
    else:
        cw = sw * z; ch = cw * H / W
    x0 = min(max(cx * sw - cw / 2, 0), sw - cw)
    y0 = min(max(cy * sh - ch / 2, 0), sh - ch)
    return x0, y0, cw, ch, W / cw


def tc_frames(tc_str, base):
    """Embedded timecode string -> frame count at the rate the timecode counts."""
    if not tc_str:
        return 0
    h, m, s, f = [int(x) for x in re.split("[:;.]", tc_str)]
    nb = int(round(base))
    n = (h * 3600 + m * 60 + s) * nb + f
    if ";" in tc_str or (abs(base - nb) > 1e-3 and nb in (30, 60)):
        drop = 2 * nb // 30
        mins = h * 60 + m
        n -= drop * (mins - mins // 10)
    return n


def tc_string(n, fps):
    """Frame count -> timecode at the clip's own rate, drop-frame for 29.97/59.94."""
    nb = int(round(fps))
    if abs(fps - nb) > 1e-3 and nb in (30, 60):
        drop = 2 * nb // 30
        fp10, fpm = nb * 600 - 9 * drop, nb * 60 - drop
        d, m = divmod(n, fp10)
        n += drop * 9 * d + (drop * ((m - drop) // fpm) if m > drop else 0)
        sep = ";"
    else:
        sep = ":"
    f = n % nb; s = n // nb
    return f"{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}{sep}{f:02d}"


def source_tc(info, seconds):
    """Source timecode of a point `seconds` into a clip, as the NLE's source monitor
    shows it: counted at the clip's own frame rate from its embedded start timecode."""
    start = tc_frames(info.get("tc", ""), info.get("tc_rate") or info["fps"])
    start = int(round(start * info["fps"] / (info.get("tc_rate") or info["fps"])))
    return tc_string(start + int(round(seconds * info["fps"])), info["fps"])


def tc(sec):
    return f"{int(sec // 60)}:{sec % 60:05.2f}"


def run(cmd, cwd=None):
    r = subprocess.run(cmd, capture_output=True, text=True, errors="ignore", cwd=cwd)
    if r.returncode != 0:
        sys.stderr.write(r.stderr[-2000:] + "\n")
        raise SystemExit(f"ffmpeg failed: {' '.join(str(c) for c in cmd[:6])} ...")
    return r
