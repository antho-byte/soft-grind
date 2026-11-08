"""Animate a video's picture into a short vertical loop with an AI video model on AceDataCloud (same account as the images).

The picture is the cover's picture cut to 9:16, without the headline (the Shorts maker adds the text on top).
For Veo the first and the last frame are the same picture, so the clip loops; Luma has its own loop switch.
Background job: python -m soft_grind.animate <project>/animate_job.json  ->  <project>/loop.mp4
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

import requests

from . import imagegen, net, notify, projects, settings, shorts, video

JOB = "animate_job.json"
DEFAULT_PROMPT = ("subtle, seamless looping animation of this illustration. gentle ambient motion only: soft rain, drifting "
                  "steam, flickering city lights, slow clouds, leaves moving a little. the camera stays still. keep the style, "
                  "colours and composition exactly. no text, no new people, no cuts.")
# name: (create endpoint, request template, estimated price in $ at the cheapest top-up tier, loops by itself)
MODELS = {
    "veo 3.1 fast (loops)": ("/veo/videos", {"action": "image2video", "model": "veo31-fast", "prompt": "{prompt}",
                                            "image_urls": ["{image}", "{image}"], "aspect_ratio": "9:16"}, 0.114, True),
    "veo 2 fast (cheapest)": ("/veo/videos", {"action": "image2video", "model": "veo2-fast", "prompt": "{prompt}",
                                             "image_urls": ["{image}"], "aspect_ratio": "9:16"}, 0.066, False),
    "luma (loops)": ("/luma/videos", {"action": "generate", "prompt": "{prompt}", "start_image_url": "{image}", "loop": True,
                                     "aspect_ratio": "9:16"}, None, True),
}


class AnimateError(RuntimeError):
    pass


def find_video_url(node) -> str | None:
    """The first video link anywhere in an answer."""
    if isinstance(node, dict):
        for k in ("video_url", "url", "output"):
            v = node.get(k)
            if isinstance(v, str) and v.startswith("http") and (".mp4" in v or k == "video_url"):
                return v
        for v in node.values():
            r = find_video_url(v)
            if r:
                return r
    elif isinstance(node, list):
        for v in node:
            r = find_video_url(v)
            if r:
                return r
    elif isinstance(node, str) and node.startswith("http") and ".mp4" in node:
        return node
    return None


def mock_clip(pdir: Path, out: Path, seconds: int = 5) -> None:
    """Practice mode: a gently zooming clip of the picture, made here (free, no AI)."""
    src = shorts.source_picture(pdir)
    if src is None:
        raise AnimateError("No picture for this video yet: make the cover first.")
    with tempfile.TemporaryDirectory() as tmp:
        pic = Path(tmp) / "v.png"
        shorts.vertical(src).resize((720, 1280)).save(pic)
        n = seconds * 24
        subprocess.run([video.ffmpeg_exe(), "-v", "error", "-y", "-loop", "1", "-framerate", "24", "-i", str(pic), "-vf",
                        f"zoompan=z='1+0.04*sin(PI*on/{n})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=720x1280:fps=24",
                        "-t", str(seconds), "-pix_fmt", "yuv420p", "-c:v", "libx264", str(out)], check=True, capture_output=True)


class Animator:
    def __init__(self, token: str, mock: bool = False, base_url: str = imagegen.BASE_URL):
        self.client = imagegen.ImageClient(token, base_url=base_url, mock=mock)
        self.mock = mock

    def _post(self, path: str, payload: dict) -> dict:
        try:
            return self.client._post(path, payload)
        except imagegen.ImageError as e:
            raise AnimateError(str(e)) from e

    def make(self, pdir: Path, out: Path, endpoint: str, template: dict, prompt: str, timeout: float = 900, poll: float = 8,
             on_tick=None) -> None:
        if self.mock:
            mock_clip(pdir, out)
            return
        src = shorts.source_picture(pdir)
        if src is None:
            raise AnimateError("No picture for this video yet: make the cover first.")
        payload = imagegen.fill_template(copy.deepcopy(template), {"image": imagegen.to_data_uri(shorts.vertical(src), 1280),
                                                                  "prompt": prompt})
        res = self._post(endpoint, payload)
        url = find_video_url(res)
        task_id = res.get("task_id") or res.get("id")
        prefix = endpoint.rsplit("/", 1)[0]
        t0 = time.time()
        while not url:
            if not task_id:
                raise AnimateError(f"No video and no task id in the answer: {json.dumps(res)[:400]}")
            if time.time() - t0 > timeout:
                raise AnimateError("The video model took too long (15 minutes). Try again later.")
            time.sleep(poll)
            if on_tick:
                on_tick(time.time() - t0)
            st = self._post(f"{prefix}/tasks", {"id": task_id, "action": "retrieve"})
            body = st.get("response", st)
            url = find_video_url(body)
            states = json.dumps(body).lower()
            if not url and ('"state": "failed"' in states or '"success": false' in states or '"state": "error"' in states):
                raise AnimateError(f"The video model gave up: {json.dumps(st)[:400]}")
        try:
            r = net.request("GET", url, retries=2, timeout=300, headers={"user-agent": "Mozilla/5.0"})
            r.raise_for_status()
        except requests.RequestException as e:
            raise AnimateError(net.friendly(e)) from e
        part = Path(out).with_name("loop.partial.mp4")
        part.write_bytes(r.content)
        if video.probe(part)["duration"] <= 0:
            raise AnimateError("The downloaded file is not a video.")
        part.replace(out)


# ---------- background job ----------
def status(pdir: Path) -> dict:
    j = projects.read_json(Path(pdir) / JOB)
    st = j.get("state", "none") if j else "none"
    if st in ("queued", "running") and time.time() - j.get("updated", 0) > projects.STALE_AFTER:
        st = "interrupted"
    return {"state": st, "running": st in ("queued", "running"), "message": j.get("message", "") if j else "",
            "error": j.get("error", "") if j else ""}


def start(pdir: Path, model: str, endpoint: str, template: dict, prompt: str, token: str, mock: bool) -> None:
    pdir = Path(pdir)
    if status(pdir)["running"]:
        raise RuntimeError("This picture is already being animated.")
    projects.write_json(pdir / JOB, {"state": "queued", "message": "queued", "updated": time.time(),
                                     "spec": {"model": model, "endpoint": endpoint, "template": template, "prompt": prompt, "mock": mock}})
    projects._spawn("soft_grind.animate", pdir, JOB, {"SOFTGRIND_IMAGE_TOKEN": token})


def run(job_path: str) -> None:
    import os
    jp = Path(job_path); pdir = jp.parent
    job = projects.read_json(jp); spec = job.get("spec", {})

    def save(**kw):
        job.update(kw); job["updated"] = time.time(); projects.write_json(jp, job)

    save(state="running", message="sending the picture", error="")
    token = os.getenv("SOFTGRIND_IMAGE_TOKEN") or settings.load_keys().get("image", "")
    try:
        Animator(token, bool(spec.get("mock"))).make(pdir, pdir / shorts.LOOP, spec["endpoint"], spec["template"], spec["prompt"],
                                                     on_tick=lambda s: save(message=f"the AI is animating · {int(s)}s"))
        save(state="done", message="done", finished=time.time())
        projects.set_meta(pdir, loop_model=spec.get("model", ""), loop_made=time.strftime("%Y-%m-%d %H:%M"))
        notify.send(f"{pdir.name}: the picture is animated", "Open soft grind. to make the shorts with it.", tags="sparkles")
    except AnimateError as e:
        save(state="failed", message="failed", error=str(e))
    except Exception as e:
        traceback.print_exc()
        save(state="failed", message="failed", error=f"{e.__class__.__name__}: {e}")


if __name__ == "__main__":
    run(sys.argv[1])
