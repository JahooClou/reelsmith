---
name: reel-cut
description: >
  The hands-on cutting tools of reelsmith: log camera originals, find shots, verify
  in-points, map and shorten music, cut to the beat one frame early, reframe to any
  aspect, render, hand over a Premiere XML linked to the originals, and measure an
  editor's re-edit. Use for a single concrete task ("log this footage", "what shots
  are in this file", "cut this to the beat", "shorten this track to 100 seconds",
  "make an XML", "what did I change in my re-edit"). For a whole edit from intake to
  delivery, use reelsmith.
---

# Reel cut

Scripts are in `${CLAUDE_PLUGIN_ROOT}/scripts/`. Read
`../reelsmith/references/pitfalls.md` before rendering anything — items 1 to 4 are
the ones that produce a plausible file that is wrong, and item 20 is the one that
costs the editor their handles.

## 0. Cut from the camera originals, always

Every step below works on the **camera original files**, and the edit list points
each clip at its original (`src`) with `t` in seconds from the start of that file.
The render, the grade and the Premiere sequence are all built from those files.

Never build the edit on, or hand over, a prerendered file: an export of an earlier
edit, a concatenated "selects" master, a vertical version someone already cut, or
reelsmith's own rendered segments. An export has lost the handles either side of
each shot, the full frame you would reframe from, the full frame rate you would
slow down from, and the original colour; an editor handed it can only trim, never
extend.

If all you were given is an export, ask where the originals are before going any
further. If they genuinely do not exist, say so plainly, and only then work from the
export, passing `--allow-derived` to `premiere_xml.py`.

## 1. Probe

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/ffmpeg_tools.py --probe ORIGINAL [ORIGINAL ...]
```

Resolution, frame rate, duration, and what a 9:16 crop would yield. Do this before
promising a reframe. A 3:2 open-gate frame gives 2232×4000 at 9:16; UHD 16:9 gives
1215×2160; HD 16:9 gives 608×1080, which is genuinely short. The usual constraint
is composition, not pixels.

Record what probing says about each original: frame rate (50p and 59.94p originals
give true slow motion on a 25p timeline), whether it carries sound, and its embedded
timecode. They all feed the edit list and the XML.

## 2. Log, then detect shots inside long files

Many originals: log them as a set first.

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/logsheet.py /shoot/CamA /shoot/CamB --out log/
```

Contact sheets in recording order, every tile labelled `CODE m:ss`, plus an index
and `clips.json`.

Camera originals are usually one take per file, so a file is often a shot. Run
detection on the long ones: continuous coverage, a multicam recording, or a
single file holding many takes.

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/shots.py ORIGINAL --out DIR --segments segments.json
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
python ${CLAUDE_PLUGIN_ROOT}/scripts/verify.py ORIGINAL --scan 106 124 --step 2 --out take.jpg

# then check the whole edit list as it will be seen: first, middle and last frame
# of every clip, cut from its original, through its 9:16 window, at its speed
python ${CLAUDE_PLUGIN_ROOT}/scripts/verify.py --edl edl.json --out check.jpg
```

Anything over about six seconds needs the dense scan. It costs a minute and it is
the single highest-value step in this skill.

The `--edl` check is the second most valuable. On a landscape original the subject
can walk out of the crop halfway through a clip; a slow-motion clip covers less
source time than its length suggests; a sprint can leave an empty lane by the last
frame. None of that is visible in a single in-point frame.

## 4. Music: map it, shorten it, cut to it

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/beats.py MUSIC --fps 25 --out beats.json
python ${CLAUDE_PLUGIN_ROOT}/scripts/music_cut.py MUSIC --beats beats.json --suggest 95 120
python ${CLAUDE_PLUGIN_ROOT}/scripts/music_cut.py MUSIC --beats beats.json --keep bar:1-44,bar:105-end --out cut.wav
python ${CLAUDE_PLUGIN_ROOT}/scripts/beats.py cut.wav --fps 25 --out cut_beats.json
```

`beats.py` tracks the beats (generated music drifts), puts them on the audible
transient, finds downbeats, bars and sections, and gives cut frames **one frame
before each beat**: audio follows video. `music_cut.py` shortens a track by whole
sections, downbeat to downbeat, with an equal-power cross-fade.

In the edit list, set `"beat_map": "cut_beats.json", "lead": 1` and give lengths in
`beats`; every tool then places the cuts the same way (`edl.md`).

Do not put every cut on the same beat count. Runs of one and two beats, then a hold
of four to eight: the held shot is what makes the pattern legible
(`../reelsmith/references/craft.md`).

## 5. Write the edit list, then render from it

The edit list is the deliverable that survives. The mp4 can always be rebuilt.

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/render.py edl.json --out DIR \
  --luts LUTDIR --captions CAPDIR
```

Schema is in `../reelsmith/references/edl.md`. Each clip names its original with
`src`; `cx`, `cy` and `z` place the 9:16 window; `speed` is a percentage or
`"conform"`. The renderer cuts every clip from its original, snaps durations to
whole frames, places `-t` after all inputs, keeps segment sound as PCM so the joins
stay frame-exact, and re-encodes the final pass at constant frame rate.

It verifies the output frame rate and warns if it drifted, which is the symptom of
a duration that was not a whole number of frames.

## 6. Hand the cut to an editor

If someone will finish in Premiere rather than taking the render:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/premiere_xml.py edl.json --out cut.xml \
  --balance GRADEDIR
```

Produces FCP7 XML, which Premiere imports without a plugin as a bin of sequences.
Use `--split` for one file per reel.

**Every clip is linked to its camera original** with in and out points. Nothing is
cut, copied or rendered for the handover. The reframe arrives as Motion Scale and
Position, slow motion as speed with frame blending off, camera sound linked on A1/A2
for real-time clips, music on A3/A4 if the edit list has one. The editor can slide a
cut, extend a shot into its handles, reframe from the full frame and re-time from
the full frame rate.

The script **refuses a source that looks like an export**: one already at the
delivery size, or one inside a render folder (`--render-dir`). It names the file and
the reason. Point the clip at its original instead. `--allow-derived` overrides it
for the case where an export really is all that exists, and the output says so.

**Colour does not travel.** FCP7 XML cannot express Lumetri, so grade values are
written as timeline markers instead. The editor puts the shared look on an
adjustment layer and dials per-clip values from the markers. Every marker also
carries the clip's Position, Scale, Speed and source timecode, so a value that
imports wrongly can be typed in, and caption text, so the words arrive with the cut.

Give the editor the list as well: shot, clip name, source TC in and out, duration,
speed. Timecode is the clip's own, counted at its own frame rate (Canon 50p counts
frames 00–49; DJI 59.94p is drop-frame with frames 00–59, from a 29.97 track).

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

## 9. Measure an editor's re-edit

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/review_xml.py reedit.xml --edl edl.json --beats beats.json --out review.md
```

From a Premiere FCP7 XML export: cut timing against the beat in frames, shot lengths
in beats, what was kept, dropped, reordered and trimmed, punch-ins, speed, extra
layers and the music edit. See `../reelsmith/references/review.md`.
