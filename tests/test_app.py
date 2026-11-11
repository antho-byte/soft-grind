"""The real app, driven page by page (Streamlit's AppTest): the flows an owner uses every day, in one regression suite."""
import importlib, logging, os, re, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
logging.disable(logging.CRITICAL)
os.environ["NO_PROXY"] = "127.0.0.1"; os.environ["no_proxy"] = "127.0.0.1"
from PIL import Image, ImageDraw
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent


def home():
    """A fresh data folder for one test, and the modules pointed at it."""
    os.environ["SOFTGRIND_HOME"] = tempfile.mkdtemp()
    for var in ("ACEDATACLOUD_API_TOKEN", "ACEDATACLOUD_IMAGE_TOKEN", "ACEDATACLOUD_AI_TOKEN", "SOFTGRIND_AI_BASE_URL"):
        os.environ.pop(var, None)
    from soft_grind import settings, security, library, projects
    for m in (settings, security, library, projects):
        importlib.reload(m)
    return settings, projects


def open_app(step=None, project=None):
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90)
    if step: at.session_state["step"] = step
    if project: at.session_state["project"] = project
    at.run()
    assert not at.exception, at.exception
    return at


def click(at, key=None, label=None, sidebar=False):
    pool = at.sidebar.button if sidebar else at.button
    [b for b in pool if (key and b.key == key) or (label and b.label == label)][0].click()
    at.run()
    assert not at.exception, at.exception


def title(at):
    return re.sub(r"<[^>]+>", "", [m.value for m in at.markdown if 'class="sg-title"' in m.value][0].split('class="sg-title">')[1])


def make_library(settings):
    from soft_grind import library
    d = Path(tempfile.mkdtemp())
    for i, (top, bot) in enumerate([((15, 20, 70), (60, 40, 130)), ((94, 94, 224), (255, 140, 120)), ((20, 120, 90), (255, 194, 122))]):
        im = Image.new("RGB", (2000, 1125)); dr = ImageDraw.Draw(im)
        for y in range(1125):
            k = y / 1125; dr.line([(0, y), (2000, y)], fill=tuple(int(top[c] + (bot[c] - top[c]) * k) for c in range(3)))
        im.save(d / f"i{i}.jpg")
    settings.save_library_dir(str(d)); library.analyse_pending(library.scan(d), None)


def wait(cond, secs=90):
    t0 = time.time()
    while time.time() - t0 < secs:
        if cond():
            return True
        time.sleep(0.4)
    return False


def test_every_page_and_tab_loads_and_old_step_names_still_work():
    home()
    at = open_app()
    assert [b.label for b in at.sidebar.button] == ["videos", "planning", "images", "settings"]
    for key, want in (("menu_planning", "planning."), ("menu_library", "the images."), ("menu_settings", "settings."), ("menu_projects", "your videos.")):
        click(at, key, sidebar=True); assert title(at).startswith(want[:-1])
    click(at, label="step by step")
    assert at.session_state["step"] == "music" and [b.label for b in at.button if b.key and b.key.startswith("tab_")] == ["music", "cover", "video"]
    for key, word in (("tab_thumbnail", "cover"), ("tab_video", "video"), ("tab_music", "music")):
        click(at, key); assert word in title(at)
    for old, new in (("playlist", "music"), ("fix images", "thumbnail"), ("setup", "settings")):    # saved sessions from older versions
        assert open_app(step=old).session_state["step"] == new


def test_new_video_gets_its_own_headline_and_background_music_works():
    settings, projects = home()
    at = open_app(); click(at, label="step by step")
    name = at.session_state["project"]; q = projects.meta(settings.projects_dir() / name)["quote"]
    assert q and q.endswith((".", "?")) and len(q.split()) <= 5
    click(at, label="generate in the background")
    pd = settings.projects_dir() / name
    assert wait(lambda: projects.job_status(pd)["state"] == "done")
    at.run(); assert len(projects.audio_files(pd / "tracks")) == 8 and len(at.session_state["tracks"]) == 8
    assert any("the songs" in m.value for m in at.markdown)                       # the old playlist page now lives on this tab


