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
