"""All bot modules import cleanly. Catches syntax + import-time errors fast."""


def test_bot_app_imports():
    from bot import app  # noqa: F401


def test_bot_handlers_import():
    from bot.handlers import (  # noqa: F401
        enrich,
        export_cmds,
        job_control,
        quota_status,
        scrape_flow,
        start_help,
    )


def test_bot_support_modules_import():
    from bot import api_quota, cities, config, job_manager, keyboards, progress, scrape_runner  # noqa: F401


def test_scraper_quota_exception_exported():
    from scraper import QuotaExhausted  # noqa: F401
