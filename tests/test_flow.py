"""End-to-end smoke test with mock Suno: generate -> tracklist -> thumbnail -> metadata."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import Image
from soft_grind import metadata, playlist, thumbnail as T
from soft_grind.suno import SunoClient, download

def test_flow():
    d = Path(tempfile.mkdtemp()); c = SunoClient(mock=True, mock_dir=d)
    tracks = []
    for i in range(3):
        for k, clip in enumerate(c.wait(c.generate("style", f"scene {i}")), 1):
            p = download(clip["audio_url"], d / "tracks" / f"{len(tracks)+1:02d}.wav")
            tracks.append({"title": clip["title"], "path": str(p), "duration": playlist.audio_duration(p)})
    assert len(tracks) == 6 and all(t["duration"] > 5 for t in tracks)
    ts = metadata.timestamps([t["duration"] for t in tracks])
    assert ts[0] == 0 and abs(ts[1] - (tracks[0]["duration"] - 4)) < 1e-6
    assert len(playlist.tracks_from_folder(d / "tracks")) == 6
    desc = metadata.make_description("q.", "s.", "scene.", tracks, "work", "Anri", "?", "#calm")
    assert "00:00 scene 0" in desc and "not affiliated" in desc and "suno" not in desc.lower()
    assert metadata.validate("t", tracks[:2], "ok") and not metadata.validate("t", tracks, "ok")
    assert metadata.validate("t", tracks, "静かな")  # japanese in pinned comment flagged
    im = Image.new("RGB", (1920, 1080), (90, 90, 200))
    assert T.render_thumbnail(im, "hello there.").size == (1280, 720)
    assert T.render_still(im, cyber=True).size == (1920, 1080)
    assert playlist.extract_ids("https://suno.com/playlist/12345678-1234-1234-1234-123456789abc")


def test_windows_file_uri():
    import nturl2path
    from soft_grind.suno import uri_to_path
    # Windows turns file:///C:/Users/antho/a%20b.wav into C:\Users\antho\a b.wav (the old code kept a leading slash)
    assert nturl2path.url2pathname("/C:/Users/antho/a%20b.wav") == "C:\\Users\\antho\\a b.wav"
    assert str(uri_to_path("file:///tmp/a%20b.wav")) == "/tmp/a b.wav"


def test_names_unique_and_on_topic():
    from soft_grind import names
    scenes = ["rainy window", "poolside sunset", "open laptop", "night shift"]
    out = names.suggest(scenes, 20, taken={"window seat rain"}, mood="calm", seed=1)
    assert len(out) == len(set(out)) == 20 and "window seat rain" not in out
    assert all(n == n.lower() and 1 <= len(n.split()) <= 5 and not n.endswith((" a", " b")) for n in out)
    assert out[0] in names.POOLS["rainy window"] and out[1] in names.POOLS["poolside sunset"]   # first names follow the scenes
    big = names.suggest(["rainy window"], 150, mood="groovy")                                      # never runs out, never repeats
    assert len(set(big)) == 150

def test_rename_files_only_inside_project_folder():
    import tempfile
    d = Path(tempfile.mkdtemp()); (d / "tracks").mkdir(); (d / "outside").mkdir()
    a = d / "tracks" / "01 - old.mp3"; b = d / "outside" / "x.mp3"; a.write_bytes(b"1"); b.write_bytes(b"2")
    ts = [{"title": "soft landing", "path": str(a)}, {"title": "other", "path": str(b)}]
    playlist.rename_files(ts, d / "tracks")
    assert (d / "tracks" / "01 - soft landing.mp3").exists() and not a.exists() and b.exists()
    assert ts[0]["path"].endswith("01 - soft landing.mp3")
