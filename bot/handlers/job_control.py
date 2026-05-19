"""/status and /cancel."""

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from bot.job_manager import jobs


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    job = jobs.current
    if job is None:
        await update.message.reply_text("No job is running.")
        return
    await update.message.reply_text(
        f"Running: {job.kind}\n"
        f"Started by chat: {job.chat_id}\n"
        f"Elapsed: {job.elapsed_seconds()}s\n"
        f"Last update: {job.last_progress or '(no progress yet)'}"
    )


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if jobs.cancel():
        await update.message.reply_text(
            "🛑 Cancellation requested. The job will stop at the next safe point "
            "and the partial CSV will be sent."
        )
    else:
        await update.message.reply_text("No job is running.")


def register(application) -> None:
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CommandHandler("cancel", cmd_cancel))
