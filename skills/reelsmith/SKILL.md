---
name: reelsmith
description: >
  Video editing from camera originals to a finished cut, for any destination:
  Reels, TikTok, Shorts, YouTube, Vimeo, aftermovies, event recaps, promos,
  documentaries and interviews. Starts with a short intake (platform, orientation,
  beat edit or story edit, pace and music, delivery as a render or as an XML for
  Premiere), then logs the footage, builds the structure, cuts it to the music or to
  the story, and delivers either a rendered file or a Premiere sequence linked to the
  originals plus an edit list. Learns from the editor's own re-edit. Use whenever
  someone wants an edit, a cut, a reel, a short, a trailer, a teaser, an aftermovie,
  a highlight film, a recap, a music-video style montage, an edit list or an XML from
  footage, or asks what shots they have, how to cut something to music, how to
  shorten a track for an edit, or what changed between two versions of a cut. Also
  use for one part of the job, such as "cut this to the beat", "find the best
  moments in this footage", "make a Premiere XML" or "review my re-edit".
---

# Reelsmith

An editor's skill. The job is the cut: the right moments, in an order that means
something, on a rhythm the viewer feels. Everything else (logging, music, reframing,
colour, captions, delivery) serves that.

It works from **camera originals**, always. The edit list points at the original
files, the render cuts from them, and the Premiere XML links them with in and out
points, so an editor can slide any cut against the full take.

State lives in `reelsmith.json` in the working folder, created at intake and updated
at every gate, so the job can be resumed and the decisions read back.

**Before touching media, read `references/pitfalls.md`.** Every item is a bug that
shipped. For real people and real events, read `references/documentary.md` too.

---

## 1. Intake: five questions first

Ask these together, in one message, before any analysis. Offer the likely answer
for each so the editor can reply in one line. Skip only what the request already
answered.

| # | Question | Why it decides things |
|---|---|---|
| 1 | **Where will it be watched?** Social (Reels, TikTok, Shorts) or long-form (YouTube, Vimeo, a screen at an event) | hook and retention rules, length, captions, safe zones, loudness, export |
| 2 | **Vertical or horizontal?** (9:16, 16:9, 4:5, 1:1) | reframing, which footage survives, caption placement |
| 3 | **Beat edit or story edit?** | a beat edit is cut to the music's grid; a story edit is cut to meaning and sound, and the music, if any, follows the story |
| 4 | **What pace, and what music?** An existing track, or one to generate with soundsmith (Suno) | tempo, shot length, where the peaks fall; see `references/music.md` |
| 5 | **What is delivered?** A rendered file, or an XML for the editing suite (Premiere) plus the edit list | whether colour and captions are done here or handed over |

