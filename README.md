# DotCo Swag — Lead Scraper

A Python tool that finds US small businesses on Google Maps, scores them as
B2B leads for branded-merchandise outreach, and exports a CSV ready to
import into Smartlead. Optional Claude AI layer recovers first names from
emails, writes personalized cold-email openers, and filters out chains.

## What it does

1. **Scrape** — queries the RapidAPI `local-business-data` endpoint for a
   chosen mix of US cities × business categories.
2. **Score** — each business gets a `lead_score` from 0 to 7 based on contact
   completeness (phone, website, email, social, rating, reviews, verified).
3. **Enrich (optional)** — Claude AI adds:
   - `first_name_ai` — inferred from email local-part (`melissa@x.com` → "Melissa")
   - `personalized_opener` — 1–2 sentence cold-email opener per lead
   - `ai_qualified` + `ai_reject_reason` — flags chains, closed businesses, mis-categorized results
4. **Export** — CSV (always), styled XLSX (optional), Smartlead-ready CSV
   (optional, with custom variables for the opener).

The targeting thesis: **smaller cities (10k–250k population) yield
owner-operated businesses where the owner reads their own email**. The CLI
lets you filter by tier (`tiny_towns`, `sweet_spot`, `mid_large`,
`major_metros`) so you can chase that conversion lever.

## Setup

### Requirements

