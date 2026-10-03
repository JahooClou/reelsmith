# -*- coding: utf-8 -*-
"""Convert an edit list to FCP7 XML for Premiere Pro, linked to the CAMERA ORIGINALS.

  python premiere_xml.py edl.json --out cut.xml
  python premiere_xml.py edl.json --out DIR --split
  python premiere_xml.py edl.json --out cut.xml --balance GRADEDIR

Every clip in the sequence is the original camera file with an in and an out point.
Nothing is cut, copied or transcoded. That is the point of handing over a sequence:
the editor can slide a cut or extend a shot against the full take, reframe again from
the full frame, and re-time from the full frame rate. A rendered segment or an export
of an earlier edit gives them none of that, so this script refuses one (see below).

Where the clips come from
  Each clip names its file with `src`, a key into the edit list's `sources` map or a
  path. `t` is seconds from the first frame of THAT file. A list with a single
  top-level `source` still works, but that file must be an original too.

What travels in the XML
  reframe       `cx`, `cy`, `z` become Motion Scale and Position, so a landscape
                original sits in the 9:16 sequence exactly as the render crops it
  speed         `speed` (percent, or "conform") becomes Time Remap; frame blending off
  camera sound  linked on A1/A2 for real-time clips (off with --no-camera-audio)
  music         edl["music"] on A3/A4, if given
  end card      edl["endcard"] as a still on V1
  markers       one per clip: Position, Scale, Speed, source timecode, grade or LUT,
                caption text and the note. If a value imports wrongly it can be typed
                in from the marker.

What does not travel: colour. FCP7 XML cannot express Lumetri, so grade values go in
the markers. Put the shared look on an adjustment layer and dial per-clip values.

Refusing derived media
  A source already at the delivery size, or one inside a render folder, is an export,
  not an original. The script stops and says why. If an export really is all there is,
  --allow-derived proceeds and says so in the output.

FCP7 XML conventions as Premiere reads them
  in/out        frames at the SEQUENCE rate from the first frame of the file, whatever
                the file's own rate
  retimed clip  in/out/duration in retimed frames: source seconds / speed * fps
  Motion Scale  percent of the clip's native pixels
  Motion Center offset from the sequence centre in sequence pixels, divided by the
                CLIP's native width and height; +x right, +y down; 0,0 is centred.
                Checked against a Premiere export (OpenTimelineIO issue 253).
"""
import argparse, json, os, sys, urllib.parse
from xml.sax.saxutils import escape
from rs_common import (find_ffmpeg, probe_source, looks_derived, source_path, clip_key,
                       speed_of, reframe, source_tc)


def fr(sec, fps):
    return int(round(sec * fps))


def pathurl(p):
    ap = os.path.abspath(p).replace("\\", "/")
    if len(ap) > 1 and ap[1] == ":":                       # Windows drive letter
        return "file://localhost/" + urllib.parse.quote(ap, safe="/:")
    return "file://localhost" + urllib.parse.quote(ap, safe="/:")


def rate(fps):
    ntsc = "TRUE" if abs(fps - round(fps)) > 1e-3 else "FALSE"
    return f"<rate><timebase>{int(round(fps))}</timebase><ntsc>{ntsc}</ntsc></rate>"


class Files:
    """Full <file> definition the first time a file appears, a reference after."""
    def __init__(self):
        self.ids, self.defined = {}, set()

    def el(self, path, fps, dur_s, w=None, h=None, audio_ch=0, video=True):
        fid = self.ids.setdefault(os.path.abspath(path).lower(), f"file-{len(self.ids) + 1}")
        if fid in self.defined:
            return fid, f'<file id="{fid}"/>'
        self.defined.add(fid)
        media = ""
        if video:
            media += (f"<video><samplecharacteristics>{rate(fps)}<width>{w}</width>"
                      f"<height>{h}</height><pixelaspectratio>square</pixelaspectratio>"
                      "</samplecharacteristics></video>")
        if audio_ch:
            media += ("<audio><samplecharacteristics><depth>16</depth><samplerate>48000"
                      f"</samplerate></samplecharacteristics><channelcount>{audio_ch}"
                      "</channelcount></audio>")
        return fid, (f'<file id="{fid}"><name>{escape(os.path.basename(path))}</name>'
                     f"<pathurl>{escape(pathurl(path))}</pathurl>{rate(fps)}"
                     f"<duration>{max(1, fr(dur_s, fps))}</duration><media>{media}</media></file>")


