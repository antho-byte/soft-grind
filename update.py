"""Self-updater: run by the start file before the app opens. Standard library only.

Downloads the newest code from GitHub when it changed and copies ONLY code files over this folder.
Your keys, projects and the helper files live outside this folder, so nothing of yours is touched.
If anything goes wrong (offline, GitHub down) it says so and the current version simply starts.
"""
import io
import os
import shutil
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
CODE = ["app.py", "update.py", "requirements.txt", "README.md", "soft_grind", "fonts", "tests"]  # start files stay


def _get(url: str, accept: str = "") -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "soft-grind-updater", **({"Accept": accept} if accept else {})})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def update() -> str:
    try:
        latest = _get(f"{API}/repos/{REPO}/commits/{BRANCH}", "application/vnd.github.sha").decode().strip()
    except Exception as e:
        return f"update check skipped ({e.__class__.__name__}): starting the version you have."
    current = VERSION_FILE.read_text().strip() if VERSION_FILE.exists() else ""
    if latest == current:
        return "already up to date."
    try:
        data = _get(f"{DL}/{REPO}/archive/refs/heads/{BRANCH}.zip")
        with tempfile.TemporaryDirectory() as tmp:
            zipfile.ZipFile(io.BytesIO(data)).extractall(tmp)
            roots = [p for p in Path(tmp).iterdir() if p.is_dir()]
            if len(roots) != 1 or not (roots[0] / "app.py").exists():
                return "update download looked wrong: starting the version you have."
            src = roots[0]
            for name in CODE:
                s, d = src / name, HERE / name
                if not s.exists():
                    continue
                if s.is_dir():
                    shutil.rmtree(d, ignore_errors=True)
                    shutil.copytree(s, d)
                else:
                    shutil.copy2(s, d)
        VERSION_FILE.write_text(latest)
        return f"updated to {latest[:7]}."
    except Exception as e:
        return f"update failed ({e.__class__.__name__}: {e}): starting the version you have."


if __name__ == "__main__":
    print("soft grind. update:", update())
    sys.exit(0)
