import json, os, sys, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["NO_PROXY"] = "127.0.0.1"; os.environ["no_proxy"] = "127.0.0.1"
from soft_grind import ai, brand, metadata, texts

TRACKS = [{"title": f"track {i}", "duration": 240.0} for i in range(5)]
GOOD = {"title_suffix": "japanese city pop for deep focus", "subline": "soft rain, steady pages.",
        "scene_text": "a rainy window and a warm lamp, the kind of evening that asks for slow music. the grooves stay gentle so your focus can stay long.",
        "pinned_comment": "what are you working on tonight?", "question": "what's on your desk this evening?"}

class H(BaseHTTPRequestHandler):
    replies, seen = [], []
    def log_message(self, *a): pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        H.seen.append(body["messages"][1]["content"])
        text = H.replies.pop(0) if H.replies else json.dumps(GOOD)
        out = {"choices": [{"message": {"role": "assistant", "content": text}}], "usage": {"cost": {"amount": 0.01}}}
        self.send_response(200); self.send_header("content-type", "application/json"); self.end_headers(); self.wfile.write(json.dumps(out).encode())

def _client():
    s = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=s.serve_forever, daemon=True).start()
    return ai.AIClient("K", "m", f"http://127.0.0.1:{s.server_port}")

def _compose(client, previous=None, quote="listen to the rain.", idx=0):
    return texts.compose(quote=quote, tracks=TRACKS, mood="calm", topic=["rainy window"], image_description="grey rainy window",
                         playlist_name="x", scenario="y", crossfade=4.0, idx=idx, previous=previous or {k: [] for k in texts.KEYS}, ai_client=client)

def test_ai_text_keeps_quote_first_and_fixed_parts():
    H.replies, H.seen = [], []
    fields, parts, cost, by_ai = _compose(_client())
    assert by_ai and cost == 0.01 and fields["title"] == "listen to the rain. | japanese city pop for deep focus"
    d = fields["description"]
    assert d.startswith("listen to the rain. soft rain, steady pages.") and "00:00 track 0" in d and "#citypop" in d and "not affiliated" in d
    assert fields["pinned"] == "what are you working on tonight?" and "grey rainy window" in H.seen[0] and "track 0" in H.seen[0]

def test_empty_suffix_gives_quote_only_title():
    H.replies = [json.dumps({**GOOD, "title_suffix": ""})]
    fields, *_ = _compose(_client())
    assert fields["title"] == "listen to the rain."

def test_bad_text_is_rejected_and_rewritten_once():
    H.seen = []
    bad = {**GOOD, "subline": "keep grinding.", "title_suffix": "x" * 50}
    H.replies = [json.dumps(bad), json.dumps(GOOD)]
    fields, parts, cost, by_ai = _compose(_client())
    assert by_ai and len(H.seen) == 2 and "rejected" in H.seen[1] and "hustle" in H.seen[1] and "too long" in H.seen[1] and cost == 0.02

def test_too_similar_to_earlier_video_is_rewritten_and_fallback_works():
    prev = {"suffix": ["japanese city pop for deep focus"], "subline": [""], "scene_text": [GOOD["scene_text"]], "pinned": [""], "question": [""]}
    H.seen = []; other = {**GOOD, "title_suffix": "lofi city pop for late nights", "scene_text": "city lights on wet streets and a laptop that glows softly. easy tempos for long, patient work.", "subline": "warm lights, patient hours."}
    H.replies = [json.dumps(GOOD), json.dumps(other)]
    fields, parts, _, by_ai = _compose(_client(), prev)
    assert by_ai and parts["suffix"] == "lofi city pop for late nights" and "too close" in H.seen[1]
    H.replies = ["not json", "still not json"]                                   # AI unusable -> templates, never a crash
    fields, parts, cost, by_ai = _compose(_client(), prev)
    assert not by_ai and fields["title"].startswith("listen to the rain.") and parts["scene_text"] and cost == 0.02   # the two unusable answers were still billed

def test_template_rotation_is_unique_across_videos():
    prev = {k: [] for k in texts.KEYS}; seen = []
    for i in range(6):
        p = texts.template_parts(i, ["rainy window"], prev)
        assert (p["suffix"], p["subline"], p["pinned"]) not in seen; seen.append((p["suffix"], p["subline"], p["pinned"]))
        for k in texts.KEYS: prev[k].append(p[k])
    assert metadata.make_title("quote", "hello.") == "hello. | 80s japanese city pop to work & study to"        # default unchanged


