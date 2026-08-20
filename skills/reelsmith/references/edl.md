# Edit list schema

The edit list is the deliverable that survives. The rendered mp4 can always be
rebuilt from it; the reverse is not true. Write it before rendering, keep it beside
the output, and version it when the cut changes.

## Schema

```json
{
  "fps": 25,
  "width": 1080,
  "height": 1920,
  "source": "path/to/master.mp4",
  "endcard": { "image": "endcard_1080x1920.png", "dur": 1.5 },

  "reels": [
    {
      "name": "Reel01_hook",
      "note": "why this reel exists, one line",
      "clips": [
        {
          "code": "CA12",
          "t": 104.3,
          "dur": 1.52,
          "lut": "CamA",
          "caption": "cap01.png",
          "text": "ON SCREEN TEXT",
          "note": "exhausted, medal on chest"
        }
      ]
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `code` | shot code from `shots.tsv`, so a clip traces back to the inventory |
| `t` | in-point in seconds from the start of the source |
| `dur` | duration on the timeline, **a whole number of frames** |
| `lut` | LUT basename without `.cube`; omit to let `--lut-map` choose by timecode |
| `caption` | PNG filename in the captions directory; omit for a clean picture |
| `text` | the caption text even when not burnt in, so it can be placed in an editor |
| `note` | what the frame shows, so a reviewer can check without opening the file |

## Frame alignment

Every `dur` must be a multiple of `1/fps`. At 25fps that is 0.04s.

```python
def frames(d, fps=25): return round(d * fps) / fps
```

A 1.3s cut is 32.5 frames. The concat swallows the half frame, the output drifts
off constant frame rate, and timing slips against music. The renderer snaps
durations for you and warns if the finished file is not at the rate you asked for,
but a list with correct durations is easier to reason about.

## In-points

`t` is a verified in-point, not a shot boundary. Shot boundaries come from
detection; in-points come from looking at the actual frame. Offset by roughly 0.4
to 1.0 seconds past a detected cut — the first frames after a cut often carry
residual motion blur.

**Run `verify.py` over every `t` in the list before rendering.** Contact sheets
sample mid-shot, so a timecode taken from one can be many seconds from the frame
you meant.

## Slow motion

If a section is already conformed in the source — 100fps written at 25p, say — the
timecodes are timeline seconds and nothing needs retiming. Say so in the file so
nobody re-applies a speed change.

Keep slow-motion cuts short. At 4x, 1.5 seconds on the timeline is 0.37 seconds of
real movement: enough to read a gesture, not enough to drag.

## Sanity checks before rendering

- every `dur` a multiple of `1/fps`
- every `t` + `dur` inside the source duration
- every `lut` file present in the LUT directory
- every `caption` file present, if captions are burnt in
- reel totals plus the end card land near the target length
