"""Real ffmpeg run on tiny mock tracks: duration = sum - crossfades, 1920x1080 h264 + aac, loudness near -14 LUFS."""
import re, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import Image
from soft_grind import playlist, video
from soft_grind.suno import _write_tone

def _setup(n=3, secs=8):
    d = Path(tempfile.mkdtemp())
    tracks = []
    for i in range(n):
        p = d / f"{i+1:02d}.wav"; _write_tone(p, secs, 180 + 60 * i); tracks.append(p)
    Image.new("RGB", (1920, 1080), (94, 94, 224)).save(d / "still.png")
    return d, tracks

def _lufs(path):
    r = subprocess.run([video.ffmpeg_exe(), "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    return float(re.findall(r"I:\s+(-?\d+\.\d) LUFS", r.stderr)[-1])

def test_render_video():
    d, tracks = _setup()
    durs = [playlist.audio_duration(t) for t in tracks]
    seen = []
    out = video.render_video(tracks, d / "still.png", d / "video.mp4", durs, crossfade=2.0, fade_in=1, fade_out=2,
                             on_progress=lambda f, m: seen.append((f, m)))
    info = video.probe(out)
    assert abs(info["duration"] - (sum(durs) - 2 * 2.0)) < 0.6            # 24 - 4 = 20 s
    assert info["vcodec"] == "h264" and info["size"] == (1920, 1080) and info["acodec"] == "aac"
    assert abs(_lufs(out) - (-14.0)) < 1.5
    assert seen[0][0] == 0.0 and seen[-1] == (1.0, "done") and all(a <= b for (a, _), (b, _) in zip(seen, seen[1:]))
    assert not (d / "video.partial.mp4").exists()

def test_crossfade_is_capped_and_errors():
    d, tracks = _setup(n=2, secs=4)
    out = video.render_video(tracks, d / "still.png", d / "v.mp4", [4.0, 4.0], crossfade=30.0)   # longer than a track: capped to half
    assert 5.5 < video.probe(out)["duration"] < 6.5                       # 8 - 2
    for args in (([], d / "still.png"), (tracks, d / "missing.png")):
        try: video.render_video(args[0], args[1], d / "x.mp4", [4.0, 4.0]); assert False
        except video.VideoError: pass


def test_preview_is_small_and_made_with_every_render():
    d, tracks = _setup()
    out = video.render_video(tracks, d / "still.png", d / "video.mp4", [playlist.audio_duration(t) for t in tracks], crossfade=2.0, fade_in=1, fade_out=2)
    prev = d / "preview.mp4"
    info = video.probe(prev)
    assert prev.exists() and info["size"][0] == 640 and info["vcodec"] == "h264" and info["acodec"] == "aac"
    assert 19 < info["duration"] < 21 and prev.stat().st_size < out.stat().st_size                      # whole 20 s clip, smaller file
    video.make_preview(out, d / "p2.mp4", seconds=5)
    assert 4 < video.probe(d / "p2.mp4")["duration"] < 6                                                  # cut to the asked length


def test_film_look_renders_with_every_effect_and_keeps_the_audio_right():
    d, tracks = _setup(n=2, secs=6)
    durs = [playlist.audio_duration(t) for t in tracks]
    look = {"grain": 2, "vignette": True, "flicker": True, "dust": True, "tint": "warm", "fps": 12}
    out = video.render_video(tracks, d / "still.png", d / "look.mp4", durs, crossfade=2.0, fade_in=1, fade_out=2, look=look)
    info = video.probe(out)
    assert abs(info["duration"] - (sum(durs) - 2.0)) < 0.6 and info["size"] == (1920, 1080) and info["vcodec"] == "h264"
    assert abs(_lufs(out) - (-14.0)) < 1.5                                       # loudness is untouched by the picture effects
    clip = video.look_preview(d / "still.png", d / "t.mp4", look, 2)
    assert abs(video.probe(clip)["duration"] - 2) < 0.5


def test_look_settings_are_cleaned_and_off_means_the_plain_fast_path():
    assert video.normalize_look(None) is None and video.normalize_look({}) is None
    assert video.normalize_look({"grain": 0, "vignette": False, "tint": "none"}) is None
    n = video.normalize_look({"grain": 9, "tint": "sparkle", "fps": 500, "vignette": 1})
    assert n["grain"] == 0 and n["tint"] == "none" and n["fps"] == 30 and n["vignette"] is True
    import pytest
    with pytest.raises(video.VideoError):
        video.look_preview(Path("x.png"), Path("y.mp4"), {})


def test_film_look_per_video_choice_beats_the_default(monkeypatch):
    import importlib, os
    os.environ["SOFTGRIND_HOME"] = tempfile.mkdtemp()
    from soft_grind import settings, projects
    importlib.reload(settings); importlib.reload(projects)
    p = Path(os.environ["SOFTGRIND_HOME"]) / "v"; p.mkdir()
    assert projects.film_look(p) is None
    settings._write_settings(film_look_default={"grain": 1, "fps": 15})
    assert projects.film_look(p)["grain"] == 1                                    # the default applies to a video with no choice
    projects.set_meta(p, film_look={})
    assert projects.film_look(p) is None                                          # "off" on this video wins
    projects.set_meta(p, film_look={"vignette": True})
    assert projects.film_look(p)["vignette"] is True
