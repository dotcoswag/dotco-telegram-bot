"""Tiny GitHub Contents API client for the leads DB.

Only what the bot needs: read a file (raw + sha), write a file with the prior
sha (the API mandates this for updates), retry on transient 5xx.

The bot uses this to persist `data/master_leads.csv` and `data/scrape_log.csv`
inside the private repo `dotcoswag/dotco-leads-db`.

A memory-backed shim is selected via env `LEADS_DB_BACKEND=memory` so tests can
run without touching GitHub.
"""

import base64
import os
import time
from typing import Optional, Tuple

import requests


class StorageError(Exception):
    pass


_API_BASE = "https://api.github.com"


def _backend() -> str:
    return os.getenv("LEADS_DB_BACKEND", "github").strip().lower()


def _repo() -> str:
    repo = os.getenv("GITHUB_LEADS_REPO", "").strip()
    if not repo:
        raise StorageError("GITHUB_LEADS_REPO is not set")
    return repo


def _pat() -> str:
    pat = os.getenv("GITHUB_PAT", "").strip()
    if not pat:
        raise StorageError("GITHUB_PAT is not set")
    return pat


def _headers() -> dict:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {_pat()}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "dotco-telegram-bot",
    }


# ── in-memory backend (tests) ────────────────────────────────

_MEM: dict[str, tuple[bytes, str]] = {}  # path -> (content, sha)


def _mem_get(path: str) -> Tuple[Optional[bytes], Optional[str]]:
    entry = _MEM.get(path)
    return entry if entry else (None, None)


def _mem_put(path: str, content: bytes, prior_sha: Optional[str], message: str) -> str:
    existing = _MEM.get(path)
    if existing is not None and prior_sha != existing[1]:
        # Simulate GitHub's 409 conflict.
        raise StorageError(f"conflict: prior_sha mismatch for {path}")
    import hashlib
    new_sha = hashlib.sha1(content + str(time.time()).encode()).hexdigest()
    _MEM[path] = (content, new_sha)
    return new_sha


def _mem_reset_for_tests() -> None:
    _MEM.clear()


# ── GitHub backend ───────────────────────────────────────────

def _gh_get(path: str) -> Tuple[Optional[bytes], Optional[str]]:
    url = f"{_API_BASE}/repos/{_repo()}/contents/{path}"
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=_headers(), timeout=20)
        except requests.RequestException as e:
            if attempt == 2:
                raise StorageError(f"GET {path} failed after retries: {e}") from e
            time.sleep(2 ** attempt)
            continue
        if resp.status_code == 404:
            return None, None
        if resp.status_code >= 500 and attempt < 2:
            time.sleep(2 ** attempt)
            continue
        if not resp.ok:
            raise StorageError(f"GET {path} → {resp.status_code}: {resp.text[:200]}")
        body = resp.json()
        encoded = body.get("content") or ""
        # GitHub returns base64 with embedded newlines.
        content = base64.b64decode(encoded.encode()) if encoded else b""
        return content, body.get("sha")
    return None, None


def _gh_put(path: str, content: bytes, prior_sha: Optional[str], message: str) -> str:
    url = f"{_API_BASE}/repos/{_repo()}/contents/{path}"
    payload = {
        "message": message,
        "content": base64.b64encode(content).decode(),
    }
    if prior_sha:
        payload["sha"] = prior_sha
    for attempt in range(3):
        try:
            resp = requests.put(url, headers=_headers(), json=payload, timeout=30)
        except requests.RequestException as e:
            if attempt == 2:
                raise StorageError(f"PUT {path} failed after retries: {e}") from e
            time.sleep(2 ** attempt)
            continue
        if resp.status_code == 409:
            # Conflict — caller must re-GET to refresh sha and retry from its end.
            raise StorageError(f"conflict: sha mismatch for {path}")
        if resp.status_code >= 500 and attempt < 2:
            time.sleep(2 ** attempt)
            continue
        if not resp.ok:
            raise StorageError(f"PUT {path} → {resp.status_code}: {resp.text[:300]}")
        return resp.json()["content"]["sha"]
    raise StorageError(f"PUT {path}: exhausted retries")


# ── public API ───────────────────────────────────────────────

def get_file(path: str) -> Tuple[Optional[bytes], Optional[str]]:
    """Return (content_bytes, sha) for the file, or (None, None) if 404."""
    if _backend() == "memory":
        return _mem_get(path)
    return _gh_get(path)


def put_file(path: str, content: bytes, prior_sha: Optional[str], message: str) -> str:
    """Create or update the file. Returns the new sha."""
    if _backend() == "memory":
        return _mem_put(path, content, prior_sha, message)
    return _gh_put(path, content, prior_sha, message)
