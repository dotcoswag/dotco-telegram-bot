"""In-memory leads master + scrape log, persisted to GitHub via github_storage.

Master schema = `scraper.COLUMNAS_CSV` (31 columns). Keyed by business_id.

Scrape log schema (4 cols, separate file):
    localidad, provincia, categoria, last_scraped_at_iso, returned_count
"""

import csv
import io
import re
import threading
from datetime import datetime, timezone
from typing import Iterable, Iterator, Optional

import scraper as scraper_mod
from bot import config, github_storage


MASTER_PATH = "data/master_leads.csv"
SCRAPE_LOG_PATH = "data/scrape_log.csv"

LOG_COLUMNS = ["localidad", "provincia", "categoria", "last_scraped_at_iso", "returned_count"]


# ── module state ─────────────────────────────────────────────

_lock = threading.Lock()
_loaded = False
MASTER: dict[str, dict] = {}
SCRAPE_LOG: dict[tuple[str, str, str], dict] = {}
# Secondary index — normalized_phone → business_id. Lets add_rows reject a
# row whose phone matches an existing master entry under a different
# business_id (RapidAPI sometimes returns the same business with two
# different place_ids).
PHONE_INDEX: dict[str, str] = {}
_master_sha: Optional[str] = None
_log_sha: Optional[str] = None
_dirty_count = 0


def _normalize_phone(phone: str) -> str:
    """US-friendly canonical form: strip everything non-digit, drop leading 1."""
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    # Anything less than 10 digits is too ambiguous to use as a dedup key.
    return digits if len(digits) >= 10 else ""


# ── load / save ──────────────────────────────────────────────

def ensure_loaded() -> None:
    """Lazy-load both files from storage on first call."""
    global _loaded, _master_sha, _log_sha
    with _lock:
        if _loaded:
            return
        master_bytes, _master_sha = github_storage.get_file(MASTER_PATH)
        log_bytes, _log_sha = github_storage.get_file(SCRAPE_LOG_PATH)
        if master_bytes:
            for row in csv.DictReader(io.StringIO(master_bytes.decode("utf-8"))):
                bid = row.get("business_id") or ""
                if bid:
                    MASTER[bid] = row
                    p = _normalize_phone(row.get("telefono", ""))
                    if p and p not in PHONE_INDEX:
                        PHONE_INDEX[p] = bid
        if log_bytes:
            for row in csv.DictReader(io.StringIO(log_bytes.decode("utf-8"))):
                key = (row.get("localidad", ""), row.get("provincia", ""), row.get("categoria", ""))
                SCRAPE_LOG[key] = row
        _loaded = True


def force_pull() -> tuple[int, int]:
    """Discard in-memory state and re-fetch both files. Returns (master_rows, log_rows)."""
    global _loaded
    with _lock:
        MASTER.clear()
        SCRAPE_LOG.clear()
        PHONE_INDEX.clear()
        _loaded = False
    ensure_loaded()
    return len(MASTER), len(SCRAPE_LOG)


def _serialize_master() -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=scraper_mod.COLUMNAS_CSV, extrasaction="ignore")
    writer.writeheader()
    for row in MASTER.values():
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


def _serialize_log() -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=LOG_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in SCRAPE_LOG.values():
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


def flush() -> None:
    """Push both files back to storage. Idempotent. Resets dirty counter on success."""
    global _master_sha, _log_sha, _dirty_count
    ensure_loaded()
    with _lock:
        master_bytes = _serialize_master()
        log_bytes = _serialize_log()
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        # Master push
        _master_sha = github_storage.put_file(
            MASTER_PATH,
            master_bytes,
            _master_sha,
            f"bot: master_leads update ({len(MASTER)} rows) {ts}",
        )
        # Log push
        _log_sha = github_storage.put_file(
            SCRAPE_LOG_PATH,
            log_bytes,
            _log_sha,
            f"bot: scrape_log update ({len(SCRAPE_LOG)} combos) {ts}",
        )
        _dirty_count = 0


# ── public API used by the scrape pipeline ───────────────────

def business_ids() -> set[str]:
    ensure_loaded()
    return set(MASTER.keys())


