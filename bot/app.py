"""Telegram bot entry point.

Build the PTB Application, register handlers, and run the webhook server.
Bound to $PORT — works locally (PORT=10000 + ngrok) and on Render free tier.

Usage:
    python -m bot.app
"""

import logging

from telegram.ext import Application

from bot import config
from bot.handlers import enrich as enrich_handler
from bot.handlers import db_cmds, export_cmds, job_control, quota_status, scrape_flow, start_help


def build_application() -> Application:
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    # Order matters: ConversationHandler (scrape_flow) routes its own callbacks
    # first when a user is mid-conversation; otherwise the global handlers below
    # match by their `score|`/`slscore|`/`feat|`/... patterns.
    start_help.register(app)
    scrape_flow.register(app)
    enrich_handler.register(app)
    export_cmds.register(app)
    job_control.register(app)
    quota_status.register(app)
    db_cmds.register(app)
    return app


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=logging.INFO,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    log = logging.getLogger("bot")

    app = build_application()
    url_path = config.TELEGRAM_BOT_TOKEN  # secret-ish; combined with WEBHOOK_SECRET_TOKEN
    webhook_url = f"{config.WEBHOOK_BASE_URL}/{url_path}"
    log.info("Starting webhook on :%d → %s", config.PORT, webhook_url)
    app.run_webhook(
        listen="0.0.0.0",
        port=config.PORT,
        url_path=url_path,
        webhook_url=webhook_url,
        secret_token=config.WEBHOOK_SECRET_TOKEN,
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
