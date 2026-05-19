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

from bot import api_quota, cities, config, keyboards, leads_db
from bot.github_storage import StorageError
from bot.job_manager import jobs
from bot.progress import ProgressBridge
from bot import scrape_runner

import scraper as scraper_mod


(
    CHOOSING_TIER,
    PICKING_STATE,
    PICKING_CITIES_IN_STATE,
    CHOOSING_CATEGORIES,
    ASKING_LIMIT,
    ASKING_MIN_SCORE,
    CONFIRM,
) = range(7)


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

    if value == keyboards.CUSTOM_TIER_VALUE:
        # Custom city picker: state list → cities in state, multi-add across states.
        context.user_data["tier_label"] = "🌎 Custom cities"
        context.user_data["selected_city_keys"] = set()  # {(state_idx, city_idx)}
        await q.edit_message_text(
            "Pick a state, then toggle cities. You can hop back to add cities from more states.\n"
            "Tap ✔ Done picking cities when finished.",
            reply_markup=keyboards.state_keyboard(),
        )
        return PICKING_STATE

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


# ── state PICKING_STATE ──────────────────────────────────────

async def cb_pick_state(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    _, value = q.data.split("|", 1)
    try:
        state_idx = int(value)
        state_label = cities.state_name(state_idx)
    except (ValueError, IndexError):
        return PICKING_STATE
    context.user_data["current_state_idx"] = state_idx
    selected_keys: set[tuple[int, int]] = context.user_data.get("selected_city_keys", set())
    selected_in_state = {ci for (si, ci) in selected_keys if si == state_idx}
    selected_total = len(selected_keys)
    await q.edit_message_text(
        f"State: {state_label}\n"
        f"Selected so far: {selected_total} cities\n\n"
        f"Toggle cities below. Population shown in (k).",
        reply_markup=keyboards.city_keyboard(state_idx, selected_in_state),
    )
    return PICKING_CITIES_IN_STATE


async def cb_cities_done_from_states(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _finalize_cities(update, context)


# ── state PICKING_CITIES_IN_STATE ────────────────────────────

async def cb_toggle_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    _, value = q.data.split("|", 1)
    try:
        city_idx = int(value)
    except ValueError:
        return PICKING_CITIES_IN_STATE
    state_idx: int = context.user_data["current_state_idx"]
    selected_keys: set[tuple[int, int]] = context.user_data.setdefault("selected_city_keys", set())
    key = (state_idx, city_idx)
    if key in selected_keys:
        selected_keys.remove(key)
    else:
        selected_keys.add(key)
    selected_in_state = {ci for (si, ci) in selected_keys if si == state_idx}
    await q.edit_message_reply_markup(
        reply_markup=keyboards.city_keyboard(state_idx, selected_in_state),
    )
    return PICKING_CITIES_IN_STATE


async def cb_back_to_states(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    selected_total = len(context.user_data.get("selected_city_keys", set()))
    await q.edit_message_text(
        f"Selected so far: {selected_total} cities\n\n"
        f"Pick another state or tap ✔ Done.",
        reply_markup=keyboards.state_keyboard(),
    )
    return PICKING_STATE


async def cb_cities_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _finalize_cities(update, context)


async def _finalize_cities(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    selected_keys: set[tuple[int, int]] = context.user_data.get("selected_city_keys", set())
    if not selected_keys:
        await q.answer("Pick at least one city.", show_alert=True)
        return PICKING_STATE
    localidades = [cities.city_at(si, ci) for (si, ci) in sorted(selected_keys)]
    context.user_data["localidades"] = localidades
    context.user_data["selected_categories"] = set()
    preview = ", ".join(f"{n} ({s})" for n, s in localidades[:5])
    more = f" … +{len(localidades) - 5} more" if len(localidades) > 5 else ""
    await q.edit_message_text(
        f"✓ {len(localidades)} cities: {preview}{more}\n\n"
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
    num_cities = len(context.user_data["localidades"])
    num_queries_per_city = len(context.user_data["categorias"])
    total_combos = num_cities * num_queries_per_city

    # Fetch live RapidAPI quota (off the event loop — it's a sync HTTP call).
    loop = asyncio.get_running_loop()
    quota = await loop.run_in_executor(None, api_quota.fetch)
    context.user_data["quota_before"] = quota

    # Each combo can return up to LIMIT_POR_LLAMADA=500 businesses (one page).
    # In practice small-mid cities return ~20-80 per category. Show both ends.
    max_cost = total_combos * scraper_mod.LIMIT_POR_LLAMADA
    typical_low = total_combos * 20
    typical_high = total_combos * 80
    if limite is not None:
        max_cost = min(max_cost, limite)
        typical_high = min(typical_high, limite)

    # Compute fresh-combo count against the master DB so we can offer to skip.
    all_combos = [
        (loc, prov, cat)
        for (loc, prov) in context.user_data["localidades"]
        for cat in context.user_data["categorias"]
    ]
    try:
        await loop.run_in_executor(None, leads_db.ensure_loaded)
        fresh_count = await loop.run_in_executor(
            None, leads_db.fresh_count, all_combos, config.COMBO_FRESH_DAYS
        )
        master_size = len(leads_db.MASTER)
    except StorageError as e:
        fresh_count = 0
        master_size = 0
        master_warning = f"\n⚠️ Master DB unreachable ({e}) — cross-scrape dedup disabled."
    else:
        master_warning = ""

    summary = (
        f"Confirm run:\n"
        f"  Tier: {context.user_data['tier_label']}\n"
        f"  Cities: {num_cities}\n"
        f"  Groups: {len(context.user_data['categorias_labels'])} "
        f"({num_queries_per_city} queries/city)\n"
        f"  Combos: {total_combos}\n"
        f"  Limit: {limite if limite is not None else 'unlimited'}\n"
        f"  Min score: {min_score}\n"
        f"\n"
        f"📊 {api_quota.summary_line(quota)}\n"
        f"Estimated cost: ~{typical_low:,}–{typical_high:,} businesses "
        f"(hard cap {max_cost:,}).\n"
        f"\n"
        f"🗄️ Master DB: {master_size:,} known businesses · "
        f"{fresh_count}/{total_combos} combos scraped in last "
        f"{config.COMBO_FRESH_DAYS}d"
    )
    summary += master_warning
    if quota is not None and quota["remaining"] <= 0:
        summary += (
            f"\n⚠️ Quota is already exhausted — the scrape will abort on the first "
            f"call. Cancel below and upgrade your plan, or wait "
            f"{api_quota.format_reset(quota['reset_seconds'])} for reset.\n"
        )
    elif quota is not None and typical_low > quota["remaining"]:
        summary += (
            f"\n⚠️ Even the low estimate ({typical_low:,}) exceeds remaining quota "
            f"({quota['remaining']:,}). The scrape will likely abort partway.\n"
        )
    await q.edit_message_text(
        summary,
        reply_markup=keyboards.confirm_keyboard(fresh_count > 0),
    )
    return CONFIRM


# ── state CONFIRM ────────────────────────────────────────────

async def cb_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    _, value = q.data.split("|", 1)
    if value not in ("skip_fresh", "run_all"):
        await q.edit_message_text("Cancelled.")
        return ConversationHandler.END
    skip_fresh = (value == "skip_fresh")

    chat_id = q.message.chat_id
    job = await jobs.try_acquire(chat_id, "scrape")
    if job is None:
        await q.edit_message_text(
            "Another job is running. /status to inspect, /cancel to stop it."
        )
        return ConversationHandler.END

    mode_label = "skip fresh combos" if skip_fresh else "run all combos"
    await q.edit_message_text(
        f"▶️ Scrape started ({mode_label}). Progress will stream here. /cancel to stop."
    )

    localidades = list(context.user_data["localidades"])
    categorias = list(context.user_data["categorias"])
    limite = context.user_data["limite"]
    min_score = context.user_data["min_score"]

    loop = asyncio.get_running_loop()
    bridge = ProgressBridge(loop, context.bot, chat_id)

    try:
        result = await loop.run_in_executor(
            None,
            lambda: scrape_runner.run(
                localidades,
                categorias,
                limite,
                min_score,
                bridge,
                job.cancel_event,
                skip_fresh,
            ),
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
        f"{rows:,} new leads this run in {elapsed//60}m {elapsed%60}s.\n"
        f"  combos run: {result['combos_done']}/{result['combos_total']} "
        f"(skipped fresh: {result.get('combos_skipped_fresh', 0)})\n"
        f"  master before: {result.get('master_primed', 0):,} → after: "
        f"{len(leads_db.MASTER):,}\n"
        f"  detail: new {result['total_nuevos']}, "
        f"dup {result['total_duplicados']}, "
        f"low-score skip {result['total_skipped_score']}"
    )
    if result.get("flush_error"):
        summary += f"\n⚠️ Master flush failed: {result['flush_error']} (data kept in memory)"
    # Re-fetch quota to show actual delta consumed by this scrape.
    quota_after = await loop.run_in_executor(None, api_quota.fetch)
    quota_before = context.user_data.get("quota_before")
    if quota_after is not None:
        if quota_before is not None:
            delta = quota_before["remaining"] - quota_after["remaining"]
            summary += f"\n📊 Used by this run: {delta} businesses."
        summary += f"\n{api_quota.summary_line(quota_after)}"
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
            PICKING_STATE: [
                CallbackQueryHandler(cb_pick_state, pattern=r"^state\|"),
                CallbackQueryHandler(cb_cities_done_from_states, pattern=r"^cities_done\|"),
                CallbackQueryHandler(cb_cancel, pattern=r"^cancel\|"),
            ],
            PICKING_CITIES_IN_STATE: [
                CallbackQueryHandler(cb_toggle_city, pattern=r"^city\|"),
                CallbackQueryHandler(cb_back_to_states, pattern=r"^state_back\|"),
                CallbackQueryHandler(cb_cities_done, pattern=r"^cities_done\|"),
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
