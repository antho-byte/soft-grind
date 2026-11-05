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

MODELS = ["chirp-v5-5", "chirp-v5", "chirp-v4-5"]

# ---- YouTube ----
TAGS_BASE = [
    "city pop", "japanese city pop", "lofi", "study music", "work music", "focus music",
    "deep work", "80s city pop", "instrumental city pop", "japanese fusion", "chill beats",
    "soft grind",
]
HASHTAGS_BASE = ["#citypop", "#lofi", "#studymusic", "#workmusic"]
MOODS = {"calm": "#calm", "groovy": "#groovy", "late night": "#nightvibes", "sunset": "#sunset"}

# Inspired-by artists: title/description only, never tags. Rotate.
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
