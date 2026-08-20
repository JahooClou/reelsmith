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
`../reelsmith/references/pitfalls.md` first — items 5, 6 and 11 are colour
specifically, and all three are silent failures.

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

If the footage will be graded from original camera files rather than an export,
say so: the values need recalculating against the source, because the export has
already had a curve applied.

## When to leave it alone

Footage that is already graded to someone's taste usually should be. Propose "leave
as-is" as a real option rather than grading by default. A cut that mixes graded and
ungraded material is worse than either.
