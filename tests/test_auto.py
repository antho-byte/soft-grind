"""The whole pipeline in mock mode: music -> image -> headline -> thumbnail -> video -> text, plus resume and cancel."""
import importlib, os, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import Image, ImageDraw

def _env():
    os.environ["SOFTGRIND_HOME"] = tempfile.mkdtemp()
    from soft_grind import settings, library, projects
    importlib.reload(settings); importlib.reload(library); importlib.reload(projects)
    return settings, library, projects

def _library(settings, library, n=6):
    d = Path(tempfile.mkdtemp())
    looks = [((15, 20, 70), (60, 40, 130)), ((94, 94, 224), (255, 140, 120)), ((150, 150, 155), (170, 170, 172)),
             ((20, 120, 90), (255, 194, 122)), ((30, 100, 200), (160, 210, 255)), ((255, 95, 158), (255, 194, 122))]
    for i in range(n):
        top, bot = looks[i % 6]; im = Image.new("RGB", (2000, 1125)); dr = ImageDraw.Draw(im)
        for y in range(1125):
            t = y / 1125; dr.line([(0, y), (2000, y)], fill=tuple(int(top[k] + (bot[k] - top[k]) * t) for k in range(3)))
        im.save(d / f"img{i}.jpg")
    settings.save_library_dir(str(d)); library.analyse_pending(library.scan(d), None)
    return d

SPEC = {"style": "instrumental lofi", "scenes": ["night shift", "neon city walk"], "n_req": 2, "minutes": 6, "model": "chirp-v5-5",
        "name_style": "mix", "mood_key": "calm", "mock": True, "crossfade": 2.0, "fade_in": 1, "fade_out": 2}

def _wait(projects, pdir, want, secs=90):
    t0 = time.time()
    while time.time() - t0 < secs:
        st = projects.auto_status(pdir)
        if st["state"] in want:
            return st
        time.sleep(0.4)
    raise AssertionError(f"auto did not reach {want}: {projects.auto_status(pdir)}")

def test_whole_video_and_second_video_differs():
    settings, library, projects = _env(); _library(settings, library)
    root = settings.projects_dir(); out = []
    for _ in range(2):
        nm = projects.create_project(root); pd = root / nm
        projects.set_meta(pd, topic=SPEC["scenes"], mood="calm")
        projects.start_auto(pd, dict(SPEC))
        st = _wait(projects, pd, {"done", "failed", "needs_attention"}); assert st["state"] == "done", st
        m = projects.meta(pd); out.append((nm, m))
        assert len(projects.audio_files(pd / "tracks")) == 4
        for f in ("thumbnail.png", "still.png", "video.mp4", "upload.txt"): assert (pd / f).exists(), f
        assert m["quote"] and m["title"] and m["description"] and m["tags"] and m["pinned"] and m["schedule"] and m["library_image"]
        assert m["quote_placeholder"] is False                                  # replaced by a headline that fits the image
        assert "00:00" in m["description"] and (pd / "images" / (Path(m["library_image"]).stem + "_16x9.png")).exists()
    (a, ma), (b, mb) = out
    assert ma["quote"] != mb["quote"] and ma["library_image"] != mb["library_image"] and ma["schedule"] != mb["schedule"]
    assert ma["playlist_name"] != mb["playlist_name"]
    ov = {p["name"]: p for p in projects.list_projects(root)}
    assert ov[a]["stage"] == "ready" and ov[b]["stage"] == "ready"

def test_needs_attention_then_resume_without_paying_twice():
    settings, library, projects = _env()                                       # empty library
    root = settings.projects_dir(); nm = projects.create_project(root); pd = root / nm
    projects.start_auto(pd, dict(SPEC))
    st = _wait(projects, pd, {"needs_attention", "done", "failed"}); assert st["state"] == "needs_attention" and "library" in st["error"]
    first = sorted(f.name for f in projects.audio_files(pd / "tracks")); tasks = projects.read_json(pd / "auto.json")["task_ids"]
    assert len(first) == 4 and projects.list_projects(root)[0]["stage"] == "needs attention"
    _library(settings, library)                                                # the user adds the images, presses continue
    projects.start_auto(pd, dict(SPEC))
    st = _wait(projects, pd, {"done", "failed", "needs_attention"}); assert st["state"] == "done", st
    assert sorted(f.name for f in projects.audio_files(pd / "tracks")) == first                 # music was not generated again
    assert projects.read_json(pd / "auto.json")["task_ids"] == tasks