def motion(scale_pct, horiz, vert):
    return f"""<filter><effect><name>Basic Motion</name><effectid>basic</effectid>
        <effectcategory>motion</effectcategory><effecttype>motion</effecttype><mediatype>video</mediatype>
        <parameter authoringApp="PremierePro"><parameterid>scale</parameterid><name>Scale</name>
          <valuemin>0</valuemin><valuemax>1000</valuemax><value>{scale_pct:.4f}</value></parameter>
        <parameter authoringApp="PremierePro"><parameterid>rotation</parameterid><name>Rotation</name>
          <valuemin>-8640</valuemin><valuemax>8640</valuemax><value>0</value></parameter>
        <parameter authoringApp="PremierePro"><parameterid>center</parameterid><name>Center</name>
          <value><horiz>{horiz:.6f}</horiz><vert>{vert:.6f}</vert></value></parameter>
        <parameter authoringApp="PremierePro"><parameterid>centerOffset</parameterid><name>Anchor Point</name>
          <value><horiz>0</horiz><vert>0</vert></value></parameter>
      </effect></filter>"""


def timeremap(pct):
    return f"""<filter><effect><name>Time Remap</name><effectid>timeremap</effectid>
        <effectcategory>motion</effectcategory><effecttype>motion</effecttype><mediatype>video</mediatype>
        <parameter authoringApp="PremierePro"><parameterid>variablespeed</parameterid><name>variablespeed</name>
          <valuemin>0</valuemin><valuemax>1</valuemax><value>0</value></parameter>
        <parameter authoringApp="PremierePro"><parameterid>speed</parameterid><name>speed</name>
          <valuemin>-100000</valuemin><valuemax>100000</valuemax><value>{pct:.4f}</value></parameter>
        <parameter authoringApp="PremierePro"><parameterid>reverse</parameterid><name>reverse</name><value>FALSE</value></parameter>
        <parameter authoringApp="PremierePro"><parameterid>frameblending</parameterid><name>frameblending</name><value>FALSE</value></parameter>
      </effect></filter>"""


def link(refs):
    return "".join(f"<link><linkclipref>{cid}</linkclipref><mediatype>{mt}</mediatype>"
                   f"<trackindex>{ti}</trackindex><clipindex>{ci}</clipindex>"
                   + (f"<groupindex>1</groupindex>" if mt == "audio" else "") + "</link>"
                   for cid, mt, ti, ci in refs)


