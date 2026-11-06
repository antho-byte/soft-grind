"""Network calls that fail politely: plain-language messages, and a retry only where it cannot cost money twice."""
from __future__ import annotations

import time

import requests


def friendly(e: Exception) -> str:
    if isinstance(e, requests.exceptions.SSLError):
        return "A secure connection could not be made. Check the date and time of your computer, or any VPN or antivirus that inspects traffic."
    if isinstance(e, requests.exceptions.ConnectTimeout):
        return "Could not connect in time. Check your internet connection and try again."
    if isinstance(e, requests.exceptions.ReadTimeout):
        return "The service took too long to answer. Try again in a minute."
    if isinstance(e, requests.exceptions.ConnectionError):
        return "Could not reach the service. Check your internet connection and try again."
    return f"The request failed ({e.__class__.__name__}). Try again in a minute."


def request(method: str, url: str, retries: int = 0, delay: float = 2.0, **kw) -> requests.Response:
    """requests.request that retries only on 'could not connect' errors (nothing reached the server, so a retry is safe)."""
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return requests.request(method, url, **kw)
        except (requests.exceptions.ConnectionError, requests.exceptions.ConnectTimeout) as e:
            last = e
            if isinstance(e, requests.exceptions.ReadTimeout):       # the server may already be working on it: never retry
                break
            if attempt < retries:
                time.sleep(delay * (attempt + 1))
        except requests.exceptions.RequestException as e:
            last = e
            break
    assert last is not None
    raise last
