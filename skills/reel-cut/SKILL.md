---
name: reel-cut
description: >
  Detect shots in video, build a verified edit list, and render finished vertical
  clips with ffmpeg. Use whenever someone wants to know what shots are in a file,
  pull short clips out of a long video, build a shot list or contact sheet, cut
  footage to the beat of a track, reframe landscape footage to 9:16, or render an
  edit from timecodes. Also use when someone has a teaser, trailer, event recap or
  interview and wants social cutdowns from it, or asks for an EDL, edit list or
  shot inventory.
---

# Reel cut

Scripts are in `${CLAUDE_PLUGIN_ROOT}/scripts/`. Read
`../reelsmith/references/pitfalls.md` before rendering anything — items 1 to 4 are
the ones that produce a plausible file that is wrong.

## 1. Probe

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/ffmpeg_tools.py --probe SOURCE
```

Resolution, frame rate, duration, and what a 9:16 crop would yield. Do this before
promising a reframe. A 3:2 open-gate frame gives 2232×4000 at 9:16; UHD 16:9 gives
1215×2160; HD 16:9 gives 608×1080, which is genuinely short. The usual constraint
is composition, not pixels.

## 2. Detect shots

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/shots.py SOURCE --out DIR --segments segments.json
```

Segments let each section carry its own threshold:

```json
[{"name": "CamA", "code": "CA", "start": 0, "end": 233.5, "threshold": 0.14},
 {"name": "SlowMo", "code": "SL", "start": 233.5, "end": 583.0, "threshold": 0.10}]
```

**Use per-segment thresholds when the material is mixed.** A threshold tuned for
handheld action merges cuts in slow motion, where consecutive frames are far more
alike. If the shot count disagrees with what the person who shot it expects, the
threshold or a segment boundary is wrong — check before building on it.

Shot codes carry the segment prefix, so a code tells you which camera and therefore
which LUT a clip needs.

## 3. Verify in-points — do not skip this

The contact sheet samples **one frame per shot, near the middle**. On a
twenty-second take that frame can be ten seconds from the shot's start. Choose a
frame from the sheet, write down the shot's start timecode, and you will cut
something else entirely. Nothing catches it until the render.

```bash
# sample a long take densely before choosing a moment inside it
python ${CLAUDE_PLUGIN_ROOT}/scripts/verify.py SOURCE --scan 106 124 --step 2 --out take.jpg

# then render every in-point you actually intend to use, and look at them
python ${CLAUDE_PLUGIN_ROOT}/scripts/verify.py SOURCE --points points.json --out check.jpg
```

Anything over about six seconds needs the dense scan. It costs a minute and it is
the single highest-value step in this skill.

## 4. Cut to beat, if there is music

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/beats.py MUSIC --fps 25 --every 4
```

Returns tempo, a beat grid, and cut points already snapped to whole frames.
`clip_durations` drops straight into an edit list.

Do not put every cut on a beat for a whole reel — it reads as mechanical. Hold a
shot through a beat where the picture earns it; the held shot is what makes the
pattern legible.

## 5. Write the edit list, then render from it

The edit list is the deliverable that survives. The mp4 can always be rebuilt.

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/render.py edl.json --source SRC --out DIR \
  --luts LUTDIR --captions CAPDIR
```

Schema is in `../reelsmith/references/edl.md`. The renderer snaps durations to
whole frames, places `-t` after all inputs, re-encodes the final pass at constant
frame rate, and picks a LUT per clip from its source timecode so colour follows a
shot when you reorder.

It verifies the output frame rate and warns if it drifted, which is the symptom of
a duration that was not a whole number of frames.

## 6. Hand the cut to an editor

If someone will finish in Premiere rather than taking the render:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/premiere_xml.py edl.json --source SRC \
  --out cut.xml --balance GRADEDIR
```

Produces FCP7 XML, which Premiere imports without a plugin as a bin of sequences
with clips cut and positioned. Use `--split` for one file per reel.

It references the **original master with in and out points**, not rendered clips.
That is the point of handing over a sequence: the editor can slide a cut or extend
a shot against the real media.

**Colour does not travel.** FCP7 XML cannot express Lumetri, so grade values are
written as timeline markers instead. The editor puts the shared look on an
adjustment layer and dials per-clip values from the markers. Caption text goes in
the markers too, so the words and their positions arrive with the cut.

CMX3600 EDL is the other format people ask for, and it cannot carry source paths at
all. FCP7 XML is the one to send.

## 7. Captions

Render the picture clean and hand over the text with its timings unless someone
specifically wants them burnt in. Caption placement is a per-shot judgement — a
fixed height that reads over a wide shot lands on a face in a close-up — and that
judgement is easier in an editor than in a script.

If burning in, use `scripts/captions.py`, which renders plates with PIL. ffmpeg's
`drawtext` cannot select a named instance of a variable font and will silently give
you Regular when you asked for Bold Condensed.

## 8. End card

Cap it at about 1.5 seconds. A static card is where completion rate dies, and if it
needs longer to read it has too much on it.
