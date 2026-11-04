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


# Romanised Japanese names. Simple, well-known words; meanings kept here so they are easy to check.
JP_POOLS = {
    "late night desk lamp": ["ranpu no akari", "tsukue no ue", "yoru no shosai", "shizuka na yoru"],
    "rainy window": ["mado no ame", "ame no hi", "ame agari", "ame no oto"],
    "morning train ride": ["asa no densha", "ichiban densha", "yoake no eki", "asa no hikari"],
    "poolside sunset": ["natsu no yuugure", "natsu no owari", "tooi natsu", "yuuyake"],
    "neon city walk": ["neon no machi", "yoru no machi", "machi no akari", "yakei"],
    "quiet library": ["toshokan no gogo", "peeji no oto", "shizuka na heya", "hon no kaori"],
    "rooftop at dusk": ["okujou no yuuhi", "yuugure no sora", "sora no iro", "tooi yakei"],
    "coffee shop corner": ["kissaten", "gogo no koohii", "madogiwa no seki", "koohii no yuge"],
    "palm trees and highway": ["kaigan doori", "yoru no doraibu", "umi e no michi", "natsu no kaze"],
    "night shift": ["nagai yoru", "shuuden made", "yonaka no hikari", "yakin"],
    "slow sunday": ["nichiyoubi no asa", "yukkuri no hi", "nonbiri", "kyou wa yasumi"],
    "open laptop": ["hitoyasumi", "shuuchuu", "shuuchuu no jikan", "sunadokei"],
}
JP_GENERIC = {
    "calm": ["tsukiakari", "hoshizora", "yoake", "yume no tochuu", "mizuumi no asa", "kaze no oto"],
    "groovy": ["natsu yasumi", "kinyoubi no yoru", "tanoshii hibi", "sanbashi", "natsu no kaze", "kaigan doori"],
}
JP_A = ["yoru no", "asa no", "natsu no", "ame no", "kaze no", "machi no"]
JP_N = ["hikari", "oto", "iro", "kaori", "sora", "michi", "kage", "yume"]

# What they mean (for checking): ranpu no akari = lamp light, tsukue no ue = on the desk, yoru no shosai = night study,
# shizuka na yoru = quiet night, mado no ame = rain at the window, ame no hi = rainy day, ame agari = after the rain,
# ame no oto = sound of rain, asa no densha = morning train, ichiban densha = first train, yoake no eki = station at dawn,
# asa no hikari = morning light, natsu no yuugure = summer dusk, natsu no owari = end of summer, tooi natsu = distant summer,
# yuuyake = sunset glow, neon no machi = neon town, yoru no machi = night town, machi no akari = city lights, yakei = night view,
# toshokan no gogo = library afternoon, peeji no oto = sound of pages, shizuka na heya = quiet room, hon no kaori = scent of books,
# okujou no yuuhi = rooftop sunset, yuugure no sora = dusk sky, sora no iro = colour of the sky, tooi yakei = distant night view,
# kissaten = old-style coffee shop, gogo no koohii = afternoon coffee, madogiwa no seki = window seat, koohii no yuge = coffee steam,
# kaigan doori = coast road, yoru no doraibu = night drive, umi e no michi = road to the sea, natsu no kaze = summer wind,
# nagai yoru = long night, shuuden made = until the last train, yonaka no hikari = midnight light, yakin = night duty,
# nichiyoubi no asa = Sunday morning, yukkuri no hi = slow day, nonbiri = leisurely, kyou wa yasumi = today is a day off,
# hitoyasumi = a short break, shuuchuu = concentration, shuuchuu no jikan = time of focus, sunadokei = hourglass,
# tsukiakari = moonlight, hoshizora = starry sky, yoake = dawn, yume no tochuu = in the middle of a dream,
# mizuumi no asa = morning at the lake, kaze no oto = sound of the wind, natsu yasumi = summer holiday,
# kinyoubi no yoru = Friday night, tanoshii hibi = fun days, sanbashi = pier.
STYLES = ["mix", "english", "japanese"]

GENERIC = {
    "calm": ["soft landing", "gentle focus", "easy tide", "low light loop", "warm static", "hush hour",
             "slow bloom", "quiet current", "paper lantern", "moon on the desk", "mellow hours", "still water"],
    "groovy": ["golden hour groove", "bounce in the step", "palm tree funk", "summer bassline", "rooftop boogie",
               "skyline strut", "shuffle on the stereo", "left lane groove", "sunny side funk", "city pop swagger"],
}
ADJ = {"calm": ["soft", "quiet", "slow", "warm", "gentle", "hazy", "mellow", "dreamy"],
       "groovy": ["bright", "sunny", "bouncy", "golden", "smooth", "neon", "breezy", "lively"]}
NOUN = ["morning", "evening", "window", "street", "lamp", "tide", "skyline", "afternoon", "balcony", "daydream"]


def _scene_pool(scene: str, style: str, rng: random.Random) -> list[str]:
    """Names for one scene, in the order they will be handed out (we pop from the end)."""
    en = rng.sample(POOLS.get(scene, []), len(POOLS.get(scene, [])))
    jp = rng.sample(JP_POOLS.get(scene, []), len(JP_POOLS.get(scene, [])))
    if style == "english":
        return en
    if style == "japanese":
        return jp
    first_jp = rng.random() < 0.5                      # mix: alternate, starting with a random language
    a, b = (jp, en) if first_jp else (en, jp)
    mixed = [x for pair in itertools.zip_longest(a, b) for x in pair if x]
    return mixed[::-1]


def suggest(scenes: list[str], count: int, taken=(), mood: str = "calm", seed=None, style: str = "mix") -> list[str]:
    """`count` names, round-robin over `scenes`, none equal to anything in `taken` or to each other.
    style: 'mix' (english and romanised japanese), 'english' or 'japanese'."""
    rng = random.Random(seed)
    mood = mood if mood in GENERIC else "calm"
    style = style if style in STYLES else "mix"
    used = {t.strip().lower() for t in taken}
    en_gen = rng.sample(GENERIC[mood], len(GENERIC[mood]))
    jp_gen = rng.sample(JP_GENERIC[mood], len(JP_GENERIC[mood]))
    en_combo = [f"{a} {n}" for a, n in itertools.product(ADJ[mood], NOUN)]
    jp_combo = [f"{a} {n}" for a, n in itertools.product(JP_A, JP_N)]
    rng.shuffle(en_combo); rng.shuffle(jp_combo)
    if style == "english":
        fallbacks = [en_gen, en_combo]
    elif style == "japanese":
        fallbacks = [jp_gen, jp_combo]
    else:
        fallbacks = [[x for pair in itertools.zip_longest(en_gen, jp_gen) for x in pair if x][::-1],
                     [x for pair in itertools.zip_longest(en_combo, jp_combo) for x in pair if x][::-1]]
    scene_list = scenes or list(POOLS)
    pools = {sc: _scene_pool(sc, style, rng) for sc in set(scene_list)}
    out, i = [], 0
    while len(out) < count:
        pool = pools[scene_list[i % len(scene_list)]]
        i += 1
        name = None
        for source in [pool] + fallbacks:              # own scene first, then mood names, then combinations
            while source:
                cand = source.pop()
                if cand not in used:
                    name = cand
                    break
            if name:
                break
        if name is None:                               # everything used: numbered fallback, still unique
            name = f"slow hour {len(used) + 1}"
        used.add(name); out.append(name)
    return out
