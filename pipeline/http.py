"""Small HTTP helper with retries, back-off and honest failure reporting."""
from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0 Safari/537.36 market-intelligence-research/1.0",
    "Accept": "*/*",
    "Accept-Language": "en-IN,en;q=0.9",
}


class FetchError(RuntimeError):
    pass


def get(url: str, *, headers: dict | None = None, timeout: float = 20, retries: int = 3,
        backoff: float = 2.0, session: requests.Session | None = None) -> requests.Response:
    """GET with retries. Raises FetchError (never returns fabricated content)."""
    sess = session or requests
    merged = {**HEADERS, **(headers or {})}
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = sess.get(url, headers=merged, timeout=timeout)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise FetchError(f"HTTP {resp.status_code}")
            if resp.status_code >= 400:
                # client errors (403 blocked, 404 moved) will not fix themselves on retry
                raise FetchError(f"HTTP {resp.status_code} (not retried)")
            return resp
        except (requests.RequestException, FetchError) as exc:
            last = exc
            if "not retried" in str(exc):
                break
            if attempt < retries:
                time.sleep(backoff ** attempt)
    raise FetchError(f"{url}: {last}")
