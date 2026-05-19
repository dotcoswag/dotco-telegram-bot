"""Smoke test for the scraping pipeline. Run once to verify end-to-end."""
import csv
import os
from collections import Counter
from scraper import scrape_combinacion

CSV_PATH = "resultados/smoketest.csv"

if os.path.exists(CSV_PATH):
    os.remove(CSV_PATH)

seen = set()
nuevos, dups, skipped = scrape_combinacion(
    localidad="Boulder",
    categoria="coffee shop",
    provincia="Colorado",
    archivo_csv=CSV_PATH,
    seen_ids=seen,
    limite_total=10,
    min_score=0,
)

print(f"\n--- scrape_combinacion returned ---")
print(f"  nuevos={nuevos}  dups={dups}  skipped={skipped}")
print(f"  seen_ids={len(seen)}")

print(f"\n--- CSV inspection ---")
with open(CSV_PATH, encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

print(f"  rows written: {len(rows)}")
if rows:
    scores = Counter(int(r["lead_score"]) for r in rows)
    print(f"  lead_score distribution: {dict(sorted(scores.items()))}")
    print(f"  with email   : {sum(1 for r in rows if r['email'])}/{len(rows)}")
    print(f"  with phone   : {sum(1 for r in rows if r['telefono'])}/{len(rows)}")
    print(f"  with website : {sum(1 for r in rows if r['website'])}/{len(rows)}")
    print(f"  with social  : {sum(1 for r in rows if r['instagram'] or r['facebook'])}/{len(rows)}")
    print(f"\n  sample row (first):")
    r = rows[0]
    for k in ("nombre", "city", "state", "rating", "review_count", "telefono", "email", "website", "lead_score"):
        print(f"    {k:14}: {r.get(k, '')!r}")
