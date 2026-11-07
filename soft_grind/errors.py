"""Plain-language versions of the errors the services return, with what to do about them."""
from __future__ import annotations

import re

RULES = [
    (r"insufficient|balance|used_up|quota|out of credit|exceeded|payment|top up|credits? (is|are) (not enough|exhausted)",
     "You are out of credits (or over the limit of this key).",
     "Top up at platform.acedata.cloud, or raise the usage limit of the key. Videos that were already made are safe."),
    (r"invalid_token|no_token|token_expired|rejected this key|invalid or wrong|401",
     "The service did not accept this key.",
     "Open settings, paste the key again, press 'save keys', then use 'check my setup'."),
    (r"token_mismatched|not allowed to use|not matched with api",
     "This key is not allowed to use this service.",
     "Use a key from the General application, or allow this service on the key in the AceDataCloud console."),
    (r"disabled",
     "AceDataCloud has disabled this application.", "Contact their support from the console."),
    (r"too_many_requests|429|rate limit|too many requests",
     "The service says there are too many requests right now.", "Wait a minute and press continue or try again."),
    (r"forbidden|safety|blocked by content",
     "The service refused this request on safety grounds.", "Change the prompt or the image a little and try again. Nothing was charged."),
    (r"could not reach|internet|timed out|too long to answer|could not connect|connection",
     "The internet connection failed.", "Check your connection. Press continue or try again: finished steps are kept."),
    (r"api_error|500|internal server error",
     "The service had a problem on its side.", "Try again in a few minutes."),
    (r"no space left|disk full|errno 28",
     "The disk is full.", "Delete or archive old videos (videos page), then try again."),
    (r"access is denied|permission",
     "The computer would not allow access to a file.", "Close any video player or File Explorer window showing this video, then try again."),
    (r"no still image|no tracks",
     "Something this step needs is missing.", "Make the cover first (cover tab) and make sure the video has tracks (music tab)."),
]


def explain(raw: str) -> dict:
    """{'title','advice','raw'}: the first rule that matches, else a generic message. `raw` is kept for copying."""
    text = (raw or "").strip()
    for pattern, title, advice in RULES:
        if re.search(pattern, text, re.I):
            return {"title": title, "advice": advice, "raw": text}
    return {"title": "Something went wrong.", "advice": "Press try again. If it keeps happening, copy the details below and send them to me.",
            "raw": text}
