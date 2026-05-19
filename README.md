# DotCo Swag — Lead Scraper

A Python tool that finds US small businesses on Google Maps, scores them as
B2B leads for branded-merchandise outreach, and exports a CSV ready to
import into Smartlead. Optional Claude AI layer recovers first names from
emails, writes personalized cold-email openers, and filters out chains.

Two ways to drive it:

- **CLI** — `python main.py`. Interactive prompts, runs locally.
- **Telegram bot** — `python -m bot.app`. Webhook-based, deployed to Render
  free tier; the same scrape flow as the CLI but operated from chat.

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
owner-operated businesses where the owner reads their own email**. Both
interfaces let you filter by tier (`tiny_towns`, `sweet_spot`, `mid_large`,
`major_metros`) so you can chase that conversion lever.

---

## Setup

### Requirements

- Python 3.10+ (tested on 3.13 locally, 3.11 on Render).
- A RapidAPI account subscribed to **local-business-data**
  (https://rapidapi.com/letscrape-6bRBa3QguO5/api/local-business-data).
- A Telegram bot token from `@BotFather` (only for the bot, not the CLI).
- *(Optional)* An Anthropic API key — only needed for AI enrichment.

### Install

```bash
git clone <this repo>
cd scraper_dotco
pip install -r requirements.txt
```

### Configure environment

Copy `.env.example` to `.env` and fill in:

```env
# Required for the scraper
RAPIDAPI_KEY=your-rapidapi-key-here

# Required for the Telegram bot (skip for CLI-only use)
TELEGRAM_BOT_TOKEN=123456:ABC-DEF_from_botfather
WEBHOOK_BASE_URL=https://your-service.onrender.com
WEBHOOK_SECRET_TOKEN=random_string_a-zA-Z0-9_-_only
PORT=10000

# Optional. Leave empty to disable all AI features.
ANTHROPIC_API_KEY=sk-ant-...

# Only used by the manual redeploy curl (see "Deploying to Render")
RENDER_API_KEY=
```

### Generate the city dataset

The included `data/us_cities.json` ships with 298 cities and real 2023
populations. To regenerate from scratch (after editing `build_data.py`):

```bash
python build_data.py
```

---

## CLI (`python main.py`)

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
6. **Confirm** — preview the plan (API calls, cities, categories), then start.

While running you'll see a live progress bar with ETA. The CSV is written
incrementally to `resultados/dotco_leads_YYYYMMDD_HHMMSS.csv` and a sidecar
`.checkpoint.json` enables resume if the run is interrupted.

After the scrape finishes the CLI offers (in order):

- **Export to XLSX?** Color-coded, frozen header, lead-score-tinted cells.
- **Enrich leads with AI?** (only shown if `ANTHROPIC_API_KEY` is set)
  Defaults to `n`. If you opt in, pick which AI features to run, see an
  estimated cost, and confirm before any spend.
- **Export to Smartlead CSV?** Drops rows without email; optional minimum
  lead score; optional drop-disqualified flag if AI ran.

---

## Telegram bot

The bot wraps the same scraper behind a `/scrape` conversation. It uses
webhooks (not long-polling) — your `WEBHOOK_BASE_URL` must be reachable
over HTTPS by Telegram's servers.

### Commands

| Command | What it does |
|---|---|
| `/start` or `/help` | Welcome + command list |
| `/scrape` | Guided scrape: tier → state(s)/cities → categories → limit → min_score → confirm. Streams a progress bar and uploads the CSV when done. |
| `/enrich` | Run AI enrichment on the last produced CSV. Pick features, see estimated cost, then explicit Yes/No. |
| `/export_smartlead` | Build a Smartlead CSV from the last scrape with a min-score filter |
| `/export_excel` | Convert the last CSV to a styled XLSX |
| `/list` | List recent files on the server (max 25). Marks the current target of `/enrich` and `/export_*`. |
| `/status` | Show running job (elapsed, last progress line) |
| `/cancel` | Request cancellation; the job stops at the next combo boundary and sends the partial CSV |

Defaults are tuned so a typical scrape takes ≤8 taps. The `/scrape`
conversation accepts inline-keyboard answers for everything; no typing of
city names or numbers (except free-form limits in some flows).

### Local development

You need an HTTPS tunnel so Telegram can POST to your laptop. With ngrok:

```bash
ngrok http 10000
# Copy the https URL into .env as WEBHOOK_BASE_URL, then:
python -m bot.app
```

The bot will set its webhook to `{WEBHOOK_BASE_URL}/{TELEGRAM_BOT_TOKEN}`
on boot and start serving updates.

### Deploying to Render

The repo ships a `render.yaml` that mirrors the production service config
(plan: free, region: oregon, env: python). The actual deploy was bootstrapped
via the Render API, **not** the GitHub OAuth app, so push-to-deploy is OFF.
After every `git push`, manually trigger a redeploy:

```bash
set -a && source .env && set +a
curl -X POST "https://api.render.com/v1/services/srv-d86c128g4nts73b7gu8g/deploys" \
  -H "Authorization: Bearer $RENDER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"clearCache":"do_not_clear"}'
```

(You can replace this with auto-deploy permanently by installing the Render
GitHub App on the repo from the Render dashboard.)

### Free tier caveats

- **Sleep & cold start.** The service sleeps after ~15 min of inactivity.
  First message after sleep takes 30–60s while the container boots.
  Acceptable for occasional B2B use.
- **Ephemeral disk.** `resultados/*.csv` is lost on redeploy or restart.
  The bot uploads every produced CSV to your Telegram chat immediately,
  so Telegram itself is your persistent store. `/list` only sees files
  produced in the current container's lifetime.
- **Long scrapes are fine.** The webhook process is long-running; scrapes
  execute in a background asyncio task and stream a progress bar back via
  message edits (throttled to one edit every 3 s to respect Telegram's
  rate limit).

---

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

**Scores 6–7 are the realistic top tier** (must have email + some social).
5 is solid. 4 is workable but needs enrichment to be useful.

---

## AI enrichment (optional)

### What it adds

| Column | Source | Why it matters |
|---|---|---|
| `first_name_ai` | Email local-part | `Hi {{first_name}}` in Smartlead becomes `Hi Melissa` instead of `Hi Team`. |
| `personalized_opener` | Business name, type, rating, reviews, category | A custom Smartlead variable; first sentence of the cold email, specific to each business. |
| `ai_qualified` / `ai_reject_reason` | Whole business profile | Drops Starbucks-like chains and mis-classified results that slip past the numeric score. |

### Models and cost (verified)

- **first_name** — Claude Haiku 4.5
- **opener** — Claude Sonnet 4.6 (quality matters)
- **qualify** — Claude Haiku 4.5

Sample of 10 leads with all three features: **~$0.014**, or roughly
**$1.40 per 1000 leads**. Disable the opener and it drops to ~$0.40 / 1000.

### Running enrichment

**From the CLI:** opt in at the prompt that appears after the scrape.

**From the bot:** `/enrich`. Picks the last scrape automatically. You'll
multi-select features via inline buttons, see the estimated cost, and
explicitly confirm before any spend.

**Standalone on any historical CSV:**

```bash
python enrich.py resultados/dotco_leads_20260519_150946.csv
python enrich.py resultados/dotco_leads_20260519_150946.csv --features first_name,qualify
```

### Failure modes (intentional)

- `ANTHROPIC_API_KEY` missing or empty → the CLI prompt never appears; the
  bot's `/enrich` responds with a setup hint and does nothing.
- User declines the prompt → no spend, no change.
- Quota / auth fails mid-run → enrichment stops, remaining rows get blank
  AI columns, the Smartlead export still produces a valid CSV using the
  `"Team"` fallback for `first_name`.

---

## Smartlead export

```bash
python export_smartlead.py resultados/dotco_leads_*.csv
python export_smartlead.py resultados/dotco_leads_*_enriched.csv --min-score 5 --require-qualified
```

Or from the bot: `/export_smartlead`, then pick a min-score via buttons.

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

Only rows with a non-empty email are exported.

---

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
├── bot/                    # Telegram bot package
│   ├── app.py              # PTB Application + run_webhook entry
│   ├── config.py           # env config, timeouts, throttles
│   ├── job_manager.py      # single-job-at-a-time registry + cooldown
│   ├── scrape_runner.py    # background coroutine over (city,category) combos
│   ├── progress.py         # ProgressBridge — throttled status-message edits
│   ├── keyboards.py        # inline-keyboard builders
│   ├── cities.py           # tier/recommended lookups from us_cities.json
│   └── handlers/
│       ├── start_help.py   # /start, /help
│       ├── scrape_flow.py  # /scrape ConversationHandler
│       ├── enrich.py       # /enrich (opt-in AI flow)
│       ├── export_cmds.py  # /list, /export_smartlead, /export_excel
│       └── job_control.py  # /status, /cancel
├── data/
│   └── us_cities.json      # 298 cities × 51 states with populations
├── resultados/             # CSV outputs (gitignored; ephemeral on Render)
├── render.yaml             # Render service config (mirrors dashboard)
├── requirements.txt
├── .env                    # secrets — gitignored
├── .env.example            # template for env vars
├── .gitignore
├── README.md
└── CLAUDE.md               # guidance for AI coding agents
```

---

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

---

## Resuming an interrupted CLI run

Each CLI scrape writes a `<csv-file>.checkpoint.json` next to its CSV. If
you abort mid-run (Ctrl+C or crash) and re-run `python main.py`, the CLI
detects the checkpoint and asks whether to resume. On clean completion the
checkpoint file is deleted.

The bot does not currently support resume — a `/cancel` mid-run sends the
partial CSV and ends the job.

---

## Known limitations

- The market-tier filter relies on populations in `data/us_cities.json`. The
  curated dataset covers 298 cities; smaller towns aren't in it. To add
  cities, edit `build_data.US_CITIES` and `build_data.CITY_POPS`, then run
  `python build_data.py`.
- Sitka and Ketchikan (AK) sit below the `tiny_towns` 10k floor — they're in
  the data but never selected by the tier filter.
- Providence is listed under both Massachusetts (where it doesn't belong)
  and Rhode Island in `US_CITIES`. Harmless duplicate.
- `mcp_server.py` and `mcp_server_hybrid.py` are leftover experiments
  toward an MCP wrapper — they don't run. Ignore them.
- Render free tier: 30–60s cold start after ~15 min idle; ephemeral disk
  loses files between deploys.
- `/cancel` on the bot can't kill the current RapidAPI call mid-flight; it
  takes effect at the next `(city × category)` boundary.

---

## Costs you might incur

- **RapidAPI** — pay per call, free tier limited. Requests with
  `extract_emails_and_contacts=true` (always on; required) cost more credits
  per response than a plain search. Watch your dashboard.
- **Anthropic** — only if you opt into AI enrichment. ~$1.40 per 1000 leads
  with all three features on. Estimated cost is shown before any AI spend.
- **Render** — free tier is free. Upgrading to a paid plan (`Starter`,
  ~$7/mo) removes the cold-start sleep and adds a persistent disk if you
  want `/list` to survive restarts.

---

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
