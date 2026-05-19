"""/scrape ConversationHandler — guided scrape flow."""

import asyncio
import os
from datetime import datetime
from typing import Optional

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import main as scraper_main

from bot import config, keyboards
from bot.job_manager import jobs
from bot.progress import ProgressBridge
from bot import scrape_runner


CHOOSING_TIER, CHOOSING_CATEGORIES, ASKING_LIMIT, ASKING_MIN_SCORE, CONFIRM = range(5)


# ── entry ────────────────────────────────────────────────────

async def cmd_scrape(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    remaining = jobs.cooldown_remaining(chat_id)
    if remaining > 0:
        await update.message.reply_text(f"⏳ Slow down — try again in {remaining}s.")
        return ConversationHandler.END
    if jobs.current is not None:
        await update.message.reply_text(
            "Another job is running. /status to inspect, /cancel to stop it."
        )
        return ConversationHandler.END
    jobs.touch_cooldown(chat_id)
    context.user_data.clear()
    context.user_data["selected_categories"] = set()
    await update.message.reply_text(
        "Step 1/4 — pick a market tier:",
        reply_markup=keyboards.tier_keyboard(),
    )
    return CHOOSING_TIER


# ── state CHOOSING_TIER ──────────────────────────────────────

async def cb_tier(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    _, value = q.data.split("|", 1)
    try:
        idx = int(value)
        tier_label = keyboards.TIER_KEYS[idx]
    except (ValueError, IndexError):
        await q.edit_message_text("Invalid choice.")
        return ConversationHandler.END
    context.user_data["tier_label"] = tier_label
    context.user_data["localidades"] = scraper_main.MERCADOS_RECOMENDADOS[tier_label]
    await q.edit_message_text(
        f"Tier: {tier_label}\n"
        f"Cities: {len(context.user_data['localidades'])}\n\n"
        f"Step 2/4 — pick category groups (multi-select):",
        reply_markup=keyboards.category_keyboard(set()),
    )
    return CHOOSING_CATEGORIES


# ── state CHOOSING_CATEGORIES ────────────────────────────────

async def cb_cat_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    _, value = q.data.split("|", 1)
    try:
        idx = int(value)
    except ValueError:
        return CHOOSING_CATEGORIES
    selected: set[int] = context.user_data["selected_categories"]
    if idx in selected:
        selected.remove(idx)
    else:
        selected.add(idx)
    await q.edit_message_reply_markup(reply_markup=keyboards.category_keyboard(selected))
    return CHOOSING_CATEGORIES


async def cb_cat_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    selected: set[int] = context.user_data["selected_categories"]
    if not selected:
        await q.answer("Pick at least one group.", show_alert=True)
        return CHOOSING_CATEGORIES
    flat: list[str] = []
    chosen_labels: list[str] = []
    for idx in sorted(selected):
        label = keyboards.CATEGORY_KEYS[idx]
        chosen_labels.append(label)
        flat.extend(scraper_main.CATEGORIAS[label])
    context.user_data["categorias_labels"] = chosen_labels
    context.user_data["categorias"] = flat
    await q.edit_message_text(
        f"Groups: {len(chosen_labels)} → {len(flat)} queries per city\n\n"
        f"Step 3/4 — reply with a max-leads number (e.g. 100), "
        f"or send `0` for unlimited."
    )
    return ASKING_LIMIT


# ── state ASKING_LIMIT ───────────────────────────────────────

async def msg_limit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    try:
        n = int(text)
        if n < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Please reply with a non-negative integer, or `0` for unlimited.")
        return ASKING_LIMIT
    context.user_data["limite"] = None if n == 0 else n
    await update.message.reply_text(
        "Step 4/4 — pick a minimum lead_score (0–7):",
        reply_markup=keyboards.min_score_keyboard(),
    )
    return ASKING_MIN_SCORE


# ── state ASKING_MIN_SCORE ───────────────────────────────────

async def cb_min_score(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    _, value = q.data.split("|", 1)
    try:
        min_score = int(value)
    except ValueError:
        return ASKING_MIN_SCORE
    context.user_data["min_score"] = min_score
    limite = context.user_data["limite"]
    summary = (
        f"Confirm run:\n"
        f"  Tier: {context.user_data['tier_label']}\n"
        f"  Cities: {len(context.user_data['localidades'])}\n"
        f"  Groups: {len(context.user_data['categorias_labels'])} "
        f"({len(context.user_data['categorias'])} queries/city)\n"
        f"  Limit: {limite if limite is not None else 'unlimited'}\n"
        f"  Min score: {min_score}\n"
    )
    await q.edit_message_text(
        summary,
        reply_markup=keyboards.yes_no_keyboard("confirm", default_no=False),
    )
    return CONFIRM


# ── state CONFIRM ────────────────────────────────────────────

async def cb_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    _, value = q.data.split("|", 1)
    if value != "yes":
        await q.edit_message_text("Cancelled.")
        return ConversationHandler.END

    chat_id = q.message.chat_id
    job = await jobs.try_acquire(chat_id, "scrape")
    if job is None:
        await q.edit_message_text(
            "Another job is running. /status to inspect, /cancel to stop it."
        )
        return ConversationHandler.END

    await q.edit_message_text("▶️ Scrape started. You'll get progress here. /cancel to stop.")

    localidades = list(context.user_data["localidades"])
    categorias = list(context.user_data["categorias"])
    limite = context.user_data["limite"]
    min_score = context.user_data["min_score"]

    loop = asyncio.get_running_loop()
    bridge = ProgressBridge(loop, context.bot, chat_id)

    try:
        result = await loop.run_in_executor(
            None,
            scrape_runner.run,
            localidades,
            categorias,
            limite,
            min_score,
            bridge,
            job.cancel_event,
        )
    except Exception as e:
        await context.bot.send_message(chat_id, f"❌ Scrape failed: {e}")
        await jobs.release()
        return ConversationHandler.END

    csv_path: Optional[str] = result.get("csv_path")
    elapsed = result["elapsed_seconds"]
    rows = result["rows_saved"]
    cancelled = result["cancelled"]

    status_emoji = "🛑" if cancelled else "✅"
    summary = (
        f"{status_emoji} {'Cancelled' if cancelled else 'Done'} — "
        f"{rows:,} leads in {elapsed//60}m {elapsed%60}s.\n"
        f"  new: {result['total_nuevos']}, "
        f"dup: {result['total_duplicados']}, "
        f"low-score skip: {result['total_skipped_score']}"
    )
    await context.bot.send_message(chat_id, summary)

    if csv_path and os.path.exists(csv_path) and os.path.getsize(csv_path) > 0:
        jobs.set_last_result(chat_id, csv_path)
        size = os.path.getsize(csv_path)
        if size > config.MAX_UPLOAD_BYTES:
            await context.bot.send_message(
                chat_id,
                f"⚠️ CSV is {size//(1024*1024)} MB — over Telegram's 50 MB limit. "
                f"File kept on server: {os.path.basename(csv_path)}",
            )
        else:
            with open(csv_path, "rb") as f:
                await context.bot.send_document(
                    chat_id=chat_id, document=f, filename=os.path.basename(csv_path)
                )
    else:
        await context.bot.send_message(chat_id, "No CSV was produced (zero rows matched).")

    await jobs.release()
    return ConversationHandler.END


# ── shared cancel ────────────────────────────────────────────

async def cb_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("Cancelled.")
    return ConversationHandler.END


async def cmd_abort(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Conversation aborted.")
    return ConversationHandler.END


# ── registration ─────────────────────────────────────────────

def register(application) -> None:
    conv = ConversationHandler(
        entry_points=[CommandHandler("scrape", cmd_scrape)],
        states={
            CHOOSING_TIER: [
                CallbackQueryHandler(cb_tier, pattern=r"^tier\|"),
                CallbackQueryHandler(cb_cancel, pattern=r"^cancel\|"),
            ],
            CHOOSING_CATEGORIES: [
                CallbackQueryHandler(cb_cat_toggle, pattern=r"^cat\|"),
                CallbackQueryHandler(cb_cat_done, pattern=r"^cat_done\|"),
                CallbackQueryHandler(cb_cancel, pattern=r"^cancel\|"),
            ],
            ASKING_LIMIT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, msg_limit),
            ],
            ASKING_MIN_SCORE: [
                CallbackQueryHandler(cb_min_score, pattern=r"^score\|"),
                CallbackQueryHandler(cb_cancel, pattern=r"^cancel\|"),
            ],
            CONFIRM: [
                CallbackQueryHandler(cb_confirm, pattern=r"^confirm\|"),
                CallbackQueryHandler(cb_cancel, pattern=r"^cancel\|"),
            ],
        },
        fallbacks=[CommandHandler("abort", cmd_abort)],
        per_chat=True,
        per_user=True,
    )
    application.add_handler(conv)
