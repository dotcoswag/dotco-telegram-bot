"""/db_stats, /db_export, /db_export_smartlead, /db_pull — master leads DB commands.

The export commands chain three pickers (state → group → min_score) via
inline keyboards. Per-chat state lives in context.user_data.
"""

import asyncio
import os
import tempfile
import threading
import time
from datetime import datetime

from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

import export_smartlead

from bot import cities, config, domain_enricher, keyboards, leads_db
from bot.github_storage import StorageError
from bot.job_manager import jobs


_DOMAIN_LOOKUP_DELAY = 1.0  # be polite to rdap.org / DNS resolvers


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
    context.user_data["dbexport_min_score"] = min_score
    mode = context.user_data.get("dbexport_mode", "csv")

    # For Smartlead mode, the next two steps depend on domain enrichment.
    # If /db_refine_domains hasn't been run, skip them entirely and warn.
    # For raw CSV export, run immediately.
    if mode == "smartlead":
        total_domains = len(leads_db.domains_in_master())
        enriched = len(leads_db.DOMAIN_INFO)
        if enriched == 0:
            chat_id = q.message.chat_id
            await q.edit_message_text(
                f"Min score: {min_score}\n\n"
                f"ℹ️ Domain enrichment hasn't been run yet "
                f"(0/{total_domains} domains enriched). Skipping the "
                f"`min_domain_age` and `mx_provider` filter steps.\n\n"
                f"Run /db_refine_domains first if you want those filters."
            )
            # No domain filters → run export directly with the score/state/group already collected.
            await _run_export(context, q)
            return
        coverage_pct = int(enriched / total_domains * 100) if total_domains else 0
        await q.edit_message_text(
            f"Min score: {min_score}\n"
            f"Domain enrichment coverage: {enriched:,}/{total_domains:,} ({coverage_pct}%)\n\n"
            f"Step 4/5 — minimum domain age filter.\n"
            f"Filters out brand-new businesses (websites <N years old).\n"
            f"Leads without enrichment data are excluded when this filter is active.",
            reply_markup=keyboards.domain_age_keyboard(prefix="dbage"),
        )
    else:
        await _run_export(context, q)


