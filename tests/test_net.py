"""Network failures become plain messages (and never crash a page); safe retries only."""
import os, sys, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["NO_PROXY"] = "127.0.0.1"; os.environ["no_proxy"] = "127.0.0.1"
import pytest
from soft_grind import ai, imagegen, net, suno
from PIL import Image

DEAD = "http://127.0.0.1:9"      # nothing listens here = internet down

def test_every_client_turns_a_dead_network_into_its_own_error():
    with pytest.raises(ai.AIError, match="Could not reach"):
        ai.AIClient("K", "m", DEAD).chat("s", "u")
    with pytest.raises(suno.SunoError, match="Could not reach"):
        suno.SunoClient("K", DEAD).generate("style", "title")
    with pytest.raises(suno.SunoError, match="Could not reach"):
        suno.SunoClient("K", DEAD).get_task("t1")
    with pytest.raises(imagegen.ImageError, match="Could not reach"):
        imagegen.ImageClient("K", DEAD).edit("/nano-banana/images", imagegen.NANO_TEMPLATE, "m", Image.new("RGB", (64, 64)), "p")
    with pytest.raises(suno.SunoError, match="Could not reach"):
        suno.download(DEAD + "/a.mp3", Path(os.environ.get("TMPDIR", "/tmp")) / "never.mp3")
    assert not (Path(os.environ.get("TMPDIR", "/tmp")) / "never.mp3").exists()                  # no half-written file

def test_retry_only_on_connection_errors_never_after_a_timeout():
    calls = {"n": 0}
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self): calls["n"] += 1; self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
    s = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=s.serve_forever, daemon=True).start()
    assert net.request("GET", f"http://127.0.0.1:{s.server_port}/", retries=2).text == "ok" and calls["n"] == 1   # no needless repeats
    import time; t = time.time()
    with pytest.raises(Exception): net.request("GET", DEAD, retries=1, delay=0.1)
    assert time.time() - t >= 0.1                                                                  # it did retry the dead connection once

def test_friendly_messages():
    import requests
    assert "internet" in net.friendly(requests.exceptions.ConnectionError())
    assert "too long" in net.friendly(requests.exceptions.ReadTimeout())
    assert "secure" in net.friendly(requests.exceptions.SSLError())
