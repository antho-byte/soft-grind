"""Unique YouTube text for every video: the AI writes the parts that should differ, the app keeps the fixed parts fixed.

Fixed: the quote at the start of the title, tracklist + timestamps, hashtags, tags, the 'not affiliated' line.
Written per video: title phrase after the quote, subline, scene paragraph, pinned comment, closing question.
Rules are checked here (brand voice, length, no japanese characters, not too close to earlier videos); one rewrite is requested if not.
"""
from __future__ import annotations

import difflib
import json
import re

from . import brand, metadata

CJK = re.compile(r"[぀-ヿ㐀-鿿＀-￯]")
HUSTLE = re.compile(r"\b(grind|grinding|hustle|hustling|crush it|rise and|no days off)\b", re.I)
KEYS = ["suffix", "subline", "scene_text", "pinned", "question"]


def sim(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def previous_parts(root, exclude: str = "", last: int = 10) -> dict[str, list[str]]:
    """What earlier videos used (saved as text_parts in project.json), oldest first."""
    from . import projects
    rows = []
    for d in projects.project_dirs(root):
        if d.name == exclude:
            continue
        m = projects.meta(d)
        if m.get("text_parts"):
            rows.append((m.get("created", 0), m["text_parts"]))
    rows = [p for _, p in sorted(rows, key=lambda r: r[0])][-last:]
    return {k: [p.get(k, "") for p in rows] for k in KEYS}


def parse_parts(raw: str) -> dict[str, str]:
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise ValueError("the answer had no JSON")
    d = json.loads(m.group(0))
    return {"suffix": str(d.get("title_suffix", "")).strip().strip('"').lower(),
            "subline": str(d.get("subline", "")).strip(), "scene_text": str(d.get("scene_text", "")).strip(),
            "pinned": str(d.get("pinned_comment", "")).strip(), "question": str(d.get("question", "")).strip()}


def check_parts(p: dict[str, str], quote: str, previous: dict[str, list[str]]) -> list[str]:
    issues = []
    if len(f"{quote} | {p['suffix']}") > 60 and p["suffix"]:
        issues.append("the title phrase is too long: the whole title should stay within 60 characters")
    if "<" in "".join(p.values()) or ">" in "".join(p.values()):
        issues.append("no < or > characters")
    if CJK.search("".join(p.values())):
        issues.append("no japanese characters")
    if HUSTLE.search(" ".join(p.values())):
        issues.append("no hustle language")
    if not p["subline"].endswith((".", "?")) or not (2 <= len(p["subline"].split()) <= 10):
        issues.append("the subline must be 3 to 8 words and end with a full stop")
    if len(p["scene_text"]) < 60:
        issues.append("the scene text is too short")
    if not (10 < len(p["pinned"]) <= 130) or not p["pinned"].endswith("?"):
        issues.append("the pinned comment must be one question of at most 110 characters")
    if not p["question"].endswith("?"):
        issues.append("the closing question must end with a question mark")
    if p["suffix"] and p["suffix"] in previous.get("suffix", [])[-3:]:
        issues.append("the title phrase repeats a recent one")
    if any(sim(p["scene_text"], old) > 0.55 for old in previous.get("scene_text", []) if old):
        issues.append("the scene text is too close to an earlier video")
    if p["pinned"] in previous.get("pinned", []) or p["subline"] in previous.get("subline", []):
        issues.append("the subline or pinned comment repeats an earlier one")
    return issues


def template_parts(idx: int, topic: list[str], previous: dict[str, list[str]]) -> dict[str, str]:
    """No-AI fallback: rotate through the pools, skipping what the last videos used."""
    def rot(pool, key, offset=0):
        recent = set(previous.get(key, [])[-4:])
        for i in range(len(pool)):
            c = pool[(idx + offset + i) % len(pool)]
            if c not in recent:
                return c
        return pool[(idx + offset) % len(pool)]
    return {"suffix": rot(brand.TITLE_SUFFIXES, "suffix"), "subline": rot(brand.SUBLINES, "subline"),
            "scene_text": metadata.default_scene_text(list(topic)),
            "pinned": rot(brand.PINNED_COMMENTS + brand.PINNED_EXTRA, "pinned"), "question": rot(brand.QUESTIONS, "question", 1)}


def compose(*, quote: str, tracks: list[dict], mood: str, topic: list[str], image_description: str, playlist_name: str,
            scenario: str, crossfade: float, idx: int, previous: dict[str, list[str]], ai_client=None) -> tuple[dict, dict, float, bool]:
    """Returns (fields, parts, credits, written_by_ai). fields = title/description/tags/pinned ready for the video page."""
    parts, cost, by_ai, feedback = None, 0.0, False, ""
    if ai_client is not None:
        ctx = {"quote": quote, "image": image_description, "mood": mood, "scenes": list(topic), "tracks": [t["title"] for t in tracks],
               "length": metadata.length_phrase(metadata.total_length([t["duration"] for t in tracks], crossfade))}
        for _ in range(2):                                           # one rewrite if the rules are not met
            try:
                raw, c = ai_client.write_video_text(ctx, previous, feedback)
                cost += c
                cand = parse_parts(raw)
                problems = check_parts(cand, quote, previous)
                if not problems:
                    parts, by_ai = cand, True
                    break
                feedback = "; ".join(problems)
            except Exception as e:                                   # network, bad JSON...: try once more, then use templates
                feedback = f"{e.__class__.__name__}: {e}"
    if parts is None:
        parts = template_parts(idx, topic, previous)
    artist = brand.ARTISTS[idx % len(brand.ARTISTS)]
    fields = {"title": metadata.make_title("quote", quote, suffix=parts["suffix"]),
              "description": metadata.make_description(quote, parts["subline"], parts["scene_text"], tracks, "working and studying",
                                                       artist, parts["question"], brand.MOODS["groovy" if mood == "groovy" else "calm"], crossfade),
              "tags": ", ".join(metadata.make_tags()), "pinned": parts["pinned"]}
    return fields, parts, cost, by_ai
