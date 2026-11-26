# -*- coding: utf-8 -*-
"""Check a rendered file the way a viewer will meet it, before it is handed over.

  python qc.py OUT.mp4
  python qc.py OUT.mp4 --edl edl.json --reel Reel01_hook --captions CAPDIR --sheet qc.jpg
  python qc.py OUT.mp4 --edl edl.json --speech            # captions transcribe speech
  python qc.py CLEAN.mp4 --edl edl.json --faces-out faces.json   # for captions.py --faces

verify.py checks the plan: the frames you are about to cut. This checks the result:

  format    size, frame rate and length (to the frame) against the edit list
  picture   black frames, and stretches where nothing moves for 2 s or more
  audio     integrated loudness and true peak; silence before the first sound and
            gaps in the sound
  faces     a caption plate on a face, a caption outside the interface margins, a
            face up under the app's top bar (vertical deliveries)
  speech    with --speech: the finished audio transcribed again and compared with
            each clip's "text", so a caption that drifted off its words is caught

FAIL means do not hand it over; fix the edit list, render, run this again. WARN means
look: a still end card or a photo insert is a freeze by design. Exit code 1 on any FAIL.

Captions are found through the edit list: a clip's "caption" names its PNG in
--captions, and the plate's opaque pixels are where the text sits for that clip's
span. Faces are found by YuNet (OpenCV Zoo, MIT) on frames sampled 5 times a second.

--faces-out writes the face boxes seen during each captioned clip. Run it on a clean
render (no plates), then let captions.py --faces place every plate where no face is.

--sheet writes a contact sheet of every flagged moment: green = face, yellow =
caption, red = caption on a face, grey lines = interface margins. Open it even when
everything passes; a script cannot read a misspelt word.
"""
import argparse, json, math, os, re, subprocess, sys
from rs_common import find_ffmpeg, probe, frames, resolve_beats

HERE = os.path.dirname(os.path.abspath(__file__))
YUNET = os.path.join(HERE, "models", "face_detection_yunet_2026may.onnx")

# Interface margins at 1080x1920 (shortform.md): "meta" is Meta's Reels-ads guidance,
# the conservative margin; "loose" keeps clear of most organic interface.
MARGINS = {"meta": dict(top=270, bottom=670, side=65),
           "loose": dict(top=250, bottom=320, side=40)}


class Report:
    def __init__(self):
        self.items = []

    def add(self, level, check, msg, fix="", at=None):
        self.items.append(dict(level=level, check=check, msg=msg, fix=fix, at=at))

    def fails(self):
        return [i for i in self.items if i["level"] == "FAIL"]


# ------------------------------------------------------------ the edit list
def clip_spans(edl, reel_name=None):
    """Record-time span of every clip of one reel: (t0, t1, clip)."""
    reels = edl["reels"]
    reel = next((r for r in reels if r["name"] == reel_name), None) if reel_name else reels[0]
    if reel is None:
        sys.exit(f"no reel named {reel_name!r}; reels: {[r['name'] for r in reels]}")
    fps = edl.get("fps", 25)
    out, t = [], 0.0
    for c in reel["clips"]:
        d = frames(c["dur"], fps)
        out.append((t, t + d, c))
        t += d
    card = edl.get("endcard")
    return reel, out, t, (frames(card["dur"], fps) if card else 0.0)


def plate_box(path):
    """Bounding box of a caption plate's opaque pixels, or None."""
    from PIL import Image
    im = Image.open(path).convert("RGBA")
    box = im.getchannel("A").point(lambda a: 255 if a > 24 else 0).getbbox()
    return (box[0], box[1], box[2] - box[0], box[3] - box[1]) if box else None


