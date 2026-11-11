"""soft grind. channel brand: colours, voice, sound presets, metadata defaults."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "fonts"

COLORS = {
    "night_indigo": "#141852", "pool_blue": "#1466D6", "dusk_violet": "#5E5EE0",
    "sunset_pink": "#FF5F9E", "coral": "#FF7A6B", "apricot": "#FFC27A",
    "palm_green": "#1F7A5A", "sand": "#F6ECDD", "cyber_yellow": "#FCEE0A",
}

TAGLINE = "city pop to work and study to."

# ---- Suno sound presets (describe the sound, never artist names: Suno blocks them) ----
NEGATIVE_TAGS = "vocals, singing, lyrics, rap, choir, spoken word, screaming"

PRESETS = {
    "lofi soul (calm, ~70 bpm)": (
        "instrumental lofi with japanese soul, mellow rhodes electric piano, warm fretless bass, "
        "soft brushed drums, nylon guitar, vinyl crackle, 70 bpm, dreamy, nostalgic, 80s japanese city pop"
    ),
    "japanese jazz (calm, ~78 bpm)": (
        "instrumental japanese jazz fusion, smooth saxophone, jazzy electric piano chords, "
        "round bass, light swing drums, clean jazz guitar, 78 bpm, late night, warm, 80s city pop"
    ),
    "city pop funk (groovy, ~100 bpm)": (
        "instrumental japanese funk pop, 80s city pop, slap bass, bright fm synth, tight drums, "
        "jazzy guitar licks, brass stabs, 100 bpm, sunny, upbeat, groovy"
    ),
}

# Scene flavours rotated across tracks so 20 tracks do not sound identical.
SCENES = [
    "late night desk lamp", "rainy window", "morning train ride", "poolside sunset",
    "neon city walk", "quiet library", "rooftop at dusk", "coffee shop corner",
    "palm trees and highway", "night shift", "slow sunday", "open laptop",
]

# What each scene should SOUND like: Suno understands sound words far better than a bare scene name.
SCENE_SOUND = {
    "late night desk lamp": "late night mood, intimate and close, soft muted keys, slow and warm",
    "rainy window": "rainy day mood, soft rain ambience in the background, mellow and reflective",
    "morning train ride": "gentle forward motion, steady light groove, fresh morning feeling",
    "poolside sunset": "golden hour warmth, breezy and sunlit, relaxed summer groove",
    "neon city walk": "night city glow, shimmering synth pads, smooth walking groove",
    "quiet library": "quiet and focused, sparse arrangement, soft dynamics, room to think",
    "rooftop at dusk": "dusk sky, wide airy pads, unhurried and open",
    "coffee shop corner": "cosy cafe warmth, light brushed groove, round bass",
    "palm trees and highway": "open road, sunny 80s drive, bright and easy groove",
    "night shift": "after hours, steady focused pulse, deep warm bass",
    "slow sunday": "lazy sunday, very relaxed, soft and spacious",
    "open laptop": "productive and steady, clean focused groove, light and modern",
}

MODELS = ["chirp-v5-5", "chirp-v5", "chirp-v4-5"]

# ---- YouTube ----
TAGS_BASE = [
    "city pop", "japanese city pop", "lofi", "study music", "work music", "focus music",
    "deep work", "80s city pop", "instrumental city pop", "japanese fusion", "chill beats",
    "soft grind",
]
HASHTAGS_BASE = ["#citypop", "#lofi", "#studymusic", "#workmusic"]
MOODS = {"calm": "#calm", "groovy": "#groovy", "late night": "#nightvibes", "sunset": "#sunset"}

# What each sound is called in the description and which search words fit it (tags and the first hashtag vary per video).
SOUND_INFO = {
    "lofi soul (calm, ~70 bpm)": ("instrumental lofi soul and japanese city pop", ["lofi", "lofi soul", "chill beats", "lofi study", "rhodes"], "#lofi"),
    "japanese jazz (calm, ~78 bpm)": ("instrumental japanese jazz and city pop", ["japanese jazz", "jazz for study", "smooth jazz", "jazz fusion",
                                                                                  "late night jazz"], "#japanesejazz"),
    "city pop funk (groovy, ~100 bpm)": ("instrumental 80s japanese city pop funk", ["city pop funk", "80s funk", "japanese funk",
                                                                                     "groovy city pop", "80s japan"], "#citypop"),
}
SCENE_TAGS = {
    "late night desk lamp": ["late night study music", "night lofi"], "rainy window": ["rainy day music", "rain lofi"],
    "morning train ride": ["morning music", "commute music"], "poolside sunset": ["sunset music", "summer city pop"],
    "neon city walk": ["night city music", "tokyo night"], "quiet library": ["library study music", "quiet study music"],
    "rooftop at dusk": ["evening chill music", "dusk lofi"], "coffee shop corner": ["coffee shop music", "cafe music"],
    "palm trees and highway": ["drive music", "80s summer"], "night shift": ["night shift music", "late night work music"],
    "slow sunday": ["sunday morning music", "slow sunday"], "open laptop": ["coding music", "productivity music"],
}


def sound_of(style: str) -> str:
    """The preset name a style prompt came from ('' when it was written by hand or improved by the AI)."""
    for name, prompt in PRESETS.items():
        if style.strip() == prompt:
            return name
    s = style.lower()
    if "jazz" in s:
        return "japanese jazz (calm, ~78 bpm)"
    if "funk" in s or "slap bass" in s:
        return "city pop funk (groovy, ~100 bpm)"
    return "lofi soul (calm, ~70 bpm)" if "lofi" in s else ""


AI_LINE = "music made with AI tools, chosen, edited and mixed by soft grind."
NO_AI_LINE = "original instrumentals in the style of 80s japanese city pop."

# Old: inspired-by artists. No longer used in new texts (real artist names in AI-music metadata can count as misleading).
ARTISTS = [
    "Tatsuro Yamashita", "Masayoshi Takanaka", "Toshiki Kadomatsu", "Casiopea", "T-Square",
    "Hiroshi Sato", "Mariya Takeuchi", "Anri", "Miki Matsubara", "Omega Tribe",
]

PINNED_COMMENTS = [
    "what are you working on tonight?",
    "what are you building right now? tell us below.",
    "what's on your desk tonight? share it below.",
]

CHANNEL_GUIDELINES = [
    "be kind. everyone here is building something.",
    "tell us what you're building tonight.",
    "no self-promo, links or spam. keep it calm.",
]

DESCRIPTION_QUESTIONS = ["what are you working on tonight?", "what's the one thing you'll finish today?"]

# Used to fill the "scenario" in the playlist-style title when a new video starts.
SCENARIOS = ["studying at 2am", "working late", "on the night train", "at your desk", "finishing the deadline",
             "reading by the window", "building something", "on a rainy sunday"]

# Title phrases after the quote ("" = quote only). The AI picks or invents one; this is the no-AI fallback pool.
TITLE_SUFFIXES = ["80s japanese city pop to work & study to", "japanese city pop for deep focus", "instrumental city pop & lofi",
                  "city pop to focus to", "lofi city pop for late nights", "chill japanese fusion for work", "80s city pop for studying", ""]
SUBLINES = ["one more hour, then rest.", "soft music for the long stretch.", "keep it gentle tonight.", "a calm soundtrack for your desk.",
            "let the city hum along.", "slow grooves, steady focus.", "for the quiet part of the day.", "headphones on, world off."]
QUESTIONS = ["what are you working on tonight?", "what's the one thing you'll finish today?", "what are you building right now?",
             "what's on your desk this evening?", "what are you studying for?", "what's keeping you up tonight?"]
PINNED_EXTRA = ["what's on your desk tonight? share it below.", "tell us what you're building this evening.",
                "what are you focusing on right now?", "what's the plan for the next hour?", "share what you're working on, we'd love to know."]

# What things cost in AceDataCloud credits (from the owner's own numbers: 4 songs = 0.56, 1 image edit = 0.20). Estimates; AI text is exact.
CREDITS = {"suno_request": 0.28, "image_edit": 0.20}
