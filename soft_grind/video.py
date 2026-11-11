"""Mix the tracks (crossfade, fades, loudness) and put them under the still image -> video.mp4 (ffmpeg).

Loudness is two-pass: pass 1 measures the finished mix, pass 2 applies exactly that correction (YouTube target -14 LUFS,
true peak -1.5 dB). The crossfade must equal the one used for the tracklist timestamps, or the chapters drift.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

TARGET_LUFS, TARGET_TP, TARGET_LRA = -14.0, -1.5, 11.0


class VideoError(RuntimeError):
    pass


def ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()          # bundled with the pip package: nothing to install by hand
    except Exception:
        found = shutil.which("ffmpeg")
        if found:
            return found
    raise VideoError("ffmpeg was not found. Restart the app so it can install it (pip install imageio-ffmpeg).")


TRACK_LUFS = -16.0          # every song is first brought to this level, so no song jumps out or sinks away in the mix
MAX_GAIN = 9.0


def track_loudness(path: Path) -> float | None:
    """Integrated loudness (LUFS) of one song, cached next to it (keyed by size and time, so a changed file is measured again)."""
    path = Path(path)
    cache = path.parent / ".levels.json"
    try:
        db = json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        db = {}
    st = path.stat()
    key = f"{path.name}|{st.st_size}|{int(st.st_mtime)}"
    if key in db:
        return db[key]
    r = subprocess.run([ffmpeg_exe(), "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=framelog=quiet", "-f", "null", "-"],
                       capture_output=True, text=True)
    found = re.findall(r"I:\s+(-?\d+(?:\.\d+)?) LUFS", r.stderr)
    lufs = float(found[-1]) if found else None
    if lufs is not None and lufs < -69:                       # silence: no meaningful level
        lufs = None
    db = {k: v for k, v in db.items() if not k.startswith(path.name + "|")}
    db[key] = lufs
    try:
        cache.write_text(json.dumps(db), encoding="utf-8")
    except OSError:
        pass
    return lufs


def track_gains(tracks: list[Path], on_progress=None) -> list[float]:
    """dB per song to bring it to TRACK_LUFS (limited to +/- MAX_GAIN, so a strange measurement can never blow a song up)."""
    out = []
    for i, t in enumerate(tracks):
        lufs = track_loudness(t)
        out.append(0.0 if lufs is None else round(max(-MAX_GAIN, min(MAX_GAIN, TRACK_LUFS - lufs)), 2))
        if on_progress:
            on_progress((i + 1) / max(1, len(tracks)))
    return out


def mix_graph(n: int, first_input: int, crossfade: float, total: float, fade_in: float, fade_out: float,
              gains: list[float] | None = None) -> str:
    """Filter graph ending in the label [mix]: n inputs -> equal format (and level) -> chained crossfades -> fade in / out."""
    g = gains or [0.0] * n
    parts = [f"[{first_input + i}:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo"
             + (f",volume={g[i]:g}dB" if g[i] else "") + f"[a{i}]" for i in range(n)]
    last = "a0"
    for i in range(1, n):
        parts.append(f"[{last}][a{i}]acrossfade=d={crossfade:g}:c1=tri:c2=tri[x{i}]")
        last = f"x{i}"
    fades = []
    if fade_in > 0:
        fades.append(f"afade=t=in:st=0:d={fade_in:g}")
    if fade_out > 0:
        fades.append(f"afade=t=out:st={max(0.0, total - fade_out):.3f}:d={fade_out:g}")
    parts.append(f"[{last}]{','.join(fades) if fades else 'anull'}[mix]")
    return ";".join(parts)


def _run(cmd: list[str], total: float, on_progress: Callable[[float], None] | None) -> str:
    """Run ffmpeg, report 0..1 progress from its -progress output, return what it wrote to stderr."""
    with tempfile.TemporaryFile("w+") as err:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err, stdin=subprocess.DEVNULL, text=True)
        for line in proc.stdout:
            if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
                try:
                    t = int(line.split("=")[1]) / 1_000_000
                    if on_progress and total > 0:
                        on_progress(min(1.0, t / total))
                except ValueError:
                    pass
        code = proc.wait()
        err.seek(0)
        text = err.read()
    if code != 0:
        raise VideoError("ffmpeg failed: " + "\n".join(text.strip().splitlines()[-6:]))
    return text


def measure_loudness(inputs: list[Path], graph: str, total: float, on_progress=None) -> dict:
    cmd = [ffmpeg_exe(), "-hide_banner", "-nostats", "-progress", "pipe:1"]
    for p in inputs:
        cmd += ["-i", str(p)]
    cmd += ["-filter_complex",
            f"{graph};[mix]loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:LRA={TARGET_LRA}:print_format=json[out]",
            "-map", "[out]", "-f", "null", "-"]
    text = _run(cmd, total, on_progress)
    blocks = re.findall(r"\{[^{}]*\}", text, flags=re.S)
    if not blocks:
        raise VideoError("Could not measure the loudness of the mix.")
    return json.loads(blocks[-1])


# ---------- film look: light film like an old print: a few dust specks, thin vertical scratches, soft colour ----------
GRAIN = {0: 0, 1: 7, 2: 14}                      # strength of the luma noise: off / low / medium
TINTS = {"none": "", "warm": "colorbalance=rs=.04:gs=.01:bs=-.04:rm=.03:bm=-.03,eq=saturation=1.05",
         "faded": "curves=all='0/0.05 1/0.95',eq=contrast=0.94:saturation=0.88"}
LOOK_DEFAULT = {"grain": 0, "vignette": False, "flicker": False, "dust": True, "scratches": False, "tint": "none", "fps": 12}


def normalize_look(look: dict | None) -> dict | None:
    """A clean look dict, or None when every effect is off (then the fast still-picture path is used)."""
    if not look:
        return None
    out = {"grain": int(look.get("grain", 0)) if int(look.get("grain", 0)) in GRAIN else 0,
           "vignette": bool(look.get("vignette")), "flicker": bool(look.get("flicker")), "dust": bool(look.get("dust")),
           "scratches": bool(look.get("scratches")),
           "tint": look.get("tint") if look.get("tint") in TINTS else "none",
           "fps": min(30, max(8, int(look.get("fps", 15))))}
    return out if (out["grain"] or out["vignette"] or out["flicker"] or out["dust"] or out["scratches"] or out["tint"] != "none") else None


_BLACK0 = "lutyuv=y='clip((val-16)*255/219,0,255)'"        # an overlay's black must add nothing (video-range black is 16, not 0)


def dust_texture() -> Path:
    """A 3840x2160 black picture with random dust: mostly tiny specks, some soft blobs, a few short hairs. Made once, then reused."""
    from . import settings
    path = settings.DATA_DIR / "cache" / "dust-v3.png"
    if path.exists():
        return path
    import numpy as np
    from PIL import Image, ImageChops, ImageDraw, ImageFilter
    rng = np.random.default_rng(20240607)
    W, H = 3840, 2160
    small, big = Image.new("L", (W, H), 0), Image.new("L", (W, H), 0)
    d, db = ImageDraw.Draw(small), ImageDraw.Draw(big)
    for _ in range(100):                                          # specks of different size and brightness
        x, y = rng.uniform(0, W), rng.uniform(0, H)
        r = float(rng.choice([0.8, 1.2, 1.8, 2.6], p=[0.45, 0.30, 0.18, 0.07]))
        d.ellipse([x - r, y - r, x + r, y + r], fill=int(rng.uniform(80, 255)))
    for _ in range(8):                                           # bigger, fainter, soft blobs
        x, y, r = rng.uniform(0, W), rng.uniform(0, H), rng.uniform(4, 9)
        db.ellipse([x - r, y - r, x + r, y + r], fill=int(rng.uniform(45, 110)))
    for _ in range(8):                                           # short wandering hairs
        x, y, ang = rng.uniform(0, W), rng.uniform(0, H), rng.uniform(0, 6.28)
        pts = [(x, y)]
        for _ in range(int(rng.integers(4, 9))):
            ang += rng.normal(0, 0.5)
            x += float(np.cos(ang)) * 4; y += float(np.sin(ang)) * 4
            pts.append((x, y))
        d.line(pts, fill=int(rng.uniform(70, 150)), width=1)
    img = ImageChops.lighter(small.filter(ImageFilter.GaussianBlur(0.6)), big.filter(ImageFilter.GaussianBlur(2.5)))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def _hash(salt: str, group: int = 3, var: str = "N") -> str:
    """A repeatable pseudo-random number 0..1 that changes every `group` frames (a scratch lives for a few frames)."""
    return f"mod(abs(sin(floor({var}/{group})*{salt})*43758.5453),1)"


def look_graph(look: dict, dust_input: int = 1) -> str:
    """The video part of the filter graph: [0:v] -> [v]. The dust picture (see dust_texture) is input number `dust_input`."""
    fps = look["fps"]
    steps = ["scale=1920:1080:force_original_aspect_ratio=decrease", "pad=1920:1080:(ow-iw)/2:(oh-ih)/2", "format=yuv420p"]
    if TINTS[look["tint"]]:
        steps.append(TINTS[look["tint"]])
    if look["vignette"]:
        steps.append("vignette=PI/5")
    if look["flicker"]:
        steps.append("eq=brightness='0.012*sin(2*PI*t*1.3)+0.008*sin(2*PI*t*7.7)':eval=frame")
    g = "[0:v]" + ",".join(steps) + "[base]"
    last = "base"
    n = 0

    def overlay(source: str, opacity: float) -> None:
        nonlocal g, last, n
        n += 1
        g += f";{source}[ov{n}];[{last}][ov{n}]blend=c0_mode=screen:c0_opacity={opacity}:c1_expr=A:c2_expr=A:shortest=0[l{n}]"
        last = f"l{n}"

    if look["dust"]:
        # a big picture of dust (real random positions, drawn once) of which a different random window is shown every frame
        w = lambda salt: f"floor({_hash(salt, 1, 'n')}*1920)"
        h = lambda salt: f"floor({_hash(salt, 1, 'n')}*1080)"
        overlay(f"[{dust_input}:v]crop=1920:1080:x='{w('12.9898')}':y='{h('78.233')}',format=gray,format=yuv420p,{_BLACK0}", 0.45)
    if look["scratches"]:
        # thin vertical lines that appear for a few frames at a random place, now and then. One row of pixels, stretched to full height.
        def line(salt_x: str, salt_p: str, prob: float) -> str:
            x0 = f"1920*{_hash(salt_x)}"
            return (f"color=c=black:s=1920x1:r={fps},format=gray,"
                    f"geq=lum='255*lt({_hash(salt_p)},{prob})*lt(abs(X-{x0}),1.2)*(0.4+0.6*{_hash('5.13')})',"
                    f"scale=1920:1080:flags=neighbor,format=yuv420p,{_BLACK0}")
        overlay(line("12.9898", "78.233", 0.06), 0.5)
        overlay(line("39.346", "11.135", 0.03), 0.35)
    tail = []
    if look["grain"]:
        tail.append(f"noise=c0s={GRAIN[look['grain']]}:c0f=t+u")      # luma only, changes every frame: looks like film, not TV static
    tail.append("format=yuv420p")
    return g + f";[{last}]" + ",".join(tail) + "[v]"


def _video_args(look: dict | None) -> tuple[list[str], list[str]]:
    """(input args before the still, encoder args). The plain path is unchanged: 2 fps still picture."""
    if look:
        return ["-framerate", str(look["fps"])], ["-r", str(look["fps"]), "-c:v", "libx264", "-preset", "veryfast",
                                                  *(["-tune", "grain"] if look["grain"] else []), "-crf", "25",
                                                  "-maxrate", "3500k", "-bufsize", "7000k"]      # grain would otherwise grow files to many GB
    return ["-framerate", "2"], ["-r", "2", "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage", "-crf", "23"]


def render_video(tracks: list[Path], still: Path, out: Path, durations: list[float], crossfade: float = 4.0,
                 fade_in: float = 3.0, fade_out: float = 6.0, on_progress: Callable[[float, str], None] | None = None,
                 look: dict | None = None) -> Path:
    look = normalize_look(look)
    if not tracks:
        raise VideoError("No tracks to mix.")
    if not Path(still).exists():
        raise VideoError("No still image yet: make the thumbnail and still first.")
    n = len(tracks)
    shortest = min(d for d in durations if d > 0) if any(d > 0 for d in durations) else 10
    cf = max(0.0, min(crossfade, shortest / 2)) if n > 1 else 0.0           # a crossfade can never be longer than a track
    total = sum(durations) - cf * (n - 1)
    fade_out = min(fade_out, total / 3)
    fade_in = min(fade_in, total / 3)

    def prog(lo, hi, msg):
        return (lambda f: on_progress(lo + (hi - lo) * f, msg)) if on_progress else None

    if on_progress:
        on_progress(0.0, "measuring loudness")
    gains = track_gains(list(tracks), prog(0.0, 0.1, "levelling the songs"))
    audio_graph = mix_graph(n, 0, cf, total, fade_in, fade_out, gains)
    m = measure_loudness(list(tracks), audio_graph, total, prog(0.1, 0.4, "measuring loudness"))

    graph = mix_graph(n, 1, cf, total, fade_in, fade_out, gains) + (
        f";[mix]loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:LRA={TARGET_LRA}"
        f":measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
        f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true[out]")
    out = Path(out); out.parent.mkdir(parents=True, exist_ok=True)
    partial = out.with_name(out.stem + ".partial.mp4")
    in_args, enc = _video_args(look)
    cmd = [ffmpeg_exe(), "-hide_banner", "-nostats", "-y", "-progress", "pipe:1", "-loop", "1", *in_args, "-i", str(still)]
    for p in tracks:
        cmd += ["-i", str(p)]
    if look:                                                  # the picture goes through the graph too
        if look["dust"]:                                      # the dust picture is the last input, after the tracks
            cmd += ["-loop", "1", "-framerate", str(look["fps"]), "-i", str(dust_texture())]
        cmd += ["-filter_complex", look_graph(look, len(tracks) + 1) + ";" + graph, "-map", "[v]", "-map", "[out]", *enc]
    else:
        cmd += ["-filter_complex", graph, "-map", "0:v", "-map", "[out]",
                "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p", *enc]
    cmd += ["-c:a", "aac", "-b:a", "256k", "-ar", "44100", "-t", f"{total:.3f}", "-movflags", "+faststart", "-f", "mp4", str(partial)]
    _run(cmd, total, prog(0.4, 1.0, "building the video"))
    os.replace(partial, out)
    try:
        make_preview(out, out.with_name("preview.mp4"))
    except VideoError:
        pass                                              # the preview is a convenience, never a reason to fail
    if on_progress:
        on_progress(1.0, "done")
    return out


def look_preview(still: Path, out: Path, look: dict, seconds: int = 20) -> Path:
    """A short silent clip of the picture with the film look, at full size, so the grain can be judged before the long render."""
    look = normalize_look(look)
    if not look:
        raise VideoError("Every effect is off: nothing to preview.")
    out = Path(out)
    partial = out.with_name(out.stem + ".partial.mp4")
    in_args, enc = _video_args(look)
    extra = ["-loop", "1", "-framerate", str(look["fps"]), "-i", str(dust_texture())] if look["dust"] else []
    _run([ffmpeg_exe(), "-hide_banner", "-nostats", "-y", "-loop", "1", *in_args, "-i", str(still), *extra,
          "-filter_complex", look_graph(look), "-map", "[v]", *enc, "-t", str(seconds), "-an", "-movflags", "+faststart",
          "-f", "mp4", str(partial)], 0, None)
    os.replace(partial, out)
    return out


def make_preview(src: Path, out: Path, seconds: int = 90) -> Path:
    """A small 640-wide copy of the first `seconds` seconds. The video page plays this one, so the page stays fast."""
    out = Path(out)
    partial = out.with_name(out.stem + ".partial.mp4")
    _run([ffmpeg_exe(), "-hide_banner", "-nostats", "-y", "-i", str(src), "-t", str(seconds), "-vf", "scale=640:-2",
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "32", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart",
          "-f", "mp4", str(partial)], 0, None)
    os.replace(partial, out)
    return out


def probe(path: Path) -> dict:
    """Duration, size and codecs of a finished file (for the tests and the page)."""
    r = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    text = r.stderr
    dur = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", text)
    size = re.search(r"Video: (\w+).*?, (\d{3,5})x(\d{3,5})", text)
    return {"duration": int(dur[1]) * 3600 + int(dur[2]) * 60 + float(dur[3]) if dur else 0.0,
            "vcodec": size[1] if size else "", "size": (int(size[2]), int(size[3])) if size else (0, 0),
            "acodec": (re.search(r"Audio: (\w+)", text) or [None, ""])[1]}