# ------------------------------------------------------------ measuring
def measure_ffmpeg(ff, path, speech):
    """One pass: black frames, freezes, silence, loudness and true peak."""
    noise = "-45dB" if speech else "-50dB"
    gap = 1.5 if speech else 1.0
    cmd = [ff, "-hide_banner", "-nostats", "-i", path,
           "-vf", "blackdetect=d=0.08:pix_th=0.10,freezedetect=n=-60dB:d=2",
           "-af", f"silencedetect=n={noise}:d={gap},ebur128=peak=true",
           "-f", "null", "-"]
    err = subprocess.run(cmd, capture_output=True, text=True, errors="ignore").stderr
    num = r"(-?[\d.]+)"
    black = [(float(a), float(b)) for a, b in
             re.findall(rf"black_start:{num} black_end:{num}", err)]
    fz_s = [float(x) for x in re.findall(rf"freeze_start: {num}", err)]
    fz_e = [float(x) for x in re.findall(rf"freeze_end: {num}", err)]
    sil_s = [float(x) for x in re.findall(rf"silence_start: {num}", err)]
    sil_e = [float(x) for x in re.findall(rf"silence_end: {num}", err)]
    summary = err[err.rfind("Summary:"):] if "Summary:" in err else ""
    I = re.search(rf"I:\s+{num} LUFS", summary)
    tp = re.search(rf"Peak:\s+{num} dBFS", summary)
    return dict(black=black,
                freeze=list(zip(fz_s, fz_e + [None] * (len(fz_s) - len(fz_e)))),
                silence=list(zip(sil_s, sil_e + [None] * (len(sil_s) - len(sil_e)))),
                lufs=float(I.group(1)) if I else None,
                peak=float(tp.group(1)) if tp else None)


def detect_faces(path, rate=5.0, width=540):
    """[(t, [(x, y, w, h), ...]), ...] in delivery pixels, sampled `rate` times a second."""
    import cv2
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    W, H = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    k = width / W
    det = cv2.FaceDetectorYN.create(YUNET, "", (width, int(H * k)), 0.75)
    step = max(1, round(fps / rate))
    out, n = [], 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        if n % step == 0:
            ok, img = cap.retrieve()
            if not ok:
                break
            small = cv2.resize(img, (width, int(H * k)))
            _, found = det.detect(small)
            boxes = []
            for f in (found if found is not None else []):
                x, y, w, h = (float(v) / k for v in f[:4])
                boxes.append(pad_face((x, y, w, h)))
            out.append((n / fps, boxes))
        n += 1
    cap.release()
    return out


def pad_face(b):
    """YuNet's box runs from the brows to the chin. Add the forehead and some air."""
    x, y, w, h = b
    return (x - 0.10 * w, y - 0.30 * h, w * 1.20, h * 1.38)


def overlap(a, b):
    ax, ay, aw, ah = a; bx, by, bw, bh = b
    w = min(ax + aw, bx + bw) - max(ax, bx)
    h = min(ay + ah, by + bh) - max(ay, by)
    return max(w, 0) * max(h, 0)


def transcribe(ff, path, model="small"):
    """Words with times. The audio is decoded by ffmpeg, not by faster-whisper's own
    PyAV reader, which breaks when the installed PyAV is newer than it expects."""
    import numpy as np
    from faster_whisper import WhisperModel
    pcm = subprocess.run([ff, "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", "16000",
                          "-f", "f32le", "-"], capture_output=True).stdout
    audio = np.frombuffer(pcm, np.float32)
    # CPU by default: "auto" picks CUDA whenever a GPU exists, then fails if the
    # cuBLAS/cuDNN libraries it needs are not installed. A short reel takes seconds.
    m = WhisperModel(model, device=os.environ.get("RS_WHISPER_DEVICE", "cpu"), compute_type="int8")
    segs, _ = m.transcribe(audio, word_timestamps=True, vad_filter=True)
    return [(w.start, w.end, w.word) for s in segs for w in (s.words or [])]


def norm_words(s):
    return [w for w in re.sub(r"[^\w\s']", " ", s.lower()).split() if w]


# ------------------------------------------------------------ the checks
def check_format(rep, info, edl, total, card, W, H, fps):
    v = info.get("video") or {}
    if (v.get("w"), v.get("h")) != (W, H):
        rep.add("FAIL", "format", f"{v.get('w')}x{v.get('h')}, edit list says {W}x{H}",
                "render again at the edit list's size")
    r = v.get("fps")
    if r and abs(r - fps) > 0.01:
        rep.add("FAIL", "format", f"{r:.3f} fps, edit list says {fps}",
                "render at the project rate; never let the encoder pick one")
    dur = info.get("duration") or 0
    want = total + card
    if want and abs(dur - want) > 1.5 / fps:
        rep.add("FAIL", "format", f"{dur:.3f} s long, edit list adds up to {want:.3f} s",
                "a clip dropped or a join drifted: count the frames and render again")
    if not info.get("audio"):
        rep.add("WARN", "format", "no audio stream", "deliver with sound unless asked not to")


