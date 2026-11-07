import os, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import Image, ImageDraw
from soft_grind import ai, headlines, library, settings
from soft_grind.thumbnail import check_quote

def _img(path, size, top, bottom):
    im = Image.new("RGB", size); d = ImageDraw.Draw(im)
    for y in range(size[1]):
        t = y / size[1]; d.line([(0, y), (size[0], y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    im.save(path)

def _folder():
    d = Path(tempfile.mkdtemp())
    _img(d / "night.jpg", (2000, 1125), (15, 20, 70), (40, 30, 110))          # dark blue
    _img(d / "sunset.png", (2000, 1125), (94, 94, 224), (255, 140, 120))      # warm
    _img(d / "grey.jpg", (1200, 1800), (150, 150, 155), (170, 170, 172))      # vertical, low saturation
    (d / "notes.txt").write_text("x")
    return d

def test_headlines_rules_and_uniqueness():
    used = set()
    for mood in ("calm", "groovy"):
        for _ in range(8):
            for h in headlines.suggest(mood, ["rainy window", "night shift"], used, n=10):
                assert not check_quote(h), (h, check_quote(h))               # lowercase, <= 4 words, ends with . or ?
                assert h.lower() not in used; used.add(h.lower())
    assert len(used) == 160                                                    # 160 unique headlines in a row, never a repeat
    first = headlines.suggest("calm", ["rainy window"], set(), 1, seed=1)[0]
    assert first in headlines.BY_SCENE["rainy window"] or first in headlines.SOFT_GRIND                    # a rare soft-grind line may come first
    assert headlines.suggest("calm", ["rainy window"], set(headlines.SOFT_GRIND), 1, seed=1)[0] in headlines.BY_SCENE["rainy window"]
    allp = set(headlines.pool("calm")) | set(headlines.pool("groovy")) | {h for v in headlines.BY_SCENE.values() for h in v} | set(headlines.SOFT_GRIND)
    assert len(allp) >= 180 and not [h for h in allp if check_quote(h)]       # every listed headline obeys the rules (3 words, lowercase, . or ?)
    assert all(len(h.split()) <= 3 and h == h.lower() and h.endswith((".", "?")) for h in allp)
    few = sum(1 for s in range(400) if headlines.suggest("calm", [], set(), 1, seed=s)[0] in headlines.SOFT_GRIND)
    assert 5 <= few <= 60                                                      # 'soft grind' lines are rare, not absent, not common
    left = headlines.suggest("calm", ["rainy window"], {h for h in allp if h != "stay in."}, 1, seed=3)[0]
    assert left                                                                # even with almost everything recently used it still answers

def test_parse_headlines_filters_bad_lines():
    txt = """1. let it rain.
- Keep Grinding!
"slow is fine."
this one has far too many words in it.
let it rain.
no full stop"""
    assert ai.parse_headlines(txt, used={"slow is fine."}) == ["let it rain."]

def test_scan_thumbs_and_colour_analysis():
    os.environ["SOFTGRIND_HOME"] = tempfile.mkdtemp()
    import importlib; importlib.reload(settings); importlib.reload(library)
    d = _folder(); files = library.scan(d)
    assert [p.name for p in files] == ["grey.jpg", "night.jpg", "sunset.png"]
    assert library.thumb(files[1]).exists() and max(Image.open(library.thumb(files[1])).size) <= 420
    by = {p.name: library.analyse(p)[0] for p in files}
    assert by["night.jpg"]["time"] == "night" and "night shift" in by["night.jpg"]["scenes"]
    assert by["sunset.png"]["time"] == "sunset" and by["grey.jpg"]["orientation"] == "vertical"
    assert all(a["method"] == "colors" and a["w"] and a["h"] for a in by.values())

def test_parse_analysis_validates():
    a = library.parse_analysis('Here you go: {"description":"a pool at sunset","mood":"groovy","time":"sunset","scenes":["poolside sunset","made up scene"],'
                               '"keywords":["pool","palms"],"has_text":false,"has_people":false,"risks":["artist signature"]}')
    assert a["scenes"] == ["poolside sunset"] and a["mood"] == "groovy" and a["risks"] == ["artist signature"] and a["method"] == "ai"

def test_matching_prefers_fit_and_unused():
    topic = ["rainy window", "night shift"]
    mk = lambda scenes, mood, **kw: {"analysis": {"scenes": scenes, "mood": mood, "risks": [], "has_text": False, "w": 2500, "orientation": "landscape", **kw}}
    d = Path(tempfile.mkdtemp()); paths = {}
    db = {}
    for name, rec in {"fit": mk(["rainy window"], "calm"), "off": mk(["poolside sunset"], "groovy"), "used": mk(["rainy window", "night shift"], "calm"),
                      "risky": mk(["rainy window"], "calm", risks=["artist signature"], has_text=True)}.items():
        p = d / f"{name}.jpg"; p.write_bytes(b"x"); db[str(p)] = rec; paths[name] = str(p)
    order = [Path(r["path"]).stem for r in library.suggest(db, topic, "calm", {paths["used"]: "mix-001"}, seed="a", n=4)]
    assert order[0] == "fit" and order.index("used") > order.index("off") - 1 and order[-1] in ("risky", "used")
    assert order.index("risky") > order.index("off")

def test_prepare_for_project_and_usage_map():
    os.environ["SOFTGRIND_HOME"] = tempfile.mkdtemp()
    import importlib; importlib.reload(settings); importlib.reload(library)
    d = _folder(); root = Path(tempfile.mkdtemp()); pd = root / "mix-001"
    out = library.prepare_for_project(d / "grey.jpg", pd)                       # vertical -> 16:9 with blur fill
    assert Image.open(out).size == (1920, 1080) and (pd / "images" / "grey_source.png").exists()
    out2 = library.prepare_for_project(d / "sunset.png", root / "mix-002")
    assert Image.open(out2).size[0] >= 1920 and abs(Image.open(out2).size[0] / Image.open(out2).size[1] - 16 / 9) < 0.02
    assert library.used_images(root) == {str(d / "grey.jpg"): "mix-001", str(d / "sunset.png"): "mix-002"}

def test_background_library_job():
    os.environ["SOFTGRIND_HOME"] = tempfile.mkdtemp()
    import importlib; importlib.reload(settings); importlib.reload(library)
    d = _folder()
    library.start_library_job(str(d), use_ai=False)
    t0 = time.time()
    while time.time() - t0 < 40 and library.library_job_status()["state"] not in ("done", "failed"): time.sleep(0.3)
    st = library.library_job_status(); assert st["state"] == "done" and st["done"] == 3, st
    db = library.load_db(); assert len(db) == 3 and all(r["analysis"]["method"] == "colors" for r in db.values())
    library.start_library_job(str(d), use_ai=False)                             # nothing new to look at: finishes at once
    time.sleep(1.5); assert library.library_job_status()["total"] == 0
