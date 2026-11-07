"""Background upload: python -m soft_grind.youtube_worker <project>/youtube.json"""
from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

from . import errors, notify, projects, youtube


def run(job_path: str) -> None:
    jp = Path(job_path)
    pdir = jp.parent
    job = projects.read_json(jp)
    last = [0.0]

    def save(**kw):
        job.update(kw)
        job["updated"] = time.time()
        projects.write_json(jp, job)

    def progress(frac: float) -> None:
        if time.time() - last[0] > 1.0 or frac >= 1.0:
            last[0] = time.time()
            save(progress=round(frac * 0.95, 3), message=f"uploading · {int(frac * 100)}%")

    save(state="running", progress=0.0, message="connecting to youtube", error="", note="")
    try:
        m = projects.meta(pdir)
        vid = youtube.upload_video(pdir / "video.mp4", m, progress)
        projects.set_meta(pdir, youtube_id=vid, youtube_at=time.strftime("%Y-%m-%d %H:%M"))      # remembered at once: never uploaded twice
        note = ""
        cover = pdir / "thumbnail.png"
        if cover.exists():
            save(progress=0.97, message="setting the cover")
            note = youtube.set_thumbnail(vid, cover)
        save(state="done", progress=1.0, message="done", note=note, finished=time.time())
        scheduled = bool(youtube.publish_at(m.get("schedule", "")))
        notify.send(f"{pdir.name}: uploaded to youtube",
                    ("It will go public at " + m.get("schedule", "") + ".") if scheduled else "It is private: open YouTube Studio to publish.",
                    tags="rocket")
    except youtube.YouTubeError as e:
        save(state="failed", message="failed", error=str(e))
        notify.send(f"{pdir.name}: the upload failed", errors.explain(str(e))["title"], priority="high", tags="warning")
    except Exception as e:
        traceback.print_exc()
        save(state="failed", message="failed", error=f"{e.__class__.__name__}: {e}")
        notify.send(f"{pdir.name}: the upload failed", errors.explain(str(e))["title"], priority="high", tags="warning")


if __name__ == "__main__":
    run(sys.argv[1])
