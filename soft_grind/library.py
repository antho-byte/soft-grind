"""Image library: scan a folder, look at each image (AI vision, or a free colour check), match images to videos."""
from __future__ import annotations

import hashlib
import json
import random
import re
import time
from pathlib import Path

from PIL import Image

from . import brand, imagegen, projects, settings

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}
ANALYSIS_SYSTEM = (
    "You describe images for a YouTube music channel called soft grind (instrumental city pop and lofi for working and studying). "
    "Look at the image and reply with ONLY a JSON object with these keys: "
    "description (one short sentence), mood ('calm' or 'groovy'), time ('morning','day','sunset' or 'night'), "
    "scenes (up to 3 items chosen ONLY from this list: " + json.dumps(brand.SCENES) + "), keywords (3 to 6 single words), "
    "has_text (true if any readable or fake text, letters or numbers appear in the image), has_people (true or false), "
    "risks (a list of short strings from: 'garbled japanese text','artist signature','brand logo','number plate','copyrighted character'; "
    "an empty list if none)."
)


# ---------- files + cache ----------
def scan(folder) -> list[Path]:
    f = Path(folder) if folder else None
    if not f or not f.is_dir():
        return []
    return sorted(p for p in f.rglob("*") if p.is_file() and p.suffix.lower() in IMG_EXT and not p.name.startswith("."))


def load_db() -> dict:
    return projects.read_json(settings.LIBRARY_FILE)


def save_db(db: dict) -> None:
    projects.write_json(settings.LIBRARY_FILE, db)


def fingerprint(p: Path) -> str:
    st = Path(p).stat()
    return f"{st.st_size}-{st.st_mtime_ns}"


def needs_analysis(db: dict, p: Path) -> bool:
    rec = db.get(str(p))
    return not rec or rec.get("fp") != fingerprint(p) or not rec.get("analysis")


def basic_info(p: Path) -> dict:
    with Image.open(p) as im:
        w, h = im.size
    return {"w": w, "h": h, "orientation": "vertical" if h > w * 1.05 else ("square" if abs(w / h - 1) < 0.15 else "landscape")}


def thumb(p: Path, side: int = 420) -> Path:
    """Small cached preview, so a grid of 60 big images stays fast."""
    settings.THUMBS_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{p}|{fingerprint(p)}|{side}".encode()).hexdigest()[:16]
    out = settings.THUMBS_DIR / f"{key}.jpg"
    if not out.exists():
        with Image.open(p) as im:
            im = im.convert("RGB"); im.thumbnail((side, side))
            im.save(out, "JPEG", quality=82)
    return out


def safe_thumb(p: Path, side: int = 420) -> Path | None:
    """thumb(), but a damaged or unreadable image gives None instead of an error."""
    try:
        return thumb(p, side)
    except Exception:
        return None


# ---------- looking at an image ----------
def heuristic_analysis(p) -> dict:
    """Free, offline guess from colours only (no AI): brightness, saturation and dominant hue. `p` is a path or an image."""
    import colorsys
    if isinstance(p, Image.Image):
        small = p.convert("RGB").resize((48, 27))
    else:
        with Image.open(p) as im:
            small = im.convert("RGB").resize((48, 27))
    px = [small.getpixel((x, y)) for y in range(small.height) for x in range(small.width)]
    n = len(px)
    hs = [colorsys.rgb_to_hsv(r / 255, g / 255, b / 255) for r, g, b in px]
    val = sum(v for _, _, v in hs) / n
    sat = sum(s for _, s, _ in hs) / n
    warm = sum(1 for h, s, v in hs if s > .25 and (h < .1 or h > .88)) / n          # pink / orange / red
    green = sum(1 for h, s, v in hs if s > .25 and .25 < h < .45) / n
    blue = sum(1 for h, s, v in hs if s > .25 and .5 < h < .75) / n
    if val < .38:
        time_, scenes = "night", ["night shift", "neon city walk", "late night desk lamp"]
    elif warm > .25:
        time_, scenes = "sunset", ["poolside sunset", "rooftop at dusk", "palm trees and highway"]
    elif sat < .18:
        time_, scenes = "day", ["rainy window", "quiet library", "coffee shop corner"]
    elif green > .2:
        time_, scenes = "day", ["palm trees and highway", "slow sunday", "morning train ride"]
    else:
        time_, scenes = ("morning" if blue > .3 else "day"), ["morning train ride", "open laptop", "coffee shop corner"]
    mood = "groovy" if (val > .55 and sat > .45) else "calm"
    return {"description": f"{time_} scene, {'bright and colourful' if mood == 'groovy' else 'soft and quiet'} (colour check)",
            "mood": mood, "time": time_, "scenes": scenes, "keywords": [time_], "has_text": False, "has_people": False,
            "risks": [], "method": "colors"}


