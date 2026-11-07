"""Setup check and diagnostics: each check says ok / warn / fail in plain words. Nothing here costs more than a fraction of a cent."""
from __future__ import annotations

import platform
import re
import shutil
import sys
import time
import uuid
from pathlib import Path

import requests

from . import ai, library, net, projects, settings, video

BASE = "https://api.acedata.cloud"
NIL = "00000000-0000-0000-0000-000000000000"


def _res(name: str, status: str, detail: str) -> dict:
    return {"name": name, "status": status, "detail": detail}


def check_folder(label: str, path: Path | None, create: bool = True) -> dict:
    if not path:
        return _res(label, "warn", "not chosen yet")
    try:
        if create:
            Path(path).mkdir(parents=True, exist_ok=True)
        probe = Path(path) / f".write-test-{uuid.uuid4().hex[:6]}"
        probe.write_text("x"); probe.unlink()
    except OSError as e:
        return _res(label, "fail", f"cannot write to {path} ({e.__class__.__name__}). Pick another folder or check its permissions.")
    return _res(label, "ok", str(path))


def check_disk(path: Path, warn_gb: float = 10.0, fail_gb: float = 2.0) -> dict:
    try:
        free = shutil.disk_usage(path if Path(path).exists() else Path(path).anchor or ".").free / 1e9
    except OSError:
        return _res("disk space", "warn", "could not read the free space")
    if free < fail_gb:
        return _res("disk space", "fail", f"only {free:.1f} GB free: videos need about 0.5 GB each")
    if free < warn_gb:
        return _res("disk space", "warn", f"{free:.1f} GB free: room for about {int(free / 0.5)} more videos")
    return _res("disk space", "ok", f"{free:.0f} GB free: room for about {int(free / 0.5)} videos")


def check_ffmpeg() -> dict:
    try:
        exe = video.ffmpeg_exe()
        import subprocess
        out = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=20).stdout.splitlines()[0]
        return _res("video tool (ffmpeg)", "ok", out[:60])
    except Exception as e:
        return _res("video tool (ffmpeg)", "fail", f"not available ({e}). Restart the app so it can install it.")


def check_background_jobs() -> dict:
    """Start a tiny process with the same code that starts music and video jobs, and wait for its answer."""
    d = settings.DATA_DIR / "selftest"
    f = d / "selftest.json"
    f.unlink(missing_ok=True)
    try:
        projects._spawn("soft_grind.selftest", d, "selftest.json")
    except Exception as e:
        return _res("background jobs", "fail", f"could not start a background process ({e.__class__.__name__}: {e})")
    t0 = time.time()
    while time.time() - t0 < 20:
        if f.exists() and projects.read_json(f).get("state") == "done":
            return _res("background jobs", "ok", f"a background process started and answered in {time.time() - t0:.1f}s")
        time.sleep(0.2)
    return _res("background jobs", "fail", "a background process did not answer. Music and video jobs may not run on this computer.")


def check_internet(base: str = BASE) -> dict:
    try:
        r = net.request("GET", base, timeout=15, retries=1)
        return _res("internet", "ok", f"reached {base.split('//')[1]} (answer {r.status_code})")
    except requests.RequestException as e:
        return _res("internet", "fail", net.friendly(e))


def check_key(label: str, token: str, path: str, base: str = BASE, saved: bool = True) -> dict:
    """Is the key accepted by this service? Asks for a task that does not exist: free, and tells accepted from rejected keys."""
    if not token:
        return _res(label, "warn", "no key yet (mock mode is used instead)")
    try:
        r = net.request("POST", f"{base}{path}", json={"id": NIL, "action": "retrieve"}, timeout=20, retries=1,
                        headers={"authorization": f"Bearer {token}", "content-type": "application/json", "accept": "application/json"})
    except requests.RequestException as e:
        return _res(label, "fail", net.friendly(e))
    try:
        code = (r.json().get("error") or {}).get("code", "")
    except ValueError:
        code = ""
    if r.status_code == 401 or code in ("invalid_token", "no_token", "token_expired"):
        return _res(label, "fail", "the service rejected this key (wrong, expired or deleted). Create a new key and paste it again.")
    if code == "token_mismatched":
        return _res(label, "fail", "this key is not allowed to use this service. Use a key from the General application, or allow this API on the key.")
    if code == "disabled":
        return _res(label, "fail", "AceDataCloud has disabled this application. Contact their support.")
    if r.status_code == 429:
        return _res(label, "warn", "the key works, but the service says too many requests right now")
    return _res(label, "ok", "the key is accepted" + ("" if saved else " (not saved yet: press 'save keys on this computer')"))


