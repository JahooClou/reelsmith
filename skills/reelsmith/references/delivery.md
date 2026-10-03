# Delivery

Two kinds of delivery, chosen at intake: a **rendered file**, or a **sequence for
the editing suite** plus the edit list. Either way the source is the camera
originals.

## Rendered file

`render.py` cuts every clip from its original, reframes, retimes and grades it,
keeps segment sound as PCM so the joins stay frame-exact, and encodes once at the end
at a constant frame rate.

YouTube's published upload recommendations **[platform]**:

| | Video | Audio |
|---|---|---|
| container | MP4 | |
| 1080p | 8 Mbps (24/25/30 fps), 12 Mbps (48/50/60) | AAC-LC or Opus, 48 kHz |
| 2160p | 35 to 45 Mbps (24/25/30), 53 to 68 Mbps (48/50/60) | stereo 384 kbps |
| frame rate | as recorded | |

Social: 1080×1920 H.264 MP4, high profile, AAC 48 kHz, at the project rate.

Loudness: no platform publishes a normalisation target for organic uploads; "−14
LUFS" is common practice, not a published YouTube figure. Mix so dialogue and
impacts are clear and the music does not clip; around −14 LUFS integrated with peaks
below −1 dBTP is a safe starting point.

Check the file before handing it over:

- count the frames, not just the duration (`ffprobe -count_frames`)
- `avg_frame_rate` equals the project rate
- the audio is the full length

## Sequence for the editing suite

```bash
python premiere_xml.py edl.json --out cut.xml --balance grade/
```

FCP7 XML, which Premiere imports without a plugin (File > Import). What travels:

- V1: every clip as the original file with in and out points
- reframe as Motion Scale and Position
- slow motion as speed, frame blending off
- A1/A2: camera sound for real-time clips
- A3/A4: the music, if the edit list names one
- one sequence marker per clip: Position, Scale, Speed, source timecode, grade
  values, caption text and the note, so anything that imports wrongly can be typed
  in

What does not travel: Lumetri colour and text layers. They go in the markers.

### Conventions Premiere reads

| Element | Meaning |
|---|---|
| clip `in`/`out` | frames at the **sequence** rate, from the first frame of the file, whatever the file's rate |
| retimed clip | `in`/`out`/`duration` in retimed frames: source seconds / speed × fps |
| Motion Scale | percent of the clip's own pixels |
| Motion Center | offset from the sequence centre in sequence pixels, divided by the clip's own width and height |

Premiere writes its own exports the same way, and adds `pproTicksIn`/`Out` and a
`masterclipid`. `review_xml.py` reads both.

## The edit list

Always deliver it, whatever else is delivered. Two files:

- **CSV**, exactly: shot, clip name, TC in, TC out, duration, plus speed when any
  clip is retimed.
- **Annotated (Markdown)**: the same rows by section, with record time, seconds
  from the start of the clip, camera and time shot, what the shot shows, and the
  reframe values.

Timecode is the clip's own, at its own rate: Canon 50p counts frames 00 to 49; DJI
59.94p is drop-frame 00 to 59 from a 29.97 track; files with no timecode track are
zero-based. TC out is exclusive. If a source monitor shows different numbers, the
seconds-from-start column still holds.

## After delivery

Ask for the editor's version back as FCP7 XML (Premiere: File > Export > Final Cut
Pro XML). An EDL loses reframes, speed and source paths. Then run `review_xml.py`
(`review.md`).
