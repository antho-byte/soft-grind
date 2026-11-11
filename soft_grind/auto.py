"""One button, whole video: python -m soft_grind.auto <project>/auto.json

music -> image from the library -> headline -> thumbnail + still -> video -> youtube text (+ next free publish slot).
Every step first checks whether its result already exists, so starting it again resumes instead of paying twice.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import traceback
from pathlib import Path

from PIL import Image

from . import ai, brand, errors, headlines, library, notify, playlist, projects, settings, texts, thumbnail as T, video, worker
from .suno import SunoError


# A batch makes two videos at once in one process. These keep them from taking the same picture, headline or publish slot,
# and from building two videos at the same time (that would make both slow).
PICK_LOCK = threading.RLock()
RENDER_LOCK = threading.Lock()


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
            ids = job.get("task_ids", [])
            done = job["done_tasks"] if "done_tasks" in job else ids[:have // 2]     # older jobs: the first ones arrived
            pending = [t for t in ids if t not in done]                              # paid for, songs never collected
            job["done_tasks"] = list(done)
            style = spec["style"]
            if spec.get("improve_prompt") and ai_client and not projects.meta(pdir).get("prompt_improved"):
                at(0, 0.0, "improving the music prompt")
                style, c = ai_client.improve_music_prompt(style, topic)
                projects.add_cost(name, "ai", c, False)
                projects.set_meta(pdir, prompt_improved=True, style=style)
            sub = dict(spec, n_req=remaining, style=projects.meta(pdir).get("style") or style)
            worker.generate_music(pdir, sub, suno_token, note=lambda m: at(0, job.get("_done", 0) / max(1, remaining), m),
                                  task_started=lambda t: save(task_ids=job.get("task_ids", []) + [t]),
                                  request_done=lambda d: (job.update(_done=d), at(0, d / max(1, remaining), f"{d}/{remaining} requests")),
                                  check_cancel=check_cancel, offset=have // 2, pending=pending,
                                  task_done=lambda t: save(done_tasks=job.get("done_tasks", []) + [t]))

        # 2 image
        check_cancel(); at(1, 0.0, "looking through the library")
        with PICK_LOCK:                                                     # one video at a time picks its picture and headline
            m = projects.meta(pdir)
            li = m.get("library_image")
            if not (li and (pdir / "images" / f"{Path(li).stem}_16x9.png").exists()):
                db = {k: v for k, v in library.load_db().items() if v.get("analysis") and Path(k).exists()}
                if not db:
                    raise NeedsAttention("The music is ready, but the library has no images the app has looked at yet. Open the images page, "
                                         "choose your folder and press 'look at the images', then press continue.")
                used = {k: v for k, v in library.used_images(root).items() if v != name}
                best = library.suggest(db, topic, mood, used, seed=name, n=1)[0]
                library.prepare_for_project(Path(best["path"]), pdir)
            li = projects.meta(pdir)["library_image"]

            # 3 headline
            check_cancel(); at(2, 0.0, "writing the headline")
            if not projects.meta(pdir).get("quote") or projects.meta(pdir).get("quote_placeholder"):
                analysis = (library.load_db().get(li) or {}).get("analysis") or {"description": "", "scenes": list(topic)[:2]}
                used_q = projects.recent_quotes(root, exclude=name, n=headlines.RECENT)
                used_q.add(projects.meta(pdir).get("quote", ""))                  # not the placeholder either
                h, c = headlines.pick(analysis, mood, list(topic), used_q, ai_client)
                projects.add_cost(name, "ai", c, False)
                projects.set_meta(pdir, quote=h, quote_placeholder=False)

        # 4 thumbnail + still
        check_cancel(); at(3, 0.0, "making the thumbnail")
        if not ((pdir / "thumbnail.png").exists() and (pdir / "still.png").exists()):
            src = Image.open(pdir / "images" / f"{Path(li).stem}_16x9.png"); src.load()
            q = projects.meta(pdir)["quote"]
            T.render_thumbnail(src, q, T.Layout()).save(pdir / "thumbnail.png")             # size 1.50, top-center
            T.render_still(src, quote=q, layout=T.Layout()).save(pdir / "still.png")        # the video picture = thumbnail design

        # 5 video
        check_cancel(); at(4, 0.0, "building the video")
        if not (pdir / "video.mp4").exists():
            while not RENDER_LOCK.acquire(timeout=20):                     # another video of the batch is being built
                check_cancel(); at(4, 0.0, "waiting for the other video to finish building")
            try:
                tr = projects.audio_files(pdir / "tracks")
                video.render_video(tr, pdir / "still.png", pdir / "video.mp4", [playlist.audio_duration(t) for t in tr],
                                   spec.get("crossfade", 4.0), spec.get("fade_in", 3.0), spec.get("fade_out", 6.0),
                                   on_progress=lambda f, msg: (check_cancel(), at(4, f, msg)), look=projects.film_look(pdir))
            finally:
                RENDER_LOCK.release()

        # 6 text + publish slot
        check_cancel(); at(5, 0.0, "writing the youtube text")
        m = projects.meta(pdir)
        if not m.get("title"):
            tracks = playlist.tracks_from_folder(pdir / "tracks")
            idx = len(projects.project_dirs(root))
            analysis = (library.load_db().get(li) or {}).get("analysis") or {}
            fields, parts, c, by_ai = texts.compose(
                quote=m["quote"], tracks=tracks, mood=mood, topic=list(topic), image_description=analysis.get("description", ""),
                playlist_name=m.get("playlist_name", ""), scenario=m.get("scenario", ""), crossfade=spec.get("crossfade", 4.0), idx=idx,
                previous=texts.previous_parts(root, exclude=name), ai_client=ai_client, sound=projects.sound_of(pdir))
            projects.add_cost(name, "ai", c, False)
            with PICK_LOCK:
                m2 = projects.meta(pdir)
                if spec.get("plan", True) and not m2.get("schedule"):
                    taken = {projects.meta(d).get("schedule", "") for d in projects.project_dirs(root) if d != pdir}
                    schedule = projects.next_free_slot(taken).strftime("%Y-%m-%d %H:%M")
                else:
                    schedule = m2.get("schedule", "")
                projects.set_meta(pdir, **fields, schedule=schedule, text_parts=parts, text_by_ai=by_ai)
            from . import metadata
            (pdir / "upload.txt").write_text(metadata.upload_txt(fields["title"], fields["description"],
                                                                 [t.strip() for t in fields["tags"].split(",")], fields["pinned"], schedule),
                                             encoding="utf-8")
        if spec.get("shorts"):                                    # a few vertical Shorts from the finished video
            at(5, 0.9, "making the shorts")
            from . import shorts
            with RENDER_LOCK:
                try:
                    shorts.make_all(pdir, int(spec["shorts"]), 30.0, "loop" if (pdir / shorts.LOOP).exists() else "zoom",
                                    dust=bool(projects.film_look(pdir)))
                except Exception as e:                            # the video itself is fine: a failed Short never fails it
                    projects.set_meta(pdir, shorts_error=str(e)[:300])
        save(state="done", step=n_steps, progress=1.0, message="ready to check", finished=time.time())
        if spec.get("upload"):
            try:
                projects.start_youtube(pdir)                      # runs on its own and sends its own phone message
            except RuntimeError as e:
                notify.send(f"{name}: not uploaded", str(e)[:120], tags="warning")
        if not spec.get("quiet"):                                # a batch sends one summary at the end instead
            notify.send(f"{name} is ready", f"\"{projects.meta(pdir).get('quote', '')}\": the music, cover, video and text are made. Open soft grind. to check it.",
                        priority="high", tags="white_check_mark")
    except Cancelled:
        save(state="cancelled", message="cancelled")
    except NeedsAttention as e:
        save(state="needs_attention", message="needs attention", error=str(e))
        notify.send(f"{name} needs you", "Open soft grind. to see what is missing.", priority="high", tags="raising_hand")
    except (SunoError, video.VideoError) as e:
        save(state="failed", message="failed", error=str(e))
        notify.send(f"{name} stopped", errors.explain(str(e))["title"], priority="high", tags="warning")
    except Exception as e:
        traceback.print_exc()
        save(state="failed", message="failed", error=f"{e.__class__.__name__}: {e}")
        notify.send(f"{name} stopped", errors.explain(str(e))["title"], priority="high", tags="warning")


if __name__ == "__main__":
    run(sys.argv[1])
