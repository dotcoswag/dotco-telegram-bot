"""
export_smartlead.py
-------------------
Converts a scraper CSV into a Smartlead-compatible import CSV.

Smartlead columns: email, first_name, last_name, company_name,
                   phone_number, website, linkedin_profile, location
Plus, when the input came from `enrich.py`:
                   personalized_opener  (custom Smartlead variable)

Rules:
- Only rows with a non-empty email are exported (Smartlead requires it).
- first_name uses `first_name_ai` from the enriched CSV when present; otherwise "Team".
- last_name is left blank.
- Optional --min-score filter drops weak leads.
- Optional --require-qualified filter drops rows where the AI marked ai_qualified=false.

Usage:
    python export_smartlead.py resultados/dotco_leads_YYYYMMDD_HHMMSS.csv
    python export_smartlead.py resultados/dotco_leads_YYYYMMDD_HHMMSS.csv --min-score 5
    python export_smartlead.py resultados/dotco_leads_YYYYMMDD_HHMMSS_enriched.csv --require-qualified
"""

import csv
import os
import sys

BASE_COLUMNS = [
    "email", "first_name", "last_name", "company_name",
    "phone_number", "website", "linkedin_profile", "location",
]

DEFAULT_FIRST_NAME = "Team"


def to_smartlead_row(row, include_opener):
    city = row.get("city", "").strip()
    state = row.get("state", "").strip()
    location = ", ".join(p for p in (city, state) if p)

    first_name_ai = (row.get("first_name_ai") or "").strip()
    first_name = first_name_ai if first_name_ai else DEFAULT_FIRST_NAME

    out = {
        "email": row.get("email", "").strip(),
        "first_name": first_name,
        "last_name": "",
        "company_name": row.get("nombre", "").strip(),
        "phone_number": row.get("telefono", "").strip(),
        "website": row.get("website", "").strip(),
        "linkedin_profile": row.get("linkedin", "").strip(),
        "location": location,
    }
    if include_opener:
        out["personalized_opener"] = (row.get("personalized_opener") or "").strip()
    return out


def export(input_csv, min_score=0, require_qualified=False):
    if not os.path.exists(input_csv):
        print(f"ERROR: file not found: {input_csv}")
        sys.exit(1)

    base, _ = os.path.splitext(input_csv)
    output_csv = f"{base}_smartlead.csv"

    # Peek at header to decide whether to include the opener column
    with open(input_csv, encoding="utf-8") as f:
        header = next(csv.reader(f), [])
    include_opener = "personalized_opener" in header
    has_qualified = "ai_qualified" in header

    if require_qualified and not has_qualified:
        print("  --require-qualified set but input has no ai_qualified column; filter disabled.")
        require_qualified = False

    output_columns = list(BASE_COLUMNS)
    if include_opener:
        output_columns.append("personalized_opener")

    total = 0
    no_email = 0
    below_score = 0
    disqualified = 0
    written = 0

    with open(input_csv, encoding="utf-8") as fin, \
         open(output_csv, "w", encoding="utf-8", newline="") as fout:
        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=output_columns)
        writer.writeheader()

        for row in reader:
            total += 1

            email = (row.get("email") or "").strip()
            if not email:
                no_email += 1
                continue

            try:
                score = int(row.get("lead_score", 0))
            except ValueError:
                score = 0
            if score < min_score:
                below_score += 1
                continue

            if require_qualified and (row.get("ai_qualified", "").strip().lower() == "false"):
                disqualified += 1
                continue

            writer.writerow(to_smartlead_row(row, include_opener))
            written += 1

    print(f"Read   : {input_csv}")
    print(f"  total rows                  : {total}")
    print(f"  skipped (no email)          : {no_email}")
    if min_score > 0:
        print(f"  skipped (score < {min_score})        : {below_score}")
    if require_qualified:
        print(f"  skipped (ai_qualified=false): {disqualified}")
    print(f"  written                     : {written}")
    if include_opener:
        print(f"  personalized_opener column  : included")
    print(f"Output : {output_csv}")
    return output_csv


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python export_smartlead.py <csv> [--min-score N] [--require-qualified]")
        sys.exit(1)

    input_csv = sys.argv[1]
    min_score = 0
    require_qualified = "--require-qualified" in sys.argv

    if "--min-score" in sys.argv:
        idx = sys.argv.index("--min-score")
        try:
            min_score = int(sys.argv[idx + 1])
        except (IndexError, ValueError):
            print("ERROR: --min-score needs an integer (e.g. --min-score 5)")
            sys.exit(1)

    export(input_csv, min_score, require_qualified)
