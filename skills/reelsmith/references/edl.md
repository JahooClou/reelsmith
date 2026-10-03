# Edit list schema

The edit list is the deliverable that survives. The rendered mp4 can always be
rebuilt from it; the reverse is not true. Write it before rendering, keep it beside
the output, and version it when the cut changes.

**It points at the camera originals.** Every clip names the original file it comes
from and an in-point in seconds from the start of that file. The render, the grade
and the Premiere sequence are all built from those files, so they show the same
frames, and the editor who receives the XML gets the full takes with their handles.

## Schema

```json
{
  "fps": 25,
  "width": 1080,
  "height": 1920,
  "sources": {
    "CamA_018": "shoot/CamA/A001C018.MOV",
    "Osmo_11":  "shoot/Osmo/DJI_0011_D.MP4"
  },
  "music": { "path": "music/anthem_cut.wav", "offset": 0 },
  "endcard": { "image": "endcard_1080x1920.png", "dur": 1.5 },

  "reels": [
    {
      "name": "Reel01_hook",
      "note": "why this reel exists, one line",
      "clips": [
        {
          "code": "CA18",
          "src": "CamA_018",
          "t": 142.6,
          "dur": 1.88,
          "cx": 0.42,
          "text": "ON SCREEN TEXT",
          "note": "sledgehammer, low angle"
        },
        {
          "code": "OS11",
          "src": "Osmo_11",
          "t": 191.0,
          "dur": 2.36,
          "speed": "conform",
          "note": "masked firefighter facing camera, slow"
        }
      ]
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `sources` | key → path of each **camera original** used. Probe them; do not hand-type rates |
| `src` | the clip's original: a key into `sources`, or a path |
| `code` | a short label, so a clip traces back to the log |
| `t` | in-point in seconds **from the first frame of that original** |
| `dur` | duration on the timeline, **a whole number of frames** |
| `speed` | percent (100 real time, 50 half speed) or `"conform"`: every source frame shown once, true slow motion with no blending. 50p on 25p = 50 %, 59.94p = 41.71 % |
| `cx`, `cy` | centre of the 9:16 window as fractions of the source frame; default 0.5 |
| `z` | window size: 1.0 is as large as the source allows, 0.8 is a punch-in |
| `lut` | LUT basename without `.cube`, for the per-camera LUT path |
| `caption` | PNG filename in the captions directory; omit for a clean picture |
| `text` | the caption text even when not burnt in, so it can be placed in an editor |
| `note` | what the frame shows, so a reviewer can check without opening the file |
| `music` | the bed, with `offset` in seconds into the file; goes on its own tracks in the XML |

**Legacy single-file lists** (`"source": "master.mp4"` and no `src`) still work,
and `--source` on the command line does the same. But that file must itself be an
original. `premiere_xml.py` refuses a source already at the delivery size or inside
a render folder, because that is an export.

## Frame alignment

Every `dur` must be a multiple of `1/fps`. At 25fps that is 0.04s.

```python
def frames(d, fps=25): return round(d * fps) / fps
```

A 1.3s cut is 32.5 frames. The concat swallows the half frame, the output drifts
off constant frame rate, and timing slips against music. The renderer snaps
durations for you and warns if the finished file is not at the rate you asked for,
but a list with correct durations is easier to reason about.

Snap `t` too, for the XML: Premiere stores in-points as whole frames at the
**sequence** rate, so an in-point of 0.30 s on a 25p timeline becomes frame 8
(0.32 s). If the list and the XML must agree to the frame, round `t` to
`n / fps × speed` before writing either.

## In-points

`t` is a verified in-point, not a shot boundary. Shot boundaries come from
detection; in-points come from looking at the actual frame. Offset by roughly 0.4
to 1.0 seconds past a detected cut — the first frames after a cut often carry
residual motion blur.

**Check the whole list before rendering or handing over:**

```bash
python verify.py --edl edl.json --out check.jpg
```

It shows the first, middle and last frame of every clip, cut from its original,
through its window, at its speed. A subject that walks out of the crop, or a sprint
that leaves an empty lane by the last frame, only shows up here.

## Slow motion

Slow motion comes from the original's frame rate, which is one more reason to cut
from originals: an export has already been conformed to the delivery rate and has
nothing left to slow down.

`"conform"` is the clean case: every recorded frame once. A clip of `dur` 1.88 s at
50 % covers 0.94 s of the original. Keep slow-motion cuts short. At 4x, 1.5 seconds
on the timeline is 0.37 seconds of real movement: enough to read a gesture, not
enough to drag.

## Sanity checks before rendering or handing over

- every `src` resolves to a file that exists and is an original
- every `dur` a multiple of `1/fps`
- every `t` + `dur` × speed inside that original's duration
- every `lut` file present in the LUT directory
- every `caption` file present, if captions are burnt in
- reel totals plus the end card land near the target length
- `verify.py --edl` looked at, clip by clip

## Handing it to an editor

`premiere_xml.py` converts this file to FCP7 XML, which Premiere imports as
sequences of the **original clips** with in and out points, reframe as Motion Scale
and Position, slow motion as speed (frame blending off), camera sound on A1/A2 for
real-time clips and the music on A3/A4.

Colour cannot travel in FCP7 XML, so `lut`, the balance values and `text` are
written as timeline markers, together with each clip's Position, Scale, Speed and
source timecode. The editor reads them off the clip and applies the look on an
adjustment layer, and can type in any value that imported wrongly.

That is another reason `note` and `text` are worth filling in even when you are
rendering yourself: they are what makes the handover legible if the job later moves
to someone else's timeline.

Hand over a plain list as well: shot, clip name, source TC in, TC out, duration,
speed. Source timecode is the clip's own, at its own rate: Canon 50p counts frames
00–49; DJI 59.94p is drop-frame 00–59, stored on a 29.97 track. `rs_common.source_tc`
does the conversion.
