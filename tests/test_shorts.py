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
        info = video.probe(out); assert info["size"] == (1080, 1920)
        period = 4 if ping else 2                                      # whole loops only, so the picture ends where it began
        assert abs(info["duration"] - 8) < 0.4 and round(info["duration"]) % period == 0


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


def test_seamless_shorts_do_not_fade_to_silence_at_the_loop_point(vid):
    """Reels replay automatically: a seamless Short starts and ends at full sound, so the replay has no gap."""
    import numpy as np
    track = projects.audio_files(vid / "tracks")[0]
    def edges(out):
        r = subprocess.run([video.ffmpeg_exe(), "-v", "error", "-i", str(out), "-ac", "1", "-ar", "8000", "-f", "s16le", "-"], capture_output=True)
        a = np.frombuffer(r.stdout, dtype="<i2").astype(float)
        rms = lambda x: float(np.sqrt((x ** 2).mean()))
        mid = rms(a[len(a) // 2 - 2000: len(a) // 2 + 2000])
        return rms(a[400:2000]) / mid, rms(a[-2000:-400]) / mid
    s_in, s_out = edges(shorts.render(vid, vid / "shorts" / "s.mp4", track, 5, 8, "lamp on.", "zoom", False, False, True))
    f_in, f_out = edges(shorts.render(vid, vid / "shorts" / "f.mp4", track, 5, 8, "lamp on.", "zoom", False, False, False))
    assert s_in > 0.6 and s_out > 0.6                                  # full sound at both ends
    assert f_out < 0.5                                                  # the old way faded out at the end


def test_best_start_finds_the_fullest_stretch(tmp_path):
    import numpy as np, wave
    rate = 8000; t = np.arange(60 * rate) / rate
    amp = np.where((t > 30) & (t < 45), 0.8, 0.1)                       # quiet song with one full stretch at 30-45 s
    s = (amp * np.sin(2 * np.pi * 330 * t) * 32767).astype("<i2")
    p = tmp_path / "x.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(s.tobytes())
    b = shorts.best_start(p, 60, 12)
    assert b is not None and 29 <= b <= 34


def test_captions_slots_and_posted_marks(vid, monkeypatch):
    import datetime as dt
    shorts.make_all(vid, 2, 6, "zoom")
    m = projects.meta(vid); row = shorts.listing(vid)[0]
    cap = shorts.captions(m, row)
    assert cap["youtube_title"].startswith("the city sleeps, we don't.") and cap["youtube_title"].endswith("#shorts")
    assert "https://youtu.be/abc123" in cap["youtube_description"] and "link in bio" in cap["instagram"] and "#lofi" in cap["tiktok"]
    shorts.set_posted(vid, row["file"], "instagram", True)
    assert "instagram" in shorts.listing(vid)[0]["posted"]
    shorts.set_posted(vid, row["file"], "instagram", False)
    assert shorts.listing(vid)[0].get("posted") == {}
    now = dt.datetime(2026, 11, 11, 12, 0)
    s = shorts.short_slots(vid.parent, 3, now)
    assert [x.strftime("%d %H") for x in s] == ["11 18", "12 18", "13 18"]
    shorts._update_row(vid, row["file"], schedule="2026-11-12 18:00")
    assert [x.day for x in shorts.short_slots(vid.parent, 2, now)] == [11, 13]          # a day with a Short is skipped


def test_ai_loop_of_the_same_picture_is_reused_for_free(vid, monkeypatch):
    calls = []
    monkeypatch.setattr(animate.Animator, "make", lambda self, pdir, out, *a, **k: (calls.append(1), _clip(out, 2)))
    ep, tpl, _, _ = animate.MODELS["veo 3.1 fast (loops)"]
    for _ in range(2):
        projects.write_json(vid / animate.JOB, {"state": "queued", "updated": 1e12,
                                                "spec": {"model": "veo", "endpoint": ep, "template": tpl, "prompt": "rain", "mock": False}})
        animate.run(str(vid / animate.JOB))
    assert len(calls) == 1 and "reused" in projects.meta(vid)["loop_model"]               # paid once, second time free


def test_short_upload_to_youtube_saves_the_id(vid, monkeypatch):
    from soft_grind import youtube
    sent = {}
    def fake_upload(path, meta, on_progress=None, now=None):
        sent.update(meta, path=str(path)); return "short123"
    monkeypatch.setattr(youtube, "upload_video", fake_upload)
    monkeypatch.setattr(projects, "_spawn", lambda *a, **k: None)
    import datetime as dt
    shorts.make_all(vid, 1, 6, "zoom")
    f = shorts.listing(vid)[0]["file"]
    shorts.start_upload(vid, f, dt.datetime(2026, 11, 20, 18, 0))
    shorts.run_upload(str(shorts._yt_job(vid, f)))
    row = shorts.listing(vid)[0]
    assert row["youtube_id"] == "short123" and "youtube" in row["posted"] and row["schedule"] == "2026-11-20 18:00"
    assert sent["schedule"] == "2026-11-20 18:00" and sent["title"].endswith("#shorts") and sent["path"].endswith(f)
    import pytest
    with pytest.raises(RuntimeError):
        shorts.start_upload(vid, f, dt.datetime(2026, 11, 21, 18, 0))                   # never twice


def test_bundle_has_the_clips_and_one_captions_file(vid):
    import io, zipfile
    shorts.make_all(vid, 2, 6, "zoom")
    rows = shorts.all_shorts(vid.parent)
    z = zipfile.ZipFile(io.BytesIO(shorts.bundle(rows)))
    names_ = z.namelist()
    assert "captions.txt" in names_ and sum(n.endswith(".mp4") for n in names_) == 2
    txt = z.read("captions.txt").decode()
    assert "INSTAGRAM" in txt and "TIKTOK" in txt and "the city sleeps, we don't." in txt
