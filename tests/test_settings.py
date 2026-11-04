import importlib, os, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def test_keys_live_outside_app_folder():
    os.environ["SOFTGRIND_HOME"] = tempfile.mkdtemp()
    from soft_grind import settings; importlib.reload(settings)
    assert settings.load_keys() == {}
    settings.save_keys(" abc ", "def")
    assert settings.load_keys() == {"suno": "abc", "image": "def"}
    assert settings.KEYS_FILE.is_relative_to(os.environ["SOFTGRIND_HOME"])
    assert not str(settings.KEYS_FILE).startswith(str(Path(__file__).resolve().parent.parent))
