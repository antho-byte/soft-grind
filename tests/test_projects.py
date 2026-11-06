import os, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from soft_grind import projects

def _wait(pdir, want, secs=40):
    t0 = time.time()
    while time.time() - t0 < secs:
        st = projects.job_status(pdir)
        if st["state"] in want:
            return st
        time.sleep(0.3)
    raise AssertionError(f"job did not reach {want}: {projects.job_status(pdir)}")

SPEC = {"style": "instrumental lofi", "scenes": ["rainy window", "open laptop"], "n_req": 3, "minutes": 6, "model": "chirp-v5-5",
        "name_style": "mix", "mood_key": "calm", "mock": True}

def test_names_and_stage():
    root = Path(tempfile.mkdtemp())
    assert projects.next_project_name(root) == "mix-001"
    (root / "mix-001").mkdir(); (root / "mix-007").mkdir(); (root / "other").mkdir()
    assert projects.next_project_name(root) == "mix-001"           # empty folders are not videos
    (root / "mix-007" / "tracks").mkdir(); (root / "mix-007" / "tracks" / "x.mp3").write_bytes(b"1")
    assert projects.next_project_name(root) == "mix-008"
    info = {"job": {"running": False}, "tracks": 0, "has_thumbnail": False, "has_upload": False, "has_video": False}
    assert projects.stage(info) == "new"
    assert projects.stage({**info, "tracks": 4}) == "needs a thumbnail"
    assert projects.stage({**info, "tracks": 4, "has_thumbnail": True}) == "needs the video"
    assert projects.stage({**info, "tracks": 4, "has_thumbnail": True, "has_video": True}) == "needs youtube text"
    assert projects.stage({**info, "tracks": 4, "has_thumbnail": True, "has_video": True, "has_upload": True}) == "ready"
    assert projects.stage({**info, "tracks": 4, "render": {"running": True}}) == "making the video"
    assert projects.stage({**info, "job": {"running": True}}) == "making music"

def test_background_job_end_to_end_and_overview():
    root = Path(tempfile.mkdtemp()); pdir = root / "mix-001"
    projects.start_music_job(pdir, dict(SPEC))
    st = _wait(pdir, {"done", "failed"})
    assert st["state"] == "done" and st["done"] == 3 and len(st["task_ids"]) == 3 and st["progress"] == 1.0
    files = projects.audio_files(pdir / "tracks")
    assert len(files) == 6
    titles = [f.stem.split(" - ", 1)[1] for f in files]
    assert len(set(titles)) == 6 and not any(t.endswith((" a", " b")) for t in titles)
    (pdir / "thumbnail.png").write_bytes(b"x")
    ov = projects.list_projects(root)
    assert len(ov) == 1 and ov[0]["tracks"] == 6 and ov[0]["seconds"] > 30 and ov[0]["stage"] == "needs the video"
    assert ov[0]["cover"].name == "thumbnail.png" and not ov[0]["job"]["running"]

def test_cancel_and_double_start_and_stale():
    root = Path(tempfile.mkdtemp()); pdir = root / "mix-002"
    projects.write_json(pdir / projects.JOB, {"state": "running", "spec": SPEC, "updated": time.time() - 500})
    assert projects.job_status(pdir)["state"] == "interrupted" and not projects.job_status(pdir)["running"]
    projects.write_json(pdir / projects.JOB, {"state": "running", "spec": SPEC, "updated": time.time()})
    try: projects.start_music_job(pdir, dict(SPEC)); assert False
    except RuntimeError: pass
    pdir2 = root / "mix-003"; spec = dict(SPEC, n_req=30)
    projects.cancel_job(pdir2); projects.start_music_job(pdir2, spec)       # a stale cancel flag is cleared on start...
    assert not (pdir2 / projects.CANCEL).exists()
    projects.cancel_job(pdir2)                                               # ...and a new one, set right after start, stops the job
    st = _wait(pdir2, {"cancelled", "done", "failed"})
    assert st["state"] == "cancelled" and st["done"] < 30


def test_next_free_slot():
    import datetime as dt
    wed = dt.datetime(2026, 11, 4, 10, 0)                                   # a Wednesday morning
    assert projects.next_free_slot(set(), wed) == dt.datetime(2026, 11, 4, 15, 0)
    assert projects.next_free_slot({"2026-11-04 15:00"}, wed) == dt.datetime(2026, 11, 6, 15, 0)       # Friday
    assert projects.next_free_slot({"2026-11-04 15:00", "2026-11-06 15:00"}, wed) == dt.datetime(2026, 11, 9, 15, 0)  # Monday
    assert projects.next_free_slot(set(), dt.datetime(2026, 11, 4, 16, 0)) == dt.datetime(2026, 11, 6, 15, 0)   # too late today

def test_render_job_in_background():
    import tempfile
    from PIL import Image
    from soft_grind.suno import _write_tone
    pdir = Path(tempfile.mkdtemp()) / "mix-001"; (pdir / "tracks").mkdir(parents=True)
    for i in range(3): _write_tone(pdir / "tracks" / f"{i+1:02d} - t{i}.wav", 8, 200 + 50 * i)
    Image.new("RGB", (1920, 1080), (200, 90, 120)).save(pdir / "still.png")
    projects.start_render(pdir, crossfade=2.0, fade_in=1, fade_out=2)
    t0 = time.time()
    while time.time() - t0 < 60 and projects.render_status(pdir)["state"] not in ("done", "failed"): time.sleep(0.3)
    st = projects.render_status(pdir); assert st["state"] == "done", st
    assert (pdir / "video.mp4").exists() and not (pdir / "video.partial.mp4").exists()
    (pdir / "still.png").unlink(); (pdir / "video.mp4").unlink()                  # a missing still is reported, not a crash
    projects.start_render(pdir)
    t0 = time.time()
    while time.time() - t0 < 30 and projects.render_status(pdir)["state"] not in ("done", "failed"): time.sleep(0.3)
    st = projects.render_status(pdir); assert st["state"] == "failed" and "still" in st["error"].lower()


def test_write_json_survives_windows_style_access_denied(monkeypatch):
    import tempfile, time as _t
    d = Path(tempfile.mkdtemp()); f = d / "auto.json"
    real, calls = os.replace, {"n": 0}
    def flaky(src, dst):                                   # Windows: denied while another process has the file open
        calls["n"] += 1
        if calls["n"] <= 5: raise PermissionError(5, "Access is denied")
        return real(src, dst)
    monkeypatch.setattr(os, "replace", flaky)
    projects.write_json(f, {"a": 1})
    assert projects.read_json(f) == {"a": 1} and calls["n"] == 6 and not list(d.glob("*.tmp"))
    monkeypatch.setattr(os, "replace", lambda s, t: (_ for _ in ()).throw(PermissionError(5, "denied")))   # never works
    monkeypatch.setattr(_t, "sleep", lambda s: None)
    projects.write_json(f, {"a": 2})                                                  # falls back to writing in place
    assert projects.read_json(f) == {"a": 2} and not list(d.glob("*.tmp"))
