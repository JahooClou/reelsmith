---
name: reelsmith
description: >
  Step-gated pipeline for turning raw footage into finished short-form vertical
  video (Reels, TikTok, Shorts). Handles concept and hooks, optional brand
  extraction, shot detection, reframing to 9:16, measured colour grading with
  generated .cube LUTs, caption typography, optional cut-to-beat music editing,
  and the final render, or a Premiere sequence linked to the camera originals, plus
  a written edit list. Use this whenever someone wants
  to make reels, shorts, vertical video, social video cutdowns, a teaser or
  trailer from existing footage, or asks to analyse footage and build an edit —
  even if they only mention one part of it, like "make a LUT for this" or "cut
  this to the beat" or "what shots do I have in this file". Also use when someone
  has a long video and wants short clips out of it.
---

# Reelsmith

Turning footage into short-form video is a chain where a mistake in an early link
is invisible until the render. Somebody picks a shot from a thumbnail, and the
thumbnail was sampled from the middle of an eighteen-second take, so the frame
they chose is ten seconds away from the timecode they wrote down. Nobody notices
until the finished cut has a stranger where the emotional payoff was supposed to be.

This pipeline exists to catch those errors while they are still cheap. It works in
eleven steps and **stops at every one for a decision.** That is the point: the
person you are working with knows things about their footage and their audience
that no amount of analysis will surface, and the gates are where that knowledge
enters.

## How to run this

Track state in `reelsmith.json` in the working directory. Create it at step 1 and
update it after each gate. It makes the work resumable and lets someone see what
was decided and why.

```json
{
  "project": "name",
  "step": 5,
  "topic": "...",
  "hooks": [],
  "brand": {"has_brand": true, "colors": {}, "fonts": {}},
  "footage": {"path": "...", "cameras": [], "originals": true},
  "ffmpeg": "path/to/ffmpeg.exe",
  "color": {"luts_generated": true, "applied": true},
  "captions": {"font": "...", "burn_in": false},
  "music": {"path": null, "bpm": null},
  "reels": []
}
```

Scripts live in `${CLAUDE_PLUGIN_ROOT}/scripts/`. They are there so you do not
rewrite them each time — read the docstring at the top of each before using it.

**Before touching anything media-related, read `references/pitfalls.md`.** When the footage is of real people and real events, also read `references/documentary.md` before step 1. The story comes before the shot list. It is
short and every item in it is a bug that has actually shipped. Several are silent
failures that produce a plausible-looking file that is wrong.

---

## Step 1 · Topic and concept

Ask what the reels are about. Not the brand, not the footage: the subject and who
is meant to watch.

Then produce **six to ten hooks across different archetypes**, not variations of
one idea. Curiosity gap, stakes, direct call-out, contrarian claim, in media res,
number. Label each with its archetype so the person learns the pattern rather than
just picking a line.

For each hook give the spoken line, the on-screen text, and the visual idea. A hook
that only works as text is half a hook.

Sketch three to five reel concepts, each one sentence, each aimed at a different
job: reach, conversion, community, proof.

**Gate:** which hooks and concepts survive? Record them and move on.

Depth on hook construction and retention structure lives in
`references/concept.md`.

---

## Step 2 · Branding

Ask whether there is a brand: logo, colours, fonts, an existing poster or deck.

If there is, extract rather than guess. `scripts/brand_extract.py` pulls a palette
from images and reads layer names, text content and fonts from a layered PSD.
Sample the actual pixels; do not eyeball hex values from a screenshot.

If there is no brand, say so plainly and skip. Do not invent one. An invented
palette that appears in eight reels becomes a brand nobody agreed to.

Record whatever exists as tokens so later steps can use them without asking again:

```json
{"paper": "#FBF4E8", "accent": "#9F1A17", "ink": "#000000",
 "display_font": "path/to.otf", "body_font": "path/to.ttf"}
```

**Gate:** confirm the extracted values before they propagate.

---

## Step 3 · Footage

Ask what footage exists and where. **The edit is always built on the camera
originals**, so the first thing to establish is where they are. Then:

- **Originals or an export?** A folder of camera files is what you want. A single
  delivered file, a selects reel, or a vertical version someone already cut is an
  export: it has no handles, it has already been cropped, retimed and graded, and
  an editor handed a sequence built on it can trim but never extend. If you are
  given an export, ask for the originals behind it. Work from the export only when
  the originals genuinely do not exist, and say so in `reelsmith.json`.
- **Which cameras, at what rates?** Probe every original. 50p and 59.94p material
  gives true slow motion on a 25p timeline; that is a creative option, so note it.
