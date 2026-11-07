"""Thumbnail headlines: lowercase, 1-3 words, ends with '.' or '?', warm. May repeat, but never within the last 30 videos."""
from __future__ import annotations

import itertools
import random

RECENT = 30          # a headline may come back after this many videos

NEUTRAL_ONE = ["focus.", "flow.", "glow.", "drive.", "steady.", "begin.", "build.", "finish.", "onward.", "momentum.", "reset.",
               "repeat.", "evening.", "create."]
CALM_ONE = ["breathe.", "unwind.", "hush.", "ease.", "lamplight.", "dusk.", "dawn.", "unhurried."]
CALM = ["you've got this.", "keep going.", "stay with it.", "almost there.", "one more.", "locked in.", "soft focus.", "deep focus.",
        "clear mind.", "clear head.", "full focus.", "in focus.", "dialed in.", "in the zone.", "flow state.", "go with it.",
        "keep at it.", "keep showing up.", "trust yourself.", "you showed up.", "good work.", "nearly done.",
        "one more page.", "one more hour.", "next step.", "start here.", "just start.", "begin again.", "try again.", "go on.",
        "breathe in.", "slow down.", "take it easy.", "ease in.", "soft start.", "gentle now.", "no rush.", "be here.", "right now.",
        "just this.", "all good.", "take a breath.", "deep calm.", "steady focus.", "calm focus.", "quiet focus.", "warm focus.",
        "slow and steady.", "nice and steady.", "stay the course.", "easy does it.", "one thing.", "one task.", "focus mode.",
        "keep it soft.", "start small.", "you're doing fine.", "slow is fine.", "one thing, slowly.", "little by little."]
GROOVY = ["good vibes.", "feel it.", "in the groove.", "groove.", "keep it moving.", "find your groove.", "feel the rhythm.",
          "let it flow.", "ride the groove.", "sunny side up.", "golden hour focus.", "city pop.", "tokyo nights.", "make it shine.",
          "bounce back.", "dance through it.", "brighter than monday.", "tonight we build."]
TIME = ["night shift.", "after hours.", "late night.", "night owl.", "midnight focus.", "midnight oil.", "3am focus.", "2am study.",
        "early bird.", "first light.", "morning focus.", "golden hour.", "golden focus.", "blue hour.", "sunday reset.", "friday focus.",
        "weekend work."]
STUDY = ["deep work.", "study mode.", "study time.", "finals focus.", "exam week.", "page one.", "chapter one.", "turn the page.",
         "clear the desk.", "desk time.", "laptop open.", "new tab.", "inbox zero.", "make something.", "write it.", "build it."]
PLACE = ["good vibes.", "city lights.", "neon glow.", "sunset mood.", "rainy focus.", "let it rain.", "soft rain.", "rainy day.",
         "window seat.", "coffee break.", "one more cup.", "lamp light.", "desk lamp.", "warm light.", "midnight drive.", "late train.",
         "last train."]
QUESTIONS = ["ready?", "still here?", "one more?", "you in?", "tired?", "need focus?", "what's next?", "coffee first?", "feeling it?",
             "still up?", "rain check?"]
SOFT_GRIND = ["soft grind.", "slow grind.", "easy grind.", "gentle grind.", "quiet grind.", "steady grind.", "warm grind."]   # rare

BY_SCENE = {
    "late night desk lamp": ["lamp light.", "desk lamp.", "late night.", "night owl.", "still up?", "lamp on.", "midnight oil.", "quiet hours."],
    "rainy window": ["rainy focus.", "let it rain.", "soft rain.", "rainy day.", "window seat.", "rain check?", "stay in."],
    "morning train ride": ["first light.", "fresh start.", "good morning.", "begin.", "late train.", "next stop.", "window seat."],
    "poolside sunset": ["golden hour.", "golden focus.", "glow.", "easy flow.", "sunset mood.", "slow glow.", "blue hour."],
    "neon city walk": ["neon glow.", "city lights.", "after hours.", "night shift.", "midnight drive.", "neon focus.", "last train."],
    "quiet library": ["page one.", "turn the page.", "chapter one.", "deep work.", "quiet focus.", "study mode.", "study time."],
    "rooftop at dusk": ["golden hour.", "blue hour.", "dusk.", "city lights.", "above it all.", "sunset mood.", "slow down."],
    "coffee shop corner": ["one more cup.", "coffee break.", "refill.", "corner table.", "coffee first?", "warm light."],
    "palm trees and highway": ["windows down.", "good vibes.", "golden hour.", "midnight drive.", "open road.", "sunny side.", "palm trees."],
    "night shift": ["night shift.", "after hours.", "3am focus.", "late night.", "midnight focus.", "night owl.", "still up?"],
    "slow sunday": ["sunday reset.", "no rush.", "take it easy.", "slow down.", "slow morning.", "easy does it.", "unhurried."],
    "open laptop": ["laptop open.", "new tab.", "inbox zero.", "deep work.", "make something.", "write it.", "just start."],
}
ADJ = {"calm": ["soft", "slow", "deep", "quiet", "steady", "warm", "gentle", "easy", "calm", "clear"],
       "groovy": ["sunny", "bright", "golden", "smooth", "breezy", "neon", "lively"]}
NOUN = ["focus", "flow", "work", "hours", "mind", "pace", "mornings", "nights"]


def pool(mood: str) -> list[str]:
    own = GROOVY if mood == "groovy" else CALM + CALM_ONE
    return list(dict.fromkeys(own + NEUTRAL_ONE + TIME + STUDY + PLACE + QUESTIONS))


def suggest(mood: str, scenes: list[str], used=(), n: int = 1, seed=None) -> list[str]:
    """n headlines: the scenes' own lines first, then the mood's, then generated combinations. Never one in `used`.
    A 'soft grind' line turns up rarely."""
    rng = random.Random(seed)
    mood = mood if mood in ADJ else "calm"
    taken = {u.strip().lower() for u in used}
    sources = [rng.sample(BY_SCENE[s], len(BY_SCENE[s])) for s in scenes if s in BY_SCENE]
    sources.append(rng.sample(pool(mood), len(pool(mood))))
    combos = [f"{a} {b}." for a, b in itertools.product(ADJ[mood], NOUN)]
    rng.shuffle(combos)
    grind = rng.sample(SOFT_GRIND, len(SOFT_GRIND))
    out = []
    while len(out) < n:
        pick = None
        if rng.random() < 0.06:                                        # rarely: the channel's own words
            pick = next((g for g in grind if g.lower() not in taken), None)
        for src in ([] if pick else sources + [combos]):
            while src:
                c = src.pop()
                if c.lower() not in taken:
                    pick = c
                    break
            if pick:
                break
        if pick is None:                                               # everything recently used: allow the oldest wording again
            pick = rng.choice(pool(mood))
        taken.add(pick.lower()); out.append(pick)
    return out


def pick(analysis: dict, mood: str, topic: list[str], used=(), ai_client=None) -> tuple[str, float]:
    """One headline that fits the image: asked from the AI when a client is given, else from the pools. Never one in `used`."""
    scenes = [s for s in analysis.get("scenes", []) if s in topic] or analysis.get("scenes", []) or list(topic)[:2]
    cost = 0.0
    if ai_client is not None:
        try:
            opts, cost = ai_client.suggest_headlines(analysis.get("description", ""), mood, scenes, used)
            if opts:
                return opts[0], cost
        except Exception:
            pass
    return suggest(mood, scenes, used, 1)[0], cost                      # the AI answer was unusable, but it was still paid for
