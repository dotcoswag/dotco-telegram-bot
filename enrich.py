"""
enrich.py
---------
Post-process a scraper CSV with optional Claude AI enrichment.

Adds up to four columns to a sidecar `<input>_enriched.csv`:
- first_name_ai          — inferred first name from email local-part
- personalized_opener    — 1-2 sentence cold-email opener
- ai_qualified           — "true" / "false"
- ai_reject_reason       — short reason when ai_qualified=false

Strictly opt-in: if ANTHROPIC_API_KEY is empty, this script is a no-op.

Usage:
    python enrich.py resultados/dotco_leads_YYYYMMDD_HHMMSS.csv
    python enrich.py file.csv --features first_name,opener
"""

import csv
import json
import os
import re
import sys

import ai_client
import ai_prompts

ALL_FEATURES = ("first_name", "opener", "qualify")

BATCH_SIZES = {
    "first_name": 50,
    "opener": 10,
    "qualify": 25,
}

MODELS = {
    "first_name": ai_client.HAIKU,
    "opener": ai_client.SONNET,
    "qualify": ai_client.HAIKU,
}

MAX_TOKENS = {
    "first_name": 1500,
    "opener": 1500,
    "qualify": 1500,
}

# Columns added to the enriched CSV (in this order, after the original columns)
AI_COLUMNS = ["first_name_ai", "personalized_opener", "ai_qualified", "ai_reject_reason"]


# ──────────────────────────────────────────────────────────────────────
# JSON parsing — tolerant of code-fence wrappers
# ──────────────────────────────────────────────────────────────────────

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _parse_json_array(text):
    if not text:
        return None
    cleaned = _FENCE_RE.sub("", text).strip()
    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            return data
        return None
    except json.JSONDecodeError:
        # Try extracting the first [...] block
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(cleaned[start:end + 1])
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                pass
        return None


# ──────────────────────────────────────────────────────────────────────
# Per-feature batch payload builders
# ──────────────────────────────────────────────────────────────────────

def _payload_first_name(rows):
    return [{"id": r["_id"], "email": r.get("email", "")} for r in rows]


def _payload_opener(rows):
    return [{
        "id": r["_id"],
        "company": r.get("nombre", ""),
        "type": r.get("tipo", ""),
        "rating": r.get("rating", ""),
        "reviews": r.get("review_count", ""),
        "city": r.get("city", ""),
        "state": r.get("state", ""),
        "category_searched": r.get("categoria_buscada", ""),
    } for r in rows]


def _payload_qualify(rows):
    return [{
        "id": r["_id"],
        "company": r.get("nombre", ""),
        "type": r.get("tipo", ""),
        "rating": r.get("rating", ""),
        "reviews": r.get("review_count", ""),
        "business_status": r.get("business_status", ""),
        "city": r.get("city", ""),
        "state": r.get("state", ""),
        "website": r.get("website", ""),
        "category_searched": r.get("categoria_buscada", ""),
    } for r in rows]


PAYLOAD_BUILDERS = {
    "first_name": _payload_first_name,
    "opener": _payload_opener,
    "qualify": _payload_qualify,
}

SYSTEMS = {
    "first_name": ai_prompts.first_name_system,
    "opener": ai_prompts.opener_system,
    "qualify": ai_prompts.qualify_system,
}


# ──────────────────────────────────────────────────────────────────────
# Result application
# ──────────────────────────────────────────────────────────────────────

def _apply_first_name(rows_by_id, results):
    for item in results:
        rid = item.get("id")
        if rid in rows_by_id:
            rows_by_id[rid]["first_name_ai"] = str(item.get("first_name", "")).strip()


def _apply_opener(rows_by_id, results):
    for item in results:
        rid = item.get("id")
        if rid in rows_by_id:
            rows_by_id[rid]["personalized_opener"] = str(item.get("opener", "")).strip()


def _apply_qualify(rows_by_id, results):
    for item in results:
        rid = item.get("id")
        if rid in rows_by_id:
            q = item.get("qualified")
            rows_by_id[rid]["ai_qualified"] = "true" if q is True else ("false" if q is False else "")
            rows_by_id[rid]["ai_reject_reason"] = str(item.get("reason", "")).strip()


APPLIERS = {
    "first_name": _apply_first_name,
    "opener": _apply_opener,
    "qualify": _apply_qualify,
}


# ──────────────────────────────────────────────────────────────────────
# Per-feature orchestration
# ──────────────────────────────────────────────────────────────────────

