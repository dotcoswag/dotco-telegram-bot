"""RapidAPI quota helper for the Telegram bot.

Reads response headers from the `local-business-data` endpoint to surface
monthly quota usage to the user before/after each scrape.

Header reference (observed 2026-05-19):
  x-ratelimit-businesses-limit       — monthly cap on businesses returned
  x-ratelimit-businesses-remaining   — can go negative when over-limit
  x-ratelimit-businesses-reset       — seconds until quota resets
Each business returned by /search counts as 1 against the BUSINESSES quota.
"""

import os
from typing import Optional

import requests


URL = "https://local-business-data.p.rapidapi.com/search"


def fetch() -> Optional[dict]:
    """Probe the API with a 1-result query and return quota info from headers.

    Returns dict with keys: limit, remaining, reset_seconds — or None on error.
    The probe call itself consumes at most 1 business from the quota when the
    quota is not yet exhausted; when exhausted, RapidAPI returns 429 (free probe).
    """
    key = os.getenv("RAPIDAPI_KEY", "").strip()
    if not key:
        return None
    try:
        resp = requests.get(
            URL,
            headers={
                "x-rapidapi-key": key,
                "x-rapidapi-host": "local-business-data.p.rapidapi.com",
            },
            params={
                "query": "restaurant",
                "limit": 1,
                "region": "us",
                "language": "en",
                "extract_emails_and_contacts": "false",
            },
            timeout=15,
        )
    except Exception:
        return None
    h = resp.headers
    try:
        return {
            "limit": int(h.get("x-ratelimit-businesses-limit", "0")),
            "remaining": int(h.get("x-ratelimit-businesses-remaining", "0")),
            "reset_seconds": int(h.get("x-ratelimit-businesses-reset", "0")),
        }
    except (TypeError, ValueError):
        return None


def format_reset(seconds: int) -> str:
    if seconds <= 0:
        return "soon"
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    if days > 0:
        return f"{days}d {hours}h"
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def summary_line(info: Optional[dict]) -> str:
    if info is None:
        return "RapidAPI quota: (couldn't fetch)"
    used = info["limit"] - info["remaining"]
    pct = (used / info["limit"] * 100) if info["limit"] > 0 else 0
    sign = "" if info["remaining"] >= 0 else " ⚠️ OVER LIMIT"
    return (
        f"RapidAPI quota (businesses): {used}/{info['limit']} used "
        f"({pct:.0f}%) — resets in {format_reset(info['reset_seconds'])}{sign}"
    )