def test_whole_video_from_the_popover_form_and_getting_started_card():
    settings, projects = home(); make_library(settings)
    at = open_app()
    assert any("getting started" in m.value for m in at.markdown)                   # no keys yet: the checklist shows
    click(at, label="automatic: the whole video"); assert at.session_state["_auto_open"]
    [s for s in at.selectbox if s.label == "length"][0].set_value("short test (4 songs)"); at.run()
    click(at, label="make the video")
    pd = settings.projects_dir() / "mix-001"
    assert wait(lambda: projects.auto_status(pd)["state"] in ("done", "failed", "needs_attention"), 120)
    st = projects.auto_status(pd); assert st["state"] == "done", st
    at.run(); info = {p["name"]: p for p in projects.list_projects(settings.projects_dir())}["mix-001"]
    assert info["stage"] == "ready" and (pd / "video.mp4").exists() and (pd / "still.png").exists()
    assert not at.session_state["_auto_open"]
    q = projects.meta(pd)["quote"]; assert projects.meta(pd)["title"].startswith(q)         # the title starts with the quote


def test_video_page_never_saves_unseen_text_then_autosaves_and_undoes():
    settings, projects = home()
    at = open_app(); click(at, label="step by step"); name = at.session_state["project"]; pd = settings.projects_dir() / name
    from soft_grind.suno import _write_tone
    for i in range(4): _write_tone(pd / "tracks" / f"{i+1:02d} - t{i}.wav", 8, 200 + 30 * i)
    at.session_state["step"] = "video"; at.run(); assert not at.exception
    assert not projects.meta(pd).get("title")                                           # a suggestion is not saved by looking at it
    click(at, label="use this text"); first = projects.meta(pd)["title"]; assert first and (pd / "upload.txt").exists()
    [t for t in at.text_input if t.label == "Title"][0].set_value("my own title."); at.run()
    assert projects.meta(pd)["title"] == "my own title." and len(projects.meta(pd)["text_history"]) == 1     # autosaved, old one kept
    click(at, label=[b.label for b in at.button if b.label.startswith("undo the last text change")][0])
    assert projects.meta(pd)["title"] == first


def test_delete_goes_to_the_trash_and_can_be_restored():
    settings, projects = home()
    at = open_app(); click(at, label="step by step"); name = at.session_state["project"]
    (settings.projects_dir() / name / "tracks").mkdir(parents=True, exist_ok=True); (settings.projects_dir() / name / "tracks" / "01 - a.mp3").write_bytes(b"0")
    click(at, "menu_projects", sidebar=True)
    click(at, f"del_{name}"); assert [b for b in at.button if b.key == f"delyes_{name}"]   # asks first
    click(at, f"delyes_{name}"); assert not projects.list_projects(settings.projects_dir()) and len(projects.list_trash(settings.projects_dir())) == 1
    restore = [b for b in at.button if b.key and b.key.startswith("restore_")][0]; restore.click(); at.run()
    assert [p["name"] for p in projects.list_projects(settings.projects_dir())] == [name]


def test_password_gate_hides_everything_until_the_right_password(monkeypatch):
    settings, projects = home()
    from soft_grind import security
    security.set_password("a long password")
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    assert not at.sidebar.button and [t.label for t in at.text_input] == ["password"]       # nothing but the login
    monkeypatch.setattr(security.time, "sleep", lambda s: None)                 # restored after the test
    at.text_input[0].set_value("nope"); click(at, label="open"); assert [e.value for e in at.error] == ["That is not the password."] and not at.sidebar.button
    at.text_input[0].set_value("a long password"); click(at, label="open"); assert at.sidebar.button


