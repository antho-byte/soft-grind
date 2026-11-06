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

    def chat(self, system: str, user: str, max_tokens: int = 400, temperature: float = 0.8,
             images: list[str] | None = None) -> tuple[str, float]:
        """Returns (text, credits_used). credits_used is 0 when the API does not report it.
        `images` are data: URIs, sent as image_url parts so a vision-capable model can look at them."""
        if self.mock:
            return user.splitlines()[0].replace("Current prompt: ", "") + ", warm tape saturation (mock)", 0.0
        if not self.token:
            raise AIError("No AI token set (sidebar → keys and settings → AI helper token).")
        r = requests.post(
            f"{self.base_url}/v1/chat/completions", timeout=90,
            headers={"accept": "application/json", "authorization": f"Bearer {self.token}", "content-type": "application/json"},
            json={"model": self.model, "max_tokens": max_tokens, "temperature": temperature,
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": user if not images else
                                [{"type": "text", "text": user}] + [{"type": "image_url", "image_url": {"url": u}} for u in images]}]},
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

    def suggest_headlines(self, description: str, mood: str, scenes: list[str], used=()) -> tuple[list[str], float]:
        user = (f"Image: {description}\nMood: {mood}\nScenes: {', '.join(scenes) or 'any'}\n"
                f"Do not use these (already used): {'; '.join(list(used)[-40:]) or 'none'}")
        text, cost = self.chat(HEADLINE_SYSTEM, user, max_tokens=200, temperature=1.0)
        return parse_headlines(text, used), cost

    def improve_music_prompt(self, prompt: str, scenes: list[str] | None = None) -> tuple[str, float]:
        user = f"Current prompt: {prompt.strip()}"
        if scenes:
            user += f"\nScenes this playlist is about: {', '.join(scenes)}"
        text, cost = self.chat(IMPROVE_SYSTEM, user, max_tokens=300)
        return clean_prompt(text), cost


HEADLINE_SYSTEM = (
    "You write short headlines that are printed on YouTube thumbnails for soft grind, a calm instrumental city pop and lofi "
    "channel for people who work and study. Rules: lowercase, 2 to 4 words, ends with a full stop or a question mark, warm and "
    "encouraging, never hustle-bro (no 'grind', 'hustle', 'crush it', 'rise'), no emoji, no quotes. "
    "The headline must feel like it belongs to the image. Reply with exactly 6 different options, one per line, no numbering."
)


def parse_headlines(text: str, used=(), limit: int = 6) -> list[str]:
    """Keep only lines that follow the brand rules and are not used yet."""
    from .thumbnail import check_quote
    out, seen = [], {u.strip().lower() for u in used}
    for line in text.splitlines():
        h = re.sub(r"^[\s\-*\d.)]+", "", line).strip().strip("\"'`“”")
        if h and not check_quote(h) and h.lower() not in seen and len(h) <= 40:
            out.append(h); seen.add(h.lower())
    return out[:limit]


def clean_prompt(text: str, limit: int = 400) -> str:
    """One tidy line: no quotes, no leading 'prompt:' label, never longer than `limit`."""
    t = re.sub(r"\s+", " ", text.strip().strip("`\"'“”")).strip()
    t = re.sub(r"^(improved )?(style )?prompt\s*:\s*", "", t, flags=re.I).strip("\"' ")
    if len(t) > limit:
        t = t[:limit].rsplit(",", 1)[0]
    return t
