---
name: reel-color
description: >
  Measure video footage and build .cube look LUTs from what was actually measured,
  then prove they work with before/after comparisons. Use whenever someone wants to
  colour grade footage, fix flat or muddy or washed-out video, make footage "pop",
  match colour between different cameras in one edit, build or generate a LUT,
  create a look for Premiere/Resolve/Lumetri, or asks whether their footage is log.
  Also use when someone complains their video looks grey, dull, overcast or lifeless,
  or when cutting together material shot on several cameras that do not match.
---

# Reel colour

Grading starts with measurement, not with a thumbnail. Two frames that look equally
flat can need opposite treatments, and the difference only shows in the numbers.

Scripts are in `${CLAUDE_PLUGIN_ROOT}/scripts/`. Read
`../reelsmith/references/pitfalls.md` first — items 5, 6, 13 to 16 and 21 are
colour specifically, and all of them are silent failures.

## Two paths, and they are not interchangeable

**Per-shot balance plus one shared look** (`balance.py`) is what you want when you
are rendering the cut yourself. It is the only approach that actually matches
cameras.

**Per-camera look LUTs** (`color.py --make-luts`) is what you want when someone
else will grade by hand in Premiere or Resolve. They get `.cube` files to drop into
a Look slot and dial by eye.

**A camera-level LUT cannot match shots.** One gamma derived from a segment median
darkens every shot above that median and lightens every one below. Exposure and
white balance often vary more from shot to shot inside one camera than they do
between cameras. If you are rendering, use `balance.py`.

## Per-shot balance

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/balance.py edl.json --out GRADEDIR
python ${CLAUDE_PLUGIN_ROOT}/scripts/render.py edl.json --out OUT --balance GRADEDIR
```

Both read each clip from its camera original (`src` in the edit list) and measure
it inside the 9:16 window it will be shown through. A bright sky or a red banner
outside the crop would otherwise set the levels of a picture that never contains
it. Values are keyed by source and in-point, so two cameras cut at the same second
do not overwrite each other.

It measures every unique clip in the edit list, computes levels, white balance and
exposure per shot, generates one shared `look.cube`, then measures each shot again
**through the chain** to set saturation. Output is `shot_params.json`, which
`render.py --balance` consumes.

The chain, in the order colourists use:

```
format=rgb48le 16-bit RGB first: see below
colorlevels    levels + white balance, per channel
eq gamma       exposure to a common target
lut3d          the shared look, identical on every shot
eq saturation  corrected last, against a measured result
```

Four details that are easy to get wrong and all produce plausible-looking output:

- **`colorlevels` on 10-bit originals.** Fed 10-bit camera files, ffmpeg runs it in
  planar `gbrp10` and returns a near-black picture with no error (a measured median
  of 0.011 where 0.40 was asked for). The chain converts to `rgb48le` first. If
  balanced shots come out wildly bright or dark, check this before the maths.

- **`eq` computes `x^(1/gamma)`.** Invert the exponent or every shot moves the
  wrong way.
- **Measure white balance on near-neutral pixels only.** A whole-frame average
  reads a red floor as a cast and corrects toward cyan.
- **Measure saturation after the chain, not before.** Levels and the look each
  raise it, so a multiplier from the source overshoots.

Shots marked `capped` hit the limits deliberately. A genuinely grey shot should
stay grey; forcing it to a saturation target looks artificial.

## 1. Measure before deciding anything

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/color.py --measure SOURCE --groups groups.json
```

`groups.json` splits the source by camera or section:

```json
[{"name": "CamA", "start": 0, "end": 233.5},
 {"name": "CamB", "start": 233.5, "end": 583.0}]
```

You get black point, white point, median, saturation and channel means per group,
plus suggested LUT values.

## 2. Read what the numbers mean

| Black (p1) | White (p99) | What it is |
|---|---|---|
| near 0 | near 1 | display-referred, already converted |
| 0.10 – 0.20 | 0.70 – 0.80 | genuine log |

**Check this even when someone tells you the camera shot log.** The file you were
handed is very often an export from an edit, where everything was conformed on the
way out. The camera shot log; the file did not. Applying a log expansion to
display-referred footage crushes shadows and clips highlights, and an export cannot
be recovered from that.

If it really is log, the maker's own conversion LUT goes first, as an input LUT.
The look built here sits on top.

**Low saturation with a full tonal range is weather, not white balance.** Overcast
and rain flatten saturation while leaving the range intact. Do not "correct" a cast
that is really a red carpet dominating the frame.

## 3. Generate

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/color.py --make-luts config.json --out LUTDIR
```

Each LUT sets black and white points, pushes the median to a common target so
cameras match in one cut, adds a gentle S-curve, and lifts saturation with a
roll-off above about 0.80 so a strong brand colour does not oversaturate first.

**Build conservative.** Colour tools scale a LUT's strength down, never up. One
that clips at full strength cannot be rescued by a slider; one that is slightly
weak can be reinforced anywhere. The generator puts the black point at half the
measured floor for exactly this reason.

## 4. Prove it

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/color.py --compare SOURCE --luts LUTDIR --out cmp.jpg
```

Renders before/after pairs and re-measures. **Read the numbers, not just the
picture.** A black point landing under 0.004 means you clipped, however good the
thumbnail looks. Lower the contrast or raise the black point and regenerate.

## 5. Hand over

Deliver the `.cube` files, the comparison sheet, and the measured numbers that
justify each value. Say plainly that these are look LUTs for display-referred
footage, not log conversions — someone will otherwise stack them on top of a
conversion and wonder why it looks wrong.

Measure the files the grade will be applied to. The edit is handed over linked to
the camera originals (see `reel-cut`), so values measured on an export are the
wrong numbers: the export has already had a curve applied. If all you were given
is an export, say so, and say the values need recalculating once the originals
arrive.

## When to leave it alone

Footage that is already graded to someone's taste usually should be. Propose "leave
as-is" as a real option rather than grading by default. A cut that mixes graded and
ungraded material is worse than either.
