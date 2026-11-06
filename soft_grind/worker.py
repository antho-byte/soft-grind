"""Background worker: python -m soft_grind.worker <project>/job.json

Generates the tracks for one project. It runs as its own process, so the app can be used (or reloaded) meanwhile.
Progress goes to job.json, which the Projects overview reads. Task ids are saved the moment they exist.
"""
from __future__ import annotations

import os
import re
import sys
import time
import traceback
from pathlib import Path

from . import brand, names, playlist, projects, settings
from .suno import SunoClient, SunoError, download


class Cancelled(Exception):
    pass


def _existing_titles(tracks_dir: Path) -> set[str]:
    return {re.sub(r"^\d+\s*[-_.]\s*", "", f.stem).strip().lower() for f in projects.audio_files(tracks_dir)}


def generate_music(pdir: Path, spec: dict, token: str, note, task_started, request_done, check_cancel, offset: int = 0) -> None:
    """Make `spec['n_req']` Suno requests (2 tracks each) into <pdir>/tracks. The callbacks report progress."""
    tracks_dir = pdir / "tracks"
    tracks_dir.mkdir(parents=True, exist_ok=True)
    client = SunoClient(token, mock=spec["mock"], mock_dir=pdir)
    n = spec["n_req"]
    for i in range(n):
        check_cancel()
        scene = spec["scenes"][(i + offset) % len(spec["scenes"])] if spec["scenes"] else "soft grind"
        label = f"request {i + 1}/{n}: {scene}"
        note(label)
        tid = client.generate(f"{spec['style']}, {scene}", scene, spec["model"], int(spec["minutes"] * 60), brand.NEGATIVE_TAGS)
        task_started(tid)                                              # saved at once, so a crash never loses paid work

        def tick(sec, label=label):
            check_cancel()
            note(f"{label} … {int(sec)}s")

        for c in client.wait(tid, on_tick=tick):
            taken = _existing_titles(tracks_dir)
            k = len(projects.audio_files(tracks_dir)) + 1
            title = names.suggest([scene], 1, taken, spec.get("mood_key", "calm"), style=spec.get("name_style", "mix"))[0]
            ext = ".wav" if c["audio_url"].endswith(".wav") else ".mp3"
            download(c["audio_url"], tracks_dir / f"{k:02d} - {playlist.safe_name(title)}{ext}")
            note(label)
        request_done(i + 1)


def run(job_path: str) -> None:
    jp = Path(job_path)
    pdir = jp.parent
    job = projects.read_json(jp)
    spec = job["spec"]

    def save(**kw):
        job.update(kw)
        job["updated"] = time.time()
        projects.write_json(jp, job)

    def check_cancel():
        if (pdir / projects.CANCEL).exists():
            raise Cancelled()

    token = os.getenv("SOFTGRIND_SUNO_TOKEN") or settings.load_keys().get("suno", "")
    n = spec["n_req"]
    save(state="running", pid=os.getpid(), done_requests=0, total_requests=n, message="starting", error="")
    try:
        generate_music(pdir, spec, token, note=lambda m: save(message=m),
                       task_started=lambda t: save(task_ids=job.get("task_ids", []) + [t]),
                       request_done=lambda d: save(done_requests=d), check_cancel=check_cancel)
        save(state="done", message="done", finished=time.time())
    except Cancelled:
        save(state="cancelled", message="cancelled")
    except SunoError as e:
        save(state="failed", message="failed", error=str(e))
    except Exception as e:                                           # never die silently: the app shows this
        traceback.print_exc()
        save(state="failed", message="failed", error=f"{e.__class__.__name__}: {e}")


if __name__ == "__main__":
    run(sys.argv[1])
