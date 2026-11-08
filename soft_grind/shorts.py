"""YouTube Shorts from a finished video: vertical 1080x1920, a short part of a track, a moving picture, the headline and logo.

The picture moves by itself (a slow zoom, free) or comes from a loop clip: one you drop in (Midjourney) or one the AI made
(see animate.py). Background job: python -m soft_grind.shorts <project>/shorts_job.json
"""
from __future__ import annotations

import sys
import tempfile
import time
import traceback
from pathlib import Path

from PIL import Image, ImageDraw

from . import notify, playlist, projects, thumbnail as T, video

W, H, FPS = 1080, 1920, 30
JOB = "shorts_job.json"
LOOP = "loop.mp4"                   # the animated background of this video (dropped in or made by the AI)
HASHTAGS = "#lofi #citypop #studymusic #shorts"


def folder(pdir: Path) -> Path:
    return Path(pdir) / "shorts"


def listing(pdir: Path) -> list[dict]:
    rows = projects.read_json(folder(pdir) / "shorts.json").get("shorts", [])
    return [r for r in rows if (folder(pdir) / r["file"]).exists()]


def source_picture(pdir: Path) -> Image.Image | None:
    """The cover's picture without the headline: the saved cover source, else the prepared image, else the video picture."""
    pdir = Path(pdir)
    cands = [pdir / "cover_source.png"]
    imgs = pdir / "images"
    if imgs.is_dir():
        cands += sorted(imgs.glob("*_16x9.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    cands += [pdir / "still.png", pdir / "thumbnail.png"]
    for c in cands:
        if c.exists():
            try:
                im = Image.open(c); im.load()
                return im.convert("RGB")
            except Exception:
                continue
    return None


def vertical(img: Image.Image) -> Image.Image:
    """The middle of a picture, cut to 9:16 and sized 1080x1920."""
    return T.cover_crop(img, (W, H))


def overlay(headline: str) -> Image.Image:
    """A transparent 1080x1920 layer: the headline high up (clear of the Shorts buttons) and the logo low in the middle."""
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sc = H / 1920
    lines = T.split_lines(headline.strip())
    font = T.fit_font(lines, 132, W - 2 * 90)
    gap = 8
    asc, desc = font.getmetrics()
    lh = asc + desc + gap
    widths = [font.getlength(l) for l in lines]
    y0 = 300

    def draw_text(d, ox, oy, fill):
        for i, l in enumerate(lines):
            d.text(((W - widths[i]) / 2 + ox, y0 + i * lh + oy), l, font=font, fill=fill)

    lay.alpha_composite(T._shadowed((W, H), draw_text, sc * 1.4))
    draw_text(ImageDraw.Draw(lay), 0, 0, (255, 255, 255, 255))
    lf = T._abril(64)
    word, dot = "soft grind", "."
    lw = lf.getlength(word) + lf.getlength(dot)
    lx, ly = (W - lw) / 2, H - 520                                   # above the caption / buttons area of the Shorts player
    d = ImageDraw.Draw(lay)
    d.text((lx, ly), word, font=lf, fill=(255, 255, 255, 235))
    d.text((lx + lf.getlength(word), ly), dot, font=lf, fill=T._rgb(T.COLORS["coral"]) + (255,))
    return lay


def pick_parts(durations: list[float], n: int, length: float) -> list[tuple[int, float]]:
    """(track index, start second) for n Shorts: different tracks spread over the mix, starting a third into each track
    (past the intro, where the groove has settled)."""
    usable = [i for i, d in enumerate(durations) if d >= length + 8] or list(range(len(durations)))
    if not usable:
        return []
    picks = [usable[round(k * (len(usable) - 1) / max(1, n - 1))] for k in range(n)] if n > 1 else [usable[len(usable) // 2]]
    out = []
    for i in dict.fromkeys(picks):
        d = durations[i]
        start = max(0.0, min(d * 0.33, d - length - 4))
        out.append((i, round(start, 2)))
    return out


def texts(meta: dict, k: int) -> dict:
    q = meta.get("quote", "soft grind.")
    vid = meta.get("youtube_id", "")
    title = f"{q} lofi city pop to work and study to {HASHTAGS.split()[-1]}"[:100]
    link = f"the full mix: https://youtu.be/{vid}" if vid else "the full mix is on the channel."
    desc = f"{q}\n{link}\n\n{HASHTAGS}"
    return {"title": title, "description": desc}


def render(pdir: Path, out: Path, track: Path, start: float, length: float, headline: str, motion: str = "zoom",
           dust: bool = False, pingpong: bool = False) -> Path:
    """One Short. motion: 'zoom' (slow push-in on the cover picture) or 'loop' (the video's loop.mp4, repeated)."""
    pdir, out = Path(pdir), Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        ov = Path(tmp) / "overlay.png"
        overlay(headline).save(ov)
        loop = pdir / LOOP
        if motion == "loop" and loop.exists():
            inputs = ([] if pingpong else ["-stream_loop", "-1"]) + ["-i", str(loop)]     # ping-pong reverses the clip, so it must end
            base = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1"
                    + (",split[f][r0];[r0]reverse[r];[f][r]concat=n=2:v=1:a=0,loop=-1:32767:0" if pingpong else "") + "[bg]")
        else:
            src = source_picture(pdir)
            if src is None:
                raise video.VideoError("No picture for this video yet: make the cover first.")
            pic = Path(tmp) / "vertical.png"
            vertical(src).resize((W * 3 // 2, H * 3 // 2), Image.LANCZOS).save(pic)
            frames = int(length * FPS)
            inputs = ["-loop", "1", "-framerate", str(FPS), "-i", str(pic)]
            # a slow, smooth push-in (drawn at 1.5x size, so it does not shimmer)
            base = (f"[0:v]zoompan=z='1+0.10*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={FPS},"
                    f"setsar=1[bg]")
        inputs += ["-ss", f"{start:.2f}", "-t", f"{length + 0.5:.2f}", "-i", str(track), "-loop", "1", "-framerate", str(FPS), "-i", str(ov)]
        g = base + ";[bg][2:v]overlay=0:0:format=auto[ov]"
        last = "ov"
        if dust:
            inputs += ["-loop", "1", "-framerate", str(FPS), "-i", str(video.dust_texture())]
            hx = video._hash("12.9898", 1, "n"); hy = video._hash("78.233", 1, "n")
            g += (f";[3:v]crop={W}:{H}:x='floor({hx}*2760)':y='floor({hy}*240)',format=gray,format=yuv420p,{video._BLACK0}[dust]"
                  f";[ov]format=yuv420p[ov2];[ov2][dust]blend=c0_mode=screen:c0_opacity=0.45:c1_expr=A:c2_expr=A:shortest=0[dusty]")
            last = "dusty"
        g += f";[{last}]format=yuv420p[v]"
        fade_out = max(0.0, length - 1.5)
        g += f";[1:a]afade=t=in:d=0.6,afade=t=out:st={fade_out:.2f}:d=1.5,loudnorm=I=-14:TP=-1.5:LRA=11[a]"
        partial = out.with_name(out.stem + ".partial.mp4")
        cmd = [video.ffmpeg_exe(), "-hide_banner", "-nostats", "-y", *inputs, "-filter_complex", g, "-map", "[v]", "-map", "[a]",
               "-t", f"{length:.2f}", "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-movflags", "+faststart", "-f", "mp4", str(partial)]
        video._run(cmd, length, None)
        partial.replace(out)
    return out


def make_all(pdir: Path, n: int = 3, length: float = 30.0, motion: str = "zoom", dust: bool = False, pingpong: bool = False,
             on_progress=None) -> list[dict]:
    """n Shorts for this video, each from a different track. Replaces the earlier Shorts of this video."""
    pdir = Path(pdir)
    tracks = projects.audio_files(pdir / "tracks")
    if not tracks:
        raise video.VideoError("This video has no songs (they may have been removed to free up space).")
    m = projects.meta(pdir)
    headline = m.get("quote") or "soft grind."
    durations = [playlist.audio_duration(t) for t in tracks]
    parts = pick_parts(durations, n, length)
    fdir = folder(pdir)
    for old in fdir.glob("short_*.mp4") if fdir.exists() else []:
        old.unlink(missing_ok=True)
    rows = []
    for k, (ti, start) in enumerate(parts, 1):
        if on_progress:
            on_progress((k - 1) / len(parts), f"short {k} of {len(parts)}")
        f = f"short_{k}.mp4"
        render(pdir, fdir / f, tracks[ti], start, min(length, max(5.0, durations[ti] - start)), headline, motion, dust, pingpong)
        rows.append({"file": f, "track": tracks[ti].stem, "start": start, "length": length, **texts(m, k)})
    projects.write_json(fdir / "shorts.json", {"shorts": rows, "made": time.time(), "motion": motion})
    if on_progress:
        on_progress(1.0, "done")
    return rows


# ---------- background job ----------
def status(pdir: Path) -> dict:
    j = projects.read_json(Path(pdir) / JOB)
    st = j.get("state", "none") if j else "none"
    if st in ("queued", "running") and time.time() - j.get("updated", 0) > projects.STALE_AFTER:
        st = "interrupted"
    return {"state": st, "running": st in ("queued", "running"), "progress": float(j.get("progress", 0.0)) if j else 0.0,
            "message": j.get("message", "") if j else "", "error": j.get("error", "") if j else ""}


def start(pdir: Path, spec: dict) -> None:
    pdir = Path(pdir)
    if status(pdir)["running"]:
        raise RuntimeError("Shorts are already being made for this video.")
    projects.write_json(pdir / JOB, {"state": "queued", "progress": 0.0, "message": "queued", "spec": spec, "updated": time.time()})
    projects._spawn("soft_grind.shorts", pdir, JOB)


def run(job_path: str) -> None:
    jp = Path(job_path); pdir = jp.parent
    job = projects.read_json(jp); spec = job.get("spec", {})

    def save(**kw):
        job.update(kw); job["updated"] = time.time(); projects.write_json(jp, job)

    save(state="running", progress=0.0, message="starting", error="")
    try:
        rows = make_all(pdir, int(spec.get("n", 3)), float(spec.get("length", 30)), spec.get("motion", "zoom"),
                        bool(spec.get("dust")), bool(spec.get("pingpong")), lambda f, m: save(progress=round(f, 3), message=m))
        save(state="done", progress=1.0, message=f"{len(rows)} shorts made", finished=time.time())
        if not spec.get("quiet"):
            notify.send(f"{pdir.name}: {len(rows)} shorts made", "Open soft grind. to watch them.", tags="clapper")
    except Exception as e:
        traceback.print_exc()
        save(state="failed", message="failed", error=f"{e.__class__.__name__}: {e}" if not isinstance(e, video.VideoError) else str(e))


if __name__ == "__main__":
    run(sys.argv[1])