- **Is it already graded?** Originals are usually not, but some cameras bake a look
  in. Step 6 measures this rather than trusting the label.
- **What are the aspect ratios?** Landscape sources need reframing decisions;
  native vertical does not.

If there is no usable footage, stop here and say what would need to be shot. The
rest of the pipeline has nothing to work on.

**Gate:** confirm the original source paths, and that they are originals.

---

## Step 4 · ffmpeg

Everything downstream needs ffmpeg. Ask where it is, or find it:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/ffmpeg_tools.py --locate
```

It checks PATH, common install locations, and the `imageio-ffmpeg` Python package.

**Prefer a full build over a bundled minimal one.** The `imageio-ffmpeg` binary
works for probing and frame extraction but often lacks `libx264`, `drawtext` and
`lut3d`, which the colour and render steps need. If only the minimal build is
present, say so and offer the choice: fetch a full build, or continue with reduced
capability.

Verify what the build can actually do rather than assuming:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/ffmpeg_tools.py --check /path/to/ffmpeg
```

**Gate:** confirm the binary and its capabilities.

---

## Step 5 · Analyse the footage

Now the work that makes the edit possible.

**Probe.** Resolution, frame rate, duration, codec, audio. `--probe`.

**Detect shots.** `scripts/shots.py`. If the footage came from several cameras and
you know the boundaries, pass them — detection thresholds that suit a fast handheld
camera will merge cuts in slow motion, and per-range thresholds fix that.

**Build a contact sheet** with shot codes and timecodes burned in.

Then the step everyone skips, and the reason this pipeline exists:

**Verify the in-points by rendering them.** A contact sheet samples one frame per
shot, usually the midpoint. For a two-second shot that is fine. For a twenty-second
take it is a different moment entirely from the timecode you are about to write
down. `scripts/verify.py` renders the exact frame at every in-point you intend to
use and lays them out labelled, so you look at what you are actually going to cut.

Any take longer than about six seconds should also be sampled densely across its
length before you pick a moment inside it.

**Reframing.** If sources are not 9:16, compute the crop. A 3:2 open-gate frame at
6000×4000 yields 2232×4000 at 9:16; 16:9 UHD yields 1215×2160. Both clear
1080×1920, so quality is rarely the constraint — composition is. Say which shots
survive the crop and which lose their subject. Record the crop per clip as `cx`
(and `cy`, `z` if needed) in the edit list: the render crops with it and the
Premiere XML carries it as Motion, so both show the same frame.

Many originals: log them as a set. Sample every file (densely for short clips,
sparsely for long continuous ones), keep the frames, and write down moments as
`file + seconds from the start of that file`. That pair is what goes in the edit
list. When the edit list is drafted, `verify.py --edl` shows the first, middle and
last frame of every clip as it will actually appear.

**Gate:** present the shot inventory and ask what to do next. This is deliberately
an open gate; the answer might be "cut it now" or "fix the colour first".

---

## Step 6 · Colour, measured

Do not design a look from a thumbnail. Measure.

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/color.py --measure SOURCE --groups groups.json
```

It reports, per camera or segment: black point, white point, median luma,
saturation, and channel means.

Read the numbers before deciding anything:

- **Black near 0 and white near 1** means display-referred. Already converted. A log
  expansion here crushes and clips.
- **Black around 0.10–0.20 with white around 0.70–0.80** means genuine log. It needs
  a conversion LUT from the camera manufacturer first; the look goes on top.
- **Low saturation with full range** is usually weather, not a white-balance error.
  Overcast and rain flatten saturation while leaving the range intact.

Then propose: grade it, or leave it. Leaving it alone is a legitimate answer, and
for footage that is already graded to someone's taste it is usually the right one.

**Gate:** grade or pass?

---

## Step 7 · Grade, and prove it

Which route depends on who does the grading.

**If you are rendering the cut, balance per shot.** This is the only approach that
matches cameras, because a camera-level LUT applies one gamma from a segment median
and so darkens every shot above it while lightening every shot below.

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/balance.py edl.json --out GRADEDIR
```

It measures each clip, corrects levels, white balance and exposure to common
targets, builds one shared `look.cube`, then measures each shot again through the
chain to set saturation. Watch the reported medians converge — that convergence
is the matching.

