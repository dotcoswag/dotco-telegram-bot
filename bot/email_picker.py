"""Pick the best email from a scraped business row.

The RapidAPI scraper already collects emails into two fields:
- `email`   : the primary email returned by the API
- `emails_extra` : a pipe-separated list of additional addresses pulled from the site

The primary is often a generic `info@` or `contact@`. The website-extracted
extras frequently include better ones — `firstname.lastname@`, `owner@`,
etc. This module ranks all available candidates and picks the highest-value
one for cold outreach.

No external APIs. No AI credits. Free, fast, deterministic.
"""

import re

_NOISE_LOCAL = {
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "postmaster", "abuse", "webmaster", "mailer-daemon",
    "automated", "notifications", "alerts",
}

_PREMIUM_ROLES = {
    "owner", "founder", "ceo", "president", "principal",
    "director", "manager", "general", "gm",
}

_GENERIC_ROLES = {"info", "contact", "hello", "team", "office", "mail", "main"}

_DEPARTMENT_ROLES = {
    "sales", "marketing", "support", "help", "service",
    "hr", "careers", "jobs", "billing", "accounting",
    "admin", "tech", "it",
}

_VALID_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _score(email: str) -> int:
    """Higher is better. Negative means 'never use'."""
    if not email or not _VALID_EMAIL.match(email):
        return -10
    local = email.split("@", 1)[0].lower()
    if local in _NOISE_LOCAL or local.startswith(tuple(_NOISE_LOCAL)):
        return -10
    # firstname.lastname / firstname_lastname / firstname-lastname → likely a real person
    if re.match(r"^[a-z]+[._-][a-z]+$", local):
        return 6
    # Premium role aliases (owner / ceo / founder / etc.) — explicit decision-maker
    if local in _PREMIUM_ROLES:
        return 5
    # Single token that ISN'T a known role → probably a first name (mike@, sarah@)
    if local.isalpha() and local not in _GENERIC_ROLES and local not in _DEPARTMENT_ROLES:
        return 4
    if local in _GENERIC_ROLES:
        return 2
    if local in _DEPARTMENT_ROLES:
        return 1
    # Anything else valid — keep but rank low
    return 0


def pick_best_email(primary: str, emails_extra: str) -> str:
    """Return the best email from primary + the pipe-separated extras list.

    Empty string if no usable candidate exists.
    """
    candidates: set[str] = set()
    if primary:
        candidates.add(primary.strip().lower())
    if emails_extra:
        for e in emails_extra.split("|"):
            e = e.strip().lower()
            if e:
                candidates.add(e)
    candidates.discard("")
    ranked = sorted(((email, _score(email)) for email in candidates),
                    key=lambda x: x[1], reverse=True)
    for email, score in ranked:
        if score >= 0:
            return email
    return ""
