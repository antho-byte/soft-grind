"""Background render: python -m soft_grind.render <project>/render.json  ->  <project>/video.mp4"""
from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

from . import errors, notify, playlist, projects, video


def run(job_path: str) -> None:
    jp = Path(job_path)
    pdir = jp.parent
    job = projects.read_json(jp)
    spec = job.get("spec", {})
    last = [0.0]

    def save(**kw):
        job.update(kw)
        job["updated"] = time.time()
        projects.write_json(jp, job)

    def progress(frac: float, msg: str) -> None:
        if time.time() - last[0] > 1.0 or frac >= 1.0:
            last[0] = time.time()
            save(progress=round(frac, 3), message=msg)

    save(state="running", progress=0.0, message="starting", error="")
    try:
        tracks = projects.audio_files(pdir / "tracks")
        durations = [playlist.audio_duration(t) for t in tracks]
        video.render_video(tracks, pdir / "still.png", pdir / "video.mp4", durations, spec.get("crossfade", 4.0),
                           spec.get("fade_in", 3.0), spec.get("fade_out", 6.0), progress,
                           look=projects.film_look(pdir))
        save(state="done", progress=1.0, message="done", finished=time.time())
        notify.send(f"{pdir.name}: the video is built", "Open soft grind. to watch it.", tags="movie_camera")
    except video.VideoError as e:
        save(state="failed", message="failed", error=str(e))
        notify.send(f"{pdir.name}: the video failed", errors.explain(str(e))["title"], priority="high", tags="warning")
    except Exception as e:
        traceback.print_exc()
        save(state="failed", message="failed", error=f"{e.__class__.__name__}: {e}")
        notify.send(f"{pdir.name}: the video failed", errors.explain(str(e))["title"], priority="high", tags="warning")


if __name__ == "__main__":
    run(sys.argv[1])
