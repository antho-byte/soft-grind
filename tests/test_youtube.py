import datetime as dt
import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
import requests

from soft_grind import projects, settings, youtube, youtube_worker

SEEN = {"tokens": [], "thumb": None, "meta": None, "chunks": []}


class H(BaseHTTPRequestHandler):
    store = bytearray()

    def log_message(self, *a): pass

    def _send(self, code, body=b"", headers=None):
        self.send_response(code)
        for k, v in (headers or {}).items(): self.send_header(k, v)
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); body = self.rfile.read(n)
        if self.path.startswith("/token"):
            form = dict(urllib.parse.parse_qsl(body.decode())); SEEN["tokens"].append(form)
            out = {"access_token": "AT"}
            if form["grant_type"] == "authorization_code": out["refresh_token"] = "RT-fake"
            return self._send(200, json.dumps(out).encode())
        if self.path.startswith("/upload/youtube/v3/videos"):
            assert self.headers["Authorization"] == "Bearer AT"
            SEEN["meta"] = json.loads(body); H.store = bytearray()
            return self._send(200, b"{}", {"Location": f"http://127.0.0.1:{self.server.server_port}/session/1"})
        if self.path.startswith("/upload/youtube/v3/thumbnails/set"):
            SEEN["thumb"] = (self.path, self.headers["Content-Type"], len(body))
            return self._send(200, b"{}")
        self._send(404)

    def do_PUT(self):
        n = int(self.headers.get("Content-Length", 0)); body = self.rfile.read(n)
        rng = self.headers["Content-Range"]; total = int(rng.split("/")[1]); start = int(rng.split(" ")[1].split("-")[0])
        assert start == len(H.store)
        H.store += body; SEEN["chunks"].append(len(body))
        if len(H.store) >= total:
            return self._send(200, json.dumps({"id": "vid123"}).encode())
        self._send(308, b"", {"Range": f"bytes=0-{len(H.store) - 1}"})


