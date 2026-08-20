# reelsmith

A step-gated pipeline for turning raw footage into finished short-form vertical
video. Claude Code plugin, three skills, nine scripts.

It is deliberately brand-agnostic. It will extract and use a brand if one exists,
and it will not invent one if there isn't.

## Why

Short-form editing is a chain where an early mistake stays invisible until the
render. Somebody picks a shot from a contact sheet, notes the shot's start
timecode, and cuts from it — but the sheet sampled the middle of a twenty-second
take, so the finished cut has a stranger where the payoff was supposed to be.

Every guardrail in this plugin is a bug that actually shipped. They are collected
in [`pitfalls.md`](skills/reelsmith/references/pitfalls.md), which is worth reading
even if you never install the plugin.

## The eleven steps

Each one stops for a decision. That is the point — the person you are working with
knows things about their footage and audience that no analysis will surface.

| | Step | Gate |
|---|---|---|
| 1 | Topic and concept | which hooks and concepts survive |
| 2 | Branding | extract, or skip if there is none |
| 3 | Footage | confirm sources |
| 4 | ffmpeg | confirm binary and its capabilities |
| 5 | Analyse: shots, framing, colour | what to do next |
| 6 | Colour measured | grade, or leave as-is |
| 7 | LUTs and before/after | apply, hand over, or retune |
| 8 | Caption typography | fonts, and burn-in or clean |
| 9 | Music | yes, or skip to render |
| 10 | Cut to beat | approve the beat-aligned list |
| 11 | Render | review |

You can also enter in the middle. "Make a LUT for this", "what shots are in this
file", "cut this to the beat" all work directly.

## Skills

| Skill | For |
|---|---|
| `reelsmith` | the full pipeline, gated |
| `reel-color` | measure footage, balance shots to match, build `.cube` LUTs |
| `reel-cut` | shot detection, verified edit lists, render |

## Scripts

All under `scripts/`, all runnable standalone.

| Script | Does |
|---|---|
| `ffmpeg_tools.py` | locate ffmpeg, report build capabilities, probe media |
| `shots.py` | scene detection per segment, labelled contact sheet |
| `verify.py` | render exact in-points, or scan a long take densely |
| `balance.py` | per-shot balance + one shared look; the matching path |
| `color.py` | measure, generate per-camera LUTs, before/after comparison |
| `render.py` | edit list to finished mp4, per-clip LUTs, CFR |
| `beats.py` | tempo and frame-aligned beat grid, numpy only |
| `premiere_xml.py` | edit list to FCP7 XML for Premiere Pro |
| `captions.py` | caption plates as PNGs, correct variable-font instances |
| `brand_extract.py` | palette from images, fonts and text from a PSD |

## Install

```bash
git clone https://github.com/USER/reelsmith
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

## A worked example

```bash
cd scripts

python ffmpeg_tools.py --locate
python ffmpeg_tools.py --probe master.mp4

python shots.py master.mp4 --out shots/ --segments segments.json
python verify.py master.mp4 --scan 106 124 --step 2 --out take.jpg
python verify.py master.mp4 --points points.json --out check.jpg

python color.py --measure master.mp4 --groups groups.json --out lutcfg.json
# rendering yourself: balance per shot, then one shared look
python balance.py edl.json --source master.mp4 --out grade/

# or hand LUTs to someone grading manually
python color.py --make-luts lutcfg.json --out luts/
python color.py --compare master.mp4 --luts luts/ --out compare.jpg

python beats.py track.mp3 --fps 25 --every 4 --out beats.json
# hand the cut to an editor instead of rendering it
python premiere_xml.py edl.json --source master.mp4 --out cut.xml --balance grade/

python render.py edl.json --source master.mp4 --out out/ \
  --balance grade/ --shots shots/shots.tsv
```

## The five that bite hardest

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

## Licence

MIT.