def check_picture(rep, m, dur, card_from):
    for a, b in m["black"]:
        if a < 0.05 or b > dur - 0.05:
            rep.add("WARN", "picture", f"black {a:.2f}-{b:.2f} s at the very start or end",
                    "fine if it is a planned fade; otherwise trim it", a)
        else:
            rep.add("FAIL", "picture", f"black frames {a:.2f}-{b:.2f} s",
                    "a clip ran past the end of its original or a segment failed: check that clip", a)
    for a, b in m["freeze"]:
        b = dur if b is None else b
        if card_from is not None and a >= card_from - 0.1:
            continue                                          # the end card is still by design
        rep.add("WARN", "picture", f"nothing moves {a:.2f}-{b:.2f} s ({b - a:.1f} s)",
                "a photo insert is fine; otherwise cut sooner, or add a move", a)


def check_audio(rep, m, dur, target, speech):
    if m["lufs"] is None:
        return
    I, tp = m["lufs"], m["peak"]
    if I < -60:
        rep.add("FAIL", "audio", "the sound is silent", "the music or camera sound did not reach the mix")
        return
    off = I - target
    if abs(off) > 5:
        rep.add("FAIL", "audio", f"{I:.1f} LUFS integrated, target {target}",
                "re-level the mix (delivery.md)")
    elif abs(off) > 2:
        rep.add("WARN", "audio", f"{I:.1f} LUFS integrated, target {target}", "re-level the mix")
    if tp is not None and tp > -1.0:
        rep.add("FAIL", "audio", f"true peak {tp:.1f} dBFS, above -1", "limit the master to -1 dBTP")
    for a, b in m["silence"]:
        b = dur if b is None else b
        if a < 0.05:
            if speech and b > 0.5:
                rep.add("WARN", "audio", f"{b:.2f} s of silence before the first sound",
                        "start on the first word", 0)
            elif b > 0.3:
                rep.add("WARN", "audio", f"{b:.2f} s of silence at the start", "start on sound", 0)
        elif b < dur - 0.1:
            rep.add("WARN", "audio", f"no sound {a:.2f}-{b:.2f} s",
                    "a pause in speech, or the music dropped out: tighten it or fill it", a)


def check_faces(rep, faces, spans, plates, W, H, margins):
    vertical = H > W
    k = H / 1920
    mg = {n: {s: v * k for s, v in d.items()} for n, d in MARGINS.items()}
    m_main = mg[margins]
    flagged = []
    for t, boxes in faces:
        if vertical:
            for b in boxes:
                if b[1] < m_main["top"] - 0.2 * b[3]:
                    rep.add("WARN", "face-top-bar",
                            f"face at y {max(b[1], 0):.0f} under the app's top bar at {t:.2f} s",
                            "lower the window (cy) or the punch-in", t)
                    flagged.append(t)
                    break
    for t0, t1, c in spans:
        name = c.get("caption")
        if not name or name not in plates or not plates[name]:
            continue
        p = plates[name]
        x, y, w, h = p
        if vertical:
            for nm, lv in ((margins, "FAIL"),):             # the margin chosen for this delivery
                g = mg[nm]
                edges = [e for e, bad in (("top", y < g["top"]), ("bottom", y + h > H - g["bottom"]),
                                          ("sides", x < g["side"] or x + w > W - g["side"])) if bad]
                if edges:
                    rep.add(lv, "caption-margins",
                            f"{name} at x {x:.0f}-{x + w:.0f}, y {y:.0f}-{y + h:.0f} crosses the "
                            f"{nm} margin at the {' and '.join(edges)}",
                            f"place it with captions.py --faces --margins {nm}, or shorten it",
                            t0)
                    break
        worst = 0.0; at = None
        for t, boxes in faces:
            if t0 <= t < t1:
                for b in boxes:
                    share = overlap(p, b) / max(b[2] * b[3], 1)
                    if share > worst:
                        worst, at = share, t
        if worst > 0.03:
            rep.add("FAIL", "caption-on-face",
                    f"{name} covers {worst * 100:.0f}% of a face at {at:.2f} s",
                    "place it with captions.py --faces, or shorten the line", at)


