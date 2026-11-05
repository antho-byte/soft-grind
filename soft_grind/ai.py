"""AI helper: AceDataCloud chat completions (OpenAI-compatible: POST /v1/chat/completions).

Used for small writing jobs (better music prompts, later headlines/names/descriptions). One call is ~1,000 tokens,
so a cheap model such as Claude Haiku costs a fraction of a cent per click.
"""
from __future__ import annotations

import re

import requests

BASE_URL = "https://api.acedata.cloud"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"   # from the API docs; change it in the app if the model card shows a newer name

IMPROVE_SYSTEM = (
    "You improve style prompts for Suno, an AI music generator, for an instrumental lofi / japanese city pop "
    "YouTube channel called soft grind. "
    "Rules: instrumental only, no vocals. Never name artists, bands or songs (Suno blocks them): describe the sound instead. "
    "Keep the user's intent and tempo family (calm = 66-80 bpm, groovy = 92-108 bpm). "
    "Be specific: genre, 3 to 5 named instruments, texture, one tempo in bpm, mood. "
    "Output one line, comma-separated, lowercase, 150 to 280 characters. "
    "Reply with ONLY the improved prompt: no quotes, no explanation."
)


class AIError(RuntimeError):
    pass


class AIClient:
    def __init__(self, token: str = "", model: str = DEFAULT_MODEL, base_url: str = BASE_URL, mock: bool = False):
        self.token, self.model, self.base_url, self.mock = token.strip(), (model or DEFAULT_MODEL).strip(), base_url.rstrip("/"), mock

    def chat(self, system: str, user: str, max_tokens: int = 400, temperature: float = 0.8) -> tuple[str, float]:
        """Returns (text, credits_used). credits_used is 0 when the API does not report it."""
        if self.mock:
            return user.splitlines()[0].replace("Current prompt: ", "") + ", warm tape saturation (mock)", 0.0
        if not self.token:
            raise AIError("No AI token set (sidebar → keys and settings → AI helper token).")
        r = requests.post(
            f"{self.base_url}/v1/chat/completions", timeout=90,
            headers={"accept": "application/json", "authorization": f"Bearer {self.token}", "content-type": "application/json"},
            json={"model": self.model, "max_tokens": max_tokens, "temperature": temperature,
                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
        )
        if r.status_code >= 400:
            try:
                e = r.json().get("error", {})
                raise AIError(f"{e.get('code', r.status_code)}: {e.get('message', r.text[:200])}")
            except ValueError:
                raise AIError(f"HTTP {r.status_code}: {r.text[:200]}")
        data = r.json()
        try:
            text = (data["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError):
            raise AIError(f"Unexpected response: {str(data)[:300]}")
        if not text:
            raise AIError("The model returned an empty answer.")
        cost = ((data.get("usage") or {}).get("cost") or {}).get("amount") or 0.0
        return text, float(cost)

    def improve_music_prompt(self, prompt: str, scenes: list[str] | None = None) -> tuple[str, float]:
        user = f"Current prompt: {prompt.strip()}"
        if scenes:
            user += f"\nScenes this playlist is about: {', '.join(scenes)}"
        text, cost = self.chat(IMPROVE_SYSTEM, user, max_tokens=300)
        return clean_prompt(text), cost


def clean_prompt(text: str, limit: int = 400) -> str:
    """One tidy line: no quotes, no leading 'prompt:' label, never longer than `limit`."""
    t = re.sub(r"\s+", " ", text.strip().strip("`\"'“”")).strip()
    t = re.sub(r"^(improved )?(style )?prompt\s*:\s*", "", t, flags=re.I).strip("\"' ")
    if len(t) > limit:
        t = t[:limit].rsplit(",", 1)[0]
    return t
