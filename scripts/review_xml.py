# -*- coding: utf-8 -*-
"""Read an editor's re-edit (FCP7 XML exported from Premiere) and say what changed.

  python review_xml.py REEDIT.xml --edl edl.json --out review.md
  python review_xml.py REEDIT.xml --beats music_beats.json --edl edl.json --out review.md

This is how the skill learns. The editor takes the cut, changes it, exports
File > Export > Final Cut Pro XML, and this script measures the changes instead of
guessing at them:

  timing     every picture cut against the nearest beat of the music AS EDITED in
             the sequence (the music clips on A1 are followed through their own
             splices), in frames. Negative = the cut leads the beat.
  rhythm     shot lengths in beats, mean shot length, the opening shots
  selection  which of the original clips were kept, dropped, moved, trimmed or
             extended; new moments taken from the same camera files; new files
             (graphics, renders, transitions)
  framing    punch-ins (scale above the fill scale) and re-centred crops
  speed      slow motion and speed-ups (Time Remap)
  sound      the music edit (which source ranges, where the splices sit), SFX and
             other audio layers

--beats is beats.py output for the ORIGINAL music file. Without it the script finds
the music on A1 and runs beats.py on it. --edl is the reelsmith edit list the XML was
first made from; without it, only the timing, rhythm and layer report are written.
"""
import argparse, collections, json, os, subprocess, sys, tempfile, urllib.parse
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))


def num(el, tag, default=None):
    v = el.findtext(tag)
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def path_of(f):
    p = f.findtext("pathurl") or ""
    p = urllib.parse.unquote(p.replace("file://localhost/", "").replace("file://", ""))
    return p


def rate_of(el):
    tb = num(el, "rate/timebase", 25)
    return tb * 1000 / 1001 if (el.findtext("rate/ntsc") or "").upper() == "TRUE" else float(tb)


def params(ci):
    out = {}
    for e in ci.findall("filter/effect"):
        for p in e.findall("parameter"):
            pid, v = p.findtext("parameterid"), p.find("value")
            if v is None:
                continue
            if v.find("horiz") is not None:
                out[pid] = (float(v.findtext("horiz")), float(v.findtext("vert")))
            else:
                try:
                    out[pid] = float(v.text)
                except (TypeError, ValueError):
                    out[pid] = v.text
    return out


def resolve_track(track, files):
    """Clipitems with -1 edges sit in a transition: take the transition's edge, and
    record the edit point at the transition's centre."""
    items, out = list(track), []
    for k, it in enumerate(items):
        if it.tag != "clipitem":
            continue
        s, e = num(it, "start"), num(it, "end")
        edit_s = edit_e = None
        if s == -1:
            tr = next((x for x in reversed(items[:k]) if x.tag == "transitionitem"), None)
            s = num(tr, "start"); edit_s = (num(tr, "start") + num(tr, "end")) / 2
        if e == -1:
            tr = next((x for x in items[k + 1:] if x.tag == "transitionitem"), None)
            e = num(tr, "end"); edit_e = (num(tr, "start") + num(tr, "end")) / 2
        f = it.find("file")
        fid = f.get("id") if f is not None else None
        fi = files.get(fid, {})
        out.append(dict(id=it.get("id"), name=it.findtext("name"), start=s, end=e,
                        edit_start=edit_s if edit_s is not None else s, edit_end=edit_e if edit_e is not None else e,
                        i=num(it, "in"), o=num(it, "out"), enabled=(it.findtext("enabled") or "TRUE") == "TRUE",
                        file=fi.get("name"), path=fi.get("path"), frate=fi.get("rate"),
                        w=fi.get("w"), h=fi.get("h"), p=params(it)))
    return out


