"""Cancel-aware scrape outer loop for the Telegram bot.

This is a reimplementation of `main.correr_scraping`'s combination loop
without the interactive `input()` checkpoint prompt and without on-disk
checkpoint writes (the filesystem is ephemeral on Render free anyway).
It calls into the same inner function (`scraper.scrape_combinacion`) so
scoring, dedup, and API logic all stay in one place.
"""

import os
import threading
import time
from datetime import datetime
from typing import Optional

import main as scraper_main
from scraper import scrape_combinacion, QuotaExhausted

from bot.progress import ProgressBridge


def run(
    localidades: list[tuple[str, str]],
    categorias: list[str],
    limite: Optional[int],
    min_score: int,
    bridge: ProgressBridge,
    cancel_event: threading.Event,
) -> dict:
    """Run a scrape job. Returns a result dict including the CSV path."""
    os.makedirs(scraper_main.RESULTADOS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archivo_csv = os.path.join(scraper_main.RESULTADOS_DIR, f"dotco_leads_{timestamp}.csv")

    combos = [(loc, prov, cat) for (loc, prov) in localidades for cat in categorias]
    total_combos = len(combos)

    seen_ids: set[str] = set()
    total_nuevos = 0
    total_duplicados = 0
    total_skipped_score = 0
    inicio = time.time()

    bridge.push(
        f"⏳ Starting scrape — {total_combos} combinations "
        f"(cities×categories), limit={limite or '∞'}, min_score={min_score}",
        force=True,
    )

    cancelled = False
    for i, (loc, prov, cat) in enumerate(combos, start=1):
        if cancel_event.is_set():
            cancelled = True
            break
        if limite is not None and len(seen_ids) >= limite:
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

        total_nuevos += nuevos
        total_duplicados += dup
        total_skipped_score += skip

        elapsed = int(time.time() - inicio)
        bridge.push(
            f"[{i}/{total_combos}] {loc}, {prov} · {cat}\n"
            f"  +{nuevos} new ({dup} dup, {skip} skip) · total saved: {len(seen_ids):,} · {elapsed}s elapsed"
        )

    elapsed_total = int(time.time() - inicio)
    return {
        "csv_path": archivo_csv if os.path.exists(archivo_csv) else None,
        "combos_done": i if total_combos else 0,
        "combos_total": total_combos,
        "rows_saved": len(seen_ids),
        "total_nuevos": total_nuevos,
        "total_duplicados": total_duplicados,
        "total_skipped_score": total_skipped_score,
        "elapsed_seconds": elapsed_total,
        "cancelled": cancelled,
    }
