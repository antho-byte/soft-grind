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


LOOP_X = 1.5          # seconds of the song after the clip that are blended into its start, so a replay runs on without a jump


def energy(track: Path, step: float = 0.5) -> list[float]:
    """Loudness (RMS) of a song per half second, from a quick low-quality decode."""
    import subprocess
    import numpy as np
    r = subprocess.run([video.ffmpeg_exe(), "-v", "error", "-i", str(track), "-ac", "1", "-ar", "4000", "-f", "s16le", "-"],
                       capture_output=True)
    a = np.frombuffer(r.stdout, dtype="<i2").astype(np.float32)
    n = int(4000 * step)
    if len(a) < n:
        return []
    a = a[: len(a) // n * n].reshape(-1, n)
    return list(np.sqrt((a ** 2).mean(axis=1)))


def best_start(track: Path, duration: float, length: float, step: float = 0.5) -> float | None:
    """Where the fullest stretch of `length` seconds starts (past the intro, clear of the ending). None if unknown."""
    e = energy(track, step)
    if not e:
        return None
    w = max(1, int(length / step))
    lo = int(max(8.0, duration * 0.15) / step)
    hi = int((duration - length - LOOP_X - 4) / step)
    if hi <= lo:
        return None
    import numpy as np
    c = np.concatenate([[0.0], np.cumsum(e)])
    means = [(c[i + w] - c[i]) / w for i in range(lo, min(hi, len(e) - w) + 1)]
    if not means:
        return None
    return round((lo + int(np.argmax(means))) * step, 2)


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


PLATFORMS = ("youtube", "instagram", "tiktok")
SHORT_HOUR = 18                      # Shorts go out daily at 18:00 (Amsterdam), apart from the long videos at 15:00


def captions(meta: dict, row: dict) -> dict:
    """Ready-to-paste text per platform. YouTube links to the full mix; Instagram and TikTok point to the link in the bio."""
    from . import brand
    q = meta.get("quote", "soft grind.")
    sound = (meta.get("sound") or "").split(" + ")[0] or brand.sound_of(meta.get("style") or "")
    genre = {"japanese jazz (calm, ~78 bpm)": "japanese jazz", "city pop funk (groovy, ~100 bpm)": "city pop funk"}.get(sound, "lofi city pop")
    vid = meta.get("youtube_id", "")
    yt_title = f"{q} {genre} to work and study to #shorts"[:100]
    yt_desc = (f"{q}\n" + (f"the full mix: https://youtu.be/{vid}" if vid else "the full mix is on the channel: soft grind.")
               + "\n\n#lofi #citypop #studymusic #shorts")
    ig = (f"{q}\n{genre} to work and study to. the full mix is on youtube: soft grind. (link in bio)\n.\n"
          "#lofi #citypop #studymusic #studywithme #lofibeats #chillbeats #japanesecitypop #worklofi")
    tt = f"{q} {genre} for deep work 🎧 full mix on youtube (link in bio) #lofi #citypop #studytok #focusmusic"
    return {"youtube_title": yt_title, "youtube_description": yt_desc, "instagram": ig, "tiktok": tt}


def all_shorts(root: Path) -> list[dict]:
    """Every Short of every video, newest video first."""
    out = []
    for p in sorted(projects.project_dirs(root), key=lambda d: d.name, reverse=True):
        m = projects.meta(p)
        for r in listing(p):
            out.append({**r, "pdir": p, "name": p.name, "quote": m.get("quote", ""), "path": folder(p) / r["file"],
                        "posted": r.get("posted", {}), "caption": captions(m, r), "yt": upload_status(p, r["file"])})
    return out


def _update_row(pdir: Path, file: str, **kw) -> None:
    fp = folder(pdir) / "shorts.json"
    with projects._locked(fp):
        data = projects.read_json(fp)
        for r in data.get("shorts", []):
            if r["file"] == file:
                r.update(kw)
        projects.write_json(fp, data)


def set_posted(pdir: Path, file: str, platform: str, on: bool) -> None:
    row = next((r for r in listing(pdir) if r["file"] == file), None)
    if row is None:
        return
    posted = dict(row.get("posted", {}))
    if on:
        posted[platform] = time.strftime("%Y-%m-%d")
    else:
        posted.pop(platform, None)
    _update_row(pdir, file, posted=posted)


def short_slots(root: Path, n: int = 7, now=None) -> list:
    """The next n free daily Shorts slots (18:00), skipping days that already have a Short planned."""
    import datetime as dt
    now = now or dt.datetime.now()
    taken = {r.get("schedule", "")[:10] for p in projects.project_dirs(root) for r in listing(p) if r.get("schedule")}
    out, day = [], now.date()
    while len(out) < n:
        slot = dt.datetime.combine(day, dt.time(SHORT_HOUR, 0))
        if slot > now and day.isoformat() not in taken:
            out.append(slot)
        day += dt.timedelta(days=1)
    return out


def _yt_job(pdir: Path, file: str) -> Path:
    return folder(pdir) / f"{Path(file).stem}.youtube.json"


def upload_status(pdir: Path, file: str) -> dict:
    j = projects.read_json(_yt_job(pdir, file))
    st = j.get("state", "none") if j else "none"
    if st in ("queued", "running") and time.time() - j.get("updated", 0) > projects.STALE_AFTER:
        st = "interrupted"
    return {"state": st, "running": st in ("queued", "running"), "error": (j or {}).get("error", ""),
            "progress": float((j or {}).get("progress", 0.0))}


def start_upload(pdir: Path, file: str, when) -> None:
    """Upload one Short to YouTube as private, going public by itself at `when` (Amsterdam time)."""
    pdir = Path(pdir)
    row = next((r for r in listing(pdir) if r["file"] == file), None)
    if row is None:
        raise RuntimeError("This Short does not exist any more.")
    if row.get("youtube_id"):
        raise RuntimeError("This Short is already on YouTube.")
    if upload_status(pdir, file)["running"]:
        raise RuntimeError("This Short is already being uploaded.")
    sched = when.strftime("%Y-%m-%d %H:%M")
    _update_row(pdir, file, schedule=sched)
    projects.write_json(_yt_job(pdir, file), {"state": "queued", "file": file, "schedule": sched, "updated": time.time()})
    projects._spawn("soft_grind.shorts", folder(pdir), _yt_job(pdir, file).name)


def run_upload(job_path: str) -> None:
    from . import youtube
    jp = Path(job_path); fdir = jp.parent; pdir = fdir.parent
    job = projects.read_json(jp)

    def save(**kw):
        job.update(kw); job["updated"] = time.time(); projects.write_json(jp, job)

    save(state="running", progress=0.0, error="")
    try:
        file = job["file"]
        row = next(r for r in listing(pdir) if r["file"] == file)
        cap = captions(projects.meta(pdir), row)
        meta = {"title": cap["youtube_title"], "description": cap["youtube_description"],
                "tags": "lofi, city pop, study music, shorts, lofi shorts", "schedule": job.get("schedule", "")}
        vid = youtube.upload_video(fdir / file, meta, lambda f: save(progress=round(f, 3)))
        _update_row(pdir, file, youtube_id=vid, posted={**row.get("posted", {}), "youtube": time.strftime("%Y-%m-%d")})
        save(state="done", progress=1.0, youtube_id=vid)
    except Exception as e:
        save(state="failed", error=str(e) if e.__class__.__name__ == "YouTubeError" else f"{e.__class__.__name__}: {e}")


def texts(meta: dict, k: int) -> dict:
    q = meta.get("quote", "soft grind.")
    vid = meta.get("youtube_id", "")
    title = f"{q} lofi city pop to work and study to {HASHTAGS.split()[-1]}"[:100]
    link = f"the full mix: https://youtu.be/{vid}" if vid else "the full mix is on the channel."
    desc = f"{q}\n{link}\n\n{HASHTAGS}"
    return {"title": title, "description": desc}


def render(pdir: Path, out: Path, track: Path, start: float, length: float, headline: str, motion: str = "zoom",
           dust: bool = False, pingpong: bool = False, seamless: bool = True) -> Path:
    """One Short. motion: 'zoom' (slow move in and back out on the cover picture) or 'loop' (the video's loop.mp4, repeated).
    seamless: the last moments flow straight into the first (sound and picture), so the automatic replay has no jump."""
    pdir, out = Path(pdir), Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    loop = pdir / LOOP
    if seamless and motion == "loop" and loop.exists():           # whole loops of the clip, so the picture ends where it began
        d = video.probe(loop)["duration"] * (2 if pingpong else 1)
        if d > 0.5:
            length = max(d, round(length / d) * d)
    with tempfile.TemporaryDirectory() as tmp:
        ov = Path(tmp) / "overlay.png"
        overlay(headline).save(ov)
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
            # a slow, smooth move (drawn at 1.5x size, so it does not shimmer); seamless: in and back out, ending where it began
            z = (f"1+0.08*(1-cos(2*PI*on/{frames}))/2" if seamless else f"1+0.10*on/{frames}")
            base = (f"[0:v]zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={FPS},"
                    f"setsar=1[bg]")
        tail = LOOP_X if seamless else 0.5
        inputs += ["-ss", f"{start:.2f}", "-t", f"{length + tail:.2f}", "-i", str(track), "-loop", "1", "-framerate", str(FPS), "-i", str(ov)]
        g = base + ";[bg][2:v]overlay=0:0:format=auto[ov]"
        last = "ov"
        if dust:
            inputs += ["-loop", "1", "-framerate", str(FPS), "-i", str(video.dust_texture())]
            hx = video._hash("12.9898", 1, "n"); hy = video._hash("78.233", 1, "n")
            g += (f";[3:v]crop={W}:{H}:x='floor({hx}*2760)':y='floor({hy}*240)',format=gray,format=yuv420p,{video._BLACK0}[dust]"
                  f";[ov]format=yuv420p[ov2];[ov2][dust]blend=c0_mode=screen:c0_opacity=0.45:c1_expr=A:c2_expr=A:shortest=0[dusty]")
            last = "dusty"
        g += f";[{last}]format=yuv420p[v]"
        if seamless:
            # the sound right after the clip is blended into its first moments: the end runs straight on into the start
            X, L_ = LOOP_X, length
            g += (f";[1:a]aresample=44100,asplit=3[s1][s2][s3]"
                  f";[s1]atrim=0:{X},asetpts=PTS-STARTPTS,afade=t=in:d={X}:curve=qsin[h]"
                  f";[s2]atrim={L_:.3f}:{L_ + X:.3f},asetpts=PTS-STARTPTS,afade=t=out:d={X}:curve=qsin[t]"
                  f";[h][t]amix=inputs=2:normalize=0:duration=longest[hx]"
                  f";[s3]atrim={X}:{L_:.3f},asetpts=PTS-STARTPTS[b]"
                  f";[hx][b]concat=n=2:v=0:a=1,loudnorm=I=-14:TP=-1.5:LRA=11[a]")
        else:
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
             on_progress=None, seamless: bool = True) -> list[dict]:
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
        best = best_start(tracks[ti], durations[ti], length)          # the fullest-sounding stretch of this song
        if best is not None:
            start = best
        ln = min(length, max(5.0, durations[ti] - start - (LOOP_X if seamless else 0)))
        render(pdir, fdir / f, tracks[ti], start, ln, headline, motion, dust, pingpong, seamless)
        rows.append({"file": f, "track": tracks[ti].stem, "start": start, "length": round(video.probe(fdir / f)["duration"], 1),
                     **texts(m, k)})
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
        motion = spec.get("motion", "zoom")
        if motion == "auto":                                     # the bulk button: the video's own loop if it has one
            motion = "loop" if (pdir / LOOP).exists() else "zoom"
        rows = make_all(pdir, int(spec.get("n", 3)), float(spec.get("length", 30)), motion,
                        bool(spec.get("dust", bool(projects.film_look(pdir)))), bool(spec.get("pingpong")),
                        lambda f, m: save(progress=round(f, 3), message=m))
        save(state="done", progress=1.0, message=f"{len(rows)} shorts made", finished=time.time())
        if not spec.get("quiet"):
            notify.send(f"{pdir.name}: {len(rows)} shorts made", "Open soft grind. to watch them.", tags="clapper")
    except Exception as e:
        traceback.print_exc()
        save(state="failed", message="failed", error=f"{e.__class__.__name__}: {e}" if not isinstance(e, video.VideoError) else str(e))


if __name__ == "__main__":
    (run_upload if sys.argv[1].endswith(".youtube.json") else run)(sys.argv[1])
