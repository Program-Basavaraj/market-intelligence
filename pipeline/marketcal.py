"""NSE session calendar helpers (IST). Holidays are read from config/holidays.json, which you
should update each year from the official NSE holiday circular (no holidays are invented here)."""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta

from .config import IST, ROOT

CLOSE_DATA_READY = time(16, 30)   # EOD data is generally available after this time (IST)


def load_holidays(path=None) -> set[date]:
    p = path or ROOT / "config" / "holidays.json"
    try:
        data = json.loads(open(p, encoding="utf-8").read())
        return {date.fromisoformat(d) for d in data.get("nse_trading_holidays", [])}
    except (OSError, ValueError):
        return set()


def is_session(d: date, holidays: set[date]) -> bool:
    return d.weekday() < 5 and d not in holidays


def expected_last_session(now: datetime, holidays: set[date]) -> date:
    """Most recent session whose end-of-day data should already exist."""
    now = now.astimezone(IST)
    d = now.date()
    if not (is_session(d, holidays) and now.time() >= CLOSE_DATA_READY):
        d -= timedelta(days=1)
    while not is_session(d, holidays):
        d -= timedelta(days=1)
    return d


def sessions_between(a: date, b: date, holidays: set[date]) -> int:
    """Number of sessions strictly after a and up to and including b."""
    n, d = 0, a + timedelta(days=1)
    while d <= b:
        n += is_session(d, holidays)
        d += timedelta(days=1)
    return n


def is_stale(last_bar: date, now: datetime, holidays: set[date], tolerance_sessions: int = 1) -> bool:
    return sessions_between(last_bar, expected_last_session(now, holidays), holidays) > tolerance_sessions
