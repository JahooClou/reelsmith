# Colour: measurement, LUT maths, .cube format

## What gets measured

Frames are sampled evenly across each group, downscaled, and pooled. From the
pooled pixels:

| Value | Meaning |
|---|---|
| `p1` | 1st percentile of luma — where black actually sits |
| `p50` | median luma — overall lightness |
| `p99` | 99th percentile — where white actually sits |
| `sat` | mean `(max-min)/max` per pixel |
| `rgb` | channel means, for cast |

Percentiles rather than min/max, because a single hot pixel or a black frame would
otherwise define the whole range.

## Reading the numbers

| p1 | p99 | Diagnosis |
|---|---|---|
| < 0.08 | > 0.88 | display-referred, already converted |
| 0.10–0.20 | 0.70–0.80 | genuine log |
| > 0.08 | > 0.98 | lifted blacks with highlights near clip — go gentle on contrast |

Saturation between roughly 0.25 and 0.35 with a full range is normal for overcast.
It is a lighting condition, not an error, and the fix is contrast plus selective
saturation rather than a white-balance move.

A warm channel mean does not necessarily mean a warm cast. A red floor, red
branding or red kit dominating frame will skew the mean without anything being
wrong.

## The transform

Applied in this order:

**1. Levels.** `x = (x - blk) / (wht - blk)`, clamped.

`blk` is set at **half** the measured `p1`, not at `p1`. Individual frames sit
below the group average, and a black point exactly on the measured floor clips
them. Half leaves headroom.

**2. Gamma.** `x = x ** gamma`, chosen so the median lands on a common target
(0.42 by default):

```
m     = (p50 - blk) / (p99 - blk)
gamma = ln(target) / ln(m)
```

Pushing every camera's median to the same value is what makes mixed-camera cuts
sit together. It matters more than any look decision.

**3. S-curve** around a pivot of 0.45:

```
x < pivot:  pivot * (x/pivot) ** (1+amount)
x >= pivot: 1 - (1-pivot) * ((1-x)/(1-pivot)) ** (1+amount)
```

Amount 0.14 to 0.18. Drop to 0.15 or lower when `p99` is above 0.985, or the
contrast pushes already-hot highlights into clip.

**4. Saturation with roll-off.**

```
l     = luma(x)
hi    = clamp((x - redguard) / (1 - redguard), 0, 1)
boost = sat - (sat - 1) * hi
x     = l + (x - l) * boost
```

Above `redguard` (0.80 typical) the multiplier eases back toward 1.0, so a strong
brand colour does not oversaturate before anything else does. Without this, red
clips first and everything else still looks flat.

**5. Split tone.** Cool the shadows, leave highlights alone:

```
w = (1 - l) ** 2
b += cool * w
r -= cool * w * 0.55
```

Weighting by `(1-l)²` keeps it in the shadows rather than tinting the whole frame.

## Why conservative

Colour tools scale a LUT's strength **down**, never up. A LUT that clips at full
strength is unrecoverable; one that is slightly weak can be reinforced anywhere in
the chain. Aim to land just short and let the operator push.

Verify by re-measuring after application. A black point under 0.004 means clipping,
whatever the thumbnail suggests.

## .cube format

```
TITLE "name"
LUT_3D_SIZE 33
DOMAIN_MIN 0.0 0.0 0.0
DOMAIN_MAX 1.0 1.0 1.0

0.000000 0.000000 0.000000
...
```

33³ = 35937 entries, about 1 MB. **Red varies fastest, then green, then blue.**
Getting that order wrong produces a file that loads without error and maps colours
to the wrong places.

Lines beginning `#` are comments and are a good place to record what the LUT is for
and that it is a look rather than a conversion — the person who finds it in six
months will not remember.

## Applying

```bash
ffmpeg -i in.mp4 -vf lut3d=file=name.cube out.mp4
```

Relative paths resolve against the working directory, so either run with `cwd` set
to the LUT directory or pass absolute paths. In Premiere's Lumetri, a look LUT goes
in **Creative → Look**, after Basic Correction. A log conversion goes in **Basic
Correction → Input LUT**. Putting a conversion in the Creative slot works but
inverts the intended order and makes exposure fixes fight the curve.
