# -*- coding: utf-8 -*-
"""Shared helpers for reelsmith scripts: locating ffmpeg, probing, frame maths."""
import json, os, re, shutil, subprocess, sys

CANDIDATES = [
    r"C:\ffmpeg\bin\ffmpeg.exe", r"Z:\ffmpeg\bin\ffmpeg.exe",
    r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
    "/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/opt/homebrew/bin/ffmpeg",
]


def find_ffmpeg(explicit=None):
    """Return (ffmpeg, ffprobe). Prefers a full build over a bundled minimal one."""
    if explicit and os.path.exists(explicit):
        return explicit, _probe_beside(explicit)
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


def tc(sec):
    return f"{int(sec // 60)}:{sec % 60:05.2f}"


def run(cmd, cwd=None):
    r = subprocess.run(cmd, capture_output=True, text=True, errors="ignore", cwd=cwd)
    if r.returncode != 0:
        sys.stderr.write(r.stderr[-2000:] + "\n")
        raise SystemExit(f"ffmpeg failed: {' '.join(str(c) for c in cmd[:6])} ...")
    return r
