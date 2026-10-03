# reelsmith

A video editing skill for Claude Code: from camera originals to a finished cut, for
social (Reels, TikTok, Shorts) or long-form (YouTube, Vimeo, event screens), as a
beat edit or a story edit, delivered as a rendered file or as a Premiere sequence
linked to the originals. Three skills, thirteen scripts.

It is deliberately brand-agnostic. It will extract and use a brand if one exists,
and it will not invent one if there isn't.

![Eight reels cut from one master](docs/reels.jpg)

*Eight reels cut from a single 9:43 master — shot detection, per-shot grade, frame-accurate cut, rendered clean so captions can be placed in an editor.*

## Why

Editing is a chain where an early mistake stays invisible until the end. Someone
picks a moment from a contact sheet, and the sheet sampled the middle of a
twenty-second take. A cut lands exactly on the beat and the whole montage feels a
hair late. An editor is handed a sequence built on an export and cannot extend a
single shot.

Every guardrail here is a bug that actually shipped, or a rule a working editor
corrected. They are collected in [`pitfalls.md`](skills/reelsmith/references/pitfalls.md)
and [`review.md`](skills/reelsmith/references/review.md).

## How it works

It starts with five questions, asked together:

1. **Where will it be watched?** Social, or YouTube / Vimeo / a screen.
2. **Vertical or horizontal?**
3. **Beat edit or story edit?**
4. **What pace, and what music?** An existing track, or one generated with the
   soundsmith (Suno) skill at a tempo that fits the frame rate.
5. **What is delivered?** A rendered file, or an XML for the editing suite.

Then it works through these steps, each ending at a gate:

| | Step | Gate |
|---|---|---|
| 1 | Intake | the brief in five lines |
| 2 | Footage: camera originals, probed | sources and delivery format |
| 3 | Log: every original sampled, moments found and verified | the strongest material, and what is missing |
| 4 | Structure: through-line, acts or music sections, peaks | section list with timings |
| 5 | Music: map, shorten, or generate | the track and its section map |
| 6 | Cut: edit list in beats, cuts one frame before the beat | the cut and its check sheets |
| 7 | Finish: reframe, colour, text, sound | |
| 8 | Deliver: render, or Premiere XML plus the edit list | the deliverable |
| 9 | Learn: measure the editor's re-edit, propose rule changes | agreed changes |

You can also enter in the middle: "cut this to the beat", "shorten this track",
"make an XML", "what did I change in my re-edit" all work directly.

## Originals, always

The edit is built on the **camera originals**, and everything that comes out of it
points back at them. The render cuts from them, the grade is measured in them, and
the Premiere XML links them with in and out points, the reframe as Motion and slow
motion as speed. `premiere_xml.py` refuses a source that looks like an export.

## Skills

| Skill | For |
|---|---|
| `reelsmith` | the whole edit, from intake to delivery, and learning from the re-edit |
| `reel-color` | measure footage, balance shots to match, build `.cube` LUTs |
| `reel-cut` | single tasks: log, find shots, map and shorten music, cut, render, XML, review |

## Colour, in one picture

![Per-shot balance, before and after](docs/grade-before-after.jpg)

Four shots from one cut, three different cameras, an overcast day with rain.

As shot, the medians run **0.380, 0.471, 0.506, 0.592** — every clip individually
plausible, and visibly mismatched the moment they sit next to each other. A single
LUT per camera cannot fix that: it applies one gamma derived from a segment median,
which darkens everything above that median and lightens everything below it.

Balanced per shot with one shared look on top: **0.384, 0.384, 0.424, 0.443**. The
spread across the cut goes from **0.212 to 0.059**.

Saturation is measured *after* the chain rather than predicted from the source,
because stretching levels raises it and the shared look raises it again. The second
shot lands at 0.350 against a 0.42 target and is left there: it is a mannequin, a
black tunic and grey sky, so there is little in the frame to saturate and forcing
it would look artificial. Shots that reach the limits are marked `capped`.

## Scripts

All under `scripts/`, all runnable standalone.