def test_settings_page_saves_keys_and_the_setup_check_runs():
    settings, projects = home()
    at = open_app("settings")
    [t for t in at.text_input if t.label == "API token"][0].set_value("fake-suno-key-123"); at.run()
    click(at, label="save keys on this computer"); assert settings.load_keys()["suno"] == "fake-suno-key-123"
    assert any("check my setup" in m.value for m in at.markdown)
    names = [re.sub(r"<[^>]+>", "|", m.value).split("|") for m in at.markdown if "sg-chk" in m.value]
    flat = " ".join(" ".join(n) for n in names); assert "projects folder" in flat and "background jobs" in flat and "Suno key" in flat
    assert any("soft grind. diagnostics" in c.value for c in at.code) and "fake-suno-key-123" not in " ".join(c.value for c in at.code)


def test_ai_buttons_survive_a_dead_network_and_damaged_pictures_never_crash():
    settings, projects = home()
    os.environ.update(SOFTGRIND_AI_BASE_URL="http://127.0.0.1:9", ACEDATACLOUD_AI_TOKEN="KEY")
    try:
        at = open_app(); click(at, label="step by step"); name = at.session_state["project"]; pd = settings.projects_dir() / name
        click(at, label="improve with AI"); assert any("Could not reach" in c.value for c in at.caption)
        (pd / "thumbnail.png").write_bytes(b"not a picture"); (pd / "still.png").write_bytes(b"\x89PNG broken")
        for step in ("projects", "video", "thumbnail"):
            open_app(step=step, project=name)                                               # asserts: no exception
    finally:
        os.environ.pop("SOFTGRIND_AI_BASE_URL", None); os.environ.pop("ACEDATACLOUD_AI_TOKEN", None)


def test_youtube_card_and_upload_button_appear_only_when_they_can_work():
    settings, projects = home()
    from soft_grind import youtube
    importlib.reload(youtube)
    at = open_app("settings")
    assert any("youtube" == m.value.strip("*") for m in at.markdown) and not [b for b in at.button if b.label == "connect youtube"]
    youtube.save_client('{"installed": {"client_id": "fake-id", "client_secret": "fake-secret"}}')
    at = open_app("settings")
    assert [b for b in at.button if b.label == "connect youtube"]
    # a finished video: no connection yet -> only a hint; connected -> the upload button, enabled once the text exists
    p = settings.projects_dir() / "mix-001"; (p / "tracks").mkdir(parents=True)
    (p / "video.mp4").write_bytes(b"v")
    at = open_app("video", "mix-001")
    assert not [b for b in at.button if b.label == "upload to YouTube"]
    youtube._write_private(youtube._token_file(), {"refresh_token": "RT-fake"})
    at = open_app("video", "mix-001")
    btn = [b for b in at.button if b.label == "upload to YouTube"]
    assert btn and btn[0].disabled
    projects.set_meta(p, title="night shift.", description="d", tags="lofi")
    at = open_app("video", "mix-001")
    assert not [b for b in at.button if b.label == "upload to YouTube"][0].disabled


def test_film_dust_switch_saves_per_video_and_can_be_switched_off():
    settings, projects = home()
    p = settings.projects_dir() / "mix-001"; (p / "tracks").mkdir(parents=True)
    Image.new("RGB", (1920, 1080), (60, 60, 160)).save(p / "still.png")
    at = open_app("video", "mix-001")
    tog = [t for t in at.toggle if t.key == "look_on_mix-001"][0]
    assert tog.value is False
    tog.set_value(True); at.run(); assert not at.exception, at.exception
    lk = projects.film_look(p); assert lk and lk["dust"] and lk["fps"] == 12 and not lk["grain"] and not lk["scratches"]
    assert [b for b in at.button if b.label == "20-second test"]
    [t for t in at.toggle if t.key == "look_on_mix-001"][0].set_value(False); at.run(); assert not at.exception
    assert projects.film_look(p) is None