- Python 3.10+ (tested on 3.13)
- A RapidAPI account subscribed to **local-business-data**
  (https://rapidapi.com/letscrape-6bRBa3QguO5/api/local-business-data)
- *(Optional)* An Anthropic API key — only needed for AI enrichment

### Install

```bash
git clone <this repo>
cd scraper_dotco
pip install -r requirements.txt
```

### Configure environment

Create `.env` in the project root:

```env
RAPIDAPI_KEY=your-rapidapi-key-here

# Optional. Leave empty to disable all AI features.
ANTHROPIC_API_KEY=sk-ant-...
```

### Generate the city dataset

The included `data/us_cities.json` ships with 298 cities and real 2023
populations. To regenerate from scratch (if you edit `build_data.py`):

```bash
python build_data.py
```

## Quick start

```bash
python main.py
```

The CLI walks you through six steps:

1. **Target market size** — tiny towns / sweet spot / mid-large / metros /
   all / pre-curated recommended markets.
2. **Geographic scope** — all US, specific states, or pick individual cities.
3. **Business categories** — pick one or more of ten groups
   (Smoke & Cannabis, Gyms & Fitness, Restaurants & Bars, Barbershops &
   Salons, Real Estate, Auto, Construction & Trades, Corporate & Coworking,
   Schools & Sports, Medical & Dental). Each group has 4–10 search terms.
4. **Result limit** — total leads cap, or unlimited.
5. **Min lead score** — drop leads below this score (0–7).
6. **Confirm** — preview the plan (number of API calls, cities sample,
   categories sample), then start the scrape.

While running you'll see a live progress bar with ETA. The CSV is written
incrementally to `resultados/dotco_leads_YYYYMMDD_HHMMSS.csv` and a sidecar
`.checkpoint.json` enables resume if the run is interrupted.

After the scrape finishes:

- **Export to XLSX?** Color-coded, frozen header, lead-score-tinted cells.
- **Enrich leads with AI?** (only shown if `ANTHROPIC_API_KEY` is set)
  Defaults to `n`. If you opt in, you'll pick which of the three AI
  features to run, see an estimated cost, and confirm before any spend.
- **Export to Smartlead CSV?** Drops rows without email; optional minimum
  lead score; optional drop-disqualified flag if AI ran.

## The lead score

Each business earns up to 7 points:

| +1 if | Notes |
|---|---|
| has phone | most coffee shops do |
| has website | filters out ghost listings |
| rating ≥ 4.0 | quality signal |
| reviews ≥ 20 | traction signal |
| `verified` | Google Business claimed |
| has email | the make-or-break field for outreach |
| has Instagram, Facebook, *or* LinkedIn | reachability fallback |

For outreach, **scores 6–7 are the realistic top tier** (must have email and
some social). 5 is solid. 4 is workable but needs enrichment to be useful.

## AI enrichment (optional)

### What it adds

| Column | Source | Why it matters |
|---|---|---|
| `first_name_ai` | Email local-part | `Hi {{first_name}}` in Smartlead becomes `Hi Melissa` instead of `Hi Team`. |
| `personalized_opener` | Business name, type, rating, reviews, category | A custom Smartlead variable; first sentence of the cold email, specific to each business. |
| `ai_qualified` / `ai_reject_reason` | Whole business profile | Drops Starbucks-like chains and mis-classified results that slip past the numeric score. |

### Models and cost

- **first_name** — Claude Haiku 4.5
- **opener** — Claude Sonnet 4.6 (quality matters)
- **qualify** — Claude Haiku 4.5

Verified cost on a 10-lead sample: **~$0.014 with all three features on**,
or roughly **$1.40 per 1000 leads**. Disable the opener and it drops to
~$0.40 / 1000 leads.

### Running enrichment

In `main.py` you'll be prompted after the scrape finishes. Two opt-out
points: an initial `y/n` (default `n`) and an explicit spend confirmation
showing the estimated cost.

Or run standalone on any historical CSV:

```bash
python enrich.py resultados/dotco_leads_20260519_150946.csv
python enrich.py resultados/dotco_leads_20260519_150946.csv --features first_name,qualify
```

### Failure modes (intentional)

- `ANTHROPIC_API_KEY` missing or empty → the AI prompt never appears; the
  rest of the pipeline runs unchanged.
- User declines the prompt → no spend, no change.
- Quota / auth fails mid-run → enrichment stops, remaining rows get blank
  AI columns, the Smartlead export still produces a valid CSV using the
  `"Team"` fallback for `first_name`.

## Smartlead export

```bash
python export_smartlead.py resultados/dotco_leads_*.csv
python export_smartlead.py resultados/dotco_leads_*_enriched.csv --min-score 5 --require-qualified
```

Output columns:

```
email, first_name, last_name, company_name, phone_number, website,
linkedin_profile, location[, personalized_opener]
```

`personalized_opener` is appended only if the input CSV has it (i.e., it
was enriched). `first_name` uses `first_name_ai` when present, otherwise
falls back to `"Team"` so templates like `Hi {{first_name}}` produce
`Hi Team`.

Filters:

- `--min-score N` — drop rows with `lead_score < N`
- `--require-qualified` — drop rows where AI flagged `ai_qualified=false`
  (silently disabled if the input isn't enriched)

Only rows with a non-empty email are exported. Smartlead can't do anything
without one.

## File layout

```
scraper_dotco/
├── main.py                 # interactive CLI entry point
├── scraper.py              # RapidAPI client, scoring, CSV writer
├── enrich.py               # AI enrichment orchestrator + CLI
├── export.py               # CSV → XLSX
├── export_smartlead.py     # CSV → Smartlead CSV
├── build_data.py           # regenerates data/us_cities.json
├── ai_client.py            # Anthropic SDK wrapper, retry, quota detection
├── ai_prompts.py           # versioned system prompts (cache-tagged)
├── smoketest.py            # 1-API-call sanity check
├── data/
│   └── us_cities.json      # 298 cities × 51 states with populations
├── resultados/             # CSV outputs land here (gitignored typically)
├── requirements.txt
├── .env                    # RAPIDAPI_KEY + (optional) ANTHROPIC_API_KEY
├── README.md
└── CLAUDE.md               # guidance for AI coding agents
```

## Output CSV columns

Defined in `scraper.COLUMNAS_CSV` and grouped as:

- **Identity** — `business_id`, `nombre`, `tipo`, `subtipo`
- **Quality** — `rating`, `review_count`, `verified`, `business_status`,
  `lead_score`, `photos_count`
- **Location** — `direccion`, `city`, `state`, `district`, `latitude`, `longitude`
- **Contact** — `telefono`, `email`, `website`
- **Social** — `instagram`, `facebook`, `linkedin`, `twitter`, `youtube`,
  `emails_extra`
- **Links** — `link_google_maps`, `booking_link`, `menu_link`, `order_link`
- **Search metadata** — `localidad_buscada`, `categoria_buscada`, `provincia`

If enriched, four more columns are appended in the sidecar `_enriched.csv`:
`first_name_ai`, `personalized_opener`, `ai_qualified`, `ai_reject_reason`.

## Resuming an interrupted run

Each scrape writes a `<csv-file>.checkpoint.json` next to its CSV. If you
abort mid-run (Ctrl+C or crash) and re-run `python main.py`, the CLI will
detect the checkpoint and ask whether to resume. On clean completion the
checkpoint file is deleted.

## Known limitations

- The market-tier filter relies on populations in `data/us_cities.json`. The
  curated dataset covers 298 cities; smaller towns aren't in it. To add
  cities, edit `build_data.US_CITIES` and `build_data.CITY_POPS`, then run
  `python build_data.py`.
- Sitka and Ketchikan (AK) sit below the `tiny_towns` 10k floor — they're
  in the data but never selected by the tier filter.
- Providence is listed under both Massachusetts (where it doesn't belong)
  and Rhode Island in `US_CITIES`. Mostly harmless duplicate.
- `mcp_server.py` and `mcp_server_hybrid.py` are leftover experiments
  toward an MCP wrapper — they don't run. Ignore them.

## Costs you might incur

- **RapidAPI** — pay per call, free tier limited. A scrape with the
  `extract_emails_and_contacts=true` flag (which is on by default and required)
  costs more credits per response than a plain search. Watch your dashboard.
- **Anthropic** — only if you opt into AI enrichment. ~$1.40 per 1000 leads
  with all three features on (see cost table above).
- Each run shows an estimated cost before any AI spend.

## Cold-email next step

After exporting to Smartlead, set up your template with `{{first_name}}`
and the custom variable `{{personalized_opener}}`:

```
Subject: Quick question about staff merch

{{personalized_opener}}

Curious how you currently handle branded gear for the team — we work
with shops like yours and could put together a few options if you're open
to a quick look.

— DotCo Swag
```

The first line will be specific to each lead; the rest is your template.
