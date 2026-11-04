"""Where YOUR stuff lives: keys + projects sit outside the app folder, so updating the app never touches them.

Default: <your user folder>/soft-grind-data   (override with the SOFTGRIND_HOME environment variable)
"""
import json
import os
from pathlib import Path

DATA_DIR = Path(os.getenv("SOFTGRIND_HOME") or Path.home() / "soft-grind-data")
PROJECTS_DIR = DATA_DIR / "projects"
KEYS_FILE = DATA_DIR / "keys.json"


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
