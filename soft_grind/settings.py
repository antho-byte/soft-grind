"""Where YOUR stuff lives: keys + projects sit outside the app folder, so updating the app never touches them.

Default: <your user folder>/soft-grind-data   (override with the SOFTGRIND_HOME environment variable)
"""
import json
import os
import shutil
from pathlib import Path

DATA_DIR = Path(os.getenv("SOFTGRIND_HOME") or Path.home() / "soft-grind-data")
KEYS_FILE = DATA_DIR / "keys.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
DEFAULT_PROJECTS = DATA_DIR / "projects"


def projects_dir() -> Path:
    """Where projects are saved: the folder chosen in the app, else <data folder>/projects."""
    try:
        chosen = json.loads(SETTINGS_FILE.read_text(encoding="utf-8")).get("projects_dir")
    except (OSError, ValueError):
        chosen = None
    return Path(chosen) if chosen else DEFAULT_PROJECTS


def save_projects_dir(text: str) -> Path:
    """Remember a new projects folder. If it is the app's own folder (it holds app.py), use its 'projects'
    subfolder, so music never mixes with program files."""
    p = Path(text.strip().strip('"').strip("'")).expanduser()
    if (p / "app.py").exists():
        p = p / "projects"
    p.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps({"projects_dir": str(p)}, indent=2), encoding="utf-8")
    return p


def _has_files(p: Path) -> bool:
    return any(f.is_file() for f in p.rglob("*"))


def move_projects(src: Path, dst: Path) -> tuple[list[str], list[str]]:
    """Move every project folder from src into dst. Never overwrites: a project that already has files in dst
    is skipped. An empty leftover folder in dst (the app creates one on start) is replaced. Returns (moved, skipped)."""
    src, dst = Path(src), Path(dst)
    moved, skipped = [], []
    if not src.is_dir() or src.resolve() == dst.resolve():
        return moved, skipped
    if dst.resolve().is_relative_to(src.resolve()):          # moving a folder into itself
        return moved, ["(the new folder is inside the old one)"]
    dst.mkdir(parents=True, exist_ok=True)
    for proj in sorted(p for p in src.iterdir() if p.is_dir()):
        target = dst / proj.name
        if target.exists():
            if _has_files(target):
                skipped.append(proj.name)
                continue
            shutil.rmtree(target)                             # only ever an empty tree
        shutil.move(str(proj), str(target))
        moved.append(proj.name)
    return moved, skipped


def load_keys() -> dict:
    try:
        return json.loads(KEYS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_keys(suno: str, image: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    KEYS_FILE.write_text(json.dumps({"suno": suno.strip(), "image": image.strip()}, indent=2), encoding="utf-8")
    try:
        KEYS_FILE.chmod(0o600)  # owner-only on Mac/Linux; ignored on Windows
    except OSError:
        pass
