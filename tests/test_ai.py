"""AIClient against a tiny local fake of POST /v1/chat/completions (shape taken from the AceDataCloud docs)."""
import json, os, sys, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["NO_PROXY"] = "127.0.0.1"; os.environ["no_proxy"] = "127.0.0.1"
from soft_grind import ai

SEEN = []
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        SEEN.append((self.path, self.headers.get("authorization"), body))
        if body["model"] == "bad-model":
            self.send_response(400); self.end_headers(); self.wfile.write(b'{"error":{"code":"bad_request","message":"model is invalid."}}'); return
        text = "  \"Prompt: instrumental lofi, rhodes, nylon guitar, 72 bpm\"\n" if body["model"] != "empty" else ""
        out = {"id": "x", "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
               "usage": {"prompt_tokens": 700, "completion_tokens": 60, "cost": {"amount": 0.0123, "currency": "credit"}}}
        self.send_response(200); self.send_header("content-type", "application/json"); self.end_headers(); self.wfile.write(json.dumps(out).encode())

def _srv():
    s = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=s.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{s.server_port}"

def test_improve_prompt_request_and_cleanup():
    url = _srv(); c = ai.AIClient("KEY", "claude-haiku-4-5-20251001", url)
    text, cost = c.improve_music_prompt("lofi beats", ["rainy window", "night shift"])
    path, auth, body = SEEN[-1]
    assert path == "/v1/chat/completions" and auth == "Bearer KEY" and body["model"] == "claude-haiku-4-5-20251001"
    assert [m["role"] for m in body["messages"]] == ["system", "user"] and "rainy window" in body["messages"][1]["content"]
    assert "Never name artists" in body["messages"][0]["content"] and body["max_tokens"] == 300
    assert text == "instrumental lofi, rhodes, nylon guitar, 72 bpm" and cost == 0.0123   # label + quotes stripped, cost read

def test_errors():
    url = _srv()
    for model, word in (("bad-model", "model is invalid"), ("empty", "empty")):
        try: ai.AIClient("KEY", model, url).chat("s", "u"); assert False
        except ai.AIError as e: assert word in str(e)
    try: ai.AIClient("", "m", url).chat("s", "u"); assert False
    except ai.AIError as e: assert "token" in str(e)

def test_clean_prompt_limits():
    long = ", ".join(["warm rhodes"] * 80)
    assert len(ai.clean_prompt(long)) <= 400 and not ai.clean_prompt(long).endswith(",")
