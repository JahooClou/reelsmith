# -*- coding: utf-8 -*-
"""Convert an edit list to FCP7 XML, which Premiere Pro imports as real sequences.

  python premiere_xml.py edl.json --source SRC --out cut.xml
  python premiere_xml.py edl.json --source SRC --out DIR --split
  python premiere_xml.py edl.json --source SRC --out cut.xml --balance GRADEDIR

Premiere reads three interchange formats. FCP7 XML is the one to use: CMX3600
cannot carry source file paths, and AAF is binary and fussy. FCP7 XML is text,
Premiere imports it without a plugin, and it arrives as a bin of sequences with
clips already cut and positioned.

The XML references your ORIGINAL master with in and out points. It does not
reference rendered clips, because the point of handing an editor a sequence is
that they can slide a cut or extend a shot against the real media.

Colour does not travel. FCP7 XML has no way to express Lumetri, so grade values
are written as timeline markers instead — the editor sees the numbers on the
clip and can dial them in, or drop the shared look on an adjustment layer.

Caption text also becomes markers, so text and position arrive with the cut.
"""
import argparse, json, os, sys, urllib.parse
from xml.sax.saxutils import escape


def f(sec, fps):
    return int(round(sec * fps))


def pathurl(p):
    ap = os.path.abspath(p).replace("\\", "/")
    if len(ap) > 1 and ap[1] == ":":                       # Windows drive letter
        return "file://localhost/" + urllib.parse.quote(ap, safe="/:")
    return "file://localhost" + urllib.parse.quote(ap, safe="/:")


def rate(fps):
    ntsc = "TRUE" if abs(fps - round(fps)) > 1e-6 else "FALSE"
    return f"<rate><timebase>{int(round(fps))}</timebase><ntsc>{ntsc}</ntsc></rate>"


def file_element(fid, src, fps, W, H, dur_frames, first):
    """Full definition once; every later reference is just <file id="..."/>."""
    if not first:
        return f'<file id="{fid}"/>'
    return f"""<file id="{fid}">
              <name>{escape(os.path.basename(src))}</name>
              <pathurl>{escape(pathurl(src))}</pathurl>
              {rate(fps)}
              <duration>{dur_frames}</duration>
              <media>
                <video>
                  <samplecharacteristics>
                    {rate(fps)}
                    <width>{W}</width><height>{H}</height>
                    <pixelaspectratio>square</pixelaspectratio>
                  </samplecharacteristics>
                </video>
                <audio>
                  <samplecharacteristics><depth>16</depth><samplerate>48000</samplerate></samplecharacteristics>
                  <channelcount>2</channelcount>
                </audio>
              </media>
            </file>"""