def music_beats(path, beats_json):
    if beats_json:
        return json.load(open(beats_json, encoding="utf-8"))
    tmp = tempfile.mktemp(suffix=".json")
    subprocess.run([sys.executable, os.path.join(HERE, "beats.py"), path, "--out", tmp],
                   check=True, capture_output=True)
    return json.load(open(tmp, encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xml")
    ap.add_argument("--edl", help="the reelsmith edit list the XML was made from")
    ap.add_argument("--beats", help="beats.py output for the original music file")
    ap.add_argument("--out", default="review.md")
    a = ap.parse_args()

    root = ET.parse(a.xml).getroot()
    files = {}
    for f in root.iter("file"):
        if f.find("pathurl") is not None:
            files[f.get("id")] = dict(name=f.findtext("name"), path=path_of(f), rate=rate_of(f),
                                      w=num(f, "media/video/samplecharacteristics/width"),
                                      h=num(f, "media/video/samplecharacteristics/height"))
    seq = root.find(".//sequence")
    fps = rate_of(seq)
    W = num(seq, "media/video/format/samplecharacteristics/width", 1920)
    H = num(seq, "media/video/format/samplecharacteristics/height", 1080)
    vt = [resolve_track(t, files) for t in seq.findall("media/video/track")]
    at = [resolve_track(t, files) for t in seq.findall("media/audio/track")]
    total = num(seq, "duration", 0)
    L = []
    add = L.append
    add(f"# Re-edit review: {seq.findtext('name')}\n")
    add(f"Sequence {W}x{H}, {fps:g} fps, {total} frames ({total / fps:.2f} s). "
        f"V1 {len(vt[0]) if vt else 0} clips; {sum(len(t) for t in vt[1:])} on upper video tracks; "
        f"{len(at)} audio tracks.\n")

    # ------------------------------------------------------------ music as edited
    music = None
    if at:
        a1 = [c for c in at[0] if c["path"]]
        if a1:
            cnt = collections.Counter(c["path"] for c in a1)
            mpath = cnt.most_common(1)[0][0]
            music = [c for c in a1 if c["path"] == mpath]
    beat_seq = []
    if music:
        bj = music_beats(music[0]["path"], a.beats)
        add("## Music\n")
        add(f"`{os.path.basename(music[0]['path'])}`, {bj.get('bpm')} BPM. Used in the sequence:\n")
        for c in music:
            s_src, e_src = c["i"] / fps, c["o"] / fps
            add(f"- source {s_src:7.2f}-{e_src:7.2f} s at sequence {c['start'] / fps:7.2f}-{c['end'] / fps:7.2f} s"
                + (f" (cross-fade, edit point {c['edit_end'] / fps:.2f} s)" if c["edit_end"] != c["end"] else ""))
            # beats inside the part of this clip that is heard up to its edit points
            for b in bj["beats"]:
                t_seq = c["start"] + (b["t"] * fps - c["i"])
                if c["edit_start"] - 0.5 <= t_seq < c["edit_end"]:
                    beat_seq.append((t_seq, b["downbeat"]))
        if len(music) > 1:
            add("\nSplices: " + ", ".join(
                f"{music[k]['o'] / fps - (music[k]['end'] - music[k]['edit_end']) / fps:.2f} s -> "
                f"{music[k + 1]['i'] / fps + (music[k + 1]['edit_start'] - music[k + 1]['start']) / fps:.2f} s of the source"
                for k in range(len(music) - 1)))
        add(f"\nMusic length in the sequence: {max(c['end'] for c in music) / fps:.2f} s.\n")
    beat_seq.sort()

    # ------------------------------------------------------------ cut timing
    v1 = sorted(vt[0], key=lambda c: c["start"]) if vt else []
    rows = []
    if beat_seq and v1:
        bt = [b for b, _ in beat_seq]
        offs = []
        for c in v1[1:]:
            j = min(range(len(bt)), key=lambda k: abs(bt[k] - c["start"]))
            offs.append(c["start"] - bt[j])
        r = collections.Counter(int(round(o)) for o in offs)
        lead = sorted(offs)[len(offs) // 2]
        add("## Cut timing against the beat\n")
        add("Frames from each picture cut to the nearest beat (negative: the cut comes first).\n")
        add("| frames | " + " | ".join(str(k) for k in sorted(r)) + " |")
        add("|---|" + "---|" * len(r))
        add("| cuts | " + " | ".join(str(r[k]) for k in sorted(r)) + " |\n")
        early = sum(1 for o in offs if -2.5 <= o <= -0.5)
        add(f"Median {lead:+.1f} frames. {early} of {len(offs)} cuts lead the beat by 1-2 frames; "
            f"{sum(1 for o in offs if abs(o) < 0.5)} are on it.\n")
        per = (bt[-1] - bt[0]) / max(len(bt) - 1, 1)
        lens = [(c["end"] - c["start"]) / per for c in v1]
        hb = collections.Counter(int(round(x)) for x in lens)
        add("Shot lengths in beats: " + ", ".join(f"{k} beat{'s' if k != 1 else ''}: {hb[k]}" for k in sorted(hb)) + ".\n")
    if v1:
        lens_s = [(c["end"] - c["start"]) / fps for c in v1]
        add(f"{len(v1)} shots on V1, mean {sum(lens_s) / len(lens_s):.2f} s, median {sorted(lens_s)[len(lens_s) // 2]:.2f} s.\n")
        add("Opening: " + "; ".join(f"{c['file']} ({(c['end'] - c['start']) / fps:.2f} s)" for c in v1[:3]) + ".\n")

    # ------------------------------------------------------------ framing and speed
    add("## Framing and speed\n")
    punch, slow, fast = [], [], []
    for c in v1:
        if not c["w"] or not c["h"]:
            continue
        fill = 100 * max(W / c["w"], H / c["h"])
        sc = c["p"].get("scale", fill) if isinstance(c["p"].get("scale"), float) else fill
        if sc > fill * 1.03:
            punch.append((c, sc / fill))
        sp = c["p"].get("speed") if isinstance(c["p"].get("speed"), float) else 100.0
        if sp < 99:
            slow.append((c, sp))
        elif sp > 101:
            fast.append((c, sp))
    add(f"- punch-ins (scaled past the fill): {len(punch)}" + (": " + ", ".join(
        f"{c['file']} at {c['start'] / fps:.2f} s x{k:.2f}" for c, k in punch) if punch else ""))
    add(f"- slow motion: {len(slow)} clips ({', '.join(sorted({f'{sp:.1f}%' for _, sp in slow}))})")
    add(f"- speed-ups: {len(fast)}" + (": " + ", ".join(f"{c['file']} {sp:.0f}%" for c, sp in fast) if fast else ""))
    # consecutive slices of one take with rising scale: a stepped punch-in
    steps = []
    for k in range(len(v1) - 2):
        a0, a1_, a2 = v1[k:k + 3]
        if a0["path"] == a1_["path"] == a2["path"] and a0["o"] == a1_["i"] and a1_["o"] == a2["i"]:
            s0, s1, s2 = (x["p"].get("scale", 0) for x in (a0, a1_, a2))
            if isinstance(s0, float) and s0 < s1 < s2:
                steps.append(a0)
    if steps:
        add(f"- stepped punch-in (one take cut into slices, each scaled further in): "
            + ", ".join(f"{c['file']} at {c['start'] / fps:.2f} s" for c in steps))
    add("")

    # ------------------------------------------------------------ layers
    add("## Other layers\n")
    for n, t in enumerate(vt[1:], 2):
        for c in t:
            add(f"- V{n} {c['start'] / fps:7.2f} s  {(c['end'] - c['start']) / fps:5.2f} s  {c['file']}")
    for n, t in enumerate(at, 1):
        for c in t:
            if music and c in music:
                continue
            if n % 2 == 0 and any(x["path"] == c["path"] and x["start"] == c["start"] for x in at[n - 2]):
                continue                                   # right channel of a stereo pair
            add(f"- A{n} {c['start'] / fps:7.2f} s  {(c['end'] - c['start']) / fps:5.2f} s  {c['file']}")
    add("")

    # ------------------------------------------------------------ against the original edit list
    if a.edl:
        e = json.load(open(a.edl, encoding="utf-8"))
        srcs = e.get("sources", {})
        orig = []
        for reel in e["reels"]:
            for k, c in enumerate(reel["clips"], 1):
                p = srcs.get(c.get("src"), c.get("src") or e.get("source"))
                p = p["path"] if isinstance(p, dict) else p
                orig.append(dict(n=k, file=os.path.basename(p or ""), t=c["t"], dur=c["dur"], note=c.get("note", ""),
                                 code=c.get("code", "")))
        used, matches = set(), []
        for c in sorted([x for t in vt for x in t], key=lambda x: x["start"]):
            sp = c["p"].get("speed") if isinstance(c["p"].get("speed"), float) else 100.0
            t_src = c["i"] / fps * sp / 100 if c["i"] is not None else None
            cand = [o for o in orig if o["file"].lower() == (c["file"] or "").lower() and t_src is not None
                    and abs(o["t"] - t_src) < 4]
            m = min(cand, key=lambda o: abs(o["t"] - t_src)) if cand else None
            if m:
                used.add(m["n"])
            matches.append((c, m, t_src))
        add("## Against the original cut\n")
        kept = [m for _, m, _ in matches if m]
        add(f"Kept {len(used)} of {len(orig)} original shots. "
            f"New moments from the same camera files: {sum(1 for c, m, t in matches if not m and any(o['file'].lower() == (c['file'] or '').lower() for o in orig))}. "
            f"New files: {len({c['file'] for c, m, t in matches if not m and not any(o['file'].lower() == (c['file'] or '').lower() for o in orig)})}.\n")
        order = [m["n"] for m in kept]
        inv = sum(1 for i in range(len(order)) for j in range(i + 1, len(order)) if order[i] > order[j])
        frac = inv / max(len(order) * (len(order) - 1) / 2, 1)
        add(f"Order: {frac:.0%} of shot pairs swapped ("
            + ("largely the original order" if frac < 0.1 else
               "partly re-ordered, in blocks" if frac < 0.3 else "substantially re-ordered") + ").\n")
        add("| at | len | file | was # | in-point moved | note |")
        add("|---|---|---|---|---|---|")
        for c, m, t in matches:
            add(f"| {c['start'] / fps:.2f} | {(c['end'] - c['start']) / fps:.2f} | {c['file']} | "
                f"{m['n'] if m else 'new'} | {(f'{t - m['t']:+.2f} s') if m else ''} | {m['note'] if m else ''} |")
        add("\nDropped: " + "; ".join(f"#{o['n']} {o['note'] or o['file']}" for o in orig if o["n"] not in used) + "\n")

    open(a.out, "w", encoding="utf-8").write("\n".join(L))
    print("\n".join(L[:40]))
    print(f"...\n-> {a.out}")


if __name__ == "__main__":
    main()
