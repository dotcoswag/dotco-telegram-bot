"""Telegram bot entry point.

Build the PTB Application, register handlers, and run the webhook server.
Bound to $PORT — works locally (PORT=10000 + ngrok) and on Render free tier.

Usage:
    python -m bot.app
"""

import logging

from telegram import BotCommand
from telegram.ext import Application

from bot import config
from bot.handlers import enrich as enrich_handler
from bot.handlers import db_cmds, export_cmds, job_control, quota_status, refine_emails, scrape_flow, start_help


# Commands shown in Telegram's native "/" menu (tap the / icon next to the input).
# Order matters — they're displayed in this order, so put the things you'll
# actually run on top.
BOT_COMMANDS: list[tuple[str, str]] = [
    ("scrape",              "🔎 Run a new lead scrape (with quota + fresh-skip preview)"),
    ("db_stats",            "🗄️ Master DB totals — by state, category, score"),
    ("db_export",           "📤 Export a filtered subset of the master DB → CSV"),
    ("db_export_smartlead", "📧 Same filters → Smartlead-format CSV"),
    ("db_refine_domains",   "🌐 Add domain age, registrar, MX provider (free, ~1/sec)"),
    ("db_pull",             "🔄 Force re-fetch master DB from GitHub"),
    ("list",                "📂 List recent result files on the server"),
    ("export_smartlead",    "📧 Smartlead CSV from the last scrape"),
    ("export_excel",        "📊 XLSX from the last scrape"),
    ("refine_emails",       "🎯 Pick best email per row from extras (free, no AI)"),
    ("enrich",              "🤖 AI-enrich the last CSV (opt-in, cost preview)"),
    ("status",              "⏱  Show the running job"),
    ("cancel",              "🛑 Cancel the running job"),
    ("quota",               "📊 Live status: RapidAPI · Anthropic · Telegram"),
    ("demo",                "🧪 Seed a synthetic CSV to test exports (no quota cost)"),
    ("help",                "❓ Show full command list"),
    ("start",               "👋 Welcome message"),
]


async def _post_init(app: Application) -> None:
    """Register the Telegram-native command menu (the `/` button)."""
    await app.bot.set_my_commands(
        [BotCommand(name, desc) for name, desc in BOT_COMMANDS]
    )


def build_application() -> Application:
    app = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(_post_init)
        .build()
    )
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
    refine_emails.register(app)
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
