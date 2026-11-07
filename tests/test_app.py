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
    assert [b.label for b in at.sidebar.button] == ["videos", "images", "settings"]
    for key, want in (("menu_library", "the images."), ("menu_settings", "settings."), ("menu_projects", "your videos.")):
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
    assert q and q.endswith((".", "?")) and len(q.split()) <= 3
    click(at, label="generate in the background")
    pd = settings.projects_dir() / name
    assert wait(lambda: projects.job_status(pd)["state"] == "done")
    at.run(); assert len(projects.audio_files(pd / "tracks")) == 8 and len(at.session_state["tracks"]) == 8
    assert any("the tracks" in m.value for m in at.markdown)                       # the old playlist page now lives on this tab


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
    click(at, f"del_{name}"); assert any("trash" in w.value for w in at.warning)          # asks first
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
    assert not [b for b in at.button if b.label == "upload to youtube"]
    youtube._write_private(youtube._token_file(), {"refresh_token": "RT-fake"})
    at = open_app("video", "mix-001")
    btn = [b for b in at.button if b.label == "upload to youtube"]
    assert btn and btn[0].disabled
    projects.set_meta(p, title="night shift.", description="d", tags="lofi")
    at = open_app("video", "mix-001")
    assert not [b for b in at.button if b.label == "upload to youtube"][0].disabled


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
