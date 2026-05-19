# CLAUDE.md

Guidance for Claude Code sessions working in this repository.

## What this project is

DotCo Swag scraper — a B2B sales lead-generation tool, not a software project.
The user runs it to produce CSVs of US small businesses for a branded-merch
outreach campaign. Every change should ultimately make leads *more reachable
and higher quality*, not the code prettier.

## Module map (current, working code)

| File | Purpose |
|---|---|
| `main.py` | Interactive CLI. Orchestrates scrape via prompts. Owns `CATEGORIAS` and `MERCADOS_RECOMENDADOS` dicts. |
| `scraper.py` | RapidAPI client + dedup + CSV writer. `scrape_combinacion()` is the non-interactive primitive. `calcular_lead_score()` computes 0–7. |
| `build_data.py` | Generates `data/us_cities.json` (298 cities × 51 states). Keyed `CITY_POPS` dict is `(state, city) → population`. |
| `export.py` | CSV → styled XLSX (color-coded by lead score). |
| `export_smartlead.py` | CSV → Smartlead-importable CSV. Reads AI columns when present; falls back to defaults. |
| `ai_client.py` | Anthropic SDK wrapper. `is_enabled()`, `call_with_retry()`, `QuotaExhausted` exception. |
| `ai_prompts.py` | Versioned system prompts for the 3 enrichment features (v2). Each prompt is cache-tagged. |
| `enrich.py` | Orchestrator for AI enrichment. Reads raw CSV, writes sidecar `_enriched.csv`. CLI: `python enrich.py <csv>`. |
| `smoketest.py` | One-off — exercises the scrape pipeline on Boulder coffee shops. Cheap (1 API call). |
| `test_email_flag.py` | One-off probe — confirmed `extract_emails_and_contacts=true` works on RapidAPI. Safe to delete. |

## Files NOT to extend

- `mcp_server.py`, `mcp_server_hybrid.py` — both non-functional. Aspirational MCP wrappers from before the AI enrichment work. They will hang on `input()` calls in `correr_scraping`, and the wire protocol isn't real MCP. Don't add features to these or invoke them.

## Hard invariants

1. **AI is strictly opt-in per run.** Every AI-touching prompt must default to `n`.
   Pipeline must work identically with `ANTHROPIC_API_KEY=` empty.
   See `feedback-ai-optional` memory for full rationale.

2. **`extract_emails_and_contacts=true`** is required on every RapidAPI search
   call (`scraper.py:99-107`). Without it, `email`, `instagram`, `facebook`,
   `linkedin` columns will be empty for every lead. Removing this flag silently
   breaks the entire outreach pipeline.

3. **`CITY_POPS` keys are `(state, city)` tuples**, not bare city names.
   This kills name-collision bugs (Jackson MS 145k vs Jackson WY 11k,
   Portland OR 631k vs Portland ME 68k, Springfield {IL/MA/MO}, etc.).
   If you re-flatten this dict you reintroduce the bug.

4. **CSV column order is defined once** in `scraper.COLUMNAS_CSV` (scraper.py:29-69).
   Don't duplicate the list elsewhere. `export.py` reads from the CSV header
   dynamically; `export_smartlead.py` maps a subset by name.

5. **Lead score 0–7** is computed in `scraper.calcular_lead_score`:
   +1 each for phone, website, rating≥4.0, reviews≥20, verified, email,
   (instagram OR facebook OR linkedin). LinkedIn was added 2026-05-19.

6. **Enrichment uses a sidecar CSV pattern** — raw `dotco_leads_*.csv` stays
   the source of truth; `enrich.py` writes `dotco_leads_*_enriched.csv` with
   four added columns: `first_name_ai`, `personalized_opener`, `ai_qualified`,
   `ai_reject_reason`. Downstream tools auto-detect and use enriched columns
   if present.

7. **No new top-level dirs without reason.** The repo is flat. Keep it flat.

## Models in use

- `claude-haiku-4-5-20251001` — first_name inference, lead qualification.
- `claude-sonnet-4-6` — personalized opener generation (quality matters here).
- Prompts in `ai_prompts.py` are versioned (`_VERSION = "v2"`). Bump the
  version when editing a prompt — the suffix participates in the cache key.

## Cost reference (verified 2026-05-19)

| Feature | Model | $ per 10 leads |
|---|---|---|
| first_name | Haiku | $0.002 |
| opener | Sonnet | $0.010 |
| qualify | Haiku | $0.002 |
| **All three** | mixed | **~$0.014** |

≈ $1.40 per 1000 leads with everything on. ≈ $0.40 per 1000 leads if opener disabled.

## Common workflows

- **Run an interactive scrape:** `python main.py`
- **Run the smoke test (1 API call):** `python smoketest.py`
- **Enrich an existing CSV:** `python enrich.py resultados/<file>.csv [--features first_name,opener,qualify]`
- **Export to Smartlead:** `python export_smartlead.py resultados/<file>.csv [--min-score N] [--require-qualified]`
- **Regenerate city/state data:** `python build_data.py`

## Known issues (do not "fix" without asking)

- **Providence is listed under Massachusetts** in `build_data.US_CITIES` as
  well as under Rhode Island. The duplicate is in the JSON. Real Providence
  is in RI. Pre-existing, low-impact, not worth a quiet fix.
- **Two Alaskan cities under the tier floor** — Sitka (8.5k) and Ketchikan
  (8.2k) are below the `tiny_towns` 10k minimum, so they're invisible to
  the market-tier filter. Drop the floor to 5k if it matters.
- **Zero-leads run trips Smartlead export.** If a scrape returns 0 leads,
  no CSV is written, but `correr_scraping` still calls Smartlead export and
  it `ERROR: file not found`s. Add a guard if/when scrapes legitimately
  return zero.

## When the user says things

- "fix X" — they almost always mean *make the lead output better*, not *clean
  up the code*. Confirm interpretation if ambiguous.
- "test it" / "run it" — fine to spend 1–2 RapidAPI calls or a few cents of
  Claude. Anything bigger, confirm cost first.
- "debug" — assume they have an output problem (wrong data, missing column,
  weird score), not a crash. Run a smoke test before theorizing.

## Project memory location

`/Users/facundomontero/.claude/projects/-Users-facundomontero-Desktop-Proyect-file-Merch-Project-Dotco-Scraper-scraper-dotco/memory/`

Index: `MEMORY.md`. Key entries:
- `user-dotco-owner.md` — who the user is and what success looks like
- `project-dotco-strategy.md` — small-city targeting thesis + score formula
- `project-known-gotchas.md` — non-obvious bugs left in the repo
- `feedback-ai-optional.md` — AI must always be opt-in
- `feedback-direct-recommendations.md` — communication style