def add_rows(rows: Iterable[dict]) -> int:
    """Add rows to MASTER. Dedups by business_id AND by normalized phone.
    First-write-wins. Returns added count.

    Triggers an auto-flush once dirty count crosses `MASTER_FLUSH_EVERY_N`.
    """
    global _dirty_count
    ensure_loaded()
    added = 0
    with _lock:
        for row in rows:
            bid = (row.get("business_id") or "").strip()
            if not bid or bid in MASTER:
                continue
            phone = _normalize_phone(row.get("telefono", ""))
            if phone and phone in PHONE_INDEX:
                # Same phone, different business_id — most likely RapidAPI
                # returned a duplicate listing. Skip without overwriting.
                continue
            MASTER[bid] = dict(row)
            if phone:
                PHONE_INDEX[phone] = bid
            added += 1
            _dirty_count += 1
    if _dirty_count >= config.MASTER_FLUSH_EVERY_N:
        try:
            flush()
        except github_storage.StorageError:
            # Caller (scrape_runner) is expected to surface flush failures to the user
            # at the end of the run; here we just let dirty rows sit in RAM.
            pass
    return added


def record_scrape(localidad: str, provincia: str, categoria: str, returned_count: int) -> None:
    """Upsert the per-combo last-scraped timestamp."""
    ensure_loaded()
    key = (localidad, provincia, categoria)
    with _lock:
        SCRAPE_LOG[key] = {
            "localidad": localidad,
            "provincia": provincia,
            "categoria": categoria,
            "last_scraped_at_iso": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "returned_count": str(returned_count),
        }


def is_fresh(localidad: str, provincia: str, categoria: str, days: int) -> bool:
    """True if this combo was scraped within `days` AND returned at least 1 business."""
    ensure_loaded()
    entry = SCRAPE_LOG.get((localidad, provincia, categoria))
    if not entry:
        return False
    try:
        when = datetime.fromisoformat(entry["last_scraped_at_iso"])
    except (KeyError, ValueError):
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    try:
        if int(entry.get("returned_count", "0")) <= 0:
            return False
    except ValueError:
        return False
    age_days = (datetime.now(timezone.utc) - when).total_seconds() / 86400
    return age_days < days


def fresh_count(combos: list[tuple[str, str, str]], days: int) -> int:
    return sum(1 for (loc, prov, cat) in combos if is_fresh(loc, prov, cat, days))


# ── public API used by /db_* commands ────────────────────────

def stats() -> dict:
    """Quick aggregates for /db_stats."""
    ensure_loaded()
    if not MASTER:
        return {"total": 0, "by_state": {}, "by_category": {}, "score_hist": {}}
    by_state: dict[str, int] = {}
    by_category: dict[str, int] = {}
    score_hist: dict[int, int] = {}
    for row in MASTER.values():
        state = row.get("state") or row.get("provincia") or "(unknown)"
        by_state[state] = by_state.get(state, 0) + 1
        cat = row.get("categoria_buscada") or "(unknown)"
        by_category[cat] = by_category.get(cat, 0) + 1
        try:
            sc = int(row.get("lead_score", 0))
        except (ValueError, TypeError):
            sc = 0
        score_hist[sc] = score_hist.get(sc, 0) + 1
    return {
        "total": len(MASTER),
        "by_state": by_state,
        "by_category": by_category,
        "score_hist": score_hist,
        "combos_logged": len(SCRAPE_LOG),
    }


def filter_rows(state: Optional[str] = None,
                category_group: Optional[str] = None,
                min_score: int = 0) -> Iterator[dict]:
    """Yield rows matching the filters. category_group expects a key from main.CATEGORIAS."""
    import main as scraper_main
    ensure_loaded()
    group_cats: Optional[set[str]] = None
    if category_group:
        group_cats = set(scraper_main.CATEGORIAS.get(category_group, []))
    for row in MASTER.values():
        if state and (row.get("state") or row.get("provincia")) != state:
            continue
        if group_cats is not None and row.get("categoria_buscada") not in group_cats:
            continue
        try:
            sc = int(row.get("lead_score", 0))
        except (ValueError, TypeError):
            sc = 0
        if sc < min_score:
            continue
        yield row


def write_filtered_csv(path: str, **filters) -> int:
    """Write the filtered rows to a CSV at `path`. Returns row count."""
    rows = list(filter_rows(**filters))
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=scraper_mod.COLUMNAS_CSV, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return len(rows)


def _reset_for_tests() -> None:
    """Clears all module state. Tests use this in setup/teardown."""
    global _loaded, _master_sha, _log_sha, _dirty_count
    with _lock:
        MASTER.clear()
        SCRAPE_LOG.clear()
        PHONE_INDEX.clear()
        _loaded = False
        _master_sha = None
        _log_sha = None
        _dirty_count = 0
