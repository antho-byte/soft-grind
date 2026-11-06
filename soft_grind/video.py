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


def mix_graph(n: int, first_input: int, crossfade: float, total: float, fade_in: float, fade_out: float) -> str:
    """Filter graph ending in the label [mix]: n inputs -> equal format -> chained crossfades -> fade in / out."""
    parts = [f"[{first_input + i}:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}]" for i in range(n)]
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


def render_video(tracks: list[Path], still: Path, out: Path, durations: list[float], crossfade: float = 4.0,
                 fade_in: float = 3.0, fade_out: float = 6.0, on_progress: Callable[[float, str], None] | None = None) -> Path:
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
    audio_graph = mix_graph(n, 0, cf, total, fade_in, fade_out)
    m = measure_loudness(list(tracks), audio_graph, total, prog(0.0, 0.4, "measuring loudness"))

    graph = mix_graph(n, 1, cf, total, fade_in, fade_out) + (
        f";[mix]loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:LRA={TARGET_LRA}"
        f":measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
        f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true[out]")
    out = Path(out); out.parent.mkdir(parents=True, exist_ok=True)
    partial = out.with_name(out.stem + ".partial.mp4")
    cmd = [ffmpeg_exe(), "-hide_banner", "-nostats", "-y", "-progress", "pipe:1", "-loop", "1", "-framerate", "2", "-i", str(still)]
    for p in tracks:
        cmd += ["-i", str(p)]
    cmd += ["-filter_complex", graph, "-map", "0:v", "-map", "[out]",
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
            "-r", "2", "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage", "-crf", "23",
            "-c:a", "aac", "-b:a", "256k", "-ar", "44100", "-t", f"{total:.3f}", "-movflags", "+faststart", "-f", "mp4", str(partial)]
    _run(cmd, total, prog(0.4, 1.0, "building the video"))
    os.replace(partial, out)
    if on_progress:
        on_progress(1.0, "done")
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
