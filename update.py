"""Self-updater: run by the start file before the app opens. Standard library only.

Downloads the newest code from GitHub when it changed and copies ONLY code files over this folder.
Your keys, projects and the helper files live outside this folder, so nothing of yours is touched.
If anything goes wrong (offline, GitHub down) it says so and the current version simply starts.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

REPO = os.getenv("SOFTGRIND_REPO", "antho-byte/soft-grind")
BRANCH = os.getenv("SOFTGRIND_BRANCH", "main")
API = os.getenv("SOFTGRIND_UPDATE_API", "https://api.github.com").rstrip("/")
DL = os.getenv("SOFTGRIND_UPDATE_DL", "https://github.com").rstrip("/")
HERE = Path(__file__).resolve().parent
VERSION_FILE = HERE / ".version"
BAD_FILE = HERE / ".bad_version"                                    # a version that failed its self-test: not tried again
HOME = Path(os.getenv("SOFTGRIND_HOME") or Path.home() / "soft-grind-data")
PREVIOUS = HOME / "previous-version"                                # the version you had before the last update
CODE = ["app.py", "update.py", "requirements.txt", "README.md", "soft_grind", "fonts", "docs", "tests", ".streamlit"]  # start files stay


def _get(url: str, accept: str = "") -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "soft-grind-updater", **({"Accept": accept} if accept else {})})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def _copy_code(src: Path, dst: Path) -> None:
    """Copy the code entries (not your data) from one folder to another, replacing folders completely."""
    dst.mkdir(parents=True, exist_ok=True)
    for name in CODE:
        s, d = Path(src) / name, Path(dst) / name
        if not s.exists():
            continue
        if s.is_dir():
            shutil.rmtree(d, ignore_errors=True)
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)


SMOKE = """
import os, sys, tempfile
os.environ["SOFTGRIND_HOME"] = tempfile.mkdtemp()
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("app.py", default_timeout=90).run()
if at.exception:
    print("app error:", at.exception[0].value)
    sys.exit(1)
"""


def smoke_test(app_dir: Path = HERE) -> tuple[bool, str]:
    """Install what the new version needs, then start the app once in a scratch data folder. (ok, why not)."""
    if not os.getenv("SOFTGRIND_SKIP_PIP"):
        try:
            r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(Path(app_dir) / "requirements.txt")],
                               capture_output=True, text=True, timeout=900)
        except (OSError, subprocess.TimeoutExpired):
            return True, "could not check (pip unavailable): continuing"
        if r.returncode != 0:                                       # most likely no internet: cannot judge the new version
            return True, "could not check (no internet for pip): continuing"
    try:
        r = subprocess.run([sys.executable, "-c", SMOKE], cwd=str(app_dir), capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return False, "the check took too long"
    if r.returncode != 0:
        tail = [l for l in (r.stdout + r.stderr).strip().splitlines() if l.strip()][-1:] or ["unknown error"]
        return False, tail[0][:200]
    return True, ""


def update() -> str:
    try:
        latest = _get(f"{API}/repos/{REPO}/commits/{BRANCH}", "application/vnd.github.sha").decode().strip()
    except Exception as e:
        return f"update check skipped ({e.__class__.__name__}): starting the version you have."
    current = VERSION_FILE.read_text().strip() if VERSION_FILE.exists() else ""
    if latest == current and all((HERE / n).exists() for n in CODE):
        return "already up to date."
    if BAD_FILE.exists() and BAD_FILE.read_text().strip() == latest:
        return "a newer version is waiting, but it failed its self-test earlier: staying on the version you have."
    copying = False
    try:
        data = _get(f"{DL}/{REPO}/archive/refs/heads/{BRANCH}.zip")
        with tempfile.TemporaryDirectory() as tmp:
            zipfile.ZipFile(io.BytesIO(data)).extractall(tmp)
            roots = [p for p in Path(tmp).iterdir() if p.is_dir()]
            if len(roots) != 1 or not (roots[0] / "app.py").exists():
                return "update download looked wrong: starting the version you have."
            src = roots[0]
            if (HERE / "app.py").exists():                          # keep the working version, in case the new one is broken
                shutil.rmtree(PREVIOUS, ignore_errors=True)
                _copy_code(HERE, PREVIOUS)
            copying = True
            _copy_code(src, HERE)
        ok, why = smoke_test()
        if not ok and PREVIOUS.exists():
            _copy_code(PREVIOUS, HERE)
            BAD_FILE.write_text(latest)
            return f"the new version ({latest[:7]}) failed its self-test ({why}): went back to the version you had."
        VERSION_FILE.write_text(latest)
        return f"updated to {latest[:7]}."
    except Exception as e:
        if copying and PREVIOUS.exists():                           # never leave a half-updated folder behind
            _copy_code(PREVIOUS, HERE)
        return f"update failed ({e.__class__.__name__}: {e}): starting the version you have."


def apply_server_config(app_dir: Path = HERE) -> str:
    """Streamlit listens only on this computer unless remote access AND a password are both set. Runs before Streamlit starts."""
    home = Path(os.getenv("SOFTGRIND_HOME") or Path.home() / "soft-grind-data")
    try:
        cfg = json.loads((home / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cfg = {}
    remote = bool(cfg.get("remote_access")) and bool(cfg.get("app_password"))
    address = "0.0.0.0" if remote else "127.0.0.1"
    cfg_file = Path(app_dir) / ".streamlit" / "config.toml"
    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    text = cfg_file.read_text(encoding="utf-8") if cfg_file.exists() else ""
    kept, skip = [], False
    for line in text.splitlines():                           # drop an earlier [server] section, keep the rest (theme, browser)
        if line.strip().startswith("["):
            skip = line.strip() == "[server]"
        if not skip:
            kept.append(line)
    cfg_file.write_text("\n".join(kept).rstrip() + f'\n\n[server]\naddress = "{address}"\n', encoding="utf-8")
    return address


if __name__ == "__main__":
    print("soft grind. update:", update())
    addr = apply_server_config()
    print("soft grind. listening on:", addr, "(this computer only)" if addr == "127.0.0.1" else "(other devices allowed, password required)")
    sys.exit(0)
