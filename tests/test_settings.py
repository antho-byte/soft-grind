import importlib, os, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def test_keys_live_outside_app_folder():
    os.environ["SOFTGRIND_HOME"] = tempfile.mkdtemp()
    from soft_grind import settings; importlib.reload(settings)
    assert settings.load_keys() == {}
    settings.save_keys(" abc ", "def")
    assert settings.load_keys() == {"suno": "abc", "image": "def", "ai": "", "ai_model": ""}
    settings.save_keys("a", "b", " c ", " claude-haiku-x ")
    assert settings.load_keys()["ai"] == "c" and settings.load_keys()["ai_model"] == "claude-haiku-x"
    assert settings.KEYS_FILE.is_relative_to(os.environ["SOFTGRIND_HOME"])
    assert not str(settings.KEYS_FILE).startswith(str(Path(__file__).resolve().parent.parent))


def test_projects_folder_and_move():
    import tempfile
    os.environ["SOFTGRIND_HOME"] = tempfile.mkdtemp()
    from soft_grind import settings; importlib.reload(settings)
    assert settings.projects_dir() == settings.DEFAULT_PROJECTS                      # default
    app = Path(tempfile.mkdtemp()) / "soft-grind"; app.mkdir(); (app / "app.py").write_text("x")
    new = settings.save_projects_dir(f'"{app}"')                                     # the app folder itself -> its projects/ subfolder
    assert new == app / "projects" and settings.projects_dir() == new
    old = settings.DEFAULT_PROJECTS
    (old / "mix-001" / "tracks").mkdir(parents=True); (old / "mix-001" / "tracks" / "01.mp3").write_bytes(b"a")
    (old / "mix-002").mkdir(); (old / "mix-002" / "thumbnail.png").write_bytes(b"b")
    (new / "mix-001" / "tracks").mkdir(parents=True)                                 # empty leftover the app made on start
    (new / "mix-002").mkdir(); (new / "mix-002" / "other.txt").write_text("keep")    # a real file already there
    moved, skipped = settings.move_projects(old, new)
    assert moved == ["mix-001"] and skipped == ["mix-002"]
    assert (new / "mix-001" / "tracks" / "01.mp3").read_bytes() == b"a" and not (old / "mix-001").exists()
    assert (new / "mix-002" / "other.txt").read_text() == "keep" and (old / "mix-002" / "thumbnail.png").exists()  # nothing lost
    assert settings.move_projects(old, old) == ([], [])
    assert settings.move_projects(old, old / "inner")[1]                              # refuses to move into itself