def _run_feature(feature, rows, rows_by_id):
    batch_size = BATCH_SIZES[feature]
    model = MODELS[feature]
    system = SYSTEMS[feature]()
    payload_builder = PAYLOAD_BUILDERS[feature]
    applier = APPLIERS[feature]
    max_tok = MAX_TOKENS[feature]

    total = len(rows)
    total_in = 0
    total_out = 0
    batches_ok = 0
    batches_failed = 0
    rows_processed = 0

    for start in range(0, total, batch_size):
        batch = rows[start:start + batch_size]
        payload = payload_builder(batch)
        user_msg = json.dumps(payload, ensure_ascii=False)

        try:
            text, usage = ai_client.call_with_retry(
                model=model,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
                max_tokens=max_tok,
            )
        except ai_client.QuotaExhausted as e:
            print(f"  ⚠️  AI quota/auth failed during {feature}: {e}")
            print(f"     Stopping {feature}. {total - rows_processed} rows will have blank {feature} columns.")
            return {"feature": feature, "processed": rows_processed, "skipped": total - rows_processed,
                    "in_tokens": total_in, "out_tokens": total_out, "aborted": True}

        if text is None:
            batches_failed += 1
            rows_processed += len(batch)
            print(f"  [{feature} batch {start // batch_size + 1}] soft failure — leaving rows blank")
            continue

        total_in += usage["input_tokens"] + usage.get("cache_creation_input_tokens", 0)
        total_out += usage["output_tokens"]

        results = _parse_json_array(text)
        if not results:
            batches_failed += 1
            rows_processed += len(batch)
            print(f"  [{feature} batch {start // batch_size + 1}] JSON parse failed — leaving rows blank")
            continue

        applier(rows_by_id, results)
        batches_ok += 1
        rows_processed += len(batch)
        print(f"  [{feature}] {rows_processed}/{total} rows processed")

    cost = ai_client.estimate_cost(model, total_in, total_out)
    return {
        "feature": feature, "processed": rows_processed, "skipped": 0,
        "batches_ok": batches_ok, "batches_failed": batches_failed,
        "in_tokens": total_in, "out_tokens": total_out, "cost_usd": cost,
        "aborted": False,
    }


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────

def estimate_total_cost(num_rows, features):
    """Rough pre-run estimate. Uses per-feature token assumptions."""
    # Per-row token estimates (in + out averaged across batch overhead)
    per_row = {
        "first_name": (10, 8),       # in / out
        "opener": (90, 60),
        "qualify": (30, 18),
    }
    total = 0.0
    for f in features:
        if f not in per_row:
            continue
        in_per, out_per = per_row[f]
        total += ai_client.estimate_cost(MODELS[f], num_rows * in_per, num_rows * out_per)
    return total


def enrich_csv(input_csv, features=ALL_FEATURES):
    if not ai_client.is_enabled():
        print("  ANTHROPIC_API_KEY not set — skipping AI enrichment.")
        return None

    if not os.path.exists(input_csv):
        print(f"ERROR: file not found: {input_csv}")
        return None

    base, _ = os.path.splitext(input_csv)
    output_csv = f"{base}_enriched.csv"

    # Load
    with open(input_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        original_columns = list(reader.fieldnames or [])
        rows = []
        for i, row in enumerate(reader):
            row["_id"] = i
            for col in AI_COLUMNS:
                row.setdefault(col, "")
            rows.append(row)

    if not rows:
        print("  Input CSV has no rows.")
        return None

    rows_by_id = {r["_id"]: r for r in rows}

    print(f"  Enriching {len(rows)} rows with features: {', '.join(features)}")

    summaries = []
    for feature in features:
        if feature not in ALL_FEATURES:
            print(f"  ⚠️  Unknown feature '{feature}', skipping.")
            continue
        print(f"  → {feature}")
        summary = _run_feature(feature, rows, rows_by_id)
        summaries.append(summary)

    # Write
    output_columns = original_columns + AI_COLUMNS
    with open(output_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=output_columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    # Report
    print()
    print(f"  Enriched CSV: {output_csv}")
    total_cost = 0.0
    total_in = 0
    total_out = 0
    for s in summaries:
        cost = s.get("cost_usd", 0.0)
        total_cost += cost
        total_in += s.get("in_tokens", 0)
        total_out += s.get("out_tokens", 0)
        status = " (ABORTED)" if s.get("aborted") else ""
        print(f"    {s['feature']:11} — {s['in_tokens']} in / {s['out_tokens']} out tokens, ~${cost:.4f}{status}")
    print(f"  Total tokens: {total_in} in / {total_out} out — estimated cost ~${total_cost:.4f}")

    return output_csv


# ──────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────

def _parse_args(argv):
    if len(argv) < 2:
        print("Usage: python enrich.py <csv> [--features first_name,opener,qualify]")
        sys.exit(1)
    input_csv = argv[1]
    features = ALL_FEATURES
    if "--features" in argv:
        idx = argv.index("--features")
        try:
            features = tuple(f.strip() for f in argv[idx + 1].split(",") if f.strip())
        except (IndexError, ValueError):
            print("ERROR: --features needs a comma-separated list (e.g. first_name,opener)")
            sys.exit(1)
    return input_csv, features


if __name__ == "__main__":
    input_csv, features = _parse_args(sys.argv)
    enrich_csv(input_csv, features)