def test_videos_page_next_step_buttons_and_bulk_actions(monkeypatch):
    settings, projects = home()
    from soft_grind import youtube
    importlib.reload(youtube)
    spawned = []
    monkeypatch.setattr(projects, "_spawn", lambda module, workdir, jobfile, env=None: spawned.append((module, jobfile)))
    from soft_grind.suno import _write_tone
    root = settings.projects_dir()
    for n in ("mix-001", "mix-002", "mix-003"):                                     # three videos with music and a cover, no video yet
        p = root / n; (p / "tracks").mkdir(parents=True)
        _write_tone(p / "tracks" / "01 - a.wav", 2, 220)
        Image.new("RGB", (1920, 1080), (60, 60, 160)).save(p / "still.png"); Image.new("RGB", (1280, 720)).save(p / "thumbnail.png")
        projects.set_meta(p, quote=f"{n}.")
    at = open_app()
    labels = {b.key: b.label for b in at.button if b.key and b.key.startswith("next_")}
    assert labels == {f"next_mix-00{i}": "make the video" for i in (1, 2, 3)}       # each card shows its one next step
    [c for c in at.checkbox if c.key == "sel_mix-001"][0].check(); at.run()
    [c for c in at.checkbox if c.key == "sel_mix-002"][0].check(); at.run(); assert not at.exception
    mk = [b for b in at.button if b.key == "bulk_mk"][0]; assert mk.label == "make 2 videos"
    up = [b for b in at.button if b.key == "bulk_up"][0]; assert up.disabled            # nothing ready to upload yet
    mk.click(); at.run(); assert not at.exception
    assert spawned == [("soft_grind.queue", "queue_render.json")]                      # one queue for both, made one after another
    q = projects.read_json(projects.queue_file("render"))
    assert sorted(Path(i).name for i in q["items"]) == ["mix-001", "mix-002"]
    assert projects.render_status(root / "mix-001")["state"] == "queued" and projects.render_status(root / "mix-003")["state"] == "none"


def test_every_card_has_an_open_button_under_its_next_step():
    settings, projects = home()
    p = settings.projects_dir() / "mix-001"; (p / "tracks").mkdir(parents=True); (p / "tracks" / "01 - a.mp3").write_bytes(b"0")
    at = open_app()
    keys = [b.key for b in at.button if b.key in ("next_mix-001", "open_mix-001")]
    assert keys == ["next_mix-001", "open_mix-001"]                                  # next step first, open below it
    click(at, "open_mix-001"); assert at.session_state["project"] == "mix-001" and at.session_state["step"] != "projects"


def test_planning_page_shows_planned_videos_and_plans_a_free_slot():
    settings, projects = home()
    from soft_grind import planning
    importlib.reload(planning)
    root = settings.projects_dir()
    soon = planning.free_slots([], 2)
    for n, q, sched in (("mix-001", "night shift.", soon[0].strftime("%Y-%m-%d %H:%M")), ("mix-002", "slow sunday.", "")):
        p = root / n; (p / "tracks").mkdir(parents=True); (p / "tracks" / "01 - a.mp3").write_bytes(b"0")
        projects.set_meta(p, quote=q, schedule=sched, title=f"{q} title", description="d", tags="lofi")
        (p / "upload.txt").write_text("old", encoding="utf-8")
    at = open_app("planning"); assert not at.exception
    page = " ".join(m.value for m in at.markdown)
    assert "night shift." in page and "free · 15:00" in page and "not planned yet** · 1" in page
    click(at, "plan_set_mix-002")
    m = projects.meta(root / "mix-002"); assert planning.parse(m["schedule"]) == soon[1]   # the first slot that was still free
    assert soon[1].strftime("%Y-%m-%d %H:%M") in (root / "mix-002" / "upload.txt").read_text()
    click(at, "plan_next"); click(at, "plan_prev"); click(at, "plan_open_mix-001")
    assert at.session_state["project"] == "mix-001"


