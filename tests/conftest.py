"""Pytest fixtures and env stubs so we can import bot.* without a real .env."""

import os
import sys

# Stub the required env vars BEFORE importing bot.config — that module exits
# the process if TELEGRAM_BOT_TOKEN or WEBHOOK_BASE_URL are missing.
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "0:test")
os.environ.setdefault("WEBHOOK_BASE_URL", "https://test.example.com")
os.environ.setdefault("WEBHOOK_SECRET_TOKEN", "test_secret")
os.environ.setdefault("PORT", "10000")
os.environ.setdefault("RAPIDAPI_KEY", "test_key_not_real")

# Ensure project root is on sys.path so `import bot.*` and `import scraper` work
# when pytest is invoked from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
