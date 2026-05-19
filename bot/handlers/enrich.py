"""/enrich — opt-in AI enrichment with cost preview."""

import asyncio
import csv
import os

from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

import ai_client
import enrich as enrich_mod

from bot import config, keyboards
from bot.job_manager import jobs


def _count_csv_rows(path: str) -> int:
    with open(path, encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)  # header
        return sum(1 for _ in reader)


async def cmd_enrich(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id

    if not ai_client.is_enabled():
        await update.message.reply_text(
            "🤖 AI is off — ANTHROPIC_API_KEY is not set.\n"
            "Set it on the Render dashboard (or in .env locally) and try again."
        )
        return

    remaining = jobs.cooldown_remaining(chat_id)
    if remaining > 0:
        await update.message.reply_text(f"⏳ Slow down — try again in {remaining}s.")
        return
    if jobs.current is not None:
        await update.message.reply_text(
            "Another job is running. /status to inspect, /cancel to stop it."
        )
        return

    last_csv = jobs.get_last_result(chat_id)
    if not last_csv or not os.path.exists(last_csv):
        await update.message.reply_text("No source CSV available. Run /scrape first.")
        return

    jobs.touch_cooldown(chat_id)
    context.user_data["enrich_csv"] = last_csv
    context.user_data["enrich_features"] = set()
    await update.message.reply_text(
        f"Source: {os.path.basename(last_csv)}\n\n"
        f"Pick features (multi-select). All default to OFF — Anthropic credits are spent only on explicit Yes.",
        reply_markup=keyboards.feature_keyboard(set()),
    )


async def cb_feature_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    _, value = q.data.split("|", 1)
    if value not in keyboards.FEATURE_KEYS:
        return
    selected: set[str] = context.user_data.setdefault("enrich_features", set())
    if value in selected:
        selected.remove(value)
    else:
        selected.add(value)
    await q.edit_message_reply_markup(reply_markup=keyboards.feature_keyboard(selected))


async def cb_feature_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    csv_path = context.user_data.get("enrich_csv")
    selected: set[str] = context.user_data.get("enrich_features", set())
    if not csv_path or not os.path.exists(csv_path):
        await q.edit_message_text("Source CSV no longer available.")
        return
    if not selected:
        await q.answer("Pick at least one feature.", show_alert=True)
        return

    rows = _count_csv_rows(csv_path)
    features = tuple(sorted(selected))
    est = enrich_mod.estimate_total_cost(rows, features)
    context.user_data["enrich_features_final"] = features
    await q.edit_message_text(
        f"Will enrich {rows} rows with: {', '.join(features)}\n"
        f"Estimated cost: ~${est:.4f} USD\n\n"
        f"Proceed?",
        reply_markup=keyboards.yes_no_keyboard("enrichconfirm", default_no=True),
    )


async def cb_enrich_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    _, value = q.data.split("|", 1)
    if value != "yes":
        await q.edit_message_text("Cancelled. No AI calls were made.")
        return

    chat_id = q.message.chat_id
    csv_path = context.user_data.get("enrich_csv")
    features = context.user_data.get("enrich_features_final")
    if not csv_path or not features:
        await q.edit_message_text("State lost. Run /enrich again.")
        return

    job = await jobs.try_acquire(chat_id, "enrich")
    if job is None:
        await q.edit_message_text(
            "Another job is running. /status to inspect, /cancel to stop it."
        )
        return

    await q.edit_message_text(f"▶️ Enriching… (~{len(features)} feature pass(es))")
    loop = asyncio.get_running_loop()
    try:
        out_path = await loop.run_in_executor(
            None, enrich_mod.enrich_csv, csv_path, features
        )
    except ai_client.QuotaExhausted as e:
        await context.bot.send_message(chat_id, f"⚠️ AI quota exhausted: {e}")
        await jobs.release()
        return
    except Exception as e:
        await context.bot.send_message(chat_id, f"❌ Enrich failed: {e}")
        await jobs.release()
        return
    finally:
        # release happens above on error paths; success path also releases
        pass

    if not out_path or not os.path.exists(out_path):
        await context.bot.send_message(chat_id, "Enrichment produced no file.")
        await jobs.release()
        return

    jobs.set_last_result(chat_id, out_path)
    size = os.path.getsize(out_path)
    if size > config.MAX_UPLOAD_BYTES:
        await context.bot.send_message(
            chat_id,
            f"⚠️ Enriched CSV is {size//(1024*1024)} MB — over Telegram's 50 MB limit. "
            f"File kept on server: {os.path.basename(out_path)}",
        )
    else:
        with open(out_path, "rb") as f:
            await context.bot.send_document(
                chat_id=chat_id, document=f, filename=os.path.basename(out_path)
            )
    await jobs.release()


def register(application) -> None:
    application.add_handler(CommandHandler("enrich", cmd_enrich))
    application.add_handler(CallbackQueryHandler(cb_feature_toggle, pattern=r"^feat\|"))
    application.add_handler(CallbackQueryHandler(cb_feature_done, pattern=r"^feat_done\|"))
    application.add_handler(CallbackQueryHandler(cb_enrich_confirm, pattern=r"^enrichconfirm\|"))
