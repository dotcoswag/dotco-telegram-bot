"""Cancel-aware scrape outer loop for the Telegram bot.

Reimplements `main.correr_scraping`'s combination loop without the interactive
`input()` checkpoint prompt (filesystem is ephemeral on Render). Adds two
things on top of the CLI flow:

- `seen_ids` is primed from `leads_db.business_ids()` so businesses already in
  the master DB are deduped across runs.
- Optional `skip_fresh` filters out combos that were scraped within
  `config.COMBO_FRESH_DAYS` and returned at least one business — this is the
  real RapidAPI-quota saver (the API has no exclude-by-id).
"""

import os
import threading
import time
from datetime import datetime
from typing import Optional

import main as scraper_main
from scraper import scrape_combinacion, QuotaExhausted

from bot import config, leads_db
from bot.github_storage import StorageError
from bot.progress import ProgressBridge


def run(
    localidades: list[tuple[str, str]],
    categorias: list[str],
    limite: Optional[int],
    min_score: int,
    bridge: ProgressBridge,
    cancel_event: threading.Event,
    skip_fresh: bool = True,
) -> dict:
    """Run a scrape job. Returns a result dict including the CSV path."""
    os.makedirs(scraper_main.RESULTADOS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archivo_csv = os.path.join(scraper_main.RESULTADOS_DIR, f"dotco_leads_{timestamp}.csv")

    # Build combo list and apply freshness filter when enabled.
    all_combos = [(loc, prov, cat) for (loc, prov) in localidades for cat in categorias]
    try:
        leads_db.ensure_loaded()
    except StorageError as e:
        bridge.push(f"⚠️ Master DB unavailable — running without cross-scrape dedup ({e})", force=True)
    if skip_fresh:
        combos = [
            (loc, prov, cat)
            for (loc, prov, cat) in all_combos
            if not leads_db.is_fresh(loc, prov, cat, config.COMBO_FRESH_DAYS)
        ]
        skipped_fresh = len(all_combos) - len(combos)
    else:
        combos = list(all_combos)
        skipped_fresh = 0
    total_combos = len(combos)

    # Prime seen_ids from the master DB so we never write a business twice.
    try:
        seen_ids: set[str] = set(leads_db.business_ids())
    except Exception:
        seen_ids = set()
    primed_count = len(seen_ids)

    total_nuevos = 0
    total_duplicados = 0
    total_skipped_score = 0
    inicio = time.time()

    bridge.push(
        f"⏳ Starting scrape\n"
        f"  combos: {total_combos} (skipped fresh: {skipped_fresh})\n"
        f"  master primed: {primed_count} business_ids loaded\n"
        f"  limit: {limite or '∞'}, min_score: {min_score}",
        force=True,
    )

    cancelled = False
    i = 0
    for i, (loc, prov, cat) in enumerate(combos, start=1):
        if cancel_event.is_set():
            cancelled = True
            break
        if limite is not None and len(seen_ids) - primed_count >= limite:
            break

        try:
            nuevos, dup, skip = scrape_combinacion(
                localidad=loc,
                categoria=cat,
                provincia=prov,
                archivo_csv=archivo_csv,
                seen_ids=seen_ids,
                limite_total=limite,
                min_score=min_score,
                cancel_event=cancel_event,
                on_new_rows=leads_db.add_rows,
            )
        except QuotaExhausted as e:
            bridge.push(
                f"🛑 RapidAPI quota exhausted — aborting scrape.\n"
                f"  {e}\n"
                f"  Check / upgrade plan: "
                f"https://rapidapi.com/letscrape-6bRBa3QguO5/api/local-business-data",
                force=True,
            )
            cancelled = True
            break
        except Exception as e:
            bridge.push(f"⚠️ Error on {loc}/{cat}: {e}", force=True)
            continue

        leads_db.record_scrape(loc, prov, cat, nuevos)
        total_nuevos += nuevos
        total_duplicados += dup
        total_skipped_score += skip

        elapsed = int(time.time() - inicio)
        bridge.push(
            f"[{i}/{total_combos}] {loc}, {prov} · {cat}\n"
            f"  +{nuevos} new ({dup} dup, {skip} skip) · "
            f"run total: {len(seen_ids) - primed_count:,} · {elapsed}s elapsed"
        )

    # Always try to flush — even on cancel/quota-exhausted — so the partial
    # progress is durable. Surface failure to the user but don't crash.
    flush_error: Optional[str] = None
    try:
        leads_db.flush()
    except Exception as e:
        flush_error = str(e)
        bridge.push(f"⚠️ Master DB flush failed: {e}", force=True)

    elapsed_total = int(time.time() - inicio)
    return {
        "csv_path": archivo_csv if os.path.exists(archivo_csv) else None,
        "combos_done": i,
        "combos_total": total_combos,
        "combos_skipped_fresh": skipped_fresh,
        "rows_saved": len(seen_ids) - primed_count,
        "total_nuevos": total_nuevos,
        "total_duplicados": total_duplicados,
        "total_skipped_score": total_skipped_score,
        "elapsed_seconds": elapsed_total,
        "cancelled": cancelled,
        "flush_error": flush_error,
        "master_primed": primed_count,
    }
