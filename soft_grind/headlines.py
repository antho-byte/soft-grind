"""Thumbnail headlines: lowercase, 2-4 words, ends with '.' or '?', warm (never hustle-bro). Unique across videos."""
from __future__ import annotations

import itertools
import random

CALM = ["you've got this.", "one more page.", "take your time.", "softly, steadily.", "stay a while.", "breathe, then begin.",
        "quiet progress.", "ease into it.", "still going.", "little by little.", "start small.", "you're doing fine.",
        "slow is fine.", "keep it soft.", "all in good time.", "be here now.", "gentle focus.", "no rush today.",
        "one thing, slowly.", "right where you are."]
GROOVY = ["keep it moving.", "find your groove.", "work with a smile.", "feel the rhythm.", "brighter than monday.",
          "sunny side up.", "let it flow.", "ride the groove.", "sway while you work.", "tonight we build.",
          "golden hour focus.", "good vibes only.", "dance through it.", "bounce back.", "make it shine."]
BY_SCENE = {
    "late night desk lamp": ["lamp on, mind on.", "still up? good.", "one small lamp.", "the quiet hours."],
    "rainy window": ["let it rain.", "rain, tea, focus.", "listen to the rain.", "grey sky, warm room."],
    "morning train ride": ["next stop: focus.", "first train, first page.", "window seat, wide mind.", "good morning, you."],
    "poolside sunset": ["sun's going down.", "golden hour work.", "one more lap?", "orange hour, easy mind."],
    "neon city walk": ["neon and focus.", "the city hums.", "walk it out.", "lights on, mind clear."],
    "quiet library": ["turn the page.", "shh, you're onto something.", "quiet pages.", "read a little more."],
    "rooftop at dusk": ["chase the sunset.", "above the noise.", "dusk looks good.", "the city can wait."],
    "coffee shop corner": ["one more cup.", "coffee and focus.", "corner table, clear head.", "refill and refocus."],
    "palm trees and highway": ["windows down.", "the long way home.", "keep driving, keep dreaming.", "palm trees, open road."],
    "night shift": ["the night is yours.", "after midnight focus.", "quiet floor, clear mind.", "almost morning."],
    "slow sunday": ["no rush today.", "sunday, softly.", "nowhere to be.", "slow morning, good light."],
    "open laptop": ["ready when you are?", "open the laptop.", "new tab, new start.", "begin anywhere."],
}
ADJ = {"calm": ["slow", "soft", "quiet", "steady", "gentle", "easy"], "groovy": ["sunny", "bright", "golden", "smooth", "breezy", "neon"]}
NOUN = {"calm": ["progress", "focus", "hours", "mornings", "evenings", "steps", "work", "wins"],
        "groovy": ["focus", "groove", "hours", "vibes", "work", "energy", "afternoon", "drive"]}


def suggest(mood: str, scenes: list[str], used=(), n: int = 1, seed=None) -> list[str]:
    """n headlines, preferring the scenes' own lines, then the mood's, then generated combinations. Never one in `used`."""
    rng = random.Random(seed)
    mood = mood if mood in ADJ else "calm"
    taken = {u.strip().lower() for u in used}
    sources = [rng.sample(BY_SCENE[s], len(BY_SCENE[s])) for s in scenes if s in BY_SCENE]
    sources.append(rng.sample(CALM if mood == "calm" else GROOVY, len(CALM if mood == "calm" else GROOVY)))
    combos = [f"{a} {b}." for a, b in itertools.product(ADJ[mood], NOUN[mood])]
    rng.shuffle(combos)
    out = []
    while len(out) < n:
        pick = None
        for src in sources + [combos]:
            while src:
                c = src.pop()
                if c.lower() not in taken:
                    pick = c
                    break
            if pick:
                break
        if pick is None:
            pick = f"day {len(taken) + 1}, softly."
        taken.add(pick.lower()); out.append(pick)
    return out


def pick(analysis: dict, mood: str, topic: list[str], used=(), ai_client=None) -> tuple[str, float]:
    """One headline that fits the image: asked from the AI when a client is given, else from the pools. Never one in `used`."""
    scenes = [s for s in analysis.get("scenes", []) if s in topic] or analysis.get("scenes", []) or list(topic)[:2]
    if ai_client is not None:
        try:
            opts, cost = ai_client.suggest_headlines(analysis.get("description", ""), mood, scenes, used)
            if opts:
                return opts[0], cost
        except Exception:
            pass
    return suggest(mood, scenes, used, 1)[0], 0.0