**If someone else will grade by hand**, generate per-camera look LUTs instead:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/color.py --make-luts config.json --out LUTDIR
python ${CLAUDE_PLUGIN_ROOT}/scripts/color.py --compare SOURCE --luts LUTDIR
```

**Build those conservative.** Colour tools scale a LUT's strength down, never up.
One that clips at full strength cannot be rescued by a slider; one that is slightly
weak can be reinforced anywhere.

Either way, read the numbers as well as the pictures. A black point landing at 0.00
means you clipped, whatever the thumbnail looks like.

**Gate:** balance and render, hand LUTs over for manual grading, or retune? All
three are normal outcomes.

Details on LUT construction, the transfer maths and the `.cube` format are in
`references/color.md`.

---

## Step 8 · Caption typography

Ask what fonts to use. If step 2 found brand fonts, propose those.

Two questions, and the second matters more than it sounds:

**Burn the captions in, or leave the picture clean?** Burnt-in captions are done and
consistent. Clean picture lets someone place text per shot in their own editor,
which is usually better, because caption position is a per-shot judgement. A fixed
vertical position that works over a wide shot lands on a face in a close-up. If in
doubt, render clean and hand over the text with its timings.

`scripts/captions.py` renders caption plates as transparent PNGs using PIL rather
than ffmpeg's `drawtext`, because `drawtext` cannot select a named instance of a
variable font — it will silently give you Regular when you asked for Bold Condensed.

Keep text clear of platform furniture: roughly the top 250px and bottom 320px of a
1080×1920 frame are covered by interface on most platforms.

**Gate:** confirm fonts and the burn-in decision.

---

## Step 9 · Music

Ask whether there is a music bed.

If not, go straight to step 11. Silence is a real choice — a cut carried by
production sound stands out in a feed where everything has a track under it.

**Gate:** music or no music?

---

## Step 10 · Cut to beat

Only if there is music.

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/beats.py MUSIC --fps 25
```

It estimates tempo, returns a beat grid, and snaps to the nearest frame at your
project rate. Then propose an edit list where cuts land on beats — typically every
2 or 4 beats, with the strongest shot on the downbeat after a phrase boundary.

Do not force every cut onto a beat. A held shot that breaks the pattern is what
makes the pattern legible.

**Gate:** approve the beat-aligned edit list, or adjust.

---

## Step 11 · Render

Write the edit list to a file first, then render from it. The file is the
deliverable that survives; the mp4 can always be rebuilt from it.

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/render.py edl.json --out OUTDIR --balance GRADEDIR
```

Every clip is cut from its camera original. With originals a file is usually one
take, so a clip overrunning its take means running off the end of the file, which
the renderer and the XML both refuse. Where one long file holds many shots,
`--shots shots.tsv` validates that no clip runs into the next shot; an overrun
reads as a two-frame glitch and never shows up in a contact sheet.

**Handing over instead of rendering.** If the person will finish in Premiere, or
asks for an edit list rather than a file, do not render at all:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/premiere_xml.py edl.json --out cut.xml --balance GRADEDIR
```

The XML links the **camera originals** with in and out points, reframe as Motion,
slow motion as speed, camera sound and music. Never point it at rendered segments or
an export: it refuses a source that looks derived and says why. Give a plain list
too (shot, clip name, source TC in, TC out, duration, speed). See `reel-cut` step 6.

The renderer handles the things that go wrong quietly:

- **Durations snapped to whole frames.** A 1.3s cut at 25fps is 32.5 frames. The
  concat step swallows the half frame and the output drifts off constant frame rate.
- **Constant frame rate on the final pass.** Concatenating segments with stream copy
  preserves each segment's timing, and the joins land between frames.
- **Per-clip LUTs**, chosen from the clip's source timecode, so colour follows a
  shot if you move it.
- **Segment sound as PCM.** AAC pads every segment, and over a long cut the joins
  slip a frame every few clips, which drifts the picture off the beat.
- **Correct flag order**, which sounds trivial and is not — `-t` placed between two
  inputs limits the second input rather than the output, and you get a file hundreds
  of times too large with no error message.

Deliver the rendered files, the edit list, and the LUTs together.

**Gate:** review the render. Expect at least one round of changes; that is the
normal shape of this work, not a failure.

---

## When someone jumps into the middle

People arrive mid-pipeline: "make me a LUT for this", "what shots are in this
file", "cut this to the beat". Serve the request directly rather than marching them
through steps 1 to 4 first. Do check the two things that invalidate later work —
whether ffmpeg can do what is needed, and whether the footage is what they think it
is (camera originals, or an export of an earlier edit) — and mention the steps they
skipped only if those steps would change the answer. A request for "an XML" or "an
edit list" still means one linked to the originals.

## Reference files

- `references/pitfalls.md` — silent failures, read before any media work
- `references/documentary.md` — story, structure, sound and dignity for real-people footage; read before cutting any documentary or news reel
- `references/concept.md` — hook archetypes, retention structure, captions and CTAs
- `references/color.md` — measurement, LUT maths, `.cube` format
- `references/edl.md` — edit list schema
