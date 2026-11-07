import importlib, os, subprocess, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

def _fresh():
    os.environ["SOFTGRIND_HOME"] = tempfile.mkdtemp()
    from soft_grind import settings, security
    importlib.reload(settings); importlib.reload(security)
    return settings, security

def test_password_hash_is_salted_and_checked():
    _, sec = _fresh()
    a, b = sec.hash_password("correct horse"), sec.hash_password("correct horse")
    assert a != b and "correct horse" not in a and sec.verify("correct horse", a) and not sec.verify("wrong", a) and not sec.verify("x", "garbage")

def test_settings_never_store_the_password_as_text_and_short_ones_are_refused():
    settings, sec = _fresh()
    try: sec.set_password("short"); assert False
    except ValueError: pass
    sec.set_password("a long password")
    raw = (settings.SETTINGS_FILE).read_text()
    assert "a long password" not in raw and sec.password_hash() in raw

def test_remote_access_needs_a_password():
    _, sec = _fresh()
    try: sec.set_remote(True); assert False
    except ValueError: pass
    assert not sec.remote_effective()
    sec.set_password("a long password"); sec.set_remote(True)
    assert sec.remote_wanted() and sec.remote_effective()
    sec.remove_password()                                                         # removing the password also closes remote access
    assert not sec.remote_wanted() and not sec.remote_effective()

def test_lockout_after_five_wrong_tries(monkeypatch):
    _, sec = _fresh(); monkeypatch.setattr(sec.time, "sleep", lambda s: None)
    sec.set_password("a long password")
    for i in range(5): assert sec.check_login("nope") == (False, "That is not the password.")
    ok, msg = sec.check_login("a long password")                                  # even the right one is refused while locked
    assert not ok and "Too many" in msg and sec.locked_for() > 0
    sec.projects.write_json(sec.STATE_FILE, {"until": time.time() - 1})           # the lock runs out
    assert sec.check_login("a long password") == (True, "")

def test_server_address_is_local_unless_remote_and_password_are_both_set():
    settings, sec = _fresh()
    app = Path(tempfile.mkdtemp()); (app / ".streamlit").mkdir()
    (app / ".streamlit" / "config.toml").write_text('[theme]\nbase = "light"\n\n[browser]\ngatherUsageStats = false\n')
    run = lambda: subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {str(ROOT)!r}); import update; print(update.apply_server_config({str(app)!r}))"],
                                 capture_output=True, text=True, env={**os.environ}).stdout.strip()
    assert run() == "127.0.0.1"                                                   # default: this computer only
    settings._write_settings(remote_access=True)
    assert run() == "127.0.0.1"                                                   # remote without a password stays closed
    sec.set_password("a long password"); sec.set_remote(True)
    assert run() == "0.0.0.0"
    text = (app / ".streamlit" / "config.toml").read_text()
    assert text.count("[server]") == 1 and 'base = "light"' in text and "gatherUsageStats" in text      # theme kept, no duplicate section
    assert run() == "0.0.0.0" and (app / ".streamlit" / "config.toml").read_text().count("[server]") == 1
    sec.remove_password(); assert run() == "127.0.0.1"
