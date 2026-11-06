"""Optional app password + remote-access switch.

- By default the app only listens on this computer (127.0.0.1): nobody else on the Wi-Fi can open it.
- "Allow other devices" binds it to the network, but ONLY when a password is also set (enforced by update.py before the server starts).
- The password is stored as a salted hash, never as text. Wrong guesses are slowed down and then locked for a while.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import socket
import time

from . import projects, settings

ITER = 200_000
MAX_FAILS, WINDOW, LOCK_SECONDS = 5, 600, 300
STATE_FILE = settings.DATA_DIR / "auth_state.json"


def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, ITER)
    return f"pbkdf2_sha256${ITER}${salt.hex()}${h.hex()}"


def verify(pw: str, stored: str) -> bool:
    try:
        _, it, salt, h = stored.split("$")
        got = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), int(it))
        return hmac.compare_digest(got.hex(), h)
    except (ValueError, TypeError):
        return False


def password_hash() -> str:
    return settings._read_settings().get("app_password", "")


def set_password(pw: str) -> None:
    if len(pw) < 8:
        raise ValueError("Use at least 8 characters.")
    settings._write_settings(app_password=hash_password(pw))


def remove_password() -> None:
    settings._write_settings(app_password="", remote_access=False)       # remote access is never allowed without a password


def remote_wanted() -> bool:
    return bool(settings._read_settings().get("remote_access"))


def set_remote(on: bool) -> None:
    if on and not password_hash():
        raise ValueError("Set a password first: other devices may only connect with one.")
    settings._write_settings(remote_access=bool(on))


def remote_effective() -> bool:
    return remote_wanted() and bool(password_hash())


def locked_for() -> int:
    """Seconds left of a lockout (0 = not locked)."""
    s = projects.read_json(STATE_FILE)
    return max(0, int(s.get("until", 0) - time.time()))


def register_failure() -> None:
    s = projects.read_json(STATE_FILE)
    now = time.time()
    if now - s.get("first", 0) > WINDOW:
        s = {"fails": 0, "first": now}
    s["fails"] = s.get("fails", 0) + 1
    if s["fails"] >= MAX_FAILS:
        s.update(until=now + LOCK_SECONDS, fails=0, first=now)
    projects.write_json(STATE_FILE, s)


def reset_failures() -> None:
    projects.write_json(STATE_FILE, {})


def check_login(pw: str) -> tuple[bool, str]:
    """(ok, message). Wrong guesses are delayed and, after five, blocked for five minutes."""
    wait = locked_for()
    if wait:
        return False, f"Too many wrong tries. Try again in {wait // 60 + 1} minute(s)."
    stored = password_hash()
    if stored and verify(pw, stored):
        reset_failures()
        return True, ""
    time.sleep(1.0)
    register_failure()
    return False, "That is not the password."


def lan_url(port: int = 8501) -> str:
    """Where a phone on the same Wi-Fi would open the app (best guess from this computer's address)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return f"http://{s.getsockname()[0]}:{port}"
    except OSError:
        return f"http://{socket.gethostname()}:{port}"
