"""Shorts: vertical 1080x1920 clips from a finished video, with a slow zoom or a loop clip; the AI loop via a fake service."""
import json, subprocess, threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from PIL import Image

from soft_grind import animate, projects, settings, shorts, video
from soft_grind.suno import _write_tone


@pytest.fixture()
def vid(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path / "data")
    p = tmp_path / "mix-001"; (p / "tracks").mkdir(parents=True)
    for k in range(3):
        _write_tone(p / "tracks" / f"0{k+1} - t{k}.wav", 30, 220 + 40 * k)
    Image.new("RGB", (1920, 1080), (40, 50, 140)).save(p / "cover_source.png")
    projects.set_meta(p, quote="the city sleeps, we don't.", youtube_id="abc123")
    return p


def _clip(path, secs=3):
    subprocess.run([video.ffmpeg_exe(), "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s=360x640:r=24:d={secs}",
                    "-pix_fmt", "yuv420p", str(path)], check=True)


def test_parts_are_different_tracks_past_the_intro():
    parts = pick = shorts.pick_parts([200, 180, 240, 30], 3, 30)  # noqa
    assert len({i for i, _ in parts}) == 3 and all(s >= 0.33 * [200, 180, 240, 30][i] - 1 for i, s in pick if i != 3)
    assert shorts.pick_parts([], 2, 30) == []


def test_zoom_shorts_with_dust_are_vertical_and_link_to_the_mix(vid):
    rows = shorts.make_all(vid, 2, 6, "zoom", dust=True)
    assert len(rows) == 2 and rows[0]["track"] != rows[1]["track"]
    info = video.probe(shorts.folder(vid) / rows[0]["file"])
    assert info["size"] == (1080, 1920) and abs(info["duration"] - 6) < 0.5 and info["acodec"] == "aac"
    assert rows[0]["title"].startswith("the city sleeps, we don't.") and len(rows[0]["title"]) <= 100
    assert "https://youtu.be/abc123" in rows[0]["description"] and "#shorts" in rows[0]["description"]
    assert [r["file"] for r in shorts.listing(vid)] == ["short_1.mp4", "short_2.mp4"]


def test_loop_clip_shorts_repeat_the_clip_and_ping_pong_works(vid):
    _clip(vid / shorts.LOOP, 2)
    for ping in (False, True):
        out = shorts.render(vid, vid / "shorts" / f"l{ping}.mp4", projects.audio_files(vid / "tracks")[0], 5, 7, "lamp on.", "loop", False, ping)
        info = video.probe(out); assert info["size"] == (1080, 1920) and abs(info["duration"] - 7) < 0.5      # a 2 s clip fills 7 s


class _Fake(BaseHTTPRequestHandler):
    seen = {}
    def log_message(self, *a): pass
    def _send(self, code, body, ctype="application/json"):
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        raw = self.rfile.read(int(self.headers["Content-Length"]))
        if self.path == "/api/v1/files/":
            _Fake.seen["upload"] = (self.headers["Authorization"], b'name="file"' in raw and b"image/jpeg" in raw)
            url = f"http://127.0.0.1:{self.server.server_port}/uploads/abc.jpg"
            return self._send(200, json.dumps({"file_url": url, "mime": "image/jpeg"}).encode())
        body = json.loads(raw)
        if self.path == "/veo/videos":
            _Fake.seen["create"] = body
            return self._send(200, json.dumps({"success": True, "task_id": "t1"}).encode())
        if self.path == "/veo/tasks":
            _Fake.seen["polls"] = _Fake.seen.get("polls", 0) + 1
            if _Fake.seen["polls"] < 2:
                return self._send(200, json.dumps({"response": {"data": [{"state": "processing"}]}}).encode())
            url = f"http://127.0.0.1:{self.server.server_port}/out.mp4"
            return self._send(200, json.dumps({"response": {"success": True, "data": [{"state": "succeeded", "video_url": url}]}}).encode())
        self._send(404, b"{}")
    def do_GET(self):
        self._send(200, _Fake.mp4, "video/mp4")


def test_ai_animation_sends_the_vertical_picture_twice_and_saves_the_loop(vid, tmp_path):
    clip = tmp_path / "c.mp4"; _clip(clip, 2); _Fake.mp4 = clip.read_bytes(); _Fake.seen = {}
    srv = HTTPServer(("127.0.0.1", 0), _Fake); threading.Thread(target=srv.serve_forever, daemon=True).start()
    ep, tpl, _, _ = animate.MODELS["veo 3.1 fast (loops)"]
    animate.Animator("fake-key", base_url=f"http://127.0.0.1:{srv.server_port}").make(vid, vid / shorts.LOOP, ep, tpl, "rain", poll=0.05)
    c = _Fake.seen["create"]
    assert c["action"] == "image2video" and c["aspect_ratio"] == "9:16" and c["prompt"] == "rain"
    assert len(c["image_urls"]) == 2 and c["image_urls"][0] == c["image_urls"][1] and c["image_urls"][0].startswith("data:image/jpeg;base64,")
    assert video.probe(vid / shorts.LOOP)["duration"] > 1
    srv.shutdown()


def test_ai_animation_practice_mode_makes_a_free_clip(vid):
    animate.Animator("", mock=True).make(vid, vid / shorts.LOOP, "/veo/videos", {}, "x")
    assert video.probe(vid / shorts.LOOP)["size"] == (720, 1280)


def test_ai_animation_with_a_platform_token_sends_a_picture_link(vid, tmp_path):
    clip = tmp_path / "c.mp4"; _clip(clip, 2); _Fake.mp4 = clip.read_bytes(); _Fake.seen = {}
    srv = HTTPServer(("127.0.0.1", 0), _Fake); threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    ep, tpl, _, _ = animate.MODELS["veo 3.1 fast (loops)"]
    animate.Animator("fake-key", base_url=base, platform_token="fake-platform-token", upload_url=base + "/api/v1/files/").make(
        vid, vid / shorts.LOOP, ep, tpl, "rain", poll=0.05)
    assert _Fake.seen["upload"] == ("Bearer fake-platform-token", True)                 # uploaded as a multipart 'file'
    assert _Fake.seen["create"]["image_urls"] == [base + "/uploads/abc.jpg"] * 2         # the link, not the picture itself
    srv.shutdown()


def test_all_channels_failed_is_explained():
    from soft_grind import errors
    assert "link" in errors.explain('HTTP 502 from /veo/videos: {"error":"all_channels_failed"}')["advice"]
