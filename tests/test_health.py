import json, os, sys, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["NO_PROXY"] = "127.0.0.1"; os.environ["no_proxy"] = "127.0.0.1"
os.environ["SOFTGRIND_HOME"] = tempfile.mkdtemp()
from soft_grind import health, projects, settings

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, status, body):
        self.send_response(status); self.send_header("content-type", "application/json"); self.end_headers(); self.wfile.write(json.dumps(body).encode())
    def do_GET(self): self._send(200, {})
    def do_POST(self):
        n = int(self.headers["content-length"]); self.rfile.read(n); auth = self.headers.get("authorization", "")
        if self.path.endswith("/chat/completions"):
            if "BAD" in auth: return self._send(401, {"error": {"code": "invalid_token", "message": "The specified token is invalid or wrong."}})
            return self._send(200, {"choices": [{"message": {"content": "ok"}}], "usage": {"cost": {"amount": 0.0001}}})
        kind = auth.replace("Bearer ", "")
        status, err = {"BAD": (401, "invalid_token"), "OTHERAPI": (400, "token_mismatched"), "OFF": (400, "disabled")}.get(kind, (404, "not_found"))
        self._send(status, {"error": {"code": err, "message": "x"}})

def _base():
    s = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=s.serve_forever, daemon=True).start(); return f"http://127.0.0.1:{s.server_port}"

def test_key_checks_tell_accepted_from_rejected():
    b = _base()
    assert health.check_key("k", "GOOD", "/suno/tasks", b)["status"] == "ok"                      # service answers 'task not found': key accepted
    r = health.check_key("k", "BAD", "/suno/tasks", b); assert r["status"] == "fail" and "rejected" in r["detail"]
    r = health.check_key("k", "OTHERAPI", "/suno/tasks", b); assert r["status"] == "fail" and "not allowed" in r["detail"]
    assert health.check_key("k", "OFF", "/suno/tasks", b)["status"] == "fail"
    assert health.check_key("k", "", "/suno/tasks", b)["status"] == "warn"
    assert "not saved" in health.check_key("k", "GOOD", "/suno/tasks", b, saved=False)["detail"]
    assert health.check_key("k", "GOOD", "/suno/tasks", "http://127.0.0.1:9")["status"] == "fail"       # internet down: plain message
    assert health.check_internet(b)["status"] == "ok" and health.check_internet("http://127.0.0.1:9")["status"] == "fail"

def test_ai_check_uses_a_tiny_call():
    b = _base()
    r = health.check_ai("GOOD", "claude-haiku-4-5-20251001", b); assert r["status"] == "ok" and "0.0001" in r["detail"]
    assert health.check_ai("BAD", "m", b)["status"] == "fail" and health.check_ai("", "m", b)["status"] == "warn"

def test_folders_disk_ffmpeg_and_background_jobs_on_this_computer():
    d = Path(tempfile.mkdtemp())
    assert health.check_folder("f", d / "new")["status"] == "ok" and health.check_folder("f", None)["status"] == "warn"
    assert health.check_disk(d)["status"] in ("ok", "warn") and health.check_ffmpeg()["status"] == "ok"
    r = health.check_background_jobs(); assert r["status"] == "ok", r                                  # real detached process, real answer

def test_diagnostics_never_contain_secrets():
    fake = "feedface" * 4                                                                              # a made-up 32-character key
    settings.save_keys(fake, "cafebabe" * 4, "deadbeef" * 4, "claude-haiku")
    root = settings.projects_dir(); pd = root / "mix-001"; pd.mkdir(parents=True)
    (pd / "auto.log").write_text(f"error calling with Bearer {fake} and key {'cafebabe' * 4} and AUTHORIZATION: Bearer abcdefgh12345678\n")
    projects.write_json(pd / projects.AUTO, {"state": "failed", "error": f"token {fake} rejected", "updated": time.time(), "spec": {}})
    text = health.diagnostics([fake])
    assert "mix-001" in text and "failed" in text and "python:" in text and "packages:" in text
    for s in (fake, "cafebabe" * 4, "deadbeef" * 4, "abcdefgh12345678"): assert s not in text, s
    assert "keys set: suno=True image=True ai=True" in text
