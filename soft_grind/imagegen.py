"""Turn vertical photos into 16:9: free blur-fill, or AI extend through the AceDataCloud image API.

The AI request is a JSON template (editable in the app) because each image model family
can name its fields differently. "{image}", "{prompt}" and "{model}" are filled in at send time.
"""
from __future__ import annotations

import base64
import io
import json
import time
from typing import Callable

import requests
from PIL import Image, ImageFilter

from .thumbnail import cover_crop

BASE_URL = "https://api.acedata.cloud"
TARGET = (1920, 1080)

DEFAULT_PROMPT = (
    "This image has a sharp photo in the centre and blurred, stretched bars on the left and right. "
    "Replace the blurred bars with a seamless, natural extension of the scene so the whole picture "
    "looks like one wide 16:9 photograph. Keep the centre photo's subject, colours, lighting and style "
    "exactly as they are. Do not add any text, letters, signatures, watermarks or logos."
)

# Request body for POST /nano-banana/images (action "edit"), per the AceDataCloud docs.
# Placeholders {image} {prompt} {model} {resolution} are filled in at send time.
NANO_TEMPLATE = {"action": "edit", "model": "{model}", "prompt": "{prompt}",
                 "image_urls": ["{image}"], "aspect_ratio": "16:9", "resolution": "{resolution}", "count": 1}

RES_ORDER = ["1K", "2K", "4K"]

# model -> (endpoint, request template, approx $ per image at the cheapest top-up tier, max resolution)
MODELS = {
    "nano-banana-2.1": ("/nano-banana/images", NANO_TEMPLATE, 0.019, "4K"),
    "nano-banana-pro": ("/nano-banana/images", NANO_TEMPLATE, 0.0333, "4K"),
    "nano-banana-2": ("/nano-banana/images", NANO_TEMPLATE, 0.0266, "4K"),
    "nano-banana": ("/nano-banana/images", NANO_TEMPLATE, 0.0133, "1K"),  # 1K only
}


def pick_resolution(model: str, wanted: str) -> str:
    """Never ask a model for more than it supports (nano-banana is 1K only)."""
    cap = MODELS.get(model, (0, 0, 0, "4K"))[3]
    return wanted if RES_ORDER.index(wanted) <= RES_ORDER.index(cap) else cap


class ImageError(RuntimeError):
    pass


# ---------- free option ----------
def blur_fill(img: Image.Image, size: tuple[int, int] = TARGET) -> Image.Image:
    """Photo centred at full height, blurred + enlarged copy of itself fills the sides."""
    img = img.convert("RGB")
    bg = cover_crop(img, size).filter(ImageFilter.GaussianBlur(size[1] / 22))
    bg = Image.blend(bg, Image.new("RGB", size, (20, 24, 82)), 0.12)  # slight night-indigo tint
    s = min(size[0] / img.width, size[1] / img.height)
    fg = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    bg.paste(fg, ((size[0] - fg.width) // 2, (size[1] - fg.height) // 2))
    return bg


def finish_16x9(img: Image.Image, size: tuple[int, int] = TARGET) -> tuple[Image.Image, str]:
    """Centre-crop to 16:9 and make sure it is at least 1920 wide. Returns (image, note)."""
    note = ""
    img = img.convert("RGB")
    if abs(img.width / img.height - 16 / 9) > 0.02:
        note += "cropped to 16:9. "
    if img.width < size[0]:
        note += f"upscaled from {img.width}px (may look soft). "
    return cover_crop(img, size if img.width <= size[0] else (img.width, round(img.width * 9 / 16))), note.strip()


# ---------- AI option ----------
def to_data_uri(img: Image.Image, max_side: int = 2048) -> str:
    img = img.convert("RGB")
    if max(img.size) > max_side:
        s = max_side / max(img.size)
        img = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    buf = io.BytesIO(); img.save(buf, "JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def fill_template(obj, values: dict):
    if isinstance(obj, str):
        for k, v in values.items():
            if obj == "{%s}" % k:
                return v
            obj = obj.replace("{%s}" % k, v)
        return obj
    if isinstance(obj, list):
        return [fill_template(x, values) for x in obj]
    if isinstance(obj, dict):
        return {k: fill_template(v, values) for k, v in obj.items()}
    return obj


def find_image_ref(node) -> str | None:
    """Find an image URL or base64 string anywhere in an API response."""
    if isinstance(node, dict):
        for key in ("image_url", "url", "b64_json", "image", "output"):
            v = node.get(key)
            if isinstance(v, str) and (v.startswith(("http", "data:")) or len(v) > 500):
                return v
        for v in node.values():
            r = find_image_ref(v)
            if r:
                return r
    elif isinstance(node, list):
        for v in node:
            r = find_image_ref(v)
            if r:
                return r
    return None


def _load(ref: str) -> Image.Image:
    if ref.startswith("http"):
        r = requests.get(ref, timeout=120, headers={"user-agent": "Mozilla/5.0"}); r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGB")
    if ref.startswith("data:"):
        ref = ref.split(",", 1)[1]
    return Image.open(io.BytesIO(base64.b64decode(ref))).convert("RGB")


class ImageClient:
    def __init__(self, token: str = "", base_url: str = BASE_URL, mock: bool = False):
        self.token, self.base_url, self.mock = token.strip(), base_url.rstrip("/"), mock

    def _post(self, path: str, payload: dict, timeout: float = 240) -> dict:
        if not self.token:
            raise ImageError("No image API token set (sidebar → image API token).")
        r = requests.post(f"{self.base_url}{path}", json=payload, timeout=timeout,
                          headers={"accept": "application/json", "authorization": f"Bearer {self.token}",
                                   "content-type": "application/json"})
        if r.status_code >= 400:
            raise ImageError(f"HTTP {r.status_code} from {path}: {r.text[:400]}")
        try:
            return r.json()
        except ValueError:
            raise ImageError(f"Response from {path} was not JSON: {r.text[:200]}")

    def edit(self, endpoint: str, template: dict, model: str, image: Image.Image, prompt: str,
             resolution: str = "2K", timeout: float = 300, poll: float = 4,
             on_tick: Callable[[float], None] | None = None) -> Image.Image:
        if self.mock:
            from PIL import ImageEnhance
            return ImageEnhance.Color(blur_fill(image)).enhance(1.25)
        payload = fill_template(template, {"image": to_data_uri(image), "prompt": prompt, "model": model,
                                           "resolution": pick_resolution(model, resolution)})
        res = self._post(endpoint, payload)
        ref = find_image_ref(res)
        if ref:
            return _load(ref)
        task_id = res.get("task_id") or res.get("id")
        if not task_id:
            raise ImageError(f"No image and no task id in response: {json.dumps(res)[:400]}")
        prefix = endpoint.rsplit("/", 1)[0]
        t0 = time.time()
        while time.time() - t0 < timeout:
            st = self._post(f"{prefix}/tasks", {"id": task_id, "action": "retrieve"})
            ref = find_image_ref(st.get("response", st))
            if ref:
                return _load(ref)
            resp = st.get("response") if isinstance(st.get("response"), dict) else {}
            if resp.get("success") is False or str(st.get("state", "")).lower() in {"failed", "error"}:
                raise ImageError(f"Image task failed: {json.dumps(st)[:400]}")
            if on_tick:
                on_tick(time.time() - t0)
            time.sleep(poll)
        raise ImageError(f"Timed out waiting for task {task_id}")
