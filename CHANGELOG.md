# Changelog

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
