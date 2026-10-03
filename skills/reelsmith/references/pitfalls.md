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

## 13. ffmpeg's `eq` filter inverts gamma

`eq=gamma=G` computes **`x^(1/G)`**, not `x^G`. So `gamma=0.6` darkens, and
`gamma=1.6` brightens — the opposite of the convention in most colour maths.

**Symptom:** every shot moves the wrong way. A shot measured at median 0.267 and
corrected toward 0.40 came out at **0.011**.

**Fix:** compute the exponent you want, then pass its reciprocal.

```python
exponent = math.log(target_mid) / math.log(measured_mid)
eq_gamma = 1.0 / exponent
```

---

## 14. One LUT per camera cannot match shots

A camera-level LUT applies one gamma derived from a segment median. That darkens
every shot above the median and lightens every shot below it — the opposite of
matching. Exposure and white balance often vary more shot to shot within one
camera than they do between cameras.

**Symptom:** a graded cut where clips are individually plausible and visibly
mismatched against each other. Medians spanning 0.14 to 0.50 across eight clips.

**Fix:** balance per shot, then apply one shared look. The order colourists use.

```
colorlevels    levels + white balance, per channel
eq gamma       exposure to a common target
lut3d          the shared look, identical everywhere
eq saturation  corrected last, against a measured result
```

Per-shot balance brought that same cut from a 0.36 median spread to 0.045.

---

## 15. White balance measured on the whole frame

Averaging all pixels reads a large coloured object as a cast. Footage with a red
floor, red kit or heavy red branding measures warm, and a whole-frame correction
pushes the image cyan to compensate for something that was never wrong.

**Fix:** measure only near-neutral pixels — saturation below about 0.16, luma
between 0.18 and 0.85 — and balance those. Apply the correction at partial
strength (around 0.65) so the scene keeps its character.

---

## 16. Saturation predicted instead of measured

Stretching levels raises saturation. An S-curve raises it again. A multiplier
computed from the source therefore overshoots, sometimes badly: a shot measured at
0.456 and "corrected" toward 0.42 came out at **0.601**.

**Fix:** correct saturation **last**, and measure it after the rest of the chain
has run. Render a probe through levels, gamma and look, measure that, then compute
the multiplier.

**And use the same sampling for both passes.** Measuring the source across five
frames and the probe across one compares an average to a single frame, and the
correction chases a difference that is not real.

---

## 17. Clips that overrun their shot

A clip whose in-point plus duration passes the end of its shot pulls frames from
the next one. It reads as a two-frame glitch mid-clip, and a contact sheet will
never show it because the sheet samples one frame per shot.

**Fix:** validate every clip against the shot list before rendering.

```python
end = clip["t"] + frames(clip["dur"], fps)
if end > shot_end: ...
```

`render.py --shots shots.tsv` does this and reports the overrun in seconds.

---

## 18. End cards held too long

A static end card is where completion rate dies. Cap it at about 1.5 seconds. If it
needs longer to read, it has too much on it.

---

## 19. Frames of real people, published somewhere they never agreed to

A reel goes to an audience the people in it expect. A README, a case study, a
portfolio page or a public repository does not, and consent for one is not consent
for the other. Spectators and children are in the footage because they came to an
event, not because they agreed to illustrate a tool.

**Why it slips through:** automated frame selection optimises for something like
sharpness or visual interest, and both of those correlate with faces. Picking "the
best frame" from an event reel will reliably hand you a crowd shot.

**Fix:** when frames leave their original context, choose them on that basis
explicitly — helmets, masks, backs, hands, equipment, wide shots. Then check at
**full resolution**, not at the size the page will display. A face behind a
respirator visor disappears in a 190px thumbnail and is perfectly readable in the
1080px source that anyone can open, and it is the source that gets published.

Check backgrounds too. A frame whose subject is safely turned away can still have a
bystander in focus behind them.

**If it is already pushed:** rewriting the commit and moving the tag removes it from
every branch and ref, but the old objects stay reachable by their SHA on most hosts
until garbage collection. Getting it right before the first push is much cheaper
than getting it back afterwards.

---

## 20. Handing over an export instead of the camera originals

**What happens:** the edit is built on whatever file arrived first: a delivered
export, a selects reel, a vertical version someone already cut. The render looks
fine. Then the sequence goes to an editor, and every clip in it is a slice of that
export.

**Why it bites:** the export has already thrown away what the editor needs. There
are no handles, so no shot can be extended by even a frame. The frame is already
cropped, so it cannot be reframed. The rate is already the delivery rate, so there is
nothing left to slow down. The colour has a curve baked in, so grade values measured
on it are wrong for the real media.

**Fix:** build the edit list on the originals from the start, `src` plus seconds
from the start of that file, and link those in the XML. `premiere_xml.py` refuses a
source already at the delivery size or inside a render folder. If an export really
is all there is, say so and use `--allow-derived`, knowingly.

---

## 21. `colorlevels` on 10-bit originals returns a black picture

Camera originals are often 10-bit (HEVC `yuv420p10le`). Fed one, ffmpeg runs
`colorlevels` in planar `gbrp10`, and in current builds that produces a near-black
frame with no error.

**Symptom:** the balance table shows medians jumping from 0.44 to 0.86 after the
chain, or a measured median of 0.011 where 0.40 was asked for. The same chain on an
8-bit export is fine, which is why it went unnoticed.

**Fix:** convert first. `balance.py` starts its chain with `format=rgb48le`, which
keeps 16-bit precision and gives the right answer.

---

## 22. AAC in render segments slips the cut off the beat

Each segment encoded with AAC sound is padded by the encoder, so its audio runs a
little past its video. The concat demuxer takes the longer stream, and the final
constant-frame-rate pass fills the gap with a duplicated frame.

**Symptom:** four clips of 47 + 47 + 59 + 47 frames render as 201 frames, not 200.
Over eighty clips the picture drifts several frames off the music.

**Fix:** keep segment sound as PCM in `.mov` and encode AAC once, in the final pass.
Count the frames of the finished file, not just its duration.

---

## 23. DJI files carry a second video stream

DJI originals (Osmo, drones) include a small thumbnail as an extra video stream.
`-map 0:v` maps both, and the filter chain fails on the thumbnail with an
unhelpful `Invalid argument`.

**Fix:** map `0:v:0`, the first video stream, everywhere a camera original is read.

---

## 24. Cuts placed exactly on the beat read as late

**What happens:** every cut sits on the beat's frame, and the whole montage feels a
hair behind the music, though every number is "right".

**Why:** the eye registers a cut faster than the ear places a beat. Editors cut one
or two frames early: audio follows video. Measured on an editor's re-edit: 42 of 67
cuts lead the beat, median −0.9 frames.

**Fix:** cut frames come from `beats.py` as `beat - lead` (default lead 1). In the
edit list give lengths in `beats` with `lead` set; do not hand-place cuts on raw
beat times.

---

## 25. A fixed beat grid on generated music

Generated tracks drift: one went from 127.8 to 131.2 BPM over 3.5 minutes. A grid
from one tempo estimate is several frames off by the end, and the drift is
invisible on the first minute you check.

**Fix:** track the beats (`beats.py` does, and reports start and end tempo), and
check that downbeats fall on the section changes you can hear.

---

## 26. Beat trackers sit beside the transient

A tracker works on a smoothed onset envelope, so its beats sit 30 to 40 ms off
the audible hit, and a per-beat "snap to transient" jumps to vocals or hats.

**Fix:** move beats by a rolling median of the per-beat transient offsets, so every
cut keeps the same lead against the drums (`beats.py` does this).
