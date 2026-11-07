"""Phone messages when a video is ready or something needs you, through ntfy (a free push service, no account).

The topic name is a random secret: whoever knows it can read the messages, so it is generated here and never guessable.
Messages carry only the video name and headline, never keys or file paths.
"""
from __future__ import annotations

import os
import secrets

from . import net, settings

DEFAULT_SERVER = "https://ntfy.sh"


def _cfg() -> dict:
    return settings._read_settings()


def topic() -> str:
    return _cfg().get("ntfy_topic", "")


def enabled() -> bool:
    return bool(_cfg().get("notify")) and bool(topic())


def server() -> str:
    return (os.getenv("SOFTGRIND_NTFY_SERVER") or _cfg().get("ntfy_server") or DEFAULT_SERVER).rstrip("/")


def enable() -> str:
    t = topic() or "softgrind-" + secrets.token_hex(10)
    settings._write_settings(notify=True, ntfy_topic=t)
    return t


def disable() -> None:
    settings._write_settings(notify=False)


def send(title: str, message: str, priority: str = "default", tags: str = "") -> bool:
    """Never raises: a message that cannot be sent must not stop a video."""
    if not enabled():
        return False
    headers = {"Title": title.encode("ascii", "replace").decode(), "Priority": priority}
    if tags:
        headers["Tags"] = tags
    try:
        r = net.request("POST", f"{server()}/{topic()}", data=message.encode("utf-8"), headers=headers, timeout=10)
        return r.status_code < 300
    except Exception:
        return False
