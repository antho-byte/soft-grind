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
APP_DIR = Path(__file__).resolve().parent.parent          # the folder with app.py (wherever it was moved to)


LIBRARY_FILE = DATA_DIR / "library.json"
LIBRARY_JOB = DATA_DIR / "library_job.json"
THUMBS_DIR = DATA_DIR / "library_thumbs"


def _read_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_settings(**kw) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cfg = _read_settings(); cfg.update(kw)
    SETTINGS_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    try:
        SETTINGS_FILE.chmod(0o600)          # holds the password hash and the phone-message topic
    except OSError:
        pass


def projects_dir() -> Path:
    """Where projects are saved: the folder chosen in the app, else <data folder>/projects.
    If the chosen folder is gone but the app folder (which moved, e.g. to the Desktop) has its own 'projects'
    folder with videos in it, that one is used and remembered: the videos moved along with the app."""
    chosen = _read_settings().get("projects_dir")
    if not chosen:
        return DEFAULT_PROJECTS
    p = Path(chosen)
    here = APP_DIR / "projects"
    if not p.exists() and p.name == "projects" and here.is_dir() and here != p and any(here.iterdir()):
        _write_settings(projects_dir=str(here), projects_moved_from=str(p))
        return here
    return p


def projects_moved_note() -> str:
    """Once, after the app found its projects in a new place: where they were before."""
    cfg = _read_settings()
    old = cfg.get("projects_moved_from", "")
    if old:
        _write_settings(projects_moved_from="")
    return old


def library_dir() -> Path | None:
    chosen = _read_settings().get("library_dir")
    return Path(chosen) if chosen else None


def save_library_dir(text: str) -> Path:
    p = Path(text.strip().strip('"').strip("'")).expanduser()
    _write_settings(library_dir=str(p))
    return p


def save_projects_dir(text: str) -> Path:
    """Remember a new projects folder. If it is the app's own folder (it holds app.py), use its 'projects'
    subfolder, so music never mixes with program files."""
    p = Path(text.strip().strip('"').strip("'")).expanduser()
    if (p / "app.py").exists():
        p = p / "projects"
    p.mkdir(parents=True, exist_ok=True)
    _write_settings(projects_dir=str(p))
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
    for proj in sorted(p for p in src.iterdir() if p.is_dir() and not p.name.startswith(".")):
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


def save_keys(suno: str, image: str, ai: str = "", ai_model: str = "", platform: str | None = None) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    keep = load_keys()
    data = {"suno": suno.strip(), "image": image.strip(), "ai": ai.strip(), "ai_model": ai_model.strip(),
            "platform": (platform if platform is not None else keep.get("platform", "")).strip()}
    KEYS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        KEYS_FILE.chmod(0o600)  # owner-only on Mac/Linux; ignored on Windows
    except OSError:
        pass


def ai_disclosure() -> bool:
    """Say in every new description that the music is made with AI tools (on unless the owner switched it off)."""
    return bool(_read_settings().get("ai_disclosure", True))


def set_ai_disclosure(on: bool) -> None:
    _write_settings(ai_disclosure=bool(on))
