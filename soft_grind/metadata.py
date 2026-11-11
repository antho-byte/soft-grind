"""YouTube upload metadata in the soft grind. voice."""
from __future__ import annotations

from . import brand

CROSSFADE = 4.0


def fmt_ts(sec: float) -> str:
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def timestamps(durations: list[float], crossfade: float = CROSSFADE) -> list[float]:
    """Start time of each track when consecutive tracks overlap by `crossfade` seconds."""
    t, out = 0.0, []
    for d in durations:
        out.append(t)
        t += d - crossfade
    return out


def total_length(durations: list[float], crossfade: float = CROSSFADE) -> float:
    return max(0.0, sum(durations) - crossfade * max(0, len(durations) - 1))


def length_phrase(total_sec: float) -> str:
    mins = int(total_sec // 60 // 5 * 5)  # round down to 5 min
    h, m = divmod(mins, 60)
    parts = []
    if h:
        parts.append(f"{h} hour" + ("s" if h > 1 else ""))
    if m:
        parts.append(f"{m} minutes")
    return " ".join(parts) or "a short mix"


def tracklist_text(tracks: list[dict], crossfade: float = CROSSFADE) -> str:
    ts = timestamps([t["duration"] for t in tracks], crossfade)
    return "\n".join(f"{fmt_ts(s)} {t['title'].lower()}" for s, t in zip(ts, tracks))


DEFAULT_SUFFIX = "80s japanese city pop to work & study to"


def make_title(style: str, quote: str, playlist: str = "", scenario: str = "", emoji: str = "🌴", suffix: str | None = None) -> str:
    if style == "quote":
        s = DEFAULT_SUFFIX if suffix is None else suffix.strip()
        return f"{quote} | {s}" if s else quote
    return f"{playlist} you're {scenario} {emoji} 80s city pop"


def make_tags(extra: list[str] | None = None, limit: int = 500, sound: str = "", scenes=()) -> list[str]:
    """The core channel tags plus words for THIS video's sound and scenes, so not every video has the same tags."""
    own = list(brand.SOUND_INFO.get(sound, ("", [], ""))[1])
    for s in scenes:
        own += brand.SCENE_TAGS.get(s, [])
    core = ["city pop", "japanese city pop", "lofi", "study music", "work music", "focus music"]
    rest = [t for t in brand.TAGS_BASE if t not in core]
    tags, size = [], 0
    for t in core + own + (extra or []) + rest:
        if t not in tags and size + len(t) + 1 <= limit:
            tags.append(t); size += len(t) + 1
    return tags


def make_description(quote: str, subline: str, scene: str, tracks: list[dict], use: str,
                     question: str, mood_tag: str, crossfade: float = CROSSFADE, sound: str = "", ai_line: bool = True) -> str:
    """The first two lines show in search and above 'more': the headline, then what this is (genre, length, for what)."""
    total = total_length([t["duration"] for t in tracks], crossfade)
    genre, _, first_tag = brand.SOUND_INFO.get(sound, ("instrumental japanese city pop and lofi", [], "#citypop"))
    tags = list(dict.fromkeys([first_tag] + brand.HASHTAGS_BASE + [mood_tag]))      # the first three show above the title
    return (
        f"{quote} {subline}".strip() + "\n"
        f"{length_phrase(total)} of {genre} for {use}.\n\n"
        f"{scene.strip()}\n\n"
        "put it on, open the laptop, get into it.\n\n"
        f"tracklist\n{tracklist_text(tracks, crossfade)}\n\n"
        f"{question}\n\n"
        "soft grind. 静かな努力 (quiet effort)\n"
        f"{brand.AI_LINE if ai_line else brand.NO_AI_LINE}\n\n"
        + " ".join(tags[:5])
    )


def validate(title: str, tracks: list[dict], pinned: str) -> list[str]:
    """Problems that would break chapters or channel rules."""
    issues = []
    if len(tracks) < 3:
        issues.append("YouTube chapters need at least 3 tracklist entries.")
    if any(t["duration"] <= 0 for t in tracks):
        issues.append("Some tracks have no duration, so timestamps are wrong.")
    if len(title) > 60:
        issues.append(f"Title is {len(title)} chars; the first 60 matter most.")
    if any(ord(c) > 0x2E7F and ord(c) < 0xA000 for c in pinned):
        issues.append("Pinned comment must not contain Japanese characters.")
    return issues


def upload_txt(title: str, description: str, tags: list[str], pinned: str, schedule: str = "") -> str:
    when = f"scheduled for {schedule} (Amsterdam time)" if schedule else "scheduled (Mon/Wed/Fri 15:00 Amsterdam)"
    return (f"TITLE\n{title}\n\nDESCRIPTION\n{description}\n\nTAGS\n{', '.join(tags)}\n\n"
            f"PINNED COMMENT\n{pinned}\n\nVISIBILITY\nprivate, {when}\n")


def default_scene_text(scenes: list[str]) -> str:
    """Two sentences for the description when nobody wrote them (edited later on the video page)."""
    if not scenes:
        return "a quiet desk, a warm lamp and the city glowing outside. slow, soft grooves that keep you company while you work."
    first = ", ".join(scenes[:2]) if len(scenes) > 1 else scenes[0]
    return f"{first}: slow, soft grooves that keep you company while you work. calm enough to focus, warm enough to stay."
