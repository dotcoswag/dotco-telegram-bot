"""/db_stats, /db_export, /db_export_smartlead, /db_pull — master leads DB commands.

The export commands chain three pickers (state → group → min_score) via
inline keyboards. Per-chat state lives in context.user_data.
"""

import asyncio
import os
import tempfile
from datetime import datetime

from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

import export_smartlead

from bot import cities, config, keyboards, leads_db
from bot.github_storage import StorageError
from bot.job_manager import jobs


# ── /db_stats ────────────────────────────────────────────────

async def cmd_db_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, leads_db.ensure_loaded)
    except StorageError as e:
        await update.message.reply_text(f"⚠️ Could not load master DB: {e}")
        return
    s = leads_db.stats()
    if s["total"] == 0:
        await update.message.reply_text(
            "🗄️ Master DB is empty. Run /scrape to start populating it."
        )
        return
    top_states = sorted(s["by_state"].items(), key=lambda x: -x[1])[:8]
    top_cats = sorted(s["by_category"].items(), key=lambda x: -x[1])[:8]
    score_hist = sorted(s["score_hist"].items())
    lines = [
        f"🗄️ Master DB stats",
        f"  Total leads: {s['total']:,}",
        f"  Combos logged: {s['combos_logged']:,}",
        f"",
        f"By state (top 8):",
    ]
    lines += [f"  {name}: {n}" for name, n in top_states]
    lines += ["", "By category (top 8):"]
    lines += [f"  {name}: {n}" for name, n in top_cats]
    lines += ["", "Lead score distribution:"]
    lines += [f"  score {sc}: {'█' * min(n, 30)} {n}" for sc, n in score_hist]
    await update.message.reply_text("\n".join(lines))


# ── shared export wizard ─────────────────────────────────────

async def _start_export(update: Update, context: ContextTypes.DEFAULT_TYPE,
                        mode: str) -> None:
    """mode = 'csv' or 'smartlead'."""
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, leads_db.ensure_loaded)
    except StorageError as e:
        await update.message.reply_text(f"⚠️ Could not load master DB: {e}")
        return
    if not leads_db.MASTER:
        await update.message.reply_text(
            "🗄️ Master DB is empty. Run /scrape first."
        )
        return
    context.user_data["dbexport_mode"] = mode
    context.user_data.pop("dbexport_state", None)
    context.user_data.pop("dbexport_group", None)
    await update.message.reply_text(
        f"Step 1/3 — filter by state:",
        reply_markup=keyboards.state_picker_keyboard(prefix="dbstate"),
    )


async def cmd_db_export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _start_export(update, context, "csv")