def test_batch_makes_several_whole_videos_each_with_its_own_headline_picture_and_slot():
    settings, projects = home(); make_library(settings)
    from soft_grind import headlines
    at = open_app()
    click(at, label="batch: several videos at once"); assert at.session_state["_batch_open"]
    [s for s in at.select_slider if s.key == "batch_n"][0].set_value(2); at.run()
    [s for s in at.selectbox if s.key == "batch_len"][0].set_value("short test (4 songs)"); at.run()
    click(at, "batch_go"); assert not at.session_state["_batch_open"]
    root = settings.projects_dir(); names = ["mix-001", "mix-002"]
    assert wait(lambda: projects.batch_status()["state"] in ("done", "cancelled", "interrupted"), 240), projects.batch_status()
    bs = projects.batch_status(); assert bs["state"] == "done" and sorted(bs["made"]) == names, bs
    metas = [projects.meta(root / n) for n in names]
    assert all((root / n / "video.mp4").exists() and m["title"].startswith(m["quote"]) for n, m in zip(names, metas))
    assert all(m["quote"] in headlines.ALL for m in metas) and metas[0]["quote"] != metas[1]["quote"]     # from your list, never twice
    assert metas[0]["schedule"] and metas[1]["schedule"] and metas[0]["schedule"] != metas[1]["schedule"]  # each its own free slot
    assert metas[0]["topic"] != metas[1]["topic"]                                                            # each its own scenes
    assert not any(projects.youtube_status(root / n)["state"] != "none" for n in names)                     # nothing uploaded
    at.run(); assert any("batch done" in m.value for m in at.markdown)


def test_shorts_card_makes_shorts_from_the_video_page():
    settings, projects = home()
    from soft_grind import shorts
    importlib.reload(shorts)
    from soft_grind.suno import _write_tone
    p = settings.projects_dir() / "mix-001"; (p / "tracks").mkdir(parents=True)
    for k in range(2): _write_tone(p / "tracks" / f"0{k+1} - t{k}.wav", 25, 220 + 40 * k)
    Image.new("RGB", (1920, 1080), (40, 50, 140)).save(p / "cover_source.png"); Image.new("RGB", (1920, 1080), (40, 50, 140)).save(p / "still.png")
    projects.set_meta(p, quote="lamp on.")
    at = open_app("video", "mix-001")
    assert any(m.value == "**shorts**" for m in at.markdown)
    [s for s in at.select_slider if s.key == "sh_n_mix-001"][0].set_value(1)
    [s for s in at.select_slider if s.key == "sh_len_mix-001"][0].set_value(15); at.run()
    click(at, "sh_make_mix-001")
    assert wait(lambda: shorts.status(p)["state"] in ("done", "failed"), 120), shorts.status(p)
    assert shorts.status(p)["state"] == "done" and len(shorts.listing(p)) == 1
    at.run(); assert not at.exception and [b for b in at.button if b.key == "sh_make_mix-001"][0].label == "make the shorts again"


def test_songs_can_be_removed_and_reordered_on_the_music_tab():
    settings, projects = home()
    from soft_grind.suno import _write_tone
    p = settings.projects_dir() / "mix-001"; (p / "tracks").mkdir(parents=True)
    for k, n in enumerate(("rain", "lamp", "train")):
        _write_tone(p / "tracks" / f"0{k+1} - {n}.wav", 3, 220 + 40 * k)
    at = open_app("music", "mix-001")
    assert any("make more songs" in e.label for e in at.expander)                     # songs exist: the generator folds away
    click(at, "rm_1")                                                                  # remove 'lamp'
    names_ = [f.name for f in projects.audio_files(p / "tracks")]
    assert names_ == ["01 - rain.wav", "02 - train.wav"] and (p / "tracks" / "removed" / "02 - lamp.wav").exists()
    click(at, "dn_0")                                                                  # rain moves down
    assert [f.name for f in projects.audio_files(p / "tracks")] == ["01 - train.wav", "02 - rain.wav"]
    assert projects.meta(p).get("songs_changed")