Then the material questions, briefly: where the originals are, which cameras and
operators to favour, which days or moments matter most, any brand rules, and how
long it should run. If the editor gives preferences mid-job ("mostly Saturday
afternoon", "more slow motion", "very dynamic"), record each one in
`reelsmith.json` under `brief` and honour it in every later step.

**Gate:** the brief, written back in five lines. Record it and move on.

The answers pick the references to load:

| Answer | Load |
|---|---|
| social, vertical | `references/shortform.md` |
| YouTube, Vimeo, horizontal, long | `references/longform.md` |
| beat edit, or any music | `references/music.md` |
| real people, events, interviews | `references/documentary.md` |
| always, before cutting | `references/craft.md` |
| XML delivery, or a re-edit came back | `references/delivery.md`, `references/review.md` |

---

## 2. Footage: originals, probed

Find the camera originals and probe them all:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/ffmpeg_tools.py --probe ORIGINAL [ORIGINAL ...]
```

Record per camera: resolution, frame rate (50p and 59.94p give clean slow motion on
a 25p timeline), sound, embedded timecode, orientation. If you were handed an export
of an earlier edit instead, ask for the originals behind it. Work from an export
only when the originals do not exist, and say so (`premiere_xml.py` refuses one
without `--allow-derived`).

Compute the reframe before promising it. UHD 16:9 to 9:16 is a 1215×2160 window,
plenty of pixels; the limit is composition. 9:16 originals into 16:9 do not work
without a design decision (a blurred fill, a split screen, a graphic frame), so say
so at the gate.

**Gate:** confirm the sources and the delivery format.

---

## 3. Log: find the moments

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/logsheet.py /shoot/CamA /shoot/CamB /shoot/Drone --out log/
```

Samples every original (densely for short clips, sparsely for long continuous
ones), writes contact sheets in recording order with every tile labelled
`CODE m:ss`, and an index. Read every sheet. Write a log: `code + seconds from the
start of the clip + what happens`, and mark:

- **establishing shots**: drone, wide, signage, the place itself
- **action peaks**: the hit, the jump, the moment of effort
- **faces**: portrait moments, reactions, eyes, exhaustion, joy
- **sound events**: a shout, a whistle, a crowd roar, a clap
- **outcome**: finish line, clock, medal, embrace, team photo
- **slow-motion candidates**: high-rate originals with motion worth stretching

Then scan the stretches you will use densely, and check the actual in-point:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/verify.py ORIGINAL --scan 106 124 --step 1 --out take.jpg
```

A sheet tile is one frame. A twenty-second take holds many moments, and the one you
liked can be ten seconds from where you would guess.

**Gate:** the log, as a short list of the strongest material per category, and
anything missing that the brief needs (say it plainly: "no medal ceremony close-ups
from Sunday").

---

## 4. Structure

**Write the through-line in one sentence before ordering anything.** "A weekend of
the hardest obstacle race in the country: the place, the effort, the finish, the
people" is a structure; "nice shots of runners" is not.

Then the shape, by edit type:

- **Story edit.** Acts and peaks from `documentary.md`: the world and the
  disruption, complications that change the situation, the outcome. Peaks at about
  24 / 54 / 80 / 95% of the running time, each followed by a breath.
- **Beat edit.** The music's sections are the acts. Map them first (step 5), then
  give each section one job: intro = place and ritual, build = escalating action,
  drop or chorus = the peak and its payoff, break = a face or a held moment, last
  chorus = everyone, outro = the closing image.

In both, `craft.md` rules apply. The ones editors notice first:

- **Show where it happens, early.** An establishing shot (drone, wide, sign) in the
  first seconds orients the viewer. It does not have to be the very first shot: a
  hook can come first and the place right after it.
- **Open on the strongest thing you have** for social; on a promise of the film for
  long-form. Never on a logo.
- **End on the truthful outcome** and a closing image, not on a fade to nothing.

**Gate:** the structure as a section list with timings and the job of each section.

---

## 5. Music

Load `references/music.md`. Three cases:

- **The editor has a track.** Map it: `beats.py` gives the tracked beats (generated
  music drifts; a fixed grid is frames off by the end), downbeats, bars and section
  boundaries. If it is too long, `music_cut.py --suggest MIN MAX` ranks splices on
  downbeats between similar bars; render the chosen one and map the cut file again.
- **Generate one.** Turn the pace answer into a tempo whose beat is a whole number
  of frames at the delivery rate, and a section plan that matches step 4. Hand both
  to the **soundsmith** skill to build the Suno prompt; it covers scoring to picture.
- **No music.** A story edit on production sound is a real choice and stands out in a
  feed. Then step 6 cuts on sound and meaning only.

**Gate:** the music file, its length, and its section map.

---

## 6. Cut

Write the edit list (`references/edl.md`): each clip names its original (`src`),
the in-point in seconds from the start of that file, and its length. For a beat
edit, give lengths in **beats** and let the tools place the cuts:

```json
{"beat_map": "music/beats.json", "lead": 1, "fps": 25, "width": 1080, "height": 1920,
 "sources": {"Dro001": "/shoot/Drone/DJI_0003.MP4", "CamA021": "/shoot/CamA/A001C021.MOV"},
 "reels": [{"name": "Recap", "clips": [
   {"code": "Dro001", "src": "Dro001", "t": 68.16, "beats": 8, "note": "establishing: the course from the air"},
   {"code": "CamA021", "src": "CamA021", "t": 4260.0, "beats": 2, "cx": 0.42, "note": "the finish, close"}]}]}
```

**Every picture cut lands `lead` frames before its beat (default 1): audio follows
video.** A cut exactly on the beat reads as late. This is applied for you from the
beat map; never place cuts on raw beat times by hand.

The rhythm rules that matter most (all in `craft.md`):

- Vary shot length. Runs of 1- and 2-beat cuts, then a hold of 4 to 8 beats. The
  hold is what makes the pattern felt.
- Hit section changes with the strongest shot; land the drop on a peak.
- Use the editor's tools, not only straight cuts: a punch-in on the same take, a
  stepped punch-in (one take sliced into 2 to 4 pieces, each scaled further in), a
  short speed-up into a cut, slow motion on a face or a peak, a held reaction.
- Every shot earns its place: one idea per shot, and no two adjacent shots that say
  the same thing.

Check it as it will be seen:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/verify.py --edl edl.json --out check.jpg
```

First, middle and last frame of every clip, cropped and at its speed. Fix the list,
not the render.

**Gate:** the cut as a table (shot, clip, in, length, what it is) plus the check
sheets. Expect changes; that is the job.

---

## 7. Finish

What is done here depends on the delivery answer.

- **Reframe** (`cx`, `cy`, `z`): one subject per frame, eyes in the upper third.
  The same window is used by the render and written into the XML as Motion.
- **Colour.** For a render: per-shot balance plus one shared look (`balance.py`,
  `reel-color` skill). For an XML: grade values go into markers; colour is the
  editor's job in the suite.
- **Text and captions.** Social: a hook card, a few short cards, burnt-in only if
  asked; keep them off faces and inside the platform's interface margins. Long-form:
  lower thirds and a title. Render text plates with `captions.py` (correct font
  weights), or hand the text over with timings.
- **Sound.** Music level and ducking, SFX on transitions and impacts (shutter
  clicks, whooshes, hits), nat sound up where it carries the moment. A sound that
  starts a frame or two before its picture feels right; one that starts after feels
  late.

---

## 8. Deliver

Load `references/delivery.md`.

**Rendered file:**

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/render.py edl.json --out out/ --balance grade/
```

**For the editing suite** (Premiere): a sequence of the original clips, nothing
rendered:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/premiere_xml.py edl.json --out cut.xml --balance grade/
```

Always hand over the edit list as well: shot, clip name, source TC in, TC out,
duration, speed, plus a version with notes and reframe values.

**Gate:** the deliverable. Ask for the editor's re-edit back as an XML.

---

## 9. Learn from the re-edit

When the editor sends their version (Premiere: File > Export > Final Cut Pro XML):

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/review_xml.py reedit.xml --edl edl.json --beats music/beats.json --out review.md
```

It measures, rather than guesses: cut timing against the beat in frames, shot
lengths in beats, what was kept, dropped, reordered, trimmed, punched in, slowed
down or added, and how the music was cut. Read `references/review.md`, summarise the
changes as rules, and propose skill updates to the editor. Change the skill only
with their agreement.

---

## When someone jumps into the middle

"Cut this to the beat", "what's in this footage", "shorten this track", "make an
XML", "review my re-edit": serve it directly with the matching step. Still check the
two things that invalidate later work: whether ffmpeg can do what is needed, and
whether the footage is camera originals. Ask only the intake questions the request
leaves open.

## Scripts

| Script | Does |
|---|---|
| `ffmpeg_tools.py` | find ffmpeg, report what the build can do, probe media |
| `logsheet.py` | log many originals: sampled frames, contact sheets, index |
| `shots.py` | shot detection inside one long file |
| `verify.py` | dense scan of a take; check every clip of an edit list as seen |
| `beats.py` | tracked beats, downbeats, bars, sections; cut frames one frame early |
| `music_cut.py` | shorten a track on downbeats; ranks the best splices |
| `balance.py`, `color.py` | per-shot balance and shared look; per-camera LUTs |
| `captions.py` | text plates as PNG with the right font weights |
| `render.py` | edit list to finished file from the originals |
| `premiere_xml.py` | edit list to a Premiere sequence linked to the originals |
| `review_xml.py` | what an editor changed in their re-edit, measured |

## References

- `references/craft.md`: cutting rules, rhythm, transitions, punch-ins, speed, sound
- `references/shortform.md`: hooks, retention, loops, captions, platform margins
- `references/longform.md`: YouTube and Vimeo structure, pacing, chapters
- `references/music.md`: beat vs story edit, pace and tempo, generating with soundsmith, cutting a track
- `references/documentary.md`: story, structure, sound and dignity with real people
- `references/delivery.md`: export settings, XML handoff, the edit list format
- `references/review.md`: reading an editor's re-edit, and what has been learned from them
- `references/edl.md`: edit list schema
- `references/color.md`: measurement, LUT maths, `.cube` format
- `references/pitfalls.md`: silent failures, read before any media work
