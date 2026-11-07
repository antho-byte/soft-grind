"""Projects on disk: metadata, background music jobs, and the overview data (cover, stage, progress)."""
from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import time
from functools import lru_cache
from pathlib import Path

from . import brand, headlines, playlist

META, JOB, CANCEL = "project.json", "job.json", "cancel"
STALE_AFTER = 120  # seconds without a heartbeat -> the job counts as interrupted


TRASH = ".trash"


def project_dirs(root: Path) -> list[Path]:
    """Project folders only: hidden ones (like the trash) never count as projects."""
    root = Path(root)
    return sorted(d for d in root.iterdir() if d.is_dir() and not d.name.startswith(".")) if root.is_dir() else []


def read_json(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_json(path: Path, data: dict) -> None:
    """Atomic write, so the app never reads a half-written file while a worker updates it.
    On Windows, replacing a file that another process has open fails with 'Access is denied'; that is retried for a moment."""
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    for attempt in range(40):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(min(0.25, 0.02 * (attempt + 1)))
    try:                                                  # last resort: overwrite in place (a reader may see it half-written once)
        path.write_text(text, encoding="utf-8")
    finally:
        tmp.unlink(missing_ok=True)


def meta(pdir: Path) -> dict:
    return read_json(Path(pdir) / META)


@contextlib.contextmanager
def _locked(path: Path, timeout: float = 5.0):
    """A tiny cross-platform lock file, so the app and a background job cannot overwrite each other's fields."""
    lock = Path(str(path) + ".lock")
    t0, held = time.time(), False
    while True:
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            held = True
            break
        except (FileExistsError, PermissionError):
            try:
                if time.time() - lock.stat().st_mtime > 10:          # left behind by a crash
                    lock.unlink(missing_ok=True)
                    continue
            except OSError:
                pass
            if time.time() - t0 > timeout:                            # never hang: carry on without the lock
                break
            time.sleep(0.02)
    try:
        yield
    finally:
        if held:
            lock.unlink(missing_ok=True)


def set_meta(pdir: Path, **kw) -> dict:
    pdir = Path(pdir)
    pdir.mkdir(parents=True, exist_ok=True)
    with _locked(pdir / META):
        m = meta(pdir)
        m.update(kw)
        write_json(pdir / META, m)
    return m


def next_project_name(root: Path, prefix: str = "mix") -> str:
    nums = []
    for p in Path(root).glob(f"{prefix}-*"):
        tail = p.name[len(prefix) + 1:]
        if tail.isdigit() and p.is_dir() and any(f.is_file() for f in p.rglob("*")):   # empty folders do not count
            nums.append(int(tail))
    return f"{prefix}-{max(nums, default=0) + 1:03d}"


def create_project(root: Path) -> str:
    """Next free name, a unique playlist name and a scenario. Returns the project name."""
    import random
    from . import names
    nm = next_project_name(root)
    pd = Path(root) / nm
    pd.mkdir(parents=True, exist_ok=True)
    taken = [m for m in (meta(d).get("playlist_name") for d in project_dirs(root)) if m]
    used_quotes = recent_quotes(root, n=headlines.RECENT)
    set_meta(pd, created=time.time(), scenario=random.choice(brand.SCENARIOS),
             playlist_name=names.suggest([random.choice(brand.SCENES)], 1, taken, "calm")[0],
             quote=headlines.suggest("calm", [], used_quotes, 1)[0], quote_placeholder=True)   # replaced once an image is chosen
    return nm


def recent_quotes(root: Path, exclude: str = "", n: int = 30) -> set[str]:
    """Headlines of the n most recent videos (a headline may be reused after that many). `exclude` = a project to leave out."""
    rows = []
    for d in project_dirs(root):
        if d.name != exclude:
            m = meta(d)
            if m.get("quote"):
                rows.append((m.get("created", 0), m["quote"]))
    return {q for _, q in sorted(rows, reverse=True)[:n]}


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
    if info.get("auto", {}).get("running"):
        return "making it"
    if info.get("auto", {}).get("state") == "needs_attention":
        return "needs attention"
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
    spent: dict[str, float] = {}
    for row in credits_rows():
        spent[row.get("project", "")] = spent.get(row.get("project", ""), 0.0) + row["credits"]
    for p in project_dirs(root):
        if not any(f.is_file() for f in p.rglob("*")):        # empty folders (the app creates one per typed name) are not videos
            continue
        n, secs = track_stats(p)
        m = meta(p)
        if not n and m.get("freed_tracks"):                   # songs were cleaned up after the video was made
            n, secs = m["freed_tracks"], m.get("freed_seconds", 0)
        info = {"name": p.name, "path": p, "tracks": n, "seconds": secs, "cover": cover_path(p),
                "quote": m.get("quote", ""), "playlist_name": m.get("playlist_name", ""),
                "has_thumbnail": (p / "thumbnail.png").exists(), "has_upload": bool(m.get("title")) and (p / "upload.txt").exists(),
                "has_video": (p / "video.mp4").exists(), "title": m.get("title", ""), "schedule": m.get("schedule", ""),
                "render": render_status(p), "auto": auto_status(p), "credits": round(spent.get(p.name, 0.0), 2),
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
    _spawn("soft_grind.worker", pdir, JOB, {"SOFTGRIND_SUNO_TOKEN": token})


def _spawn(module: str, workdir: Path, jobfile: str, env_extra: dict | None = None) -> None:
    """Start `python -m <module> <workdir>/<jobfile>` as its own process that outlives page reloads."""
    env = dict(os.environ)
    env.update({k: v for k, v in (env_extra or {}).items() if v})
    kw = {}
    if sys.platform == "win32":
        kw["creationflags"] = 0x00000008 | 0x00000200      # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    Path(workdir).mkdir(parents=True, exist_ok=True)
    with open(Path(workdir) / f"{jobfile.split('.')[0]}.log", "ab") as log:
        subprocess.Popen([sys.executable, "-m", module, str(Path(workdir) / jobfile)], cwd=str(brand.ROOT), env=env,
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


YT = "youtube.json"


def youtube_status(pdir: Path) -> dict:
    j = read_json(Path(pdir) / YT)
    state = j.get("state", "none") if j else "none"
    fresh = time.time() - (j or {}).get("updated", 0) < STALE_AFTER
    if state in ("queued", "running") and not fresh:
        state = "interrupted"
    return {"state": state, "running": state in ("queued", "running"), "progress": float((j or {}).get("progress", 0.0)),
            "message": (j or {}).get("message", ""), "error": (j or {}).get("error", ""), "note": (j or {}).get("note", "")}


def start_youtube(pdir: Path, again: bool = False) -> None:
    """Upload video.mp4 with its title, description, tags, thumbnail and schedule. Refuses a second upload unless `again`."""
    pdir = Path(pdir)
    if youtube_status(pdir)["running"]:
        raise RuntimeError("This video is already being uploaded.")
    m = meta(pdir)
    if m.get("youtube_id") and not again:
        raise RuntimeError("This video is already on YouTube.")
    if not (pdir / "video.mp4").exists():
        raise RuntimeError("Make the video first.")
    if not m.get("title"):
        raise RuntimeError("Write the YouTube text first (video tab).")
    write_json(pdir / YT, {"state": "queued", "progress": 0.0, "message": "queued", "updated": time.time()})
    _spawn("soft_grind.youtube_worker", pdir, YT)


AUTO = "auto.json"
AUTO_STEPS = ["making the music", "choosing the image", "writing the headline", "making the thumbnail", "building the video",
              "writing the youtube text"]


def auto_status(pdir: Path) -> dict:
    j = read_json(Path(pdir) / AUTO)
    if not j:
        return {"state": "none", "running": False, "progress": 0.0, "message": "", "error": "", "step": -1, "step_name": ""}
    fresh = time.time() - j.get("updated", 0) < STALE_AFTER
    state = j.get("state", "none")
    if state in ("queued", "running") and not fresh:
        state = "interrupted"
    step = j.get("step", 0)
    return {"state": state, "running": state in ("queued", "running"), "progress": float(j.get("progress", 0.0)),
            "message": j.get("message", ""), "error": j.get("error", ""), "step": step,
            "step_name": AUTO_STEPS[step] if 0 <= step < len(AUTO_STEPS) else ""}


def start_auto(pdir: Path, spec: dict, suno_token: str = "", ai_token: str = "") -> None:
    """Make a whole video in the background: music, image, headline, thumbnail, video, text. Safe to start again to resume."""
    pdir = Path(pdir); pdir.mkdir(parents=True, exist_ok=True)
    if auto_status(pdir)["running"]:
        raise RuntimeError("This video is already being made.")
    if meta(pdir).get("freed_tracks"):
        raise RuntimeError("The songs of this video were deleted to free up space: starting again would buy new music. Make a new video instead.")
    (pdir / CANCEL).unlink(missing_ok=True)
    prev = read_json(pdir / AUTO)                                     # keep the list of paid requests across a resume
    write_json(pdir / AUTO, {"state": "queued", "spec": spec, "step": 0, "progress": 0.0, "message": "queued", "updated": time.time(),
                             "task_ids": prev.get("task_ids", [])})
    _spawn("soft_grind.auto", pdir, AUTO, {"SOFTGRIND_SUNO_TOKEN": suno_token, "SOFTGRIND_AI_TOKEN": ai_token})


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


# ---------- trash: delete is a move, so a mistake can be undone ----------
def is_busy(pdir: Path) -> bool:
    return (job_status(pdir)["running"] or render_status(pdir)["running"] or auto_status(pdir)["running"]
            or youtube_status(pdir)["running"])


def free_space(pdir: Path) -> float:
    """Delete the songs and working images of a FINISHED video (the video, thumbnail and upload text stay). Returns MB freed."""
    import shutil
    pdir = Path(pdir)
    if is_busy(pdir):
        raise RuntimeError(f"{pdir.name} is still being made.")
    if not (pdir / "video.mp4").exists():
        raise RuntimeError("Only finished videos can be cleaned up: make the video first, so nothing is lost.")
    n, secs = track_stats(pdir)
    freed = 0
    for sub in ("tracks", "images"):
        d = pdir / sub
        if d.is_dir():
            freed += sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
            shutil.rmtree(d, ignore_errors=True)
    left = sum(f.stat().st_size for sub in ("tracks", "images") if (pdir / sub).is_dir() for f in (pdir / sub).rglob("*") if f.is_file())
    if left:
        raise RuntimeError("Some files are still in use (a player or File Explorer window?). Close it and try again.")
    if n:
        set_meta(pdir, freed_tracks=n, freed_seconds=secs)
    return round(freed / 1e6, 1)


def trash_project(pdir: Path) -> Path:
    """Move a project into <projects>/.trash. Refuses while something is still being made for it."""
    import shutil
    pdir = Path(pdir)
    if is_busy(pdir):
        raise RuntimeError(f"{pdir.name} is still being made. Cancel it first, then delete it.")
    dest = pdir.parent / TRASH / f"{pdir.name}__{time.strftime('%Y%m%d-%H%M%S')}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(pdir), str(dest))
    except PermissionError:
        raise RuntimeError("Windows says the files are in use. Close any video player or File Explorer window showing this "
                           "project, then try again.")
    return dest


def list_trash(root: Path) -> list[dict]:
    t = Path(root) / TRASH
    out = []
    for d in (sorted(x for x in t.iterdir() if x.is_dir()) if t.is_dir() else []):
        name, _, stamp = d.name.rpartition("__")
        n, _ = track_stats(d)
        out.append({"folder": d, "name": name or d.name, "deleted": stamp, "tracks": n, "quote": meta(d).get("quote", ""),
                    "size_mb": sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) / 1e6})
    return sorted(out, key=lambda r: r["deleted"], reverse=True)


def restore_project(folder: Path, root: Path) -> str:
    """Put a trashed project back under its old name (or the next free name if that name is taken again)."""
    import shutil
    folder, root = Path(folder), Path(root)
    name = folder.name.rpartition("__")[0] or folder.name
    if (root / name).exists() and any(f.is_file() for f in (root / name).rglob("*")):
        name = next_project_name(root)
    elif (root / name).exists():
        shutil.rmtree(root / name)                           # an empty leftover folder
    shutil.move(str(folder), str(root / name))
    return name


def delete_forever(folder: Path) -> None:
    import shutil
    shutil.rmtree(folder)


# ---------- credits ledger: one file, so the total is easy to read ----------
def _ledger_path() -> Path:
    from . import settings as _s
    return _s.DATA_DIR / "credits.json"


def add_cost(project: str, kind: str, credits: float, estimated: bool = True) -> None:
    """Remember what something cost. Never raises: bookkeeping must not stop a video."""
    if not credits:
        return
    try:
        path = _ledger_path()
        with _locked(path):
            data = read_json(path)
            if not data and path.exists() and path.stat().st_size > 2:
                return                                              # unreadable right now: never overwrite the history
            rows = data.get("rows", [])
            rows.append({"at": time.time(), "project": project, "kind": kind, "credits": round(float(credits), 4), "estimated": bool(estimated)})
            write_json(path, {"rows": rows[-5000:]})
    except Exception:
        pass


def credits_rows() -> list[dict]:
    return read_json(_ledger_path()).get("rows", [])


def credits_for(project: str) -> float:
    return round(sum(r["credits"] for r in credits_rows() if r.get("project") == project), 2)


def credits_this_month(now=None) -> float:
    t = time.localtime(now or time.time())
    return round(sum(r["credits"] for r in credits_rows()
                     if time.localtime(r["at"]).tm_year == t.tm_year and time.localtime(r["at"]).tm_mon == t.tm_mon), 2)
