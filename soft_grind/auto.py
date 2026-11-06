"""One button, whole video: python -m soft_grind.auto <project>/auto.json

music -> image from the library -> headline -> thumbnail + still -> video -> youtube text (+ next free publish slot).
Every step first checks whether its result already exists, so starting it again resumes instead of paying twice.
"""
from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

from PIL import Image

from . import ai, brand, headlines, library, metadata, playlist, projects, settings, thumbnail as T, video, worker
from .suno import SunoError


class Cancelled(Exception):
    pass


class NeedsAttention(Exception):
    pass


def run(job_path: str) -> None:
    jp = Path(job_path)
    pdir = jp.parent
    name, root = pdir.name, pdir.parent
    job = projects.read_json(jp)
    spec = job["spec"]
    n_steps = len(projects.AUTO_STEPS)
    keys = settings.load_keys()

    def save(**kw):
        job.update(kw)
        job["updated"] = time.time()
        projects.write_json(jp, job)

    def at(step, frac, msg):
        save(step=step, progress=round((step + min(1.0, max(0.0, frac))) / n_steps, 3), message=msg)

    def check_cancel():
        if (pdir / projects.CANCEL).exists():
            raise Cancelled()

    suno_token = os.getenv("SOFTGRIND_SUNO_TOKEN") or keys.get("suno", "")
    ai_token = os.getenv("SOFTGRIND_AI_TOKEN") or keys.get("ai", "")
    ai_client = ai.AIClient(ai_token, spec.get("ai_model") or keys.get("ai_model") or ai.DEFAULT_MODEL) if (spec.get("use_ai") and ai_token) else None
    topic = spec.get("scenes") or brand.SCENES[:4]
    mood = spec.get("mood_key", "calm")
    save(state="running", error="", step=0, progress=0.0, message="starting")
    try:
        # 1 music
        check_cancel()
        have, want = len(projects.audio_files(pdir / "tracks")), spec["n_req"] * 2
        if have < want:
            remaining = spec["n_req"] - have // 2
            style = spec["style"]
            if spec.get("improve_prompt") and ai_client and not projects.meta(pdir).get("prompt_improved"):
                at(0, 0.0, "improving the music prompt")
                style, _ = ai_client.improve_music_prompt(style, topic)
                projects.set_meta(pdir, prompt_improved=True, style=style)
            sub = dict(spec, n_req=remaining, style=projects.meta(pdir).get("style") or style)
            worker.generate_music(pdir, sub, suno_token, note=lambda m: at(0, job.get("_done", 0) / max(1, remaining), m),
                                  task_started=lambda t: save(task_ids=job.get("task_ids", []) + [t]),
                                  request_done=lambda d: (job.update(_done=d), at(0, d / max(1, remaining), f"{d}/{remaining} requests")),
                                  check_cancel=check_cancel, offset=have // 2)

        # 2 image
        check_cancel(); at(1, 0.0, "looking through the library")
        m = projects.meta(pdir)
        li = m.get("library_image")
        if not (li and (pdir / "images" / f"{Path(li).stem}_16x9.png").exists()):
            db = {k: v for k, v in library.load_db().items() if v.get("analysis") and Path(k).exists()}
            if not db:
                raise NeedsAttention("The music is ready, but the library has no images the app has looked at yet. Open the library step, "
                                     "choose your folder and press 'look at the images', then press continue.")
            used = {k: v for k, v in library.used_images(root).items() if v != name}
            best = library.suggest(db, topic, mood, used, seed=name, n=1)[0]
            library.prepare_for_project(Path(best["path"]), pdir)
        li = projects.meta(pdir)["library_image"]

        # 3 headline
        check_cancel(); at(2, 0.0, "writing the headline")
        if not projects.meta(pdir).get("quote"):
            analysis = (library.load_db().get(li) or {}).get("analysis") or {"description": "", "scenes": list(topic)[:2]}
            used_q = {projects.meta(d).get("quote", "") for d in root.iterdir() if d.is_dir() and d != pdir}
            h, _ = headlines.pick(analysis, mood, list(topic), used_q, ai_client)
            projects.set_meta(pdir, quote=h)

        # 4 thumbnail + still
        check_cancel(); at(3, 0.0, "making the thumbnail")
        if not ((pdir / "thumbnail.png").exists() and (pdir / "still.png").exists()):
            src = Image.open(pdir / "images" / f"{Path(li).stem}_16x9.png"); src.load()
            q = projects.meta(pdir)["quote"]
            T.render_thumbnail(src, q, T.Layout(T.suggest_anchor(src, q), 0.9)).save(pdir / "thumbnail.png")
            T.render_still(src).save(pdir / "still.png")

        # 5 video
        check_cancel(); at(4, 0.0, "building the video")
        if not (pdir / "video.mp4").exists():
            tr = projects.audio_files(pdir / "tracks")
            video.render_video(tr, pdir / "still.png", pdir / "video.mp4", [playlist.audio_duration(t) for t in tr],
                               spec.get("crossfade", 4.0), spec.get("fade_in", 3.0), spec.get("fade_out", 6.0),
                               on_progress=lambda f, msg: (check_cancel(), at(4, f, msg)))

        # 6 text + publish slot
        check_cancel(); at(5, 0.0, "writing the youtube text")
        m = projects.meta(pdir)
        if not m.get("title"):
            tracks = playlist.tracks_from_folder(pdir / "tracks")
            idx = sum(1 for d in root.iterdir() if d.is_dir())
            quote = m["quote"]
            title = metadata.make_title("quote", quote, m.get("playlist_name", ""), m.get("scenario", ""), "🌴")
            desc = metadata.make_description(quote, "one more hour, then rest.", metadata.default_scene_text(list(topic)), tracks,
                                             "working and studying", brand.ARTISTS[idx % len(brand.ARTISTS)],
                                             brand.DESCRIPTION_QUESTIONS[idx % len(brand.DESCRIPTION_QUESTIONS)],
                                             brand.MOODS["groovy" if mood == "groovy" else "calm"], spec.get("crossfade", 4.0))
            tags = ", ".join(metadata.make_tags())
            pinned = brand.PINNED_COMMENTS[idx % len(brand.PINNED_COMMENTS)]
            taken = {projects.meta(d).get("schedule", "") for d in root.iterdir() if d.is_dir() and d != pdir}
            schedule = projects.next_free_slot(taken).strftime("%Y-%m-%d %H:%M")
            projects.set_meta(pdir, title=title, description=desc, tags=tags, pinned=pinned, schedule=schedule)
            (pdir / "upload.txt").write_text(metadata.upload_txt(title, desc, [t.strip() for t in tags.split(",")], pinned, schedule),
                                             encoding="utf-8")
        save(state="done", step=n_steps, progress=1.0, message="ready to check", finished=time.time())
    except Cancelled:
        save(state="cancelled", message="cancelled")
    except NeedsAttention as e:
        save(state="needs_attention", message="needs attention", error=str(e))
    except (SunoError, video.VideoError) as e:
        save(state="failed", message="failed", error=str(e))
    except Exception as e:
        traceback.print_exc()
        save(state="failed", message="failed", error=f"{e.__class__.__name__}: {e}")


if __name__ == "__main__":
    run(sys.argv[1])
