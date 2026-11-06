"""Projects on disk: metadata, background music jobs, and the overview data (cover, stage, progress)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from functools import lru_cache
from pathlib import Path

from . import brand, playlist

META, JOB, CANCEL = "project.json", "job.json", "cancel"
STALE_AFTER = 120  # seconds without a heartbeat -> the job counts as interrupted


def read_json(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_json(path: Path, data: dict) -> None:
    """Atomic write, so the app never reads a half-written file while the worker updates it."""
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def meta(pdir: Path) -> dict:
    return read_json(Path(pdir) / META)


def set_meta(pdir: Path, **kw) -> dict:
    m = meta(pdir); m.update(kw); write_json(Path(pdir) / META, m); return m


def next_project_name(root: Path, prefix: str = "mix") -> str:
    nums = []
    for p in Path(root).glob(f"{prefix}-*"):
        tail = p.name[len(prefix) + 1:]
        if tail.isdigit() and p.is_dir() and any(f.is_file() for f in p.rglob("*")):   # empty folders do not count
            nums.append(int(tail))
    return f"{prefix}-{max(nums, default=0) + 1:03d}"


def audio_files(tracks_dir: Path) -> list[Path]:
    d = Path(tracks_dir)
    return sorted(p for p in d.iterdir() if p.suffix.lower() in playlist.AUDIO_EXT) if d.is_dir() else []


@lru_cache(maxsize=2048)
def _dur(path: str, mtime_ns: int) -> float:
    return playlist.audio_duration(path)


def track_stats(pdir: Path) -> tuple[int, float]:
    files = audio_files(Path(pdir) / "tracks")
    return len(files), sum(_dur(str(f), f.stat().st_mtime_ns) for f in files)


def cover_path(pdir: Path) -> Path | None:
    pdir = Path(pdir)
    for name in ("thumbnail.png", "still.png"):
        if (pdir / name).exists():
            return pdir / name
    imgs = sorted((pdir / "images").glob("*_16x9.png")) if (pdir / "images").is_dir() else []
    return imgs[0] if imgs else None


def job_status(pdir: Path) -> dict:
    j = read_json(Path(pdir) / JOB)
    if not j:
        return {"state": "none", "running": False, "progress": 0.0, "message": ""}
    fresh = time.time() - j.get("updated", 0) < STALE_AFTER
    running = j.get("state") in ("queued", "running") and fresh
    state = j.get("state", "none")
    if state in ("queued", "running") and not fresh:
        state = "interrupted"
    total = max(1, j.get("total_requests") or (j.get("spec") or {}).get("n_req", 1))
    return {"state": state, "running": running, "progress": min(1.0, j.get("done_requests", 0) / total),
            "message": j.get("message", ""), "error": j.get("error", ""), "done": j.get("done_requests", 0),
            "total": total, "task_ids": j.get("task_ids", [])}


def stage(info: dict) -> str:
    """Where a video is in the flow, in the app's own words."""
    if info["job"]["running"]:
        return "making music"
    if info.get("render", {}).get("running"):
        return "making the video"
    if info["tracks"] == 0:
        return "new"
    if not info["has_thumbnail"]:
        return "needs a thumbnail"
    if not info["has_video"]:
        return "needs the video"
    if not info["has_upload"]:
        return "needs youtube text"
    return "ready"


def list_projects(root: Path) -> list[dict]:
    root = Path(root)
    out = []
    for p in sorted(d for d in root.iterdir() if d.is_dir()) if root.is_dir() else []:
        if not any(f.is_file() for f in p.rglob("*")):        # empty folders (the app creates one per typed name) are not videos
            continue
        n, secs = track_stats(p)
        m = meta(p)
        info = {"name": p.name, "path": p, "tracks": n, "seconds": secs, "cover": cover_path(p),
                "quote": m.get("quote", ""), "playlist_name": m.get("playlist_name", ""),
                "has_thumbnail": (p / "thumbnail.png").exists(), "has_upload": bool(m.get("title")) and (p / "upload.txt").exists(),
                "has_video": (p / "video.mp4").exists(), "title": m.get("title", ""), "schedule": m.get("schedule", ""),
                "render": render_status(p),
                "job": job_status(p), "updated": max([f.stat().st_mtime for f in p.rglob("*") if f.is_file()] or [p.stat().st_mtime])}
        info["stage"] = stage(info)
        out.append(info)
    return sorted(out, key=lambda i: i["updated"], reverse=True)


def start_music_job(pdir: Path, spec: dict, token: str = "") -> None:
    """Write the job file and start the worker as its own process, so the app can be used while it runs."""
    pdir = Path(pdir); pdir.mkdir(parents=True, exist_ok=True)
    if job_status(pdir)["running"]:
        raise RuntimeError("A music job is already running for this project.")
    (pdir / CANCEL).unlink(missing_ok=True)
    write_json(pdir / JOB, {"state": "queued", "spec": spec, "task_ids": [], "done_requests": 0,
                            "total_requests": spec["n_req"], "message": "queued", "updated": time.time()})
    _spawn("soft_grind.worker", pdir, JOB, token)


def _spawn(module: str, pdir: Path, jobfile: str, token: str = "") -> None:
    """Start `python -m <module> <job file>` as its own process that outlives page reloads."""
    env = dict(os.environ)
    if token:
        env["SOFTGRIND_SUNO_TOKEN"] = token
    kw = {}
    if sys.platform == "win32":
        kw["creationflags"] = 0x00000008 | 0x00000200      # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    with open(pdir / f"{jobfile.split('.')[0]}.log", "ab") as log:
        subprocess.Popen([sys.executable, "-m", module, str(pdir / jobfile)], cwd=str(brand.ROOT), env=env,
                         stdout=log, stderr=log, stdin=subprocess.DEVNULL, close_fds=True, **kw)


RENDER = "render.json"


def render_status(pdir: Path) -> dict:
    j = read_json(Path(pdir) / RENDER)
    if not j:
        return {"state": "none", "running": False, "progress": 0.0, "message": "", "error": ""}
    fresh = time.time() - j.get("updated", 0) < STALE_AFTER
    state = j.get("state", "none")
    running = state in ("queued", "running") and fresh
    if state in ("queued", "running") and not fresh:
        state = "interrupted"
    return {"state": state, "running": running, "progress": float(j.get("progress", 0.0)),
            "message": j.get("message", ""), "error": j.get("error", "")}


def start_render(pdir: Path, crossfade: float = 4.0, fade_in: float = 3.0, fade_out: float = 6.0) -> None:
    pdir = Path(pdir)
    if render_status(pdir)["running"]:
        raise RuntimeError("The video is already being made.")
    write_json(pdir / RENDER, {"state": "queued", "progress": 0.0, "message": "queued", "updated": time.time(),
                               "spec": {"crossfade": crossfade, "fade_in": fade_in, "fade_out": fade_out}})
    _spawn("soft_grind.render", pdir, RENDER)


def next_free_slot(taken: set[str], now=None, hour: int = 15):
    """Next Monday / Wednesday / Friday at `hour`:00 (Amsterdam time as you read it) that no other video uses."""
    import datetime as dt
    now = now or dt.datetime.now()
    day = now.date()
    for _ in range(120):
        slot = dt.datetime.combine(day, dt.time(hour, 0))
        if day.weekday() in (0, 2, 4) and slot > now and slot.strftime("%Y-%m-%d %H:%M") not in taken:
            return slot
        day += dt.timedelta(days=1)
    return now


def cancel_job(pdir: Path) -> None:
    Path(pdir).mkdir(parents=True, exist_ok=True)
    (Path(pdir) / CANCEL).write_text("1")
