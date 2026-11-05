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
    info = {"job": {"running": False}, "tracks": 0, "has_thumbnail": False, "has_upload": False}
    assert projects.stage(info) == "new"
    assert projects.stage({**info, "tracks": 4}) == "needs a thumbnail"
    assert projects.stage({**info, "tracks": 4, "has_thumbnail": True}) == "needs youtube text"
    assert projects.stage({**info, "tracks": 4, "has_thumbnail": True, "has_upload": True}) == "ready"
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
    assert len(ov) == 1 and ov[0]["tracks"] == 6 and ov[0]["seconds"] > 30 and ov[0]["stage"] == "needs youtube text"
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