def parse_analysis(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON in the answer")
    d = json.loads(m.group(0))
    scenes = [s for s in (d.get("scenes") or []) if s in brand.SCENES][:3]
    return {"description": str(d.get("description", ""))[:200], "mood": "groovy" if d.get("mood") == "groovy" else "calm",
            "time": d.get("time") if d.get("time") in ("morning", "day", "sunset", "night") else "day",
            "scenes": scenes, "keywords": [str(k) for k in (d.get("keywords") or [])][:6],
            "has_text": bool(d.get("has_text")), "has_people": bool(d.get("has_people")),
            "risks": [str(r) for r in (d.get("risks") or [])][:5], "method": "ai"}


def analyse(p: Path, client=None) -> tuple[dict, float]:
    """(analysis, credits). With an AIClient the model looks at the picture; without one, a colour check is used."""
    info = basic_info(p)
    if client is None:
        return {**heuristic_analysis(p), **info}, 0.0
    with Image.open(p) as im:
        uri = imagegen.to_data_uri(im, 768)
    text, cost = client.chat(ANALYSIS_SYSTEM, "Describe this image.", max_tokens=300, temperature=0.2, images=[uri])
    return {**parse_analysis(text), **info}, cost


def analyse_pending(files: list[Path], client=None, on_progress=None) -> float:
    db, spent = load_db(), 0.0
    todo = [p for p in files if needs_analysis(db, p)]
    for i, p in enumerate(todo, 1):
        try:
            a, cost = analyse(p, client)
            db[str(p)] = {"fp": fingerprint(p), "analysis": a, "cost": cost, "at": time.time()}
            spent += cost
        except Exception as e:                                   # one bad image must not stop the other 59
            db[str(p)] = {"fp": fingerprint(p), "analysis": None, "error": f"{e.__class__.__name__}: {e}"}
        save_db(db)
        if on_progress:
            on_progress(i, len(todo), p.name)
    return spent


def start_library_job(folder: str, use_ai: bool, ai_token: str = "", ai_model: str = "") -> None:
    if library_job_status()["running"]:
        raise RuntimeError("The images are already being looked at.")
    projects.write_json(settings.LIBRARY_JOB, {"state": "queued", "done": 0, "total": 0, "message": "queued", "updated": time.time(),
                                               "spec": {"folder": str(folder), "use_ai": use_ai, "model": ai_model}})
    projects._spawn("soft_grind.library_worker", settings.DATA_DIR, settings.LIBRARY_JOB.name,
                    {"SOFTGRIND_AI_TOKEN": ai_token if use_ai else ""})


def library_job_status() -> dict:
    j = projects.read_json(settings.LIBRARY_JOB)
    if not j:
        return {"state": "none", "running": False, "progress": 0.0, "message": "", "error": "", "done": 0, "total": 0}
    fresh = time.time() - j.get("updated", 0) < projects.STALE_AFTER
    state = j.get("state", "none")
    if state in ("queued", "running") and not fresh:
        state = "interrupted"
    total = max(1, j.get("total", 0))
    return {"state": state, "running": state in ("queued", "running"), "progress": min(1.0, j.get("done", 0) / total),
            "message": j.get("message", ""), "error": j.get("error", ""), "done": j.get("done", 0), "total": j.get("total", 0),
            "spent": j.get("spent", 0.0)}


# ---------- matching images to videos ----------
def used_images(root: Path) -> dict[str, str]:
    """image path -> name of the video that uses it."""
    out = {}
    for d in projects.project_dirs(root):
        img = projects.meta(d).get("library_image")
        if img:
            out[img] = d.name
    return out


def score(rec: dict, topic: list[str], mood: str, used_by: str | None) -> tuple[float, list[str]]:
    a = rec.get("analysis") or {}
    s, why = 0.0, []
    fit = [sc for sc in a.get("scenes", []) if sc in topic]
    if fit:
        s += min(6, 3 * len(fit)); why.append("fits " + ", ".join(fit))
    if a.get("mood") == mood:
        s += 2; why.append(f"{mood} mood")
    if used_by:
        s -= 12; why.append(f"already used in {used_by}")
    if a.get("risks"):
        s -= 3 * len(a["risks"]); why.append("check: " + ", ".join(a["risks"]))
    if a.get("has_text"):
        s -= 4; why.append("has text in the image")
    if a.get("orientation") == "vertical":
        s -= 1; why.append("vertical: gets a 16:9 fill")
    if a.get("w", 9999) < 1920:
        s -= 1; why.append("under 1920px wide")
    return s, why


def suggest(db: dict, topic: list[str], mood: str, used: dict[str, str], seed: str = "", n: int = 3) -> list[dict]:
    """Best n images for a video, rotating between close scores so every video does not get the same picture."""
    rng = random.Random(seed)
    rows = []
    for path, rec in db.items():
        if not rec.get("analysis") or not Path(path).exists():
            continue
        sc, why = score(rec, topic, mood, used.get(path))
        rows.append({"path": path, "score": sc + rng.random() * 0.9, "why": why, "analysis": rec["analysis"]})
    return sorted(rows, key=lambda r: r["score"], reverse=True)[:n]


def prepare_for_project(path: Path, pdir: Path) -> Path:
    """Put a library image into the project as <name>_16x9.png (vertical ones get the free blur fill)."""
    path, pdir = Path(path), Path(pdir)
    imgs = pdir / "images"; imgs.mkdir(parents=True, exist_ok=True)
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.save(imgs / f"{path.stem}_source.png")
        if im.height > im.width * 1.05:
            out = imagegen.blur_fill(im)
        else:
            out, _ = imagegen.finish_16x9(im)
        if out.width > 3840:
            out = out.resize((3840, round(out.height * 3840 / out.width)))
        dest = imgs / f"{path.stem}_16x9.png"
        out.save(dest)
    projects.set_meta(pdir, library_image=str(path))
    return dest
