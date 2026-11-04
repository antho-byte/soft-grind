"""Unique track names that stay on the playlist's topic (the scenes you picked). Lowercase, short, no punctuation."""
from __future__ import annotations

import itertools
import random

POOLS = {
    "late night desk lamp": ["desk lamp hours", "after midnight glow", "one more task", "lamp light lullaby",
                             "the quiet inbox", "midnight to do list", "warm lamp cold tea"],
    "rainy window": ["window seat rain", "soft rain on glass", "grey sky warm room", "umbrella season",
                     "raindrop tempo", "puddles and playlists", "drizzle study"],
    "morning train ride": ["first train out", "window seat sunrise", "commuter daydream", "platform coffee",
                           "rails and rhythm", "early light express", "station sunrise"],
    "poolside sunset": ["pool light fade", "sunset laps", "palm shade slow", "orange hour drift",
                        "deck chair dusk", "poolside static", "golden water"],
    "neon city walk": ["neon crosswalk", "after hours stroll", "glow of the block", "vending machine blue",
                       "side street shimmer", "last train lights", "downtown drift"],
    "quiet library": ["page by page", "shelf light", "silent aisle", "bookmarked", "reading room hum",
                      "library lamp", "soft footsteps"],
    "rooftop at dusk": ["rooftop hour", "skyline slow", "antenna sunset", "fire escape breeze",
                        "city from above", "dusk on the roof", "blue hour terrace"],
    "coffee shop corner": ["corner table", "second cup", "latte art loop", "steam and strings",
                           "window booth", "barista playlist", "cafe afternoon"],
    "palm trees and highway": ["palm lined drive", "coastal cruise", "windows down", "highway sunset",
                               "long road home", "convertible daydream", "sun visor"],
    "night shift": ["night shift groove", "clock in tune in", "3am focus", "overtime glow", "quiet floor",
                    "fluorescent calm", "after the meeting"],
    "slow sunday": ["slow sunday light", "sunday reset", "lazy morning loop", "no plans today",
                    "pancake tempo", "sunday drift", "blanket weather"],
    "open laptop": ["open laptop", "new tab new tune", "cursor blink", "deep work mode", "inbox zero dreams",
                    "tab by tab", "focus bloom"],
}

GENERIC = {
    "calm": ["soft landing", "gentle focus", "easy tide", "low light loop", "warm static", "hush hour",
             "slow bloom", "quiet current", "paper lantern", "moon on the desk", "mellow hours", "still water"],
    "groovy": ["golden hour groove", "bounce in the step", "palm tree funk", "summer bassline", "rooftop boogie",
               "skyline strut", "shuffle on the stereo", "left lane groove", "sunny side funk", "city pop swagger"],
}
ADJ = {"calm": ["soft", "quiet", "slow", "warm", "gentle", "hazy", "mellow", "dreamy"],
       "groovy": ["bright", "sunny", "bouncy", "golden", "smooth", "neon", "breezy", "lively"]}
NOUN = ["morning", "evening", "window", "street", "lamp", "tide", "skyline", "afternoon", "balcony", "daydream"]


def suggest(scenes: list[str], count: int, taken=(), mood: str = "calm", seed=None) -> list[str]:
    """`count` names, round-robin over `scenes`, none equal to anything in `taken` or to each other."""
    rng = random.Random(seed)
    mood = mood if mood in GENERIC else "calm"
    used = {t.strip().lower() for t in taken}
    pools = {s: rng.sample(POOLS.get(s, []), len(POOLS.get(s, []))) for s in set(scenes)}
    generic = rng.sample(GENERIC[mood], len(GENERIC[mood]))
    combos = [f"{a} {n}" for a, n in itertools.product(ADJ[mood], NOUN)]
    rng.shuffle(combos)
    out, i = [], 0
    scene_list = scenes or list(POOLS)
    for s in scene_list:
        pools.setdefault(s, rng.sample(POOLS.get(s, []), len(POOLS.get(s, []))))
    while len(out) < count:
        pool = pools[scene_list[i % len(scene_list)]]
        i += 1
        name = None
        for source in (pool, generic, combos):          # own scene first, then mood names, then adjective + noun
            while source:
                cand = source.pop()
                if cand not in used:
                    name = cand
                    break
            if name:
                break
        if name is None:                                  # all pools empty: numbered fallback, still unique
            name = f"slow hour {len(used) + 1}"
        used.add(name); out.append(name)
    return out