def check_speech(rep, words, spans):
    for t0, t1, c in spans:
        text = c.get("text")
        if not text:
            continue
        want = norm_words(text)
        heard = set(w for s, e, ww in words if e >= t0 - 0.4 and s <= t1 + 0.4
                    for w in norm_words(ww))
        miss = [w for w in want if w not in heard]
        if not want:
            continue
        share = len(miss) / len(want)
        if share > 0.5:
            rep.add("FAIL", "caption-speech",
                    f"clip {c.get('code', '?')}: '{text}' is mostly not said during it ({', '.join(miss[:6])})",
                    "re-time the clip to the words, or correct the text", t0)
        elif miss:
            rep.add("WARN", "caption-speech",
                    f"clip {c.get('code', '?')}: not heard during it: {', '.join(miss[:6])}",
                    "names and numbers spelled as said; check the timing", t0)


# ------------------------------------------------------------ outputs
def faces_by_caption(faces, spans):
    out = {}
    for t0, t1, c in spans:
        name = c.get("caption")
        if not name:
            continue
        boxes = [list(map(round, b)) for t, bs in faces if t0 <= t < t1 for b in bs]
        out[os.path.splitext(name)[0]] = dict(t0=round(t0, 3), t1=round(t1, 3), faces=boxes)
    return out