| Script | Does |
|---|---|
| `ffmpeg_tools.py` | locate ffmpeg, report build capabilities, probe media |
| `logsheet.py` | log many originals: sampled frames, contact sheets in recording order, index |
| `shots.py` | scene detection per segment, labelled contact sheet |
| `verify.py` | render exact in-points, scan a long take, or check a whole edit list cropped and timed |
| `balance.py` | per-shot balance + one shared look; the matching path |
| `color.py` | measure, generate per-camera LUTs, before/after comparison |
| `render.py` | edit list to finished mp4 from the camera originals: reframe, speed, per-clip colour, CFR |
| `beats.py` | tracked beats, downbeats, bars, sections; cut frames one frame before the beat |
| `music_cut.py` | shorten a track on downbeats; ranks the best splices |
| `premiere_xml.py` | edit list to FCP7 XML for Premiere Pro, linked to the camera originals; refuses exports |
| `review_xml.py` | measure what an editor changed in their re-edit (FCP7 XML) |
| `captions.py` | caption plates as PNGs, correct variable-font instances |
| `brand_extract.py` | palette from images, fonts and text from a PSD |

## Install

```bash
git clone https://github.com/JahooClou/reelsmith
```

Then in Claude Code:

```
/plugin marketplace add /path/to/reelsmith
/plugin install reelsmith
```

## Requirements

- **ffmpeg**, a full build. The one bundled with `imageio-ffmpeg` can extract
  frames but usually lacks `libx264` and `lut3d`, so colour and render fail later
  rather than at the point of use. `ffmpeg_tools.py --locate` tells you which you
  have.
- **Python 3.9+** with `Pillow` and `numpy`.
- `psd-tools` only if reading PSD brand files.

```bash
pip install Pillow numpy psd-tools
```

## Originals, always

The edit is built on the **camera originals**, and everything that comes out of it
points back at them. The edit list names each clip's original file (`src`) and an
in-point in seconds from the start of that file. The render cuts from those files,
the grade is measured in them, and the Premiere XML links them with in and out
points, the reframe as Motion and slow motion as speed.

Nothing is prerendered for the handover. An export of an earlier edit has no
handles, is already cropped, already at the delivery frame rate and already graded,
so an editor given a sequence built on one can trim but never extend.
`premiere_xml.py` refuses a source that looks like an export and says why.

## A worked example

```bash
cd scripts

python ffmpeg_tools.py --locate
python logsheet.py /shoot/CamA /shoot/CamB /shoot/Drone --out log/
python verify.py /shoot/CamA/A001C014.MOV --scan 106 124 --step 1 --out take.jpg

python beats.py track.wav --fps 25 --out beats.json
python music_cut.py track.wav --beats beats.json --suggest 95 120
python music_cut.py track.wav --beats beats.json --keep bar:1-44,bar:105-end --out cut.wav
python beats.py cut.wav --fps 25 --out cut_beats.json

# write edl.json: sources, beat_map cut_beats.json, lead 1, clips with src, t, beats, cx, speed
python verify.py --edl edl.json --out check.jpg      # every clip, cropped and timed

python balance.py edl.json --out grade/              # per-shot balance + shared look
python premiere_xml.py edl.json --out cut.xml --balance grade/   # for the editing suite
python render.py edl.json --out out/ --balance grade/            # or a finished file

# the editor's version comes back as FCP7 XML
python review_xml.py reedit.xml --edl edl.json --beats beats.json --out review.md
```

## The seven that bite hardest

1. **Contact sheets sample mid-shot.** Always render your in-points and look at
   them before cutting.
2. **`-t` between two inputs limits the wrong input.** A fifteen-second cut renders
   as 1.4 GB with no error.
3. **Cut durations must be whole frames**, or the concat drifts off constant frame
   rate.
4. **Measure before assuming log.** The file you were handed is often an export
   that was already conformed, and a log expansion on it is unrecoverable.
5. **One LUT per camera cannot match shots.** Balance per shot, then apply one
   shared look. And `eq` computes `x^(1/gamma)`, so invert the exponent.
6. **Hand over the originals, never an export.** A sequence built on an export has
   no handles and nothing left to reframe, slow down or grade.
7. **Cut one frame before the beat.** Audio follows video; a cut exactly on the
   beat reads as late.

## Licence

MIT.
