"""Env config for the Telegram bot."""

import os
import sys

from dotenv import load_dotenv

load_dotenv()


def _required(name: str) -> str:
    val = os.getenv(name, "").strip()
    if not val:
        print(f"FATAL: {name} is not set. See .env.example.", file=sys.stderr)
        sys.exit(1)
    return val


TELEGRAM_BOT_TOKEN = _required("TELEGRAM_BOT_TOKEN")
WEBHOOK_BASE_URL = _required("WEBHOOK_BASE_URL").rstrip("/")
WEBHOOK_SECRET_TOKEN = os.getenv("WEBHOOK_SECRET_TOKEN", "").strip() or None
PORT = int(os.getenv("PORT", "10000"))

CHAT_COOLDOWN_SECONDS = 30
PROGRESS_THROTTLE_SECONDS = 3
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # Telegram bot document limit

# Leads master DB — bot/leads_db.py
GITHUB_LEADS_REPO = os.getenv("GITHUB_LEADS_REPO", "").strip()
GITHUB_PAT = os.getenv("GITHUB_PAT", "").strip()
MASTER_FLUSH_EVERY_N = int(os.getenv("MASTER_FLUSH_EVERY_N", "50"))
COMBO_FRESH_DAYS = int(os.getenv("COMBO_FRESH_DAYS", "30"))
