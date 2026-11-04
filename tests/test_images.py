"""ImageClient against a tiny local fake of the API (sync response, and task-polling response)."""
import base64, io, json, os, sys, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["NO_PROXY"] = "127.0.0.1"; os.environ["no_proxy"] = "127.0.0.1"
from PIL import Image
from soft_grind import imagegen as G

def _png_b64():
    b = io.BytesIO(); Image.new("RGB", (1600, 900), (200, 80, 120)).save(b, "PNG")
    return base64.b64encode(b.getvalue()).decode()

SEEN = []
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        SEEN.append((self.path, self.headers.get("authorization"), body))
        if self.path.endswith("/tasks"):
            out = {"state": "done", "response": {"success": True, "data": [{"image_url": "data:image/png;base64," + _png_b64()}]}}
        elif self.path.startswith("/poll"):
            out = {"task_id": "t1"}
        elif self.path.startswith("/bad"):
            self.send_response(401); self.end_headers(); self.wfile.write(b'{"error":"nope"}'); return
        else:
            out = {"success": True, "data": [{"image_url": "data:image/png;base64," + _png_b64()}]}
        self.send_response(200); self.send_header("content-type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps(out).encode())

def _server():
    s = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, f"http://127.0.0.1:{s.server_port}"

def test_blur_and_finish():
    v = Image.new("RGB", (800, 1200), (10, 200, 30))
    assert G.blur_fill(v).size == (1920, 1080)
    out, note = G.finish_16x9(Image.new("RGB", (1344, 768))); assert out.size == (1920, 1080) and "upscaled" in note

def test_sync_and_polling_and_error():
    s, url = _server(); v = Image.new("RGB", (800, 1200), (10, 200, 30)); c = G.ImageClient("KEY", url)
    ep, tpl, _, _ = G.MODELS["nano-banana-2.1"]
    img = c.edit(ep, tpl, "nano-banana-2.1", G.blur_fill(v), "p", "2K"); assert img.size == (1600, 900)
    path, auth, body = SEEN[-1]
    assert path == "/nano-banana/images" and auth == "Bearer KEY"
    assert body["model"] == "nano-banana-2.1" and body["prompt"] == "p" and body["action"] == "edit"
    assert body["aspect_ratio"] == "16:9" and body["resolution"] == "2K" and body["count"] == 1
    assert body["image_urls"][0].startswith("data:image/jpeg;base64,")
    c.edit(ep, tpl, "nano-banana", v, "p", "4K"); assert SEEN[-1][2]["resolution"] == "1K"  # plain model is 1K only
    # task id first, then poll <prefix>/tasks
    assert c.edit("/poll/images", tpl, "nano-banana-2.1", v, "p", poll=0.01).size == (1600, 900)
    assert SEEN[-1][0] == "/poll/tasks" and SEEN[-1][2] == {"id": "t1", "action": "retrieve"}
    try: G.ImageClient("KEY", url).edit("/bad/images", tpl, "m", v, "p"); assert False
    except G.ImageError as e: assert "401" in str(e)
    try: G.ImageClient("", url).edit(ep, tpl, "m", v, "p"); assert False
    except G.ImageError as e: assert "token" in str(e)
