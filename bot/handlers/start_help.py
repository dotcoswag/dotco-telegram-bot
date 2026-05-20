"""/start and /help commands."""

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes


WELCOME = (
    "👋 DotCo Lead Bot\n\n"
    "Commands:\n"
    "  /scrape — guided scrape (tier → categories → limit → min_score)\n"
    "  /enrich — run AI enrichment on the last scrape (opt-in, default off)\n"
    "  /export_smartlead — build a Smartlead-compatible CSV\n"
    "  /export_excel — convert the last CSV to XLSX\n"
    "  /refine_emails — picks the best email per row from emails_extra (free)\n"
    "  /list — list result files on the server\n"
    "  /status — show the running job\n"
    "  /cancel — request cancellation of the running job\n"
    "  /quota — live quota for RapidAPI + Anthropic + Telegram status\n"
    "  /demo — seed a synthetic CSV so /export_* can be tested without API\n"
    "\n"
    "Master DB (persistent across runs, cross-scrape dedup):\n"
    "  /db_stats — totals, by state, by category, score histogram\n"
    "  /db_export — filter (state → group → min_score) → CSV\n"
    "  /db_export_smartlead — same filters → Smartlead CSV\n"
    "  /db_refine_domains — free enrichment: domain age + MX provider + registrar\n"
    "  /db_pull — force re-fetch master from GitHub\n"
    "\n"
    "  /help — show this message\n\n"
    "ℹ️ First message after ~15 min idle may take 30–60s — Render free tier "
    "puts the service to sleep when inactive."
)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(WELCOME)


def register(application) -> None:
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_start))
