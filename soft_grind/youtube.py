"""Upload a finished video to YouTube (Data API v3) with plain HTTP: no Google libraries needed.

Login: the Google "Desktop app" OAuth flow with PKCE. The client file you download from Google Cloud and the token we get back
live in the data folder (owner-only), never in the repo, never in logs.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import http.server
import json
import os
import secrets
import time
import urllib.parse
import webbrowser
from pathlib import Path

import requests

from . import net, settings

SCOPE = "https://www.googleapis.com/auth/youtube.upload"
AUTH_URL = os.getenv("SOFTGRIND_YT_AUTH", "https://accounts.google.com/o/oauth2/v2/auth")
TOKEN_URL = os.getenv("SOFTGRIND_YT_TOKEN", "https://oauth2.googleapis.com/token")
API = os.getenv("SOFTGRIND_YT_API", "https://www.googleapis.com")
CHUNK = 8 * 256 * 1024 * 4          # 8 MB, a multiple of 256 KB as the API requires
MAX_THUMB = 2_000_000


class YouTubeError(Exception):
    pass


def _client_file() -> Path:
    return settings.DATA_DIR / "youtube_client.json"


def _token_file() -> Path:
    return settings.DATA_DIR / "youtube_token.json"


def _write_private(path: Path, data: dict) -> None:
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)     # owner-only from the first byte
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ---------- the client file from Google Cloud ----------
def save_client(raw: str | bytes) -> None:
    """Accept the downloaded JSON (Desktop app type). Raises YouTubeError with a plain message when it is the wrong file."""
    try:
        data = json.loads(raw)
    except ValueError:
        raise YouTubeError("That is not a JSON file. Use the file you downloaded from Google Cloud (Credentials, Download JSON).")
    inner = data.get("installed") or data.get("web")
    if not inner or not inner.get("client_id"):
        raise YouTubeError("This JSON does not look like a Google login file. Create an OAuth client of type 'Desktop app' and download that one.")
    if "installed" not in data:
        raise YouTubeError("This is a 'Web application' login file. Create a new OAuth client of type 'Desktop app' instead.")
    _write_private(_client_file(), {"installed": {k: inner.get(k, "") for k in ("client_id", "client_secret")}})


def has_client() -> bool:
    try:
        return bool(json.loads(_client_file().read_text(encoding="utf-8"))["installed"]["client_id"])
    except (OSError, ValueError, KeyError):
        return False


def _client() -> dict:
    try:
        return json.loads(_client_file().read_text(encoding="utf-8"))["installed"]
    except (OSError, ValueError, KeyError):
        raise YouTubeError("The Google login file is missing. Add it in settings, under 'youtube'.")


def connected() -> bool:
    try:
        return bool(json.loads(_token_file().read_text(encoding="utf-8")).get("refresh_token"))
    except (OSError, ValueError):
        return False


def disconnect() -> None:
    _token_file().unlink(missing_ok=True)


# ---------- login ----------
def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def login(timeout: float = 240.0, open_browser=webbrowser.open) -> None:
    """Open the browser for the one-time permission, wait for Google to call back on this computer, store the refresh token."""
    c = _client()
    verifier, challenge = _pkce()
    state = secrets.token_urlsafe(16)
    got: dict = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))
            if "code" in q or "error" in q:
                got.update(q)
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write(b"<html><body style='font-family:sans-serif;padding:40px'><h2>soft grind.</h2>"
                             b"<p>You can close this tab and go back to the app.</p></body></html>")

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    srv.timeout = 1.0
    redirect = f"http://127.0.0.1:{srv.server_port}"
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": c["client_id"], "redirect_uri": redirect, "response_type": "code", "scope": SCOPE, "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256", "access_type": "offline", "prompt": "consent"})
    open_browser(url)
    end = time.time() + timeout
    try:
        while time.time() < end and not got:
            srv.handle_request()
    finally:
        srv.server_close()
    if not got:
        raise YouTubeError("No answer from the browser. Press connect again and approve access in the Google window.")
    if got.get("error"):
        raise YouTubeError(f"Google said: {got['error']}. If it says access_denied, add your Gmail as a test user (consent screen) and retry.")
    if got.get("state") != state:
        raise YouTubeError("The login answer did not match this request. Try again.")
    r = _post_token({"client_id": c["client_id"], "client_secret": c.get("client_secret", ""), "code": got["code"],
                     "code_verifier": verifier, "redirect_uri": redirect, "grant_type": "authorization_code"})
    if not r.get("refresh_token"):
        raise YouTubeError("Google did not give a lasting login. Remove the app at myaccount.google.com/permissions and connect again.")
    _write_private(_token_file(), {"refresh_token": r["refresh_token"]})


def _post_token(data: dict) -> dict:
    try:
        r = net.request("POST", TOKEN_URL, retries=2, data=data, timeout=30)
    except requests.RequestException as e:
        raise YouTubeError(net.friendly(e))
    try:
        j = r.json()
    except ValueError:
        j = {}
    if r.status_code != 200:
        err = j.get("error", f"http {r.status_code}")
        if err == "invalid_grant":
            disconnect()
            raise YouTubeError("The YouTube login expired (Google does this every 7 days while the app is in 'testing'). "
                               "Press connect again, and set the consent screen to 'In production' to stop it.")
        raise YouTubeError(f"Google refused the login ({err}).")
    return j


def _access_token() -> str:
    try:
        refresh = json.loads(_token_file().read_text(encoding="utf-8"))["refresh_token"]
    except (OSError, ValueError, KeyError):
        raise YouTubeError("Not connected to YouTube yet. Open settings and press connect.")
    c = _client()
    return _post_token({"client_id": c["client_id"], "client_secret": c.get("client_secret", ""), "refresh_token": refresh,
                        "grant_type": "refresh_token"})["access_token"]


# ---------- what to send ----------
def _amsterdam_offset(local: dt.datetime) -> int:
    """Hours Amsterdam is ahead of UTC at this local time (EU summer time: last Sunday of March to last Sunday of October)."""
    def last_sunday(month: int) -> dt.datetime:
        d = dt.datetime(local.year, month, 31)
        return d - dt.timedelta(days=(d.weekday() + 1) % 7)
    start = last_sunday(3).replace(hour=2)
    end = last_sunday(10).replace(hour=3)
    return 2 if start <= local < end else 1


def publish_at(schedule: str, now: dt.datetime | None = None) -> str | None:
    """'2026-11-09 15:00' (Amsterdam) -> '2026-11-09T14:00:00Z'. None when empty, malformed or already in the past."""
    try:
        local = dt.datetime.strptime(schedule, "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return None
    utc = local - dt.timedelta(hours=_amsterdam_offset(local))
    if utc <= (now or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)) + dt.timedelta(minutes=5):
        return None
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_body(meta: dict, now: dt.datetime | None = None) -> dict:
    title = (meta.get("title") or "").replace("<", "").replace(">", "").strip()[:100]
    if not title:
        raise YouTubeError("This video has no title yet. Write the YouTube text first (video tab).")
    tags, size = [], 0
    for t in [x.strip() for x in (meta.get("tags") or "").replace("\n", ",").split(",") if x.strip()]:
        if size + len(t) + 1 > 480:
            break
        tags.append(t); size += len(t) + 1
    status = {"privacyStatus": "private", "selfDeclaredMadeForKids": False, "embeddable": True}
    when = publish_at(meta.get("schedule", ""), now)
    if when:
        status["publishAt"] = when
    return {"snippet": {"title": title, "description": (meta.get("description") or "").replace("<", "").replace(">", "")[:5000],
                        "tags": tags, "categoryId": "10", "defaultLanguage": "en"}, "status": status}


# ---------- upload ----------
def _check(r: requests.Response, what: str) -> None:
    if r.status_code < 300 or r.status_code == 308:
        return
    try:
        err = r.json().get("error", {})
        reason = (err.get("errors") or [{}])[0].get("reason", "") or err.get("status", "")
        msg = err.get("message", "")
    except ValueError:
        reason, msg = "", r.text[:200]
    if reason == "quotaExceeded" or r.status_code == 403 and "quota" in msg.lower():
        raise YouTubeError("YouTube's daily upload limit is used up. It resets at midnight Pacific time; try again tomorrow.")
    if reason in ("uploadLimitExceeded",):
        raise YouTubeError("YouTube says you reached the daily upload limit of this channel. Try again tomorrow.")
    if r.status_code == 401:
        raise YouTubeError("YouTube did not accept the login. Open settings and press connect again.")
    if reason in ("forbidden", "insufficientPermissions") or r.status_code == 403:
        raise YouTubeError(f"YouTube refused {what} ({reason or 403}): {msg[:160]}")
    raise YouTubeError(f"YouTube error while {what}: http {r.status_code} {reason} {msg[:160]}")


def upload_video(video: Path, meta: dict, on_progress=None, now: dt.datetime | None = None) -> str:
    """Resumable upload; returns the video id. Retries a broken connection by asking YouTube how much it already has."""
    video = Path(video)
    size = video.stat().st_size
    body = build_body(meta, now)
    tok = _access_token()
    H = {"Authorization": f"Bearer {tok}"}
    try:
        r = requests.post(f"{API}/upload/youtube/v3/videos", params={"uploadType": "resumable", "part": "snippet,status"},
                          headers={**H, "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)}, json=body, timeout=60)
        _check(r, "starting the upload")
        session = r.headers["Location"]
        pos, fails = 0, 0
        with open(video, "rb") as f:
            while True:
                f.seek(pos)
                chunk = f.read(CHUNK)
                end = pos + len(chunk) - 1
                try:
                    r = requests.put(session, data=chunk, timeout=600,
                                     headers={"Content-Length": str(len(chunk)), "Content-Range": f"bytes {pos}-{end}/{size}"})
                except requests.RequestException as e:
                    fails += 1
                    if fails > 6:
                        raise YouTubeError(net.friendly(e) + " The upload stopped; press upload again to continue.")
                    time.sleep(min(2 ** fails, 30))
                    q = requests.put(session, headers={"Content-Length": "0", "Content-Range": f"bytes */{size}"}, timeout=60)
                    if q.status_code == 308:
                        rng = q.headers.get("Range", "")
                        pos = int(rng.split("-")[1]) + 1 if "-" in rng else 0
                    continue
                if r.status_code in (200, 201):
                    vid = r.json()["id"]
                    if on_progress:
                        on_progress(1.0)
                    return vid
                if r.status_code == 308:
                    fails = 0
                    rng = r.headers.get("Range", "")
                    pos = int(rng.split("-")[1]) + 1 if "-" in rng else pos
                    if on_progress:
                        on_progress(min(pos / size, 0.99))
                    continue
                if r.status_code >= 500:
                    fails += 1
                    if fails > 6:
                        _check(r, "uploading")
                    time.sleep(min(2 ** fails, 30))
                    continue
                _check(r, "uploading")
    except requests.RequestException as e:
        raise YouTubeError(net.friendly(e))


def set_thumbnail(video_id: str, image: Path) -> str:
    """Returns '' on success or a plain-language note (the video itself is already safe on YouTube)."""
    image = Path(image)
    data, ctype = image.read_bytes(), "image/png"
    if len(data) > MAX_THUMB:
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.open(image).convert("RGB").save(buf, "JPEG", quality=90)
        data, ctype = buf.getvalue(), "image/jpeg"
    try:
        r = requests.post(f"{API}/upload/youtube/v3/thumbnails/set", params={"videoId": video_id, "uploadType": "media"},
                          headers={"Authorization": f"Bearer {_access_token()}", "Content-Type": ctype}, data=data, timeout=120)
    except requests.RequestException as e:
        return net.friendly(e)
    if r.status_code >= 300:
        if r.status_code == 403:
            return "YouTube did not accept the cover: the channel must be verified (youtube.com/verify). Set it by hand in YouTube Studio."
        return f"The cover could not be set (http {r.status_code}). Set it by hand in YouTube Studio."
    return ""


def studio_url(video_id: str) -> str:
    return f"https://studio.youtube.com/video/{video_id}/edit"
