"""Single-job global mutex + per-chat cooldown + cancellation.

Free-tier Render is single-instance and RAM-constrained — at most one scrape
or one enrich runs at a time. Cooldown protects RapidAPI/Anthropic quota when
the bot is open to anyone with the bot handle.
"""

import asyncio
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from bot import config


@dataclass
class Job:
    chat_id: int
    kind: str  # "scrape" | "enrich" | "export"
    started_at: float
    cancel_event: threading.Event = field(default_factory=threading.Event)
    last_progress: str = ""
    last_combo: str = ""

    def elapsed_seconds(self) -> int:
        return int(time.time() - self.started_at)


class JobManager:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._current: Optional[Job] = None
        self._cooldown: dict[int, float] = {}
        self._last_result_csv: dict[int, str] = {}

    # ── cooldown ─────────────────────────────────────────────
    def cooldown_remaining(self, chat_id: int) -> int:
        last = self._cooldown.get(chat_id, 0.0)
        remaining = config.CHAT_COOLDOWN_SECONDS - (time.time() - last)
        return max(0, int(remaining))

    def touch_cooldown(self, chat_id: int) -> None:
        self._cooldown[chat_id] = time.time()

    # ── job mutex ────────────────────────────────────────────
    async def try_acquire(self, chat_id: int, kind: str) -> Optional[Job]:
        """Returns the new Job on success, or None if another job is running."""
        async with self._lock:
            if self._current is not None:
                return None
            self._current = Job(chat_id=chat_id, kind=kind, started_at=time.time())
            return self._current

    async def release(self) -> None:
        async with self._lock:
            self._current = None

    @property
    def current(self) -> Optional[Job]:
        return self._current

    def cancel(self) -> bool:
        if self._current is None:
            return False
        self._current.cancel_event.set()
        return True

    # ── last result per chat ─────────────────────────────────
    def set_last_result(self, chat_id: int, csv_path: str) -> None:
        self._last_result_csv[chat_id] = csv_path

    def get_last_result(self, chat_id: int) -> Optional[str]:
        return self._last_result_csv.get(chat_id)


jobs = JobManager()
