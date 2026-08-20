# Pitfalls

Every item here is a bug that shipped, wasted an afternoon, or produced a file
that looked fine and was wrong. Most fail silently.

---

## 1. Contact sheets sample the midpoint, not the in-point

**What happens:** you build a contact sheet, one frame per detected shot. You see a
frame you want, note the shot's start timecode, and cut from it. The frame you
liked was sampled from the middle of the shot.

For a 2-second shot, the error is a second. For a 20-second take it is ten, and
the moment you chose is long gone.

**Why it bites:** long takes are exactly where the good moments hide. A
twenty-second handheld run contains a gesture, a face, a reaction. The detector
sees one shot; the contact sheet shows one frame; you cut from the wrong end of it.

**Fix:** for any take longer than about six seconds, sample it densely across its
length before choosing. Then, before rendering, **render every in-point you intend
to use and look at them.** `scripts/verify.py` does this. It takes minutes and it
catches errors nothing else will.

---

## 2. `-t` placed between inputs limits the wrong thing

```bash
# WRONG: -t applies to the caption PNG, not the video
ffmpeg -ss 10 -i video.mp4 -t 2 -i caption.png -filter_complex ... out.mp4

# RIGHT: -t after all inputs, before the output
ffmpeg -ss 10 -i video.mp4 -i caption.png -filter_complex ... -t 2 out.mp4
```

**Symptom:** a fifteen-second cut renders as a 1.4 GB file. No error, no warning.
The video ran from the in-point to the end of the source.

**Rule:** input options go before their `-i`. Output options go after all inputs.
`-ss` before `-i` is input seeking and is what you want; `-t` belongs with the
output.

---

## 3. Cut durations that are not whole frames

At 25fps a frame is 0.04s. A 1.3s cut is 32.5 frames.

**Symptom:** the concatenated output reports 24.81fps instead of 25, and
`r_frame_rate` reads `50/1`. Players cope; some platforms re-encode; the timing
drifts against music.

**Fix:** snap every duration to a whole frame before cutting.

```python
def frames(d, fps=25): return round(d * fps) / fps
```

---

## 4. Concat with stream copy gives variable frame rate

```bash
# preserves each segment's timing; joins land between frames
ffmpeg -f concat -i list.txt -c copy out.mp4
```

**Fix:** re-encode the final pass with an explicit constant rate.

```bash
ffmpeg -f concat -safe 0 -i list.txt -r 25 -fps_mode cfr \
  -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p \
  -c:a aac -b:a 192k -movflags +faststart out.mp4
```

Encode segments at a slightly better quality than the target (CRF 16 for a CRF 18
delivery) so the second pass has headroom.

**Verify, do not assume:**

```bash
ffprobe -v error -select_streams v:0 \
  -show_entries stream=avg_frame_rate,nb_frames \
  -show_entries format=duration -of default=noprint_wrappers=1 out.mp4
```

`avg_frame_rate` should be exactly your target.

---

## 5. "Log footage" that is not log

Someone tells you a camera shot C-Log, S-Log or V-Log. Before applying a
conversion, measure.

| | Black (p1) | White (p99) |
|---|---|---|
| Log | 0.10 – 0.20 | 0.70 – 0.80 |
| Display-referred | near 0 | near 1 |

**Why it happens:** the file you were handed is often an export from an edit, where
everything was already conformed. The camera shot log; the file did not.

**Cost of getting it wrong:** a log expansion on display-referred footage crushes
shadows and clips highlights, and it is not recoverable from the export.

---

## 6. LUTs that clip at full strength

Colour tools scale a LUT's intensity **down**, never up. A LUT that clips at 100%
cannot be rescued.

**Fix:** put the black point at roughly half the measured floor rather than exactly
on it, and keep saturation moderate. Verify by re-measuring after application — if
the black point lands at 0.00, you clipped, whatever the thumbnail suggests.

Protect saturated channels: above roughly 0.80, roll the saturation multiplier back
toward 1.0, or a strong brand red will oversaturate before anything else does.

---

## 7. A file a library can read is not a file the app can open

Writing a PSD with a Python library and reading it back with the same family of
library proves nothing. Photoshop is stricter.

**Fix:** when the target is a specific application, either verify in that
application or generate assets plus a script the application runs itself. Exporting
layers as PNGs and generating a JSX that builds the document natively is slower to
set up and always works.

**General form:** verification has to happen against the real consumer of the
artefact, not against a convenient proxy.

---

## 8. Variable fonts through `drawtext`

ffmpeg's `drawtext` uses FreeType and renders the **default instance** of a variable
font. Ask for Bold Condensed, get Regular, no warning.

**Fix:** render caption plates as transparent PNGs with PIL, which can select a
named instance:

```python
f = ImageFont.truetype("bahnschrift.ttf", 64)
f.set_variation_by_name("Bold Condensed")
```

Then `overlay` the PNG. You also get exact control over blocks, padding and
letter-spacing, which `drawtext` does not offer.

---

## 9. Caption position fixed globally

A caption at a fixed height works over a wide shot and lands on a face in a
close-up.

**Fix:** position per shot, or render the picture clean and hand over the text with
its timings so it can be placed in an editor. When the choice is unclear, clean is
the safer deliverable.

Keep clear of platform interface: roughly the top 250px and bottom 320px of a
1080×1920 frame.

---

## 10. Scene detection at one threshold across mixed material

A threshold tuned for handheld action merges cuts in slow motion, where successive
frames are far more similar.

**Fix:** detect per segment with a threshold suited to each. Roughly 0.14 for normal
speed, 0.10 for slow motion, as a starting point. Compare the shot count against
what the person who shot it expects — a mismatch usually means a wrong threshold or
a wrong segment boundary.

---

## 11. Segment boundaries that are slightly wrong

If camera A ends at 29.72s and you set the boundary at 28.40s, the last shot of
camera A gets camera B's colour treatment and the wrong shot code.

**Fix:** derive boundaries from the shot list, not from round numbers, and check the
resulting per-camera counts against what the shooter reports.

---

## 12. Aspect ratio assumed rather than probed

Square, 4:5 and 9:16 all look "vertical" in a thumbnail. Square loses roughly 40% of
a phone screen.

**Fix:** probe. And compute the crop before promising a reframe:

| Source | 9:16 crop |
|---|---|
| 6000×4000 open gate 3:2 | 2232×4000 |
| 3840×2160 UHD 16:9 | 1215×2160 |
| 1920×1080 HD 16:9 | 608×1080 — below 1080×1920 |

Only the last is genuinely short of resolution. The usual constraint is composition,
not pixels.

---

## 13. End cards held too long

A static end card is where completion rate dies. Cap it at about 1.5 seconds. If it
needs longer to read, it has too much on it.
