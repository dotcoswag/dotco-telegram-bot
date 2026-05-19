"""/list, /export_smartlead, /export_excel."""

import asyncio
import os

from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

import export as export_excel
import export_smartlead
import main as scraper_main

from bot import keyboards
from bot.job_manager import jobs


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    d = scraper_main.RESULTADOS_DIR
    if not os.path.isdir(d):
        await update.message.reply_text("No results yet.")
        return
    files = sorted(
        f for f in os.listdir(d) if f.endswith((".csv", ".xlsx"))
    )
    if not files:
        await update.message.reply_text("No results yet.")
        return
    last = jobs.get_last_result(update.effective_chat.id)
    last_name = os.path.basename(last) if last else None
    lines = []
    for f in files[-25:]:  # cap for readability
        size_kb = os.path.getsize(os.path.join(d, f)) // 1024
        marker = " ← /enrich, /export_* target" if f == last_name else ""
        lines.append(f"  {f}  ({size_kb} KB){marker}")
    await update.message.reply_text(
        f"Recent files in resultados/ (max 25 shown):\n\n" + "\n".join(lines)
    )


# ── /export_smartlead ────────────────────────────────────────

async def cmd_export_smartlead(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    last_csv = jobs.get_last_result(chat_id)
    if not last_csv or not os.path.exists(last_csv):
        await update.message.reply_text(
            "No source CSV available. Run /scrape first, or re-upload isn't supported yet."
        )
        return
    context.user_data["smartlead_csv"] = last_csv
    await update.message.reply_text(
        f"Source: {os.path.basename(last_csv)}\nPick a minimum lead_score:",
        reply_markup=keyboards.min_score_keyboard(prefix="slscore"),
    )


async def cb_smartlead_score(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    _, value = q.data.split("|", 1)
    if value == "":  # cancel button
        await q.edit_message_text("Cancelled.")
        return
    try:
        min_score = int(value)
    except ValueError:
        await q.edit_message_text("Invalid score.")
        return
    csv_path = context.user_data.pop("smartlead_csv", None)
    if not csv_path or not os.path.exists(csv_path):
        await q.edit_message_text("Source CSV no longer available.")
        return

    await q.edit_message_text(f"Building Smartlead CSV (min_score={min_score})…")
    loop = asyncio.get_running_loop()
    try:
        out_path = await loop.run_in_executor(
            None, export_smartlead.export, csv_path, min_score, False
        )
    except SystemExit:
        # export_smartlead.export calls sys.exit on a missing file, which we already guarded.
        await q.message.reply_text("Export failed (file vanished).")
        return
    if not out_path or not os.path.exists(out_path):
        await q.message.reply_text("Export produced no file.")
        return
    with open(out_path, "rb") as f:
        await context.bot.send_document(chat_id=q.message.chat_id, document=f,
                                        filename=os.path.basename(out_path))


# ── /export_excel ────────────────────────────────────────────

async def cmd_export_excel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    last_csv = jobs.get_last_result(chat_id)
    if not last_csv or not os.path.exists(last_csv):
        await update.message.reply_text("No source CSV available. Run /scrape first.")
        return
    await update.message.reply_text(f"Converting {os.path.basename(last_csv)} to XLSX…")
    loop = asyncio.get_running_loop()
    try:
        out_path = await loop.run_in_executor(None, export_excel.csv_to_xlsx, last_csv, None)
    except Exception as e:
        await update.message.reply_text(f"Conversion failed: {e}")
        return
    with open(out_path, "rb") as f:
        await context.bot.send_document(chat_id=chat_id, document=f,
                                        filename=os.path.basename(out_path))


def register(application) -> None:
    application.add_handler(CommandHandler("list", cmd_list))
    application.add_handler(CommandHandler("export_smartlead", cmd_export_smartlead))
    application.add_handler(CommandHandler("export_excel", cmd_export_excel))
    application.add_handler(CallbackQueryHandler(cb_smartlead_score, pattern=r"^slscore\|"))
