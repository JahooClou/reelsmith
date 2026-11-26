# Changelog

## 2.2.0 (2026-11-26)

Checking the result, not only the plan, and matching a reference's pace.

- **`qc.py`: check the rendered file before it leaves.** Size, rate and length against
  the edit list; black frames and stretches where nothing moves for 2 s; integrated
  loudness, true peak, silence before the first sound and gaps in the sound; caption
  plates on a face, outside the interface margins, or a face up under the app's top
  bar; with `--speech`, each caption compared with the words said under it. FAIL
  exits 1. `--sheet` draws faces, plates and margins on every flagged frame. Faces
  come from YuNet (OpenCV Zoo, MIT), bundled in `scripts/models/` with its licence.
- **`captions.py --faces`: plates place themselves off faces.** `qc.py --faces-out`
  measures the faces on a clean render; each plate with `"y": "auto"` then takes the
  first spot off every face inside the margins (bottom of the safe area, under the
  chin, above the head, then up the frame), shrinking to 85 % and 72 %, then the
  looser margins, then none. It never gives up the face; when nothing fits it says
  so. Auto-placed plates also keep inside the side margins.
- **`pace.py`: the pace of a reference, in numbers.** Hits per second (anything new
  on screen), cuts per second (jump cuts included), average shot, the longest still
  stretch and where it is, words per second and the first word; a 6 fps sheet of the
  first six seconds. Given a reference and a cut, marks anything more than 20 % off.
- `SKILL.md`: measure a named reference at intake, compare the draft's pace in step 6,
  place plates off faces in step 7, run `qc.py` in step 8.
- `shortform.md`: "Matching a reference" (look, pace, match).
- `delivery.md`: what `qc.py` covers and what is still checked by hand.
- `pitfalls.md` §30: faster-whisper picking CUDA without its libraries, and a newer
  PyAV than it expects.

## 2.1.0 (2026-10-16)

Lessons from the next round of live projects: a 16:9 beat edit built in After Effects,
a photo slideshow re-timed to the editor's re-edit, a product film rebuilt from an old
edit, and a documentary reel.

- **Never the same moment twice.** `verify.py --edl` now lists every pair of clips from
  one original whose source ranges come within 5 s; `--repeats` runs only that test and
  exits 1 when it finds any. Slices of one take (a stepped punch-in) count as one shot;
  `"allow_repeat": true` exempts a clip. Replaces the old "repeat with variation" rule
  in `craft.md`, which the editor overruled.
- `pitfalls.md` §20: finding the camera originals behind an old edit by image
  (grade-insensitive thumbnails, SIFT check, in-point and speed alignment).
- `pitfalls.md` §27 to §29: repeated moments, interval timelapses stored with repeated
  frames, screen recordings that show tokens and e-mail addresses. §12: probe device
  and screen recordings too.
- `delivery.md`: finishing a picture rendered in another application (sound from the
  original file, encoded once; loudness and a per-shot check sheet).
- `craft.md` §5: photo inserts change one frame before the beat; AF beep at focus lock,
  shutter click on the beat.
- `documentary.md`: an exclusion is a list of takes, each checked at full resolution.
- `review.md`: the new rules with their evidence.

## 2.0.0 (2026-10-03)

A general editing skill: five-question intake, social or long-form, beat or story edit,
cuts one frame before the beat, render or Premiere XML linked to the camera originals,
and `review_xml.py` to learn from the editor's re-edit. Installable as a plugin from the
repo.

## 1.0.0 (2026-08-20)

Step-gated short-form pipeline: logging, shot detection, per-shot balance and shared
look, captions, render, and `premiere_xml.py`.
