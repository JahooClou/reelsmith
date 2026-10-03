# Music: beat edits, story edits, tempo and tracks

## Beat edit or story edit

| | Beat edit | Story edit |
|---|---|---|
| What drives the cut | the music's grid | meaning, action and sound |
| Where cuts fall | one frame before beats, mostly on bars and phrase ends | on action, on a look, on a sound |
| Music | chosen or generated first; picture is cut to it | chosen or written to the cut; may drop out |
| Typical use | aftermovies, promos, social montages, trailers | documentaries, interviews, news, portraits |
| Risk | mechanical: every shot the same length | slack: no drive |

Most real films mix them: a story edit with beat-edit montages, or a beat edit with
one held story moment where the music drops out.

## Pace to tempo

At 25 fps a beat lasts `1500 / BPM` frames. A tempo whose beat or bar is a whole
number of frames keeps the cut grid exact and avoids drift. Frame-exact at 25 fps:

| Pace | BPM (25 fps) | Beat | Shot length in practice |
|---|---|---|---|
| calm, cinematic | 75, 93.75 (16 fr), 100 (15 fr) | 0.6 to 0.8 s | 2 to 8 beats |
| driving | 115.4 (13 fr), 125 (12 fr) | 0.48 to 0.52 s | 1 to 4 beats |
| energetic | 136.4 (11 fr), 150 (10 fr) | 0.4 to 0.44 s | 1 to 4 beats |
| frantic | 166.7 (9 fr), 187.5 (8 fr) | 0.32 to 0.36 s | 2 to 4 beats; 1-beat cuts become a strobe |

At 30 fps use `1800 / BPM` (for example 120, 128.6, 150), at 24 fps `1440 / BPM`
(120, 144). Anything between works if the beats are tracked (`beats.py`): the cut
frames then round to the nearest frame, which is what an editor does by hand.

## Generating the track (soundsmith)

When the editor wants new music, hand the **soundsmith** skill a brief built from
the edit:

1. **Tempo**: the frame-exact BPM from the table, with "no tempo changes".
2. **Length**: the target running time plus two bars, to leave room for the end.
3. **Structure**: one section per act of the edit, in order, with lengths in bars.
   For example: intro 8 bars (place, ritual), build 16 (escalating action), drop 16
   (peak, payoff), break 4 (a face, hold), final chorus 8 (everyone), outro 4
   (closing image, hard stop).
4. **Character**: genre and instrumentation from the brief; for an event film,
   whatever the event uses (its own song, its brand music).
5. **Ending**: a real ending on a downbeat, not a fade.

Generated music drifts in tempo (one 3.5-minute track went from 127.8 to 131.2 BPM)
and its sections are not always the length asked for. Always map what came back
with `beats.py`, and cut to that map, not to the brief.

## Mapping a track

```bash
python beats.py track.wav --fps 25 --out beats.json
```

Reports the tempo at start and end, and flags drift. Writes tracked beats placed on
the audible transient, downbeats, bars with loudness, and section boundaries: a bar
whose loudness steps by 2.5 dB or more starts a section. Read the section list
before cutting anything: it is the music's structure.

## Shortening a track

```bash
python music_cut.py track.wav --beats beats.json --suggest 95 120
python music_cut.py track.wav --beats beats.json --keep bar:1-44,bar:105-end --out cut.wav
python beats.py cut.wav --fps 25 --out cut_beats.json
```

- Cut whole sections, downbeat to downbeat. The usual move is from the end of the
  build into the last chorus: it keeps the intro and the real ending and loses a
  repeat.
- `--suggest` ranks single splices that reach the target length by bar similarity,
  section starts and energy.
- The cross-fade is equal-power, about a second, centred on the splice, as an
  editor lays it in the timeline.
- Then map the cut file. Its beats are what the picture is cut to.

Reference: an editor's cut of a 3:29.8 track kept 0:00 to 1:22.7 (intro, verse,
build, up to the chorus) and joined 3:12.1 to the end (final chorus and ending): a
100.4 s track with one 24-frame cross-fade. `music_cut.py --keep bar:1-44,bar:105-end`
reproduces it within a frame.

## When the music stops

A drop-out is one of the strongest tools in a beat edit: a second of silence or of
nat sound before the drop, a held face with only breath and crowd. Plan it in the
structure, and if the track is generated, ask for it (`[Break - drums drop out]`).
