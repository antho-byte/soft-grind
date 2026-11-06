# soft grind. studio: on hold and ideas

## On hold: soundbar overlay on the video (asked for, parked by the owner)
Put the owner's 15-minute green-screen soundbar clip as a looping layer in the bottom-right of every video.

- Plan: loop the clip (`-stream_loop -1`), key out the green (`chromakey`), overlay bottom-right with a margin, 24 fps.
- Benchmark (4-core cloud machine, 1080p): about 3x real time, so ~20 min per hour of video (plus the audio pass). Without the overlay a video takes a few minutes.
- Build with a **preview frame button** first (one frame, a few seconds) so the green-screen edges and size can be checked before a long render.
- Alternative: draw the bars from the real audio (ffmpeg showfreqs): synced to the music, needs no clip.
- Needs from the owner: a ~10 s sample of the clip, where the full clip lives, the size on screen, and whether it is on for every video (including the automatic ones) or per video.

## Ideas
- Tailscale for starting videos from a phone / work laptop (the home computer must stay on).
- Detect the same picture saved twice in the image library (image fingerprint).
- YouTube upload as private + scheduled (needs a Google API setup).