def check_ai(token: str, model: str, base: str = "") -> dict:
    if not token:
        return _res("AI helper key", "warn", "no key yet (the AI buttons are off)")
    try:
        text, cost = ai.AIClient(token, model, base_url=base).chat("Reply with exactly one word.", "Say ok.", max_tokens=8, temperature=0)
    except ai.AIError as e:
        msg = str(e)
        if "model" in msg.lower():
            msg += f" Check the model name '{model}' on the Chat tab at platform.acedata.cloud/models."
        return _res("AI helper key", "fail", msg)
    return _res("AI helper key", "ok", f"answered '{text[:20]}' with model {model}" + (f" · {cost:.4f} credits" if cost else ""))


def check_library(folder: Path | None) -> dict:
    if not folder:
        return _res("image library", "warn", "no folder chosen yet (images page)")
    if not Path(folder).is_dir():
        return _res("image library", "fail", f"the folder {folder} does not exist")
    files = library.scan(folder)
    db = library.load_db()
    done = sum(1 for p in files if not library.needs_analysis(db, p))
    if not files:
        return _res("image library", "warn", f"no images in {folder}")
    return _res("image library", "ok" if done == len(files) else "warn", f"{len(files)} images, {done} looked at")


def run_all(suno_token: str, image_token: str, ai_token: str, ai_model: str, saved: dict | None = None) -> list[dict]:
    saved = saved or {}
    out = [check_folder("projects folder", settings.projects_dir()), check_disk(settings.projects_dir()),
           check_library(settings.library_dir()), check_ffmpeg(), check_background_jobs(), check_internet(),
           check_key("Suno key", suno_token, "/suno/tasks", saved=saved.get("suno", "") == suno_token),
           check_key("image key", image_token, "/nano-banana/tasks", saved=saved.get("image", "") == image_token),
           check_ai(ai_token, ai_model)]
    from . import security
    out.append(_res("who can open the app", "ok" if not security.remote_effective() else "warn",
                    "only this computer" if not security.remote_effective() else "other devices on your network, with a password"))
    return out


# ---------- diagnostics: everything I would ask you for, with the secrets removed ----------
def scrub(text: str, extra_secrets=()) -> str:
    for s in {*extra_secrets, *[v for v in settings.load_keys().values() if isinstance(v, str)]}:
        if s and len(s) >= 8:
            text = text.replace(s, "***")
    text = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{8,}", r"\1***", text)
    return re.sub(r"\b[0-9a-f]{32}\b", "***", text)


def tail(path: Path, n: int = 25) -> str:
    try:
        return "\n".join(Path(path).read_text(encoding="utf-8", errors="replace").splitlines()[-n:])
    except OSError:
        return ""


def diagnostics(extra_secrets=()) -> str:
    from importlib import metadata as im
    pkgs = []
    for p in ("streamlit", "pillow", "numpy", "requests", "mutagen", "imageio-ffmpeg"):
        try:
            pkgs.append(f"{p} {im.version(p)}")
        except im.PackageNotFoundError:
            pkgs.append(f"{p} (missing)")
    version = (Path(__file__).resolve().parent.parent / ".version")
    root = settings.projects_dir()
    keys = settings.load_keys()
    lines = ["soft grind. diagnostics", f"time: {time.strftime('%Y-%m-%d %H:%M:%S')}",
             f"app version: {version.read_text().strip()[:7] if version.exists() else 'unknown'}",
             f"python: {sys.version.split()[0]} on {platform.platform()}", "packages: " + ", ".join(pkgs),
             f"keys set: suno={bool(keys.get('suno'))} image={bool(keys.get('image'))} ai={bool(keys.get('ai'))} model={keys.get('ai_model', '')}",
             f"projects folder: {root}", f"library folder: {settings.library_dir()}", f"data folder: {settings.DATA_DIR}", ""]
    for r in (check_folder("projects folder", root, create=False), check_disk(root), check_ffmpeg()):
        lines.append(f"[{r['status']}] {r['name']}: {r['detail']}")
    lines.append("")
    recent = sorted(projects.project_dirs(root), key=lambda d: max([f.stat().st_mtime for f in d.glob("*") if f.is_file()] or [0]), reverse=True)[:4]
    for d in recent:
        lines.append(f"--- {d.name}")
        for label, st in (("auto", projects.auto_status(d)), ("music", projects.job_status(d)), ("video", projects.render_status(d))):
            if st["state"] != "none":
                lines.append(f"{label}: {st['state']} {st.get('message', '')} {st.get('error', '')}".strip())
        for logname in ("auto.log", "job.log", "render.log"):
            t = tail(d / logname)
            if t.strip():
                lines += [f"[{logname}]", t]
    lines.append("--- library job: " + str(library.library_job_status()))
    return scrub("\n".join(lines), extra_secrets)
