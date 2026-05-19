"""/quota and /demo commands.

/quota — show live status of every external service the bot depends on:
  • RapidAPI (live businesses quota from response headers)
  • Anthropic (key configured/not, since the SDK has no remaining-credits API)
  • Telegram (webhook URL, pending updates, last error)

/demo — seed a synthetic CSV on the server so /export_smartlead and /export_excel
        can be tested end-to-end without spending RapidAPI quota.
"""

import asyncio
import csv
import os
from datetime import datetime

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

import ai_client
import main as scraper_main
import scraper as scraper_mod

from bot import api_quota
from bot.job_manager import jobs


# ── /quota ───────────────────────────────────────────────────

async def cmd_quota(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    loop = asyncio.get_running_loop()
    quota = await loop.run_in_executor(None, api_quota.fetch)

    # Telegram side
    try:
        bot_info = await context.bot.get_me()
        webhook = await context.bot.get_webhook_info()
        tg_line = (
            f"Telegram: @{bot_info.username} ✓\n"
            f"  pending updates: {webhook.pending_update_count}"
        )
        if webhook.last_error_message:
            ts = datetime.utcfromtimestamp(webhook.last_error_date).strftime("%H:%M:%S UTC")
            tg_line += f"\n  last error ({ts}): {webhook.last_error_message[:100]}"
    except Exception as e:
        tg_line = f"Telegram: error fetching info — {e}"

    # Anthropic side — there is no public endpoint for remaining credits on a
    # standard key, so we only report whether the key is wired up.
    if ai_client.is_enabled():
        ai_line = (
            "Anthropic: key configured ✓\n"
            "  No live quota API — see console.anthropic.com for usage / limits"
        )
    else:
        ai_line = "Anthropic: not configured (set ANTHROPIC_API_KEY to enable /enrich)"

    lines = ["📊 Service status\n"]
    lines.append(api_quota.summary_line(quota))
    if quota is not None and quota["remaining"] <= 0:
        lines.append(
            f"  ⚠️ Quota exhausted. New scrapes will abort on the first call.\n"
            f"  Reset in {api_quota.format_reset(quota['reset_seconds'])}, or upgrade the plan."
        )
    elif quota is not None:
        lines.append(f"  {quota['remaining']:,} businesses remaining this cycle")
    lines.append("")
    lines.append(ai_line)
    lines.append("")
    lines.append(tg_line)
    await update.message.reply_text("\n".join(lines))


# ── /demo ────────────────────────────────────────────────────

DEMO_ROWS = [
    {
        "business_id": "demo-001", "nombre": "Demo Smoke Shop", "tipo": "smoke shop",
        "subtipo": "tobacco shop", "rating": "4.6", "review_count": "85",
        "verified": "true", "business_status": "OPERATIONAL", "lead_score": "6",
        "photos_count": "12", "direccion": "123 Main St", "city": "Madison",
        "state": "Wisconsin", "district": "Downtown", "latitude": "43.07",
        "longitude": "-89.40", "telefono": "+1-608-555-0101",
        "email": "owner@demosmoke.example", "website": "https://demosmoke.example",
        "instagram": "https://instagram.com/demosmoke", "facebook": "",
        "linkedin": "", "twitter": "", "youtube": "", "emails_extra": "",
        "link_google_maps": "https://maps.google.com/?cid=demo1",
        "booking_link": "", "menu_link": "", "order_link": "",
        "localidad_buscada": "Madison", "categoria_buscada": "smoke shop",
        "provincia": "Wisconsin",
    },
    {
        "business_id": "demo-002", "nombre": "Boulder Yoga Co.", "tipo": "yoga studio",
        "subtipo": "fitness", "rating": "4.9", "review_count": "210",
        "verified": "true", "business_status": "OPERATIONAL", "lead_score": "7",
        "photos_count": "30", "direccion": "55 Pearl St", "city": "Boulder",
        "state": "Colorado", "district": "", "latitude": "40.02",
        "longitude": "-105.27", "telefono": "+1-303-555-0202",
        "email": "hello@boulderyoga.example", "website": "https://boulderyoga.example",
        "instagram": "https://instagram.com/boulderyoga",
        "facebook": "https://facebook.com/boulderyoga", "linkedin": "",
        "twitter": "", "youtube": "", "emails_extra": "studio@boulderyoga.example",
        "link_google_maps": "https://maps.google.com/?cid=demo2",
        "booking_link": "", "menu_link": "", "order_link": "",
        "localidad_buscada": "Boulder", "categoria_buscada": "yoga studio",
        "provincia": "Colorado",
    },
    {
        "business_id": "demo-003", "nombre": "Bend Brewery", "tipo": "brewery",
        "subtipo": "restaurant", "rating": "4.3", "review_count": "450",
        "verified": "true", "business_status": "OPERATIONAL", "lead_score": "5",
        "photos_count": "60", "direccion": "200 SW Industrial Way",
        "city": "Bend", "state": "Oregon", "district": "", "latitude": "44.06",
        "longitude": "-121.31", "telefono": "+1-541-555-0303",
        "email": "", "website": "https://bendbrewery.example",
        "instagram": "", "facebook": "", "linkedin": "", "twitter": "",
        "youtube": "", "emails_extra": "",
        "link_google_maps": "https://maps.google.com/?cid=demo3",
        "booking_link": "", "menu_link": "", "order_link": "",
        "localidad_buscada": "Bend", "categoria_buscada": "brewery",
        "provincia": "Oregon",
    },
    {
        "business_id": "demo-004", "nombre": "Asheville Barber Co.",
        "tipo": "barbershop", "subtipo": "personal care", "rating": "4.8",
        "review_count": "120", "verified": "false", "business_status": "OPERATIONAL",
        "lead_score": "4", "photos_count": "18", "direccion": "10 Biltmore Ave",
        "city": "Asheville", "state": "North Carolina", "district": "",
        "latitude": "35.59", "longitude": "-82.55",
        "telefono": "+1-828-555-0404", "email": "info@ashevillebarber.example",
        "website": "", "instagram": "", "facebook": "", "linkedin": "",
        "twitter": "", "youtube": "", "emails_extra": "",
        "link_google_maps": "https://maps.google.com/?cid=demo4",
        "booking_link": "", "menu_link": "", "order_link": "",
        "localidad_buscada": "Asheville", "categoria_buscada": "barbershop",
        "provincia": "North Carolina",
    },
    {
        "business_id": "demo-005", "nombre": "Santa Fe Real Estate",
        "tipo": "real estate agency", "subtipo": "professional services",
        "rating": "3.9", "review_count": "12", "verified": "false",
        "business_status": "OPERATIONAL", "lead_score": "2", "photos_count": "4",
        "direccion": "500 Cerrillos Rd", "city": "Santa Fe", "state": "New Mexico",
        "district": "", "latitude": "35.69", "longitude": "-105.94",
        "telefono": "", "email": "agent@santaferealty.example",
        "website": "https://santaferealty.example",
        "instagram": "", "facebook": "", "linkedin": "", "twitter": "",
        "youtube": "", "emails_extra": "",
        "link_google_maps": "https://maps.google.com/?cid=demo5",
        "booking_link": "", "menu_link": "", "order_link": "",
        "localidad_buscada": "Santa Fe", "categoria_buscada": "real estate agency",
        "provincia": "New Mexico",
    },
]


async def cmd_demo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    os.makedirs(scraper_main.RESULTADOS_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(scraper_main.RESULTADOS_DIR, f"dotco_leads_DEMO_{ts}.csv")
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=scraper_mod.COLUMNAS_CSV)
        writer.writeheader()
        for row in DEMO_ROWS:
            writer.writerow(row)
    jobs.set_last_result(chat_id, path)
    await update.message.reply_text(
        f"✓ Demo CSV created: {os.path.basename(path)} ({len(DEMO_ROWS)} rows).\n\n"
        f"Now try:\n"
        f"  /export_smartlead — emails only, with min_score filter\n"
        f"  /export_excel — formatted XLSX\n"
        f"  /enrich — requires ANTHROPIC_API_KEY"
    )
    with open(path, "rb") as f:
        await context.bot.send_document(chat_id=chat_id, document=f,
                                        filename=os.path.basename(path))


def register(application) -> None:
    application.add_handler(CommandHandler("quota", cmd_quota))
    application.add_handler(CommandHandler("demo", cmd_demo))