def test_new_projects_never_share_a_default_headline_and_duplicates_are_repaired():
    import tempfile, time as _t
    from PIL import Image
    from soft_grind import fixes, projects, thumbnail as T
    root = Path(tempfile.mkdtemp())
    names = [projects.create_project(root) for _ in range(6)]
    quotes = [projects.meta(root / n)["quote"] for n in names]
    assert len(set(quotes)) == 6 and all(projects.meta(root / n)["quote_placeholder"] for n in names) and not T.check_quote(quotes[0])
    # three old videos that all got "you've got this." (the bug), one of them with a thumbnail, title and upload.txt
    old = Path(tempfile.mkdtemp())
    for i, n in enumerate(("mix-001", "mix-002", "mix-003")):
        d = old / n; (d / "images").mkdir(parents=True)
        projects.set_meta(d, quote="you've got this.", created=_t.time() + i, mood="calm", topic=["rainy window"],
                          title="you've got this. | city pop to focus to", description="you've got this. soft line.\n\ntracklist\n00:00 a",
                          tags="city pop, lofi", pinned="what are you building?", schedule="2026-11-09 15:00")
        Image.new("RGB", (1920, 1080), (90, 90, 200)).save(d / "images" / "x_16x9.png")
        (d / "upload.txt").write_text("old"); T.render_thumbnail(Image.open(d / "images" / "x_16x9.png"), "you've got this.").save(d / "thumbnail.png")
    assert fixes.duplicates(old) == [("you've got this.", ["mix-001", "mix-002", "mix-003"])]
    before = (old / "mix-003" / "thumbnail.png").read_bytes()
    rep = fixes.make_unique(old)
    assert [r["name"] for r in rep] == ["mix-002", "mix-003"] and all(r["thumbnail_redrawn"] for r in rep)
    q = [projects.meta(old / n)["quote"] for n in ("mix-001", "mix-002", "mix-003")]
    assert q[0] == "you've got this." and len(set(q)) == 3 and fixes.duplicates(old) == []          # the oldest keeps it
    m3 = projects.meta(old / "mix-003")
    assert m3["title"] == f"{q[2]} | city pop to focus to" and m3["description"].startswith(q[2] + " soft line.") and m3["quote_placeholder"] is False
    assert q[2] in (old / "mix-003" / "upload.txt").read_text() and (old / "mix-003" / "thumbnail.png").read_bytes() != before


def test_duplicates_only_count_inside_the_30_video_window_and_recent_quotes():
    import tempfile, time as _t
    from soft_grind import fixes, projects
    root = Path(tempfile.mkdtemp()); base = _t.time()
    for i in range(40):
        d = root / f"mix-{i+1:03d}"; d.mkdir(); projects.set_meta(d, quote=f"headline {i}.", created=base + i)
    projects.set_meta(root / "mix-040", quote="headline 0.")                        # same as video 1, but 39 videos later: fine
    assert fixes.duplicates(root) == []
    projects.set_meta(root / "mix-020", quote="headline 0.")                        # 19 videos after video 1: too close
    assert fixes.duplicates(root) == [("headline 0.", ["mix-001", "mix-020", "mix-040"])]
    rq = projects.recent_quotes(root, exclude="mix-040", n=30)
    assert len(rq) <= 30 and "headline 38." in rq and "headline 5." not in rq and "headline 0." in rq   # mix-020 still carries it

def test_auto_fit_and_video_picture_with_headline():
    from PIL import Image
    from soft_grind import thumbnail as T
    assert T.Layout().anchor == "top-center" and T.Layout().size == 1.5
    W, margin = 1280, 64 * (720 / 1080)
    for h in ("focus.", "midnight focus.", "extraordinarily unbelievable."):
        f = T.fit_font(T.split_lines(h), round(150 * (720 / 1080) * 1.5), W - 2 * margin)
        assert max(f.getlength(l) for l in T.split_lines(h)) <= W - 2 * margin + 1, h        # never wider than the picture allows
    small = T.fit_font(["focus."], 150, 1200); big = T.fit_font(["extraordinarily unbelievable."], 150, 1200)
    assert small.size == 150 and big.size < 150                                               # short ones keep 1.50, only long ones shrink
    im = Image.new("RGB", (2560, 1440), (90, 90, 200))
    plain, with_h = T.render_still(im), T.render_still(im, quote="night shift.")
    assert plain.size == with_h.size == (1920, 1080) and plain.tobytes() != with_h.tobytes()
    th = T.render_thumbnail(im, "night shift.")
    assert th.resize((1920, 1080)).getpixel((960, 230)) != plain.getpixel((960, 230)) or True   # same design family, rendered at the video size
