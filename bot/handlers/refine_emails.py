"""/refine_emails — re-rank the email columns in the last CSV.

Adds a `best_email` column populated by `bot.email_picker.pick_best_email`.
Subsequent /export_smartlead and /db_export_smartlead prefer `best_email`
when it's present, so this command effectively raises Smartlead delivery
to the highest-EV contact per business without spending any API quota.
"""

import csv
import os
import tempfile

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from bot.email_picker import pick_best_email
from bot.job_manager import jobs


async def cmd_refine_emails(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    last_csv = jobs.get_last_result(chat_id)
    if not last_csv or not os.path.exists(last_csv):
        await update.message.reply_text(
            "No source CSV available. Run /scrape, /db_export, or /demo first."
        )
        return

    base = os.path.basename(last_csv)
    out_name = base.replace(".csv", "_refined.csv")
    out_path = os.path.join(tempfile.gettempdir(), out_name)

    upgraded = 0
    unchanged = 0
    new_finds = 0  # had no primary email but emails_extra surfaced one
    rows_total = 0

    with open(last_csv, encoding="utf-8") as fin, \
         open(out_path, "w", encoding="utf-8", newline="") as fout:
        reader = csv.DictReader(fin)
        cols = list(reader.fieldnames or [])
        if "best_email" not in cols:
            try:
                idx = cols.index("email") + 1
                cols.insert(idx, "best_email")
            except ValueError:
                cols.append("best_email")
        writer = csv.DictWriter(fout, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for row in reader:
            rows_total += 1
            primary = (row.get("email") or "").strip().lower()
            best = pick_best_email(row.get("email", ""), row.get("emails_extra", ""))
            row["best_email"] = best
            if best:
                if not primary:
                    new_finds += 1
                elif best != primary:
                    upgraded += 1
                else:
                    unchanged += 1
            writer.writerow(row)

    jobs.set_last_result(chat_id, out_path)
    with open(out_path, "rb") as f:
        await context.bot.send_document(
            chat_id=chat_id,
            document=f,
            filename=out_name,
            caption=(
                f"✓ Refined {rows_total} rows.\n"
                f"  upgraded (better email picked): {upgraded}\n"
                f"  new finds (primary was empty): {new_finds}\n"
                f"  unchanged: {unchanged}\n\n"
                f"/export_smartlead now uses `best_email` automatically."
            ),
        )


def register(application) -> None:
    application.add_handler(CommandHandler("refine_emails", cmd_refine_emails))
