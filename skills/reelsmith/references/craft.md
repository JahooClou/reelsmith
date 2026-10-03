# Craft: cutting rules

The rules here hold for every kind of edit. The ones marked **(editor)** come from
a working editor's re-edit of a reelsmith cut and are measured, not assumed; see
`review.md` for the numbers.

---

## 1. Timing a cut

- **The picture cut comes one frame before the beat. Audio follows video. (editor)**
  The eye registers a cut faster than the ear places a beat, so a cut exactly on the
  transient looks late. In the editor's re-edit 42 of 67 cuts lead the beat (36 of
  them by one or two frames), 13 are on it, median −0.9 frames. `beats.py` places cut frames at `beat - lead`
  (lead 1 at 25 fps, 1 to 2 at 50/60 fps). A beat time is the audible transient,
  not the tracker's smoothed estimate, which runs 30 to 40 ms early or late.
- **Not every cut is on a beat.** Section changes, drops and the first shot after a
  break should be; inside a run, a cut on the off-beat or on an action can feel
  better. In story edits, cut on action, on a look, or on a sound.
- **Cut on action.** Leave the outgoing shot as the movement starts and enter the
  next one mid-movement. The motion hides the join.
- **Sound leads picture across scene changes.** Bring the next scene's sound in a
  few frames to a second before its picture (J-cut), or let a sound trail over the
  next picture (L-cut).

## 2. Rhythm

- **Vary length.** A run of one- and two-beat cuts, then a held shot of four to
  eight beats. The editor's re-edit: 35 of 68 shots are one or two beats long, 13
  three beats, 12 four beats, and a handful of holds of 6 to 15 beats on faces,
  embraces and the closing image. Mean shot 1.44 s.
- **A flurry before a drop.** Three to six one-beat shots of the same kind of
  action, then the drop on the strongest shot.
- **Hold where the face is still being read.** Exhaustion, joy and embraces get
  length; equipment and wide action do not.
- **Repeat with variation.** The same take can come back later, reframed or slowed
  (the editor reused one relay take three times, at 100%, punched in, and in
  slices). A repeat with no new information is padding.

## 3. Order

- **Establish the place early. (editor)** A drone or wide shot of the venue in the
  opening seconds tells the viewer where they are. It need not be shot 1: a hook can
  come first, then the place. The editor opened on 4.2 s and 3.7 s of drone, then the
  hook.
- **Escalate.** Each section should hit harder than the last. Order by intensity,
  not by the timetable, as long as the order makes no false claim (do not cut a
  medal before the race it was won in if the film says it is the same person).
- **Reorder in blocks.** The editor kept the original order inside sections and
  moved whole blocks (about a quarter of shot pairs swapped). Revise structure at the
  section level first, then the shots inside.
- **Close on outcome and people.** Finish line, faces, the team, a closing wide,
  then the end card.

## 4. Inside the shot

- **Punch-in.** Scale into the same take (110 to 200%) to pull a face or an action
  out of a wide. UHD on a 1080×1920 or 1920×1080 timeline: a 16:9 frame has 2x of
  clean headroom; a 9:16 window cut from UHD has only about 1.12x before it
  upscales, so a 2x punch-in there is visibly softer. The editor punched in on 18 of
  68 shots, up to 2.2x, accepting the softness on fast moments.
- **Stepped punch-in. (editor)** One take cut into three or four consecutive
  slices, each scaled further in (100, 125, 180%), one slice per beat, then back to
  the wide. Good on a clock, a face, a decisive moment.
- **Reframe per shot.** One subject, eyes in the upper third, leading room in the
  direction of movement. Re-centre per shot; never trust one crop for a whole take.
- **Slow motion as punctuation.** Use the camera's frame rate: 50p at 50% and
  59.94p at 41.71% on a 25p timeline show every recorded frame once. Slow faces,
  impacts and moments of release; leave runs at speed. The editor used 13 slow clips
  in 100 s.
- **Speed-up as a transition.** A few frames at 300 to 500% into a cut feel like a
  whip. Used once in the re-edit, into the slideshow.

## 5. Transitions

- **Straight cuts by default.** A dissolve is a statement about time.
- **Designed transitions are moments, not glue.** Film burns, flashes, a camera
  shutter or a whip belong at section changes or into an inserted piece (a photo
  slideshow, a title), with their own sound. The editor used three film-burn
  overlays on V2 only around the slideshow.
- **Inserted pieces** (a photo slideshow, an animated title) should look like they
  belong to the film. For a camera-viewfinder photo insert: each photo opens
  defocused and racks to sharp, the AF point sits on the face (the visor when a mask
  hides it), and a shutter closes on the cut. (editor)
- **Overlays on V2** (a quick insert over the cut) let a second image punch in for
  a few frames without breaking the music edit underneath.

## 6. Sound

- **Music is not everything.** Duck it under a shout, a whistle or a crowd roar
  when the moment is the sound.
- **SFX sell transitions and impacts.** A shutter click on a photo cut, a whoosh on
  a whip, a hit on an impact. The editor laid a shutter click and beep under every
  slideshow photo.
- **Cross-fade music edits.** A splice in the music gets a short cross-fade centred
  on the edit point (about a second, two beats), on a downbeat.
- **End on the music's ending.** Cut the track so it finishes, rather than fading a
  chorus out.

## 7. Graphics and end card

- **End card short.** About 1.5 s on social; longer only with a reason (credits,
  partners), and then animated. The editor's end plate sits on V2 over the last 4.9 s,
  under the music's final hit.
- **One job per card**, inside the platform's interface margins (`shortform.md`),
  never on a face.