async def cmd_db_export_smartlead(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _start_export(update, context, "smartlead")


async def cb_dbexport_state(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    _, value = q.data.split("|", 1)
    if value == "all":
        context.user_data["dbexport_state"] = None
        state_label = "All states"
    else:
        try:
            idx = int(value)
            context.user_data["dbexport_state"] = cities.state_name(idx)
            state_label = cities.state_name(idx)
        except (ValueError, IndexError):
            await q.edit_message_text("Invalid choice.")
            return
    await q.edit_message_text(
        f"State: {state_label}\n\nStep 2/3 — filter by category group:",
        reply_markup=keyboards.group_picker_keyboard(prefix="dbgrp"),
    )


async def cb_dbexport_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    _, value = q.data.split("|", 1)
    if value == "all":
        context.user_data["dbexport_group"] = None
        group_label = "All groups"
    else:
        try:
            idx = int(value)
            context.user_data["dbexport_group"] = keyboards.CATEGORY_KEYS[idx]
            group_label = keyboards.CATEGORY_KEYS[idx]
        except (ValueError, IndexError):
            await q.edit_message_text("Invalid choice.")
            return
    await q.edit_message_text(
        f"Group: {group_label}\n\nStep 3/3 — minimum lead_score:",
        reply_markup=keyboards.min_score_keyboard(prefix="dbscore"),
    )


async def cb_dbexport_score(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    _, value = q.data.split("|", 1)
    try:
        min_score = int(value)
    except ValueError:
        await q.edit_message_text("Invalid choice.")
        return

    chat_id = q.message.chat_id
    mode = context.user_data.pop("dbexport_mode", "csv")
    state = context.user_data.pop("dbexport_state", None)
    group = context.user_data.pop("dbexport_group", None)

    loop = asyncio.get_running_loop()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag_state = (state or "all").replace(" ", "")
    tag_group = (group.split(" ")[-1] if group else "all").replace("&", "and")
    raw_path = os.path.join(
        tempfile.gettempdir(),
        f"dbexport_{tag_state}_{tag_group}_score{min_score}_{ts}.csv",
    )

    await q.edit_message_text(
        f"Filtering master DB…\n  state: {state or 'all'}\n  group: {group or 'all'}\n  min_score: {min_score}"
    )
    try:
        count = await loop.run_in_executor(
            None,
            lambda: leads_db.write_filtered_csv(
                raw_path, state=state, category_group=group, min_score=min_score
            ),
        )
    except Exception as e:
        await context.bot.send_message(chat_id, f"❌ Filter failed: {e}")
        return

    if count == 0:
        await context.bot.send_message(chat_id, "No rows matched the filters.")
        try: os.remove(raw_path)
        except OSError: pass
        return

    if mode == "smartlead":
        try:
            sl_path = await loop.run_in_executor(
                None, export_smartlead.export, raw_path, 0, False
            )
        except SystemExit:
            await context.bot.send_message(chat_id, "Smartlead export failed.")
            return
        deliver = sl_path
        label = f"Smartlead CSV — {count} rows pre-filter"
    else:
        deliver = raw_path
        label = f"DB export — {count} rows"

    if not os.path.exists(deliver) or os.path.getsize(deliver) == 0:
        await context.bot.send_message(chat_id, "Export produced an empty file.")
        return

    size = os.path.getsize(deliver)
    if size > config.MAX_UPLOAD_BYTES:
        await context.bot.send_message(
            chat_id,
            f"⚠️ File is {size//(1024*1024)} MB — over Telegram's 50 MB limit."
        )
        return
    with open(deliver, "rb") as f:
        await context.bot.send_document(
            chat_id=chat_id,
            document=f,
            filename=os.path.basename(deliver),
            caption=label,
        )
    # Track for /export_smartlead-style follow-up if user wants to re-filter.
    jobs.set_last_result(chat_id, raw_path)


# ── /db_pull ─────────────────────────────────────────────────

async def cmd_db_pull(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if jobs.current is not None:
        await update.message.reply_text(
            "Another job is running — refusing to clobber in-memory master."
        )
        return
    loop = asyncio.get_running_loop()
    try:
        master_rows, log_rows = await loop.run_in_executor(None, leads_db.force_pull)
    except StorageError as e:
        await update.message.reply_text(f"⚠️ Pull failed: {e}")
        return
    await update.message.reply_text(
        f"🔄 Pulled from GitHub.\n"
        f"  Master rows: {master_rows:,}\n"
        f"  Combo log rows: {log_rows:,}"
    )


def register(application) -> None:
    application.add_handler(CommandHandler("db_stats", cmd_db_stats))
    application.add_handler(CommandHandler("db_export", cmd_db_export))
    application.add_handler(CommandHandler("db_export_smartlead", cmd_db_export_smartlead))
    application.add_handler(CommandHandler("db_pull", cmd_db_pull))
    application.add_handler(CallbackQueryHandler(cb_dbexport_state, pattern=r"^dbstate\|"))
    application.add_handler(CallbackQueryHandler(cb_dbexport_group, pattern=r"^dbgrp\|"))
    application.add_handler(CallbackQueryHandler(cb_dbexport_score, pattern=r"^dbscore\|"))