def build_sequence(edl, reel, seq_i, files, infos, a, bal):
    fps = edl.get("fps", 25)
    W, H = edl.get("width", 1080), edl.get("height", 1920)
    v1, a1, a2, markers = [], [], [], []
    pos = 0
    for n, c in enumerate(reel["clips"], 1):
        path = source_path(edl, c, a.source)
        info = infos[path]
        d = fr(c["dur"], fps)
        if d < 1:
            continue
        sp = speed_of(c, info["fps"], fps)
        sin = fr(c["t"] / sp, fps)                         # retimed frames at sequence rate
        dur_clip = fr(info["dur"] / sp, fps)
        if sin + d > dur_clip:
            sys.exit(f"{reel['name']} clip {n}: runs past the end of {os.path.basename(path)}")
        start, end = pos, pos + d
        pos = end

        x0, y0, cw, ch, k = reframe(info["w"], info["h"], W, H,
                                    c.get("cx", 0.5), c.get("cy", 0.5), c.get("z", 1.0))
        offx = (info["w"] / 2 - (x0 + cw / 2)) * k        # sequence pixels, + = right
        offy = (info["h"] / 2 - (y0 + ch / 2)) * k        # sequence pixels, + = down
        filt = motion(k * 100, offx / info["w"], offy / info["h"])
        if abs(sp - 1) > 1e-6:
            filt += timeremap(sp * 100)

        name = escape(c.get("code") or os.path.basename(path))
        vid = f"v-{seq_i}-{n}"
        has_audio = info["audio_ch"] and not a.no_camera_audio and abs(sp - 1) < 1e-6
        refs = [(vid, "video", 1, len(v1) + 1)]
        if has_audio:
            refs += [(f"a1-{seq_i}-{n}", "audio", 1, len(a1) + 1),
                     (f"a2-{seq_i}-{n}", "audio", 2, len(a2) + 1)]
        lk = link(refs) if has_audio else ""
        fid, fe = files.el(path, info["fps"], info["dur"], info["w"], info["h"], info["audio_ch"])
        v1.append(f"""<clipitem id="{vid}"><name>{name}</name><enabled>TRUE</enabled>
      <duration>{dur_clip}</duration>{rate(fps)}<start>{start}</start><end>{end}</end>
      <in>{sin}</in><out>{sin + d}</out>{fe}<compositemode>normal</compositemode>{filt}{lk}</clipitem>""")
        if has_audio:
            for ch_i, tr in ((1, a1), (2, a2)):
                tr.append(f"""<clipitem id="a{ch_i}-{seq_i}-{n}"><name>{name}</name><enabled>TRUE</enabled>
      <duration>{dur_clip}</duration>{rate(fps)}<start>{start}</start><end>{end}</end>
      <in>{sin}</in><out>{sin + d}</out><file id="{fid}"/>
      <sourcetrack><mediatype>audio</mediatype><trackindex>{min(ch_i, info['audio_ch'])}</trackindex></sourcetrack>{lk}</clipitem>""")

        bits = []
        if c.get("text"):
            bits.append(f'TEXT: {c["text"]}')
        if bal:
            e = bal.get(clip_key(c))
            if e:
                p = e.get("params", {})
                bits.append(f"GRADE gamma={p.get('gamma')} sat={e.get('sat')} blk={p.get('imin')} "
                            f"wht r{p.get('rimax')}/g{p.get('gimax')}/b{p.get('bimax')}")
        elif c.get("lut"):
            bits.append(f'LUT: {c["lut"]}')
        if c.get("note"):
            bits.append(c["note"])
        bits += [f"POSITION {W / 2 + offx:.0f}, {H / 2 + offy:.0f}", f"SCALE {k * 100:.2f}",
                 f"SPEED {sp * 100:.2f}%", f"SRC {os.path.basename(path)} IN {source_tc(info, c['t'])}"]
        markers.append(f"""<marker><name>{n:02d} {name}</name>
      <comment>{escape(' | '.join(bits))}</comment><in>{start}</in><out>-1</out></marker>""")

    card = edl.get("endcard")
    if card and os.path.exists(card.get("image", "")):
        cd = fr(card.get("dur", 1.5), fps)
        _, fe = files.el(card["image"], fps, cd / fps, W, H)
        v1.append(f"""<clipitem id="card-{seq_i}"><name>end card</name><enabled>TRUE</enabled>
      <duration>{cd}</duration>{rate(fps)}<start>{pos}</start><end>{pos + cd}</end>
      <in>0</in><out>{cd}</out>{fe}</clipitem>""")
        pos += cd

    atracks = [a1, a2] if a1 else []
    mu = edl.get("music")
    if mu and mu.get("path"):
        mp = mu["path"]
        mdur = mu.get("duration") or probe_source(infos["__ffprobe"], mp)["dur"]
        off = fr(mu.get("offset", 0), fps)
        out = min(pos, fr(mdur, fps) - off)
        _, fe = files.el(mp, fps, mdur, audio_ch=2, video=False)
        base = len(atracks) + 1
        mid = [f"mus-{seq_i}-1", f"mus-{seq_i}-2"]
        lk = link([(mid[0], "audio", base, 1), (mid[1], "audio", base + 1, 1)])
        for ch_i in (1, 2):
            atracks.append([f"""<clipitem id="{mid[ch_i - 1]}"><name>{escape(os.path.basename(mp))}</name>
      <enabled>TRUE</enabled><duration>{fr(mdur, fps)}</duration>{rate(fps)}<start>0</start><end>{out}</end>
      <in>{off}</in><out>{off + out}</out>{fe if ch_i == 1 else f'<file id="{files.ids[os.path.abspath(mp).lower()]}"/>'}
      <sourcetrack><mediatype>audio</mediatype><trackindex>{ch_i}</trackindex></sourcetrack>{lk}</clipitem>"""])

    tracks = "".join(f"<track>{''.join(t)}</track>" for t in atracks)
    return f"""<sequence id="seq-{seq_i}">
  <name>{escape(reel['name'])}</name>
  <duration>{pos}</duration>{rate(fps)}
  <timecode>{rate(fps)}<string>00:00:00:00</string><frame>0</frame><displayformat>NDF</displayformat></timecode>
  <media>
    <video><format><samplecharacteristics>{rate(fps)}<width>{W}</width><height>{H}</height>
      <pixelaspectratio>square</pixelaspectratio><fielddominance>none</fielddominance></samplecharacteristics></format>
      <track>{''.join(v1)}</track></video>
    <audio><format><samplecharacteristics><depth>16</depth><samplerate>48000</samplerate></samplecharacteristics></format>
      {tracks}</audio>
  </media>
  {''.join(markers)}
</sequence>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edl")
    ap.add_argument("--out", required=True)
    ap.add_argument("--source", help="default file for clips with no `src` (must be an original)")
    ap.add_argument("--split", action="store_true", help="one .xml per reel")
    ap.add_argument("--balance", help="GRADEDIR from balance.py, values go into markers")
    ap.add_argument("--project", default="reelsmith cut")
    ap.add_argument("--allow-derived", action="store_true",
                    help="proceed even if a source looks like an export or a render")
    ap.add_argument("--no-camera-audio", action="store_true")
    ap.add_argument("--render-dir", action="append", default=[],
                    help="render output folder(s); sources inside them are refused")
    ap.add_argument("--ffmpeg")
    a = ap.parse_args()

    edl = json.load(open(a.edl, encoding="utf-8"))
    from rs_common import resolve_beats
    resolve_beats(edl, a.edl)
    _, fp = find_ffmpeg(a.ffmpeg)
    if not fp:
        sys.exit("ffprobe not found: it is needed to read each original's rate, size and timecode")
    W, H = edl.get("width", 1080), edl.get("height", 1920)

    infos, derived = {"__ffprobe": fp}, []
    for r in edl["reels"]:
        for c in r["clips"]:
            p = source_path(edl, c, a.source)
            if not p:
                sys.exit(f"{r['name']}: a clip has no `src` and there is no `source` or --source")
            if p in infos:
                continue
            if not os.path.exists(p):
                sys.exit(f"source not found: {p}")
            infos[p] = probe_source(fp, p)
            why = looks_derived(infos[p], W, H, p, a.render_dir)
            if why:
                derived.append((p, why))
    if derived:
        print("These sources do not look like camera originals:")
        for p, why in derived:
            print(f"  {p}\n     {'; '.join(why)}")
        if not a.allow_derived:
            sys.exit("\nThe XML must link the camera originals, not an export or rendered segments.\n"
                     "Point each clip's `src` at the original file and give `t` from the start of\n"
                     "that file. If an export really is all that exists, re-run with --allow-derived.")
        print("--allow-derived: proceeding. The editor gets no handles beyond this file.\n")

    bal = None
    if a.balance:
        raw = json.load(open(os.path.join(a.balance, "shot_params.json"), encoding="utf-8"))
        bal = raw.get("clips", raw)

    def wrap(seqs):
        return ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n'
                f'<xmeml version="4">\n<project><name>{escape(a.project)}</name>\n'
                f'<children>\n{"".join(seqs)}\n</children>\n</project>\n</xmeml>\n')

    n_src = len(infos) - 1
    if a.split:
        os.makedirs(a.out, exist_ok=True)
        for i, reel in enumerate(edl["reels"], 1):
            p = os.path.join(a.out, f"{reel['name']}.xml")
            open(p, "w", encoding="utf-8").write(wrap([build_sequence(edl, reel, i, Files(), infos, a, bal)]))
            print(f"{reel['name']:34} {len(reel['clips']):3d} clips -> {p}")
    else:
        files = Files()
        seqs = [build_sequence(edl, r, i, files, infos, a, bal) for i, r in enumerate(edl["reels"], 1)]
        open(a.out, "w", encoding="utf-8").write(wrap(seqs))
        print(f"{len(seqs)} sequence(s) -> {a.out}")
    kind = "file(s), including the derived ones listed above" if derived else "camera original(s)"
    print(f"linked to {n_src} {kind}; nothing was cut or rendered")
    print("\nPremiere: File > Import, pick the .xml. Each reel arrives as a sequence of")
    print("original clips with in/out, reframe and speed set. Markers carry the exact")
    print("values, the source timecode and any grade, so a misread value can be typed in.")


if __name__ == "__main__":
    main()
