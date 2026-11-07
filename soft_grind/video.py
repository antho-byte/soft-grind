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


# ---------- film look: grain, vignette, flicker, dust, tint ----------
GRAIN = {0: 0, 1: 7, 2: 14}                      # strength of the luma noise: off / low / medium
TINTS = {"none": "", "warm": "colorbalance=rs=.04:gs=.01:bs=-.04:rm=.03:bm=-.03,eq=saturation=1.05",
         "faded": "curves=all='0/0.05 1/0.95',eq=contrast=0.94:saturation=0.88"}
LOOK_DEFAULT = {"grain": 1, "vignette": True, "flicker": True, "dust": False, "tint": "none", "fps": 15}


def normalize_look(look: dict | None) -> dict | None:
    """A clean look dict, or None when every effect is off (then the fast still-picture path is used)."""
    if not look:
        return None
    out = {"grain": int(look.get("grain", 0)) if int(look.get("grain", 0)) in GRAIN else 0,
           "vignette": bool(look.get("vignette")), "flicker": bool(look.get("flicker")), "dust": bool(look.get("dust")),
           "tint": look.get("tint") if look.get("tint") in TINTS else "none",
           "fps": min(30, max(8, int(look.get("fps", 15))))}
    return out if (out["grain"] or out["vignette"] or out["flicker"] or out["dust"] or out["tint"] != "none") else None


def look_graph(look: dict) -> str:
    """The video part of the filter graph: [0:v] -> [v]."""
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
    if look["dust"]:                                   # a few bright specks per frame, drawn small and scaled up so they look soft
        g += (f";color=c=black:s=480x270:r={fps},format=gray,geq=lum='if(gt(random(1),0.9995),255,0)',"
              f"scale=1920:1080:flags=bicubic,format=yuv420p[dust];[base][dust]blend=all_mode=screen:all_opacity=0.3:shortest=0[dusty]")
        last = "dusty"
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
    audio_graph = mix_graph(n, 0, cf, total, fade_in, fade_out)
    m = measure_loudness(list(tracks), audio_graph, total, prog(0.0, 0.4, "measuring loudness"))

    graph = mix_graph(n, 1, cf, total, fade_in, fade_out) + (
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
        cmd += ["-filter_complex", look_graph(look) + ";" + graph, "-map", "[v]", "-map", "[out]", *enc]
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
    _run([ffmpeg_exe(), "-hide_banner", "-nostats", "-y", "-loop", "1", *in_args, "-i", str(still),
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
