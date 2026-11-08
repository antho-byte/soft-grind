"""Thumbnail headlines. Every new video takes one from the owner's list (headline_list.json): lowercase, ends with '.' or '?'.

The scene and the mood decide which groups come first; a headline may come back, but never within the last 30 videos.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

RECENT = 30          # a headline may come back after this many videos
LIST_FILE = Path(__file__).with_name("headline_list.json")


def _load() -> dict[str, list[str]]:
    data = json.loads(LIST_FILE.read_text(encoding="utf-8"))
    return {k: [h.strip() for h in v if h.strip()] for k, v in data.items() if not k.startswith("_") and isinstance(v, list)}


GROUPS = _load()                                   # focus, calm, night, motivation, study_work
ALL = list(dict.fromkeys(h for v in GROUPS.values() for h in v))

# which groups fit a scene best (first = best); unknown scenes fall back to the mood
BY_SCENE = {
    "late night desk lamp": ["night", "focus"], "rainy window": ["calm", "focus"], "morning train ride": ["motivation", "calm"],
    "poolside sunset": ["calm", "motivation"], "neon city walk": ["night", "motivation"], "quiet library": ["study_work", "focus"],
    "rooftop at dusk": ["calm", "night"], "coffee shop corner": ["study_work", "calm"], "palm trees and highway": ["motivation", "calm"],
    "night shift": ["night", "focus"], "slow sunday": ["calm", "study_work"], "open laptop": ["study_work", "focus"],
}
BY_MOOD = {"calm": ["calm", "focus"], "groovy": ["motivation", "focus"]}


def preferred_groups(mood: str, scenes: list[str]) -> list[str]:
    out: list[str] = []
    for s in scenes:
        out += BY_SCENE.get(s, [])
    out += BY_MOOD.get(mood, BY_MOOD["calm"])
    return [g for g in dict.fromkeys(out) if g in GROUPS]


def suggest(mood: str, scenes: list[str], used=(), n: int = 1, seed=None) -> list[str]:
    """n headlines from the list: the groups that fit the scenes and mood first, then the rest. Never one in `used`
    (the last 30 videos); if every headline was used recently, the list starts over."""
    rng = random.Random(seed)
    taken = {u.strip().lower() for u in used}
    first = preferred_groups(mood, scenes)
    best = [h for g in first for h in GROUPS[g]]
    rest = [h for h in ALL if h not in best]
    rng.shuffle(best); rng.shuffle(rest)
    order = list(dict.fromkeys(best + rest))
    out = []
    for h in order:
        if len(out) == n:
            break
        if h.lower() not in taken:
            out.append(h); taken.add(h.lower())
    while len(out) < n:                                           # everything used recently: allow a repeat
        out.append(rng.choice([h for h in ALL if h not in out] or ALL))
    return out


def unused(used=()) -> list[str]:
    taken = {u.strip().lower() for u in used}
    return [h for h in ALL if h.lower() not in taken] or list(ALL)


def pick(analysis: dict, mood: str, topic: list[str], used=(), ai_client=None) -> tuple[str, float]:
    """One headline from the list that fits the image: the AI chooses from the list when a client is given, else the groups do."""
    scenes = [s for s in analysis.get("scenes", []) if s in topic] or analysis.get("scenes", []) or list(topic)[:2]
    cost = 0.0
    if ai_client is not None:
        try:
            options = suggest(mood, scenes, used, 40, seed=analysis.get("description", ""))   # a fitting shortlist from the list
            opts, cost = ai_client.suggest_headlines(analysis.get("description", ""), mood, scenes, used, options=options)
            if opts:
                return opts[0], cost
        except Exception:
            pass
    return suggest(mood, scenes, used, 1)[0], cost                      # the AI answer was unusable, but it was still paid for
