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
