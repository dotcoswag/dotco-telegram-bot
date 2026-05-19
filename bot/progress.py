"""Bridge from a worker thread (sync scraper) back to the asyncio loop (Telegram bot)."""

import asyncio
import time

from bot import config


class ProgressBridge:
    """Send throttled progress messages from a worker thread to a Telegram chat.

    The scraper is synchronous and runs in a thread-pool executor. PTB's bot
    methods are coroutines on the main asyncio loop. We bridge by scheduling
    each send via asyncio.run_coroutine_threadsafe.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, bot, chat_id: int):
        self._loop = loop
        self._bot = bot
        self._chat_id = chat_id
        self._last_sent = 0.0

    def push(self, text: str, force: bool = False) -> None:
        now = time.time()
        if not force and (now - self._last_sent) < config.PROGRESS_THROTTLE_SECONDS:
            return
        self._last_sent = now
        try:
            asyncio.run_coroutine_threadsafe(
                self._bot.send_message(chat_id=self._chat_id, text=text),
                self._loop,
            )
        except Exception:
            # Best-effort progress — never fail the scrape because of a send error.
            pass