def test_cancel():
    settings, library, projects = _env(); _library(settings, library)
    root = settings.projects_dir(); nm = projects.create_project(root); pd = root / nm
    projects.start_auto(pd, dict(SPEC, n_req=30)); projects.cancel_job(pd)
    st = _wait(projects, pd, {"cancelled", "done", "failed"}); assert st["state"] == "cancelled"


def test_whole_video_with_ai_written_text():
    import json, threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    GOOD = {"title_suffix": "lofi city pop for late nights", "subline": "warm lights, patient hours.",
            "scene_text": "city lights on wet streets and a laptop that glows softly. easy tempos for long, patient work that asks for nothing loud.",
            "pinned_comment": "what are you building tonight?", "question": "what's keeping you up this evening?"}
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_POST(self):
            self.rfile.read(int(self.headers["content-length"]))
            out = {"choices": [{"message": {"role": "assistant", "content": json.dumps(GOOD)}}], "usage": {"cost": {"amount": 0.01}}}
            self.send_response(200); self.send_header("content-type", "application/json"); self.end_headers(); self.wfile.write(json.dumps(out).encode())
    srv = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.environ["SOFTGRIND_AI_BASE_URL"] = f"http://127.0.0.1:{srv.server_port}"; os.environ["NO_PROXY"] = "127.0.0.1"; os.environ["no_proxy"] = "127.0.0.1"
    try:
        settings, library, projects = _env(); _library(settings, library)
        root = settings.projects_dir(); nm = projects.create_project(root); pd = root / nm
        projects.start_auto(pd, dict(SPEC, use_ai=True), ai_token="KEY")
        st = _wait(projects, pd, {"done", "failed", "needs_attention"}); assert st["state"] == "done", st
        m = projects.meta(pd)
        assert m["text_by_ai"] is True and m["title"] == f"{m['quote']} | lofi city pop for late nights"
        assert m["description"].startswith(f"{m['quote']} warm lights, patient hours.") and m["pinned"] == "what are you building tonight?"
        assert m["text_parts"]["suffix"] == "lofi city pop for late nights" and "00:00" in m["description"]
    finally:
        os.environ.pop("SOFTGRIND_AI_BASE_URL", None)


def test_continuing_collects_paid_songs_instead_of_paying_again(tmp_path, monkeypatch):
    """The computer slept after a request was paid: on continue its songs are fetched, and only the rest is new."""
    from soft_grind import worker
    calls = {"generate": 0, "wait": []}

    class Fake:
        def __init__(self, *a, **k): pass
        def generate(self, *a, **k):
            calls["generate"] += 1; return f"new-{calls['generate']}"
        def wait(self, tid, on_tick=None):
            calls["wait"].append(tid)
            if tid == "gone": raise worker.SunoError("expired")
            return [{"audio_url": f"https://x/{tid}-{k}.mp3"} for k in (1, 2)]
    monkeypatch.setattr(worker, "SunoClient", Fake)
    monkeypatch.setattr(worker, "download", lambda url, dest: dest.write_bytes(b"x"))
    done = []
    spec = {"mock": True, "n_req": 3, "scenes": ["rainy window"], "model": "m", "minutes": 6, "style": "A", "mood_key": "calm"}
    worker.generate_music(tmp_path, spec, "", lambda m: None, lambda t: None, lambda d: None, lambda: None,
                          pending=["paid-1", "gone"], task_done=done.append)
    assert calls["generate"] == 2                                     # 3 wanted: 1 collected, the expired one asked anew
    assert calls["wait"][:2] == ["paid-1", "gone"] and "paid-1" in done and "gone" in done
    assert len(list((tmp_path / "tracks").iterdir())) == 6
