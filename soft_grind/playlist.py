"""Get tracks: from a published Suno playlist URL, a list of song links, or a local folder."""
from __future__ import annotations

import re
from pathlib import Path

import requests
from mutagen import File as MutagenFile

from .suno import download

UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".flac", ".ogg"}
UA = {"user-agent": "Mozilla/5.0", "accept": "application/json"}


class PlaylistError(RuntimeError):
    pass


def extract_ids(text: str) -> list[str]:
    seen, out = set(), []
    for m in UUID.findall(text):
        if m.lower() not in seen:
            seen.add(m.lower()); out.append(m.lower())
    return out


def fetch_playlist(url_or_id: str, max_pages: int = 10) -> tuple[str, list[dict]]:
    """Read a PUBLISHED Suno playlist. Returns (name, tracks)."""
    ids = extract_ids(url_or_id)
    if not ids:
        raise PlaylistError("No playlist id found in that link.")
    pid, tracks, name = ids[0], [], "playlist"
    for page in range(1, max_pages + 1):
        r = requests.get(f"https://studio-api.prod.suno.com/api/playlist/{pid}/",
                         params={"page": page}, headers=UA, timeout=30)
        if r.status_code in (401, 403, 404):
            raise PlaylistError(f"Suno returned {r.status_code}. Is the playlist published (public)?")
        r.raise_for_status()
        data = r.json()
        name = data.get("name") or name
        items = data.get("playlist_clips") or []
        if not items:
            break
        for it in items:
            c = it.get("clip") or {}
            if c.get("id"):
                tracks.append({"id": c["id"], "title": (c.get("title") or "untitled"),
                               "audio_url": c.get("audio_url") or f"https://cdn1.suno.ai/{c['id']}.mp3",
                               "duration": (c.get("metadata") or {}).get("duration") or 0})
    if not tracks:
        raise PlaylistError("Playlist is empty or could not be read.")
    return name, tracks


def tracks_from_song_links(text: str) -> list[dict]:
    """Fallback: paste suno.com/song/<id> links (one per line)."""
    return [{"id": i, "title": f"track {n:02d}", "audio_url": f"https://cdn1.suno.ai/{i}.mp3", "duration": 0}
            for n, i in enumerate(extract_ids(text), 1)]


def safe_name(s: str) -> str:
    return re.sub(r"[^a-z0-9 _-]+", "", s.lower()).strip()[:60] or "track"


def download_tracks(tracks: list[dict], out_dir: Path, progress=None) -> list[dict]:
    out = []
    for i, t in enumerate(tracks, 1):
        path = out_dir / f"{i:02d} - {safe_name(t['title'])}.mp3"
        if not path.exists():
            download(t["audio_url"], path)
        out.append({**t, "path": str(path), "duration": audio_duration(path) or t.get("duration") or 0})
        if progress:
            progress(i / len(tracks), t["title"])
    return out


def audio_duration(path: Path | str) -> float:
    try:
        f = MutagenFile(str(path))
        return float(f.info.length) if f is not None and f.info else 0.0
    except Exception:
        return 0.0


def tracks_from_folder(folder: str | Path) -> list[dict]:
    """Import already-downloaded audio (e.g. from usesuno.com). Title = filename without number prefix."""
    folder = Path(folder).expanduser()
    if not folder.is_dir():
        raise PlaylistError(f"Folder not found: {folder}")
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in AUDIO_EXT and not p.name.startswith("_"))
    if not files:
        raise PlaylistError("No audio files in that folder.")
    out = []
    for p in files:
        title = re.sub(r"^\d+\s*[-_.]\s*", "", p.stem).strip().lower() or p.stem.lower()
        out.append({"id": p.stem, "title": title, "path": str(p), "duration": audio_duration(p)})
    return out


def rename_files(tracks: list[dict], tracks_dir: Path) -> None:
    """Rename audio files that live in the project's tracks folder to 'NN - title.ext'.
    Files outside it (e.g. an imported folder) are never touched."""
    tracks_dir = Path(tracks_dir).resolve()
    for i, t in enumerate(tracks, 1):
        src = Path(t["path"])
        if not src.exists() or src.parent.resolve() != tracks_dir:
            continue
        dst = tracks_dir / f"{i:02d} - {safe_name(t['title'])}{src.suffix}"
        if dst != src:
            src.replace(dst)
            t["path"] = str(dst)