@pytest.fixture()
def env(tmp_path, monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(youtube, "API", base); monkeypatch.setattr(youtube, "TOKEN_URL", base + "/token")
    monkeypatch.setattr(youtube, "CHUNK", 262144)
    SEEN.update(tokens=[], thumb=None, meta=None, chunks=[])
    yield tmp_path
    srv.shutdown()


CLIENT = json.dumps({"installed": {"client_id": "fake-id.apps.example", "client_secret": "fake-secret"}})


def test_client_file_validation(env):
    with pytest.raises(youtube.YouTubeError): youtube.save_client("not json")
    with pytest.raises(youtube.YouTubeError): youtube.save_client(json.dumps({"web": {"client_id": "x"}}))
    youtube.save_client(CLIENT)
    assert youtube.has_client() and not youtube.connected()


def test_publish_at_amsterdam_time():
    now = dt.datetime(2026, 11, 1, 12, 0)
    assert youtube.publish_at("2026-11-09 15:00", now) == "2026-11-09T14:00:00Z"        # winter: +1
    assert youtube.publish_at("2026-07-06 15:00", dt.datetime(2026, 7, 1)) == "2026-07-06T13:00:00Z"   # summer: +2
    assert youtube.publish_at("2026-10-24 15:00", dt.datetime(2026, 10, 1)) == "2026-10-24T13:00:00Z"  # day before the clocks change
    assert youtube.publish_at("2026-10-26 15:00", dt.datetime(2026, 10, 1)) == "2026-10-26T14:00:00Z"  # day after
    assert youtube.publish_at("2026-11-01 08:00", now) is None                            # in the past: upload private, no schedule
    assert youtube.publish_at("", now) is None and youtube.publish_at("garbage", now) is None


def test_build_body_cleans_text():
    body = youtube.build_body({"title": "a <b> title", "description": "x<y", "tags": "lofi, city pop,\nstudy", "schedule": ""})
    assert body["snippet"]["title"] == "a b title" and body["snippet"]["tags"] == ["lofi", "city pop", "study"]
    assert body["status"]["privacyStatus"] == "private" and "publishAt" not in body["status"]
    with pytest.raises(youtube.YouTubeError): youtube.build_body({"title": ""})


def test_login_flow(env):
    youtube.save_client(CLIENT)

    def fake_browser(url):
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        assert q["code_challenge_method"] == "S256" and q["scope"] == youtube.SCOPE
        threading.Thread(target=lambda: requests.get(q["redirect_uri"], params={"code": "abc", "state": q["state"]}), daemon=True).start()

    youtube.login(timeout=20, open_browser=fake_browser)
    assert youtube.connected()
    ex = SEEN["tokens"][0]
    assert ex["grant_type"] == "authorization_code" and ex["code"] == "abc" and ex["code_verifier"]
    youtube.disconnect(); assert not youtube.connected()


def test_login_rejects_wrong_state(env):
    youtube.save_client(CLIENT)

    def bad_browser(url):
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        threading.Thread(target=lambda: requests.get(q["redirect_uri"], params={"code": "abc", "state": "forged"}), daemon=True).start()

    with pytest.raises(youtube.YouTubeError): youtube.login(timeout=20, open_browser=bad_browser)
    assert not youtube.connected()


def test_upload_end_to_end(env):
    youtube.save_client(CLIENT); youtube._write_private(youtube._token_file(), {"refresh_token": "RT-fake"})
    p = env / "mix-001"; p.mkdir()
    (p / "video.mp4").write_bytes(b"v" * 600_000); (p / "thumbnail.png").write_bytes(b"png")
    projects.set_meta(p, title="night shift.", description="d", tags="lofi, study", schedule="2999-01-04 15:00")
    youtube_worker.run(str(_job(p)))
    st = projects.youtube_status(p)
    assert st["state"] == "done", st
    assert projects.meta(p)["youtube_id"] == "vid123"
    assert len(SEEN["chunks"]) == 3 and sum(SEEN["chunks"]) == 600_000                  # sent in pieces, nothing lost
    assert SEEN["meta"]["snippet"]["title"] == "night shift." and SEEN["meta"]["status"]["publishAt"] == "2999-01-04T14:00:00Z"
    assert "videoId=vid123" in SEEN["thumb"][0] and SEEN["thumb"][1] == "image/png"
    with pytest.raises(RuntimeError): projects.start_youtube(p)                          # never uploaded twice by accident


def _job(p):
    projects.write_json(p / projects.YT, {"state": "queued", "updated": 1e12})
    return p / projects.YT


def test_start_youtube_preconditions(env):
    p = env / "mix-002"; p.mkdir()
    with pytest.raises(RuntimeError): projects.start_youtube(p)                          # no video
    (p / "video.mp4").write_bytes(b"v")
    with pytest.raises(RuntimeError): projects.start_youtube(p)                          # no title


def test_upload_queue_does_several_videos_one_after_another(env, monkeypatch):
    from soft_grind import queue
    youtube.save_client(CLIENT); youtube._write_private(youtube._token_file(), {"refresh_token": "RT-fake"})
    monkeypatch.setattr(projects, "_spawn", lambda *a, **k: None)                    # run the queue here, not as a process
    ps = []
    for n in ("mix-010", "mix-011", "mix-012"):
        p = env / n; p.mkdir(); (p / "video.mp4").write_bytes(b"v" * 1000)
        projects.set_meta(p, title=f"{n} title", description="d", tags="lofi", schedule="2999-01-04 15:00")
        ps.append(p)
    projects.set_meta(ps[2], youtube_id="old")                                      # already on youtube: skipped, never twice
    added = projects.start_queue("upload", ps)
    assert added == ["mix-010", "mix-011"]
    assert projects.youtube_status(ps[0])["state"] == "queued" and {i["name"]: i["stage"] for i in projects.list_projects(env)}["mix-010"] == "in the queue"
    queue.run(str(projects.queue_file("upload")))
    assert all(projects.meta(p)["youtube_id"] == "vid123" for p in ps[:2]) and projects.meta(ps[2])["youtube_id"] == "old"
    assert projects.read_json(projects.queue_file("upload"))["state"] == "done"
    assert {i["name"]: i["stage"] for i in projects.list_projects(env)}["mix-010"] == "scheduled"