def write_sheet(ff, path, rep, faces, spans, plates, W, H, margins, out):
    from PIL import Image, ImageDraw
    times = sorted({round(i["at"], 2) for i in rep.items if i["at"] is not None})[:24]
    if not times:
        times = [round((t0 + t1) / 2, 2) for t0, t1, _ in spans][:24] or [0.0]
    TW = 270; TH = int(TW * H / W); k = TW / W
    cols = min(6, len(times)); rows = math.ceil(len(times) / cols)
    sheet = Image.new("RGB", (cols * TW, rows * (TH + 22)), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    g = {s: v * H / 1920 for s, v in MARGINS[margins].items()}
    for n, t in enumerate(times):
        png = out + f"_{n:02d}.png"
        subprocess.run([ff, "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1",
                        "-vf", f"scale={TW}:{TH}", png], capture_output=True)
        if not os.path.exists(png):
            continue
        tile = Image.open(png).convert("RGB"); os.remove(png)
        td = ImageDraw.Draw(tile)
        if H > W:
            for yy in (g["top"], H - g["bottom"]):
                td.line([(0, yy * k), (TW, yy * k)], fill=(150, 150, 150))
        fb = min(faces, key=lambda f: abs(f[0] - t))[1] if faces else []
        for b in fb:
            td.rectangle([b[0] * k, b[1] * k, (b[0] + b[2]) * k, (b[1] + b[3]) * k], outline=(60, 220, 90), width=2)
        for t0, t1, c in spans:
            p = plates.get(c.get("caption"))
            if p and t0 <= t < t1:
                hit = any(overlap(p, b) > 0.03 * b[2] * b[3] for b in fb)
                td.rectangle([p[0] * k, p[1] * k, (p[0] + p[2]) * k, (p[1] + p[3]) * k],
                             outline=(230, 60, 60) if hit else (240, 200, 40), width=2)
        x, y = (n % cols) * TW, (n // cols) * (TH + 22)
        sheet.paste(tile, (x, y))
        d.text((x + 4, y + TH + 4), f"{t:.2f} s", fill=(230, 230, 230))
    sheet.save(out, quality=88)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("file")
    ap.add_argument("--edl")
    ap.add_argument("--reel", help="which reel of the edit list this file is (default: the first)")
    ap.add_argument("--captions", help="directory holding the caption PNGs")
    ap.add_argument("--margins", choices=list(MARGINS), default="loose")
    ap.add_argument("--lufs", type=float, default=-14.0, help="integrated loudness target")
    ap.add_argument("--speech", action="store_true",
                    help="the captions transcribe speech: check silence as speech and compare words")
    ap.add_argument("--whisper-model", default="small")
    ap.add_argument("--no-faces", action="store_true")
    ap.add_argument("--faces-out", help="write face boxes per captioned clip (for captions.py --faces)")
    ap.add_argument("--sheet", help="contact sheet of the flagged moments (jpg)")
    ap.add_argument("--json", help="write the report as JSON")
    a = ap.parse_args()

    ff, fp = find_ffmpeg()
    if not ff or not fp:
        sys.exit("ffmpeg and ffprobe not found")
    info = probe(fp, a.file)
    v = info.get("video") or {}
    W, H, fps = v.get("w"), v.get("h"), v.get("fps") or 25
    rep = Report()

    spans, total, card = [], 0.0, 0.0
    if a.edl:
        edl = json.load(open(a.edl, encoding="utf-8"))
        resolve_beats(edl, a.edl)
        _, spans, total, card = clip_spans(edl, a.reel)
        check_format(rep, info, edl, total, card, edl.get("width", 1080),
                     edl.get("height", 1920), edl.get("fps", 25))
    dur = info.get("duration") or total + card

    m = measure_ffmpeg(ff, a.file, a.speech)
    check_picture(rep, m, dur, total if card else None)
    check_audio(rep, m, dur, a.lufs, a.speech)

    plates = {}
    if a.captions and spans:
        for _, _, c in spans:
            n = c.get("caption")
            if n and n not in plates:
                p = os.path.join(a.captions, n)
                plates[n] = plate_box(p) if os.path.exists(p) else None
                if plates[n] is None:
                    rep.add("FAIL", "caption-file", f"{n} missing or empty", "render the plates again")
    faces = []
    if not a.no_faces:
        faces = detect_faces(a.file)
        check_faces(rep, faces, spans, plates, W, H, a.margins)
        if faces and sum(1 for _, b in faces if b) == 0 and plates:
            rep.add("WARN", "faces", "no face found anywhere; the caption-on-face check had nothing to test")
    if a.faces_out:
        json.dump(faces_by_caption(faces, spans), open(a.faces_out, "w", encoding="utf-8"), indent=1)
        print(f"face boxes per caption -> {a.faces_out}")
    if a.speech and spans:
        try:
            check_speech(rep, transcribe(ff, a.file, a.whisper_model), spans)
        except ImportError:
            rep.add("WARN", "caption-speech", "faster-whisper is not installed; words not compared",
                    "pip install faster-whisper")
        except Exception as e:
            rep.add("WARN", "caption-speech", f"transcription failed, words not compared: {e}",
                    "for a GPU set RS_WHISPER_DEVICE=cuda once cuBLAS and cuDNN are installed")

    print(f"{os.path.basename(a.file)}  {W}x{H}  {fps:.3f} fps  {dur:.2f} s  "
          f"{m['lufs'] if m['lufs'] is not None else '?'} LUFS  peak {m['peak'] if m['peak'] is not None else '?'} dBFS")
    order = {"FAIL": 0, "WARN": 1}
    for i in sorted(rep.items, key=lambda i: (order[i["level"]], i["at"] or 0)):
        at = f"{i['at']:7.2f}s " if i["at"] is not None else " " * 9
        print(f"{i['level']:4} {at}{i['check']:16} {i['msg']}")
        if i["fix"]:
            print(f"{'':31}fix: {i['fix']}")
    status = "FAIL" if rep.fails() else "PASS"
    print(f"\n{status}: {len(rep.fails())} fail, {len(rep.items) - len(rep.fails())} warn")
    if a.sheet:
        write_sheet(ff, a.file, rep, faces, spans, plates, W, H, a.margins, a.sheet)
        print(f"sheet -> {a.sheet}")
    if a.json:
        json.dump(dict(status=status, lufs=m["lufs"], peak=m["peak"], items=rep.items),
                  open(a.json, "w", encoding="utf-8"), indent=1)
    sys.exit(1 if rep.fails() else 0)


if __name__ == "__main__":
    main()
