"""Phone messages, the credits ledger and plain-language errors."""
import importlib, os, sys, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["NO_PROXY"] = "127.0.0.1"; os.environ["no_proxy"] = "127.0.0.1"
from soft_grind import errors


def fresh():
    os.environ["SOFTGRIND_HOME"] = tempfile.mkdtemp()
    from soft_grind import settings, security, library, projects, notify
    for m in (settings, security, library, projects, notify):
        importlib.reload(m)
    return settings, projects, notify


SEEN = []
class Ntfy(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("content-length", 0))).decode("utf-8")
        SEEN.append({"path": self.path, "title": self.headers.get("Title"), "priority": self.headers.get("Priority"),
                     "tags": self.headers.get("Tags"), "body": body})
        self.send_response(200); self.end_headers(); self.wfile.write(b"{}")

def ntfy_server():
    s = HTTPServer(("127.0.0.1", 0), Ntfy); threading.Thread(target=s.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{s.server_port}"


def test_phone_messages_go_to_a_secret_topic_and_never_raise():
    settings, projects, notify = fresh(); SEEN.clear()
    os.environ["SOFTGRIND_NTFY_SERVER"] = ntfy_server()
    try:
        assert not notify.enabled() and notify.send("x", "y") is False and not SEEN          # off by default: nothing is sent
        t = notify.enable(); assert t.startswith("softgrind-") and len(t) >= 24 and notify.enable() == t   # long random name, stable
        assert notify.send("mix-001 is ready – done", "\"focus.\": check it", priority="high", tags="white_check_mark") is True
        m = SEEN[-1]; assert m["path"] == f"/{t}" and m["priority"] == "high" and m["tags"] == "white_check_mark"
        assert m["title"].isascii() and "mix-001 is ready" in m["title"] and "focus." in m["body"]       # header stays plain ascii, body keeps its text
        notify.disable(); n = len(SEEN); assert notify.send("a", "b") is False and len(SEEN) == n
        notify.enable(); os.environ["SOFTGRIND_NTFY_SERVER"] = "http://127.0.0.1:9"
        assert notify.send("a", "b") is False                                                           # unreachable server: no crash
    finally:
        os.environ.pop("SOFTGRIND_NTFY_SERVER", None)


def test_the_whole_video_job_messages_the_phone_and_records_what_it_cost():
    settings, projects, notify = fresh(); SEEN.clear()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import test_auto
    importlib.reload(test_auto)
    test_auto.os.environ["SOFTGRIND_HOME"] = os.environ["SOFTGRIND_HOME"]
    os.environ["SOFTGRIND_NTFY_SERVER"] = ntfy_server(); notify.enable()
    try:
        test_auto._library(settings, importlib.import_module("soft_grind.library"))
        root = settings.projects_dir(); nm = projects.create_project(root); pd = root / nm
        projects.start_auto(pd, dict(test_auto.SPEC))
        assert test_auto._wait(projects, pd, {"done", "failed", "needs_attention"}, 120)["state"] == "done"
        assert wait_for(lambda: any("is ready" in m["title"] for m in SEEN))
        m = [m for m in SEEN if "is ready" in m["title"]][0]; assert m["priority"] == "high" and nm in m["title"] and projects.meta(pd)["quote"] in m["body"]
        assert all(os.environ["SOFTGRIND_HOME"] not in m["body"] for m in SEEN)                         # no file paths in messages
        projects.set_meta(pd, quote="x")
    finally:
        os.environ.pop("SOFTGRIND_NTFY_SERVER", None)


def wait_for(cond, secs=15):
    t0 = time.time()
    while time.time() - t0 < secs:
        if cond(): return True
        time.sleep(0.2)
    return False


def test_credits_ledger_per_video_and_per_month():
    settings, projects, _ = fresh()
    projects.add_cost("mix-001", "music", 0.28); projects.add_cost("mix-001", "ai", 0.0123, False); projects.add_cost("mix-002", "image", 0.2)
    projects.add_cost("mix-002", "ai", 0)                                                              # nothing to record
    assert projects.credits_for("mix-001") == 0.29 and projects.credits_for("mix-002") == 0.2 and projects.credits_for("none") == 0
    assert projects.credits_this_month() == 0.49
    old = time.time() - 70 * 86400; rows = projects.credits_rows(); rows[0]["at"] = old
    projects.write_json(projects._ledger_path(), {"rows": rows})
    assert projects.credits_this_month() == 0.21                                                       # last quarter's cost is not this month's
    root = settings.projects_dir(); (root / "mix-002" / "tracks").mkdir(parents=True); (root / "mix-002" / "tracks" / "a.mp3").write_bytes(b"0")
    assert projects.list_projects(root)[0]["credits"] == 0.2


def test_ledger_survives_several_writers():
    import subprocess
    settings, projects, _ = fresh(); root = Path(__file__).resolve().parent.parent
    code = ("import sys; sys.path.insert(0, %r); from soft_grind import projects\n"
            "for i in range(25): projects.add_cost('p' + sys.argv[1], 'music', 0.01)" % str(root))
    procs = [subprocess.Popen([sys.executable, "-c", code, str(n)]) for n in range(4)]
    for p in procs: assert p.wait(timeout=60) == 0
    assert len(projects.credits_rows()) == 100                                                         # none lost


def test_plain_language_errors_keep_the_original_for_copying():
    cases = {"insufficient balance for this request": "out of credits", "401: invalid_token: The specified token is invalid": "did not accept this key",
             "token_mismatched: key not matched": "not allowed to use this service", "429: too_many_requests": "too many requests",
             "Could not reach the service. Check your internet": "internet connection failed", "[Errno 28] No space left on device": "disk is full",
             "PermissionError: [WinError 5] Access is denied": "would not allow access", "forbidden: blocked": "safety grounds", "weird new thing": "Something went wrong"}
    for raw, word in cases.items():
        e = errors.explain(raw); assert word in e["title"] and e["advice"] and e["raw"] == raw, raw
    assert errors.explain("")["title"]


def test_free_space(tmp_path, monkeypatch):
    from soft_grind import projects
    monkeypatch.setenv("SOFTGRIND_HOME", str(tmp_path / "home"))
    p = tmp_path / "mix-001"; (p / "tracks").mkdir(parents=True); (p / "images").mkdir()
    (p / "tracks" / "a.mp3").write_bytes(b"x" * 2000); (p / "images" / "i.png").write_bytes(b"y" * 1000)
    (p / "thumbnail.png").write_bytes(b"t")
    import pytest
    with pytest.raises(RuntimeError):                       # no video yet: nothing may be deleted
        projects.free_space(p)
    assert (p / "tracks" / "a.mp3").exists()
    (p / "video.mp4").write_bytes(b"v")
    assert projects.free_space(p) >= 0
    assert not (p / "tracks").exists() and not (p / "images").exists()
    assert (p / "video.mp4").exists() and (p / "thumbnail.png").exists()


def test_errors_ignore_numbers_in_paths():
    from soft_grind import errors
    assert errors.explain("FileNotFoundError: /p/mix-500/tracks")["title"] == "Something went wrong."
    assert "key" in errors.explain("HTTP 401 invalid_token")["title"]
    assert "too many" in errors.explain("error 429 too_many_requests")["title"]


def test_new_videos_get_a_fresh_mix_of_scenes(tmp_path, monkeypatch):
    """Each new video starts with different scene flavours: the ones recent videos used least."""
    from soft_grind import brand, projects
    monkeypatch.setenv("SOFTGRIND_HOME", str(tmp_path / "home"))
    root = tmp_path / "projects"; root.mkdir()
    topics = []
    for _ in range(4):
        nm = projects.create_project(root)
        projects.set_meta(root / nm, tracks_placeholder=True)
        t = projects.meta(root / nm)["topic"]
        assert len(t) == 5 and len(set(t)) == 5 and set(t) <= set(brand.SCENES)
        topics.append(t)
    assert not set(topics[1]) & set(topics[0])                       # 12 scenes: the second video avoids all five of the first
    assert len({tuple(sorted(t)) for t in topics}) == 4               # never the same mix twice in a row
