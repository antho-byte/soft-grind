"""update.py against a local fake GitHub (commit sha + zip archive)."""
import io, os, shutil, subprocess, sys, tempfile, threading, zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent

def make_zip(version):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("soft-grind-main/app.py", f"# app {version}\n")
        z.writestr("soft-grind-main/soft_grind/new_module.py", f"V={version}\n")
        z.writestr("soft-grind-main/requirements.txt", "streamlit\n")
        z.writestr("soft-grind-main/update.py", (ROOT / "update.py").read_text())   # the updater ships itself
        for extra in ("README.md", "fonts/f.txt", "tests/t.txt", ".streamlit/config.toml"):  # every other CODE entry
            z.writestr(f"soft-grind-main/{extra}", "x\n")
    return b.getvalue()

STATE = {"sha": "a" * 40, "v": 1, "fail": False}
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if STATE["fail"]: self.send_response(500); self.end_headers(); return
        body = STATE["sha"].encode() if "/commits/" in self.path else make_zip(STATE["v"])
        self.send_response(200); self.end_headers(); self.wfile.write(body)

def run(app, port):
    env = {**os.environ, "SOFTGRIND_UPDATE_API": f"http://127.0.0.1:{port}", "SOFTGRIND_UPDATE_DL": f"http://127.0.0.1:{port}",
           "NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"}
    return subprocess.run([sys.executable, str(app / "update.py")], env=env, capture_output=True, text=True).stdout

def test_update_flow():
    srv = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
    app = Path(tempfile.mkdtemp()) / "soft-grind"; app.mkdir(); shutil.copy(ROOT / "update.py", app)
    (app / "keep_me.txt").write_text("user file"); (app / "app.py").write_text("# old\n")
    out = run(app, srv.server_port); assert "updated to aaaaaaa" in out, out
    assert (app / "app.py").read_text() == "# app 1\n" and (app / "soft_grind/new_module.py").exists()
    assert (app / "keep_me.txt").read_text() == "user file"          # never touches files outside the code list
    assert "up to date" in run(app, srv.server_port)                  # same sha -> no download
    STATE.update(sha="b" * 40, v=2); out = run(app, srv.server_port)
    assert "updated to bbbbbbb" in out and (app / "app.py").read_text() == "# app 2\n"
    import shutil as _sh; _sh.rmtree(app / ".streamlit")                # a missing expected file forces a re-download
    assert "updated to bbbbbbb" in run(app, srv.server_port) and (app / ".streamlit/config.toml").exists()
    STATE["fail"] = True; out = run(app, srv.server_port)             # GitHub down -> keep current version
    assert "skipped" in out and (app / "app.py").read_text() == "# app 2\n"
