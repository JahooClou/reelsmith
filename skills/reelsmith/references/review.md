# Learning from the editor's re-edit

The editor's version of a cut is the most valuable feedback the skill gets. Read it
as data, measure it, and turn it into rules. Do not trust impressions of what
changed.

## Process

1. Ask for an FCP7 XML export of the re-edited sequence, not an EDL.
2. Run:

   ```bash
   python review_xml.py reedit.xml --edl edl.json --beats beats.json --out review.md
   ```

   `--beats` is `beats.py` output for the original music file. Without it, the
   script maps the music it finds on A1.

3. Read the report alongside what the editor said. Separate:
   - **rules**: general and repeatable ("cut one frame before the beat")
   - **taste**: specific to this film ("more drone in the intro")
   - **corrections**: something the skill did wrong ("the AF box belongs on the
     face")
4. Propose changes to the skill as a short list, each one tied to a measurement.
   Apply them only after the editor agrees.
5. Add the rules to the table below with the date and the evidence.

## What the report measures

| Section | Measures |
|---|---|
| Music | which source ranges the music edit uses and where the splices are |
| Cut timing | frames from every picture cut to the nearest beat, as a histogram |
| Rhythm | shot lengths in beats, mean and median shot length, the opening shots |
| Framing and speed | punch-ins past the fill scale, stepped punch-ins, slow motion, speed-ups |
| Other layers | upper video tracks (overlays, graphics, transitions) and SFX tracks |
| Against the original cut | kept, dropped, reordered (share of shot pairs swapped), in-points moved, new moments from the same files, new files |

## Rules learned so far

| Date | Rule | Evidence | Where it lives now |
|---|---|---|---|
| 3 Oct 2026 | Cut one frame before the beat: audio follows video | event aftermovie re-edit: 42 of 67 cuts lead the beat (36 by 1 to 2 frames), 13 are on it, median −0.9 frames; editor's statement | `beats.py --lead`, edit list `lead`, `craft.md` §1 |
| 3 Oct 2026 | Establish the place early, but not necessarily first | re-edit opens on 4.2 s and 3.7 s of drone, then the hook; editor's statement | SKILL step 4, `craft.md` §3 |
| 3 Oct 2026 | Vary rhythm: mostly 1 to 2 beats, holds of 4 to 15 on faces and outcomes | shot lengths in beats: 1: 8, 2: 27, 3: 13, 4: 12, 5 to 15: 8 | `craft.md` §2 |
| 3 Oct 2026 | Punch in and slice; do not only cut wide | 18 of 68 shots scaled past fill (up to ×2.2); one stepped punch-in of three slices on the finish clock | `craft.md` §4 |
| 3 Oct 2026 | Shorten music by whole sections, downbeat to downbeat, cross-faded | 3:29.8 track cut 0:00 to 1:22.7 + 3:12.1 to end, 24-frame cross-fade, 100.4 s | `music_cut.py`, `music.md` |
| 3 Oct 2026 | Inserted pieces get designed transitions and SFX | film-burn overlays around the slideshow, a shutter click and beep under every photo | `craft.md` §5 and §6 |
| 3 Oct 2026 | Reorder in blocks, keep the order inside sections | 24% of shot pairs swapped; 54 of 82 shots kept, 10 new moments from the same files | `craft.md` §3 |
| 3 Oct 2026 | Photo inserts: open defocused, rack to sharp; the AF point sits on the face | editor's corrections to the viewfinder slideshow | `craft.md` §5 |

## Reading the timing histogram

- Most cuts at −1 or −2 frames: the editor leads the beat, as intended.
- A spread of −4 to +6: cuts on action rather than on the beat, normal inside
  runs.
- Cuts at +1 or later in a beat edit: those read as late. Check whether they are
  deliberate (an L-cut, a held reaction) before calling them a rule.
