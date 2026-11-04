"""AceDataCloud Suno REST client (the API behind SunoMCP) + an offline mock for testing.

Endpoints (from the SunoMCP source): POST {base}/suno/audios, POST {base}/suno/tasks.
"""
from __future__ import annotations

import math
import struct
import time
import wave
from pathlib import Path
from typing import Callable

import requests

BASE_URL = "https://api.acedata.cloud"


class SunoError(RuntimeError):
    pass


class SunoClient:
    def __init__(self, token: str = "", base_url: str = BASE_URL, mock: bool = False,
                 mock_dir: Path | None = None):
        self.token, self.base_url, self.mock = token.strip(), base_url.rstrip("/"), mock
        self.mock_dir = Path(mock_dir or ".")
        self._mock_n = 0

    # ---------- low level ----------
    def _post(self, path: str, payload: dict, timeout: float = 120) -> dict:
        if not self.token:
            raise SunoError("No AceDataCloud API token set.")
        r = requests.post(
            f"{self.base_url}{path}", json=payload, timeout=timeout,
            headers={"accept": "application/json", "authorization": f"Bearer {self.token}",
                     "content-type": "application/json"},
        )
        if r.status_code >= 400:
            try:
                err = r.json().get("error", {})
                msg = f"{err.get('code', r.status_code)}: {err.get('message', r.text[:200])}"
            except Exception:
                msg = f"HTTP {r.status_code}: {r.text[:200]}"
            raise SunoError(msg)
        return r.json()

    # ---------- generation ----------
    def generate(self, style: str, title: str, model: str = "chirp-v5-5",
                 duration: int | None = None, negative_tags: str = "") -> str:
        """Start an instrumental custom-mode generation. Returns a task id (2 clips per task)."""
        if self.mock:
            self._mock_n += 1
            return f"mock-{self._mock_n}-{title}"
        payload = {
            "action": "generate", "custom": True, "instrumental": True, "lyric": "",
            "title": title, "style": style, "model": model, "async": True,
        }
        if negative_tags:
            payload["negative_tags"] = negative_tags
        if duration:
            payload["duration"] = int(max(10, min(360, duration)))
        res = self._post("/suno/audios", payload)
        task_id = res.get("task_id")
        if not task_id:
            raise SunoError(f"No task_id in response: {str(res)[:200]}")
        return task_id

    def extend(self, audio_id: str, continue_at: float, style: str = "",
               model: str = "chirp-v5-5") -> str:
        """Extend a clip from `continue_at` seconds (for 6-8 minute tracks)."""
        payload = {"action": "extend", "audio_id": audio_id, "lyric": "", "continue_at": continue_at,
                   "custom": True, "instrumental": True, "model": model, "async": True}
        if style:
            payload["style"] = style
        return self._post("/suno/audios", payload)["task_id"]

    def get_task(self, task_id: str) -> dict:
        """Return {'state': 'pending'|'complete'|'failed', 'clips': [...], 'error': str}."""
        if self.mock:
            title = task_id.split("-", 2)[-1]
            clips = []
            for i in (1, 2):
                p = self.mock_dir / f"_mock_{task_id.split('-')[1]}_{i}.wav"
                _write_tone(p, seconds=6 + i, freq=220 * (1 + 0.1 * int(task_id.split('-')[1])))
                clips.append({"id": f"{task_id}-{i}", "title": title, "audio_url": p.as_uri(),
                              "image_url": "", "duration": 6 + i})
            return {"state": "complete", "clips": clips, "error": ""}
        res = self._post("/suno/tasks", {"id": task_id, "action": "retrieve"})
        resp = res.get("response") if isinstance(res.get("response"), dict) else {}
        data = resp.get("data") or []
        state_raw = str(res.get("state", "")).lower()
        if resp.get("success") is False or state_raw in {"failed", "error", "cancelled", "canceled"}:
            return {"state": "failed", "clips": [], "error": str(resp.get("error") or res.get("error") or state_raw)}
        clips = [
            {"id": d.get("id"), "title": d.get("title") or "", "audio_url": d.get("audio_url"),
             "image_url": d.get("image_url") or "", "duration": d.get("duration") or 0}
            for d in data if isinstance(d, dict) and d.get("audio_url")
        ]
        unfinished = "finished_at" in res and res["finished_at"] is None
        done = bool(clips) and not unfinished and resp.get("success") is True
        return {"state": "complete" if done else "pending", "clips": clips if done else [], "error": ""}

    def wait(self, task_id: str, timeout: float = 900, poll: float = 6,
             on_tick: Callable[[float], None] | None = None) -> list[dict]:
        t0 = time.time()
        while True:
            st = self.get_task(task_id)
            if st["state"] == "complete":
                return st["clips"]
            if st["state"] == "failed":
                raise SunoError(f"Generation failed: {st['error']}")
            if time.time() - t0 > timeout:
                raise SunoError(f"Timed out waiting for task {task_id}")
            if on_tick:
                on_tick(time.time() - t0)
            time.sleep(poll)


def _write_tone(path: Path, seconds: float, freq: float, rate: int = 22050) -> None:
    if path.exists():
        return
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        n = int(seconds * rate)
        w.writeframes(b"".join(
            struct.pack("<h", int(6000 * math.sin(2 * math.pi * freq * i / rate))) for i in range(n)))


def download(url: str, dest: Path) -> Path:
    """Download (or copy, for file:// mock urls) an audio file."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if url.startswith("file://"):
        dest.write_bytes(Path(url[7:]).read_bytes())
        return dest
    with requests.get(url, stream=True, timeout=120, headers={"user-agent": "Mozilla/5.0"}) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
    return dest