def build_sequence(reel, src, fps, W, H, src_frames, seq_i, seen_file, bal=None):
    clips, markers = [], []
    pos = 0
    vid, aud1, aud2, links = [], [], [], []
    for n, c in enumerate(reel["clips"], 1):
        d = f(c["dur"], fps)
        if d < 1:
            continue
        sin = f(c["t"], fps)
        sout = sin + d
        start, end = pos, pos + d
        pos = end

        vid_id = f"cv-{seq_i}-{n}"
        a1_id = f"ca1-{seq_i}-{n}"
        a2_id = f"ca2-{seq_i}-{n}"
        name = escape(c.get("code") or f"clip{n}")
        fe = file_element("file-1", src, fps, W, H, src_frames, not seen_file[0])
        seen_file[0] = True

        link = (f"""<link><linkclipref>{vid_id}</linkclipref><mediatype>video</mediatype>
                    <trackindex>1</trackindex><clipindex>{n}</clipindex></link>
                  <link><linkclipref>{a1_id}</linkclipref><mediatype>audio</mediatype>
                    <trackindex>1</trackindex><clipindex>{n}</clipindex><groupindex>1</groupindex></link>
                  <link><linkclipref>{a2_id}</linkclipref><mediatype>audio</mediatype>
                    <trackindex>2</trackindex><clipindex>{n}</clipindex><groupindex>1</groupindex></link>""")

        vid.append(f"""<clipitem id="{vid_id}">
              <name>{name}</name><enabled>TRUE</enabled>
              <duration>{src_frames}</duration>{rate(fps)}
              <start>{start}</start><end>{end}</end>
              <in>{sin}</in><out>{sout}</out>
              {fe}
              <compositemode>normal</compositemode>
              {link}
            </clipitem>""")

        for ch, aid in ((1, a1_id), (2, a2_id)):
            aud = aud1 if ch == 1 else aud2
            aud.append(f"""<clipitem id="{aid}">
              <name>{name}</name><enabled>TRUE</enabled>
              <duration>{src_frames}</duration>{rate(fps)}
              <start>{start}</start><end>{end}</end>
              <in>{sin}</in><out>{sout}</out>
              <file id="file-1"/>
              <sourcetrack><mediatype>audio</mediatype><trackindex>{ch}</trackindex></sourcetrack>
              {link}
            </clipitem>""")

        # colour and caption travel as markers, since XML cannot carry Lumetri
        bits = []
        if c.get("text"):
            bits.append(f'TEXT: {c["text"]}')
        if bal:
            e = bal.get(f"{c['t']:.2f}")
            if e:
                p = e.get("params") or e.get("p") or {}
                bits.append(f"GRADE gamma={p['gamma']} sat={e['sat']} "
                            f"blk={p['imin']} wht r{p['rimax']}/g{p['gimax']}/b{p['bimax']}")
        elif c.get("lut"):
            bits.append(f'LUT: {c["lut"]}')
        if c.get("note"):
            bits.append(c["note"])
        if bits:
            markers.append(f"""<marker>
            <comment>{escape(' | '.join(bits))}</comment>
            <name>{name}</name><in>{start}</in><out>-1</out>
          </marker>""")

    return f"""<sequence id="seq-{seq_i}">
        <name>{escape(reel['name'])}</name>
        <duration>{pos}</duration>{rate(fps)}
        <timecode>{rate(fps)}<string>00:00:00:00</string><frame>0</frame>
          <displayformat>NDF</displayformat></timecode>
        <media>
          <video>
            <format><samplecharacteristics>{rate(fps)}
              <width>{W}</width><height>{H}</height>
              <pixelaspectratio>square</pixelaspectratio>
            </samplecharacteristics></format>
            <track>{''.join(vid)}</track>
          </video>
          <audio>
            <format><samplecharacteristics><depth>16</depth><samplerate>48000</samplerate></samplecharacteristics></format>
            <track>{''.join(aud1)}</track>
            <track>{''.join(aud2)}</track>
          </audio>
        </media>
        {''.join(markers)}
      </sequence>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edl")
    ap.add_argument("--source", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--split", action="store_true", help="one .xml per reel")
    ap.add_argument("--balance", help="GRADEDIR from balance.py, values go into markers")
    ap.add_argument("--project", default="reelsmith cut")
    ap.add_argument("--ffmpeg")
    a = ap.parse_args()

    edl = json.load(open(a.edl, encoding="utf-8"))
    fps = edl.get("fps", 25)
    W, H = edl.get("width", 1080), edl.get("height", 1920)
    bal = None
    if a.balance:
        raw = json.load(open(os.path.join(a.balance, "shot_params.json"),
                             encoding="utf-8"))
        # tolerate both shapes: {"look":..,"clips":{..}} and a bare {timecode: {..}}
        bal = raw.get("clips", raw)

    src_frames = 0
    try:
        from rs_common import find_ffmpeg, probe
        _, fp = find_ffmpeg(a.ffmpeg)
        if fp:
            src_frames = f(probe(fp, a.source)["duration"], fps)
    except Exception:
        pass
    if not src_frames:
        src_frames = 10 ** 7            # Premiere only needs it to exceed the outs

    def wrap(seqs):
        return ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n'
                f'<xmeml version="4">\n  <project>\n    <name>{escape(a.project)}</name>\n'
                f'    <children>\n      {"".join(seqs)}\n    </children>\n'
                '  </project>\n</xmeml>\n')

    if a.split:
        os.makedirs(a.out, exist_ok=True)
        for i, reel in enumerate(edl["reels"], 1):
            seen = [False]
            s = build_sequence(reel, a.source, fps, W, H, src_frames, i, seen, bal)
            p = os.path.join(a.out, f"{reel['name']}.xml")
            open(p, "w", encoding="utf-8").write(wrap([s]))
            print(f"{reel['name']:34} {len(reel['clips']):2d} clips -> {p}")
    else:
        seen = [False]
        seqs = [build_sequence(r, a.source, fps, W, H, src_frames, i, seen, bal)
                for i, r in enumerate(edl["reels"], 1)]
        open(a.out, "w", encoding="utf-8").write(wrap(seqs))
        print(f"{len(seqs)} sequences -> {a.out}")

    print("\nPremiere: File > Import, pick the .xml. It arrives as a bin of")
    print("sequences, clips cut and positioned, linked to the master.")
    print("Colour is in the markers: XML cannot carry Lumetri. Put the shared")
    print("look on an adjustment layer and dial per-clip values from the markers.")


if __name__ == "__main__":
    main()