async def cb_dbexport_age(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    _, value = q.data.split("|", 1)
    if value == "any":
        context.user_data["dbexport_min_age"] = 0
        age_label = "any"
    else:
        try:
            context.user_data["dbexport_min_age"] = int(value)
            age_label = f"{value}+ years"
        except ValueError:
            await q.edit_message_text("Invalid choice.")
            return
    await q.edit_message_text(
        f"Min domain age: {age_label}\n\n"
        f"Step 5/5 — mail-provider filter.\n"
        f"'Professional only' keeps just Google Workspace or Microsoft 365 — "
        f"those leads are most likely to read business emails.",
        reply_markup=keyboards.mx_provider_keyboard(prefix="dbmx"),
    )


async def cb_dbexport_mx(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    _, value = q.data.split("|", 1)
    context.user_data["dbexport_mx_filter"] = None if value == "any" else value
    await _run_export(context, q)


async def _run_export(context: ContextTypes.DEFAULT_TYPE, q) -> None:
    """Shared between /db_export (after min_score) and /db_export_smartlead
    (after the mx step). Reads accumulated state from user_data."""
    chat_id = q.message.chat_id
    mode = context.user_data.pop("dbexport_mode", "csv")
    state = context.user_data.pop("dbexport_state", None)
    group = context.user_data.pop("dbexport_group", None)
    min_score = context.user_data.pop("dbexport_min_score", 0)
    min_age = context.user_data.pop("dbexport_min_age", 0)
    mx_filter = context.user_data.pop("dbexport_mx_filter", None)

    loop = asyncio.get_running_loop()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag_state = (state or "all").replace(" ", "")
    tag_group = (group.split(" ")[-1] if group else "all").replace("&", "and")
    raw_path = os.path.join(
        tempfile.gettempdir(),
        f"dbexport_{tag_state}_{tag_group}_score{min_score}_{ts}.csv",
    )

    filter_summary = (
        f"  state: {state or 'all'}\n  group: {group or 'all'}\n"
        f"  min_score: {min_score}"
    )
    if min_age > 0:
        filter_summary += f"\n  min_domain_age: {min_age}+ yrs"
    if mx_filter:
        filter_summary += f"\n  mx_filter: {mx_filter}"
    await q.edit_message_text(f"Filtering master DB…\n{filter_summary}")

    try:
        count = await loop.run_in_executor(
            None,
            lambda: leads_db.write_filtered_csv(
                raw_path,
                include_enrichment_columns=(mode != "smartlead"),
                state=state, category_group=group, min_score=min_score,
                min_domain_age=min_age, mx_filter=mx_filter,
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
        master_rows, log_rows, domain_rows = await loop.run_in_executor(
            None, leads_db.force_pull
        )
    except StorageError as e:
        await update.message.reply_text(f"⚠️ Pull failed: {e}")
        return
    await update.message.reply_text(
        f"🔄 Pulled from GitHub.\n"
        f"  Master rows: {master_rows:,}\n"
        f"  Combo log rows: {log_rows:,}\n"
        f"  Domain enrichment rows: {domain_rows:,}"
    )


# ── /db_refine_domains ───────────────────────────────────────

def _enrich_domains_worker(bridge, cancel_event: threading.Event) -> dict:
    """Run on the executor; iterates unique master domains and enriches missing
    ones via domain_enricher. Returns a summary dict."""
    leads_db.ensure_loaded()
    all_domains = leads_db.domains_in_master()
    todo = [d for d in all_domains if d not in leads_db.DOMAIN_INFO]
    bridge.push(
        f"🌐 {len(all_domains)} unique domains in master · "
        f"{len(todo)} need enrichment · "
        f"{len(all_domains) - len(todo)} already cached",
        force=True,
    )
    if not todo:
        return {"total": len(all_domains), "looked_up": 0, "cached": len(all_domains),
                "failed": 0, "cancelled": False}

    looked_up = 0
    failed = 0
    flush_every = 25  # checkpoint to GitHub periodically
    start = time.time()

    for i, domain in enumerate(todo, start=1):
        if cancel_event.is_set():
            try:
                leads_db.flush_domain_info()
            except Exception:
                pass
            return {"total": len(all_domains), "looked_up": looked_up,
                    "cached": len(all_domains) - len(todo),
                    "failed": failed, "cancelled": True}
        try:
            info = domain_enricher.enrich_domain(domain)
            leads_db.upsert_domain_info(info)
            looked_up += 1
            if info.get("registrar") or info.get("mx_provider") not in ("", "none"):
                pass  # success
            else:
                failed += 1
        except Exception:
            failed += 1

        if i % 10 == 0 or i == len(todo):
            elapsed = int(time.time() - start)
            bridge.push(
                f"[{i}/{len(todo)}] enriched · {failed} no-data · {elapsed}s elapsed"
            )
        if i % flush_every == 0:
            try:
                leads_db.flush_domain_info()
            except Exception:
                pass
        # Throttle so we don't hammer rdap.org or the DNS resolvers.
        if cancel_event.wait(timeout=_DOMAIN_LOOKUP_DELAY):
            return {"total": len(all_domains), "looked_up": looked_up,
                    "cached": len(all_domains) - len(todo),
                    "failed": failed, "cancelled": True}

    try:
        leads_db.flush_domain_info()
    except Exception:
        pass
    return {"total": len(all_domains), "looked_up": looked_up,
            "cached": len(all_domains) - len(todo),
            "failed": failed, "cancelled": False}


async def cmd_db_refine_domains(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if jobs.current is not None:
        await update.message.reply_text(
            "Another job is running — wait for it to finish or /cancel it first."
        )
        return
    job = await jobs.try_acquire(chat_id, "refine_domains")
    if job is None:
        await update.message.reply_text("Couldn't acquire lock.")
        return

    from bot.progress import ProgressBridge
    loop = asyncio.get_running_loop()
    bridge = ProgressBridge(loop, context.bot, chat_id)
    try:
        result = await loop.run_in_executor(
            None, _enrich_domains_worker, bridge, job.cancel_event
        )
    except Exception as e:
        await context.bot.send_message(chat_id, f"❌ Enrich failed: {e}")
        await jobs.release()
        return

    status = "🛑 Cancelled" if result["cancelled"] else "✅ Done"
    await context.bot.send_message(
        chat_id,
        f"{status}\n"
        f"  Total domains: {result['total']:,}\n"
        f"  Looked up this run: {result['looked_up']:,}\n"
        f"  Already cached: {result['cached']:,}\n"
        f"  No data returned: {result['failed']:,}\n\n"
        f"/db_export* now includes columns: domain_age_years, registrar, mx_provider"
    )
    await jobs.release()


def register(application) -> None:
    application.add_handler(CommandHandler("db_stats", cmd_db_stats))
    application.add_handler(CommandHandler("db_export", cmd_db_export))
    application.add_handler(CommandHandler("db_export_smartlead", cmd_db_export_smartlead))
    application.add_handler(CommandHandler("db_pull", cmd_db_pull))
    application.add_handler(CommandHandler("db_refine_domains", cmd_db_refine_domains))
    application.add_handler(CallbackQueryHandler(cb_dbexport_state, pattern=r"^dbstate\|"))
    application.add_handler(CallbackQueryHandler(cb_dbexport_group, pattern=r"^dbgrp\|"))
    application.add_handler(CallbackQueryHandler(cb_dbexport_score, pattern=r"^dbscore\|"))
    application.add_handler(CallbackQueryHandler(cb_dbexport_age, pattern=r"^dbage\|"))
    application.add_handler(CallbackQueryHandler(cb_dbexport_mx, pattern=r"^dbmx\|"))
