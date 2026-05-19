# CLAUDE.md

Guidance for Claude Code sessions working in this repository.

## What this project is

DotCo Swag scraper — a B2B sales lead-generation tool, not a software project.
The user runs it to produce CSVs of US small businesses for a branded-merch
outreach campaign. Two interfaces ship today:

1. **CLI** (`python main.py`) — original interactive flow, runs locally.
2. **Telegram bot** (`python -m bot.app`) — webhook-based, deployed to Render
   free tier so the user can drive scrapes from their phone.

Every change should ultimately make leads *more reachable and higher quality*,
not the code prettier.

## Module map

### Core (CLI + bot share these)

| File | Purpose |
|---|---|
| `main.py` | Interactive CLI. Orchestrates scrape via prompts. Owns `CATEGORIAS`, `MERCADOS_RECOMENDADOS`, `RESULTADOS_DIR`. |
| `scraper.py` | RapidAPI client + dedup + CSV writer. `scrape_combinacion()` is the non-interactive primitive. `calcular_lead_score()` computes 0–7. |
| `build_data.py` | Generates `data/us_cities.json` (298 cities × 51 states). `CITY_POPS` is `(state, city) → population`. |
| `export.py` | CSV → styled XLSX (color-coded by lead score). `csv_to_xlsx()` is non-interactive. |
| `export_smartlead.py` | CSV → Smartlead-importable CSV. `export(csv, min_score, require_qualified)` is non-interactive. Reads AI columns when present. |
| `ai_client.py` | Anthropic SDK wrapper. `is_enabled()`, `call_with_retry()`, `QuotaExhausted` exception. |
| `ai_prompts.py` | Versioned system prompts for the 3 enrichment features (v2). Each prompt is cache-tagged. |
| `enrich.py` | AI enrichment orchestrator. Reads raw CSV, writes sidecar `_enriched.csv`. Non-interactive. CLI: `python enrich.py <csv>`. |
| `smoketest.py` | One-off — exercises the scrape pipeline on Boulder coffee shops. Cheap (1 API call). |
| `test_email_flag.py` | One-off probe — confirmed `extract_emails_and_contacts=true` works on RapidAPI. Safe to delete. |

### Telegram bot (`bot/` package)

| File | Purpose |
|---|---|
| `bot/app.py` | Entry point. Builds PTB `Application`, registers handlers, runs `run_webhook` on `$PORT`. |
| `bot/config.py` | Env config. `_required()` fail-fast for missing env vars. Owns timeouts/throttles. |
| `bot/job_manager.py` | Singleton `jobs` registry. One running job at a time per server. Cooldown per chat. `try_acquire` / `release` / `cancel`. |
| `bot/scrape_runner.py` | Background coroutine that iterates over `(city, category)` combos, calls `scraper.scrape_combinacion` via `run_in_executor`. |
| `bot/progress.py` | `ProgressBridge` — edits a single status message with a throttled progress bar (default 3s). |
| `bot/keyboards.py` | All inline keyboard builders (tier, state, cities, categories, min_score, features, yes/no). |
| `bot/cities.py` | Loads `data/us_cities.json` and presents tier/recommended filters to handlers. |
| `bot/handlers/start_help.py` | `/start`, `/help` — welcome + command list. |
| `bot/handlers/scrape_flow.py` | `/scrape` `ConversationHandler` — tier → state → cities → categories → limit → min_score → confirm. |
| `bot/handlers/enrich.py` | `/enrich` — opt-in AI flow with cost preview + explicit Yes/No. |
| `bot/handlers/export_cmds.py` | `/list`, `/export_smartlead`, `/export_excel`. |
| `bot/handlers/job_control.py` | `/status`, `/cancel`. |

### Files NOT to extend

- `mcp_server.py`, `mcp_server_hybrid.py` — both non-functional. Aspirational
  MCP wrappers from before the AI enrichment work. They hang on `input()`
  calls in `correr_scraping`, and the wire protocol isn't real MCP. Don't
  add features to these or invoke them.

## Hard invariants

1. **AI is strictly opt-in per run.** Every AI-touching prompt must default
   to `n` / no-button. Pipeline must work identically with
   `ANTHROPIC_API_KEY=` empty (the bot hides `/enrich` behind an
   `is_enabled()` check and replies with a setup hint when missing).
   See `feedback-ai-optional` memory.

2. **`extract_emails_and_contacts=true`** is required on every RapidAPI search
   call (`scraper.py:99-107`). Without it, `email`, `instagram`, `facebook`,
   `linkedin` columns are empty for every lead and `lead_score` caps at 5.

3. **`CITY_POPS` keys are `(state, city)` tuples**, not bare city names.
   Kills name-collision bugs (Jackson MS 145k vs Jackson WY 11k, Portland
   OR 631k vs Portland ME 68k, Springfield {IL/MA/MO}, etc.). Re-flattening
   reintroduces the bug.

4. **CSV column order is defined once** in `scraper.COLUMNAS_CSV`
   (scraper.py:29-69). `export.py` reads the CSV header dynamically;
   `export_smartlead.py` maps a subset by name. Don't duplicate the list.

5. **Lead score 0–7** in `scraper.calcular_lead_score`: +1 each for phone,
   website, rating≥4.0, reviews≥20, verified, email, (instagram OR facebook
   OR linkedin).

6. **Enrichment uses a sidecar CSV pattern** — raw `dotco_leads_*.csv` is
   the source of truth; `enrich.py` writes `dotco_leads_*_enriched.csv`
   with four added columns: `first_name_ai`, `personalized_opener`,
   `ai_qualified`, `ai_reject_reason`. Downstream tools auto-detect.

7. **The bot must never call `main.correr_scraping`.** That function is full
   of `input()` prompts and will hang on a server with no TTY. The bot uses
   `scraper.scrape_combinacion` directly in `bot/scrape_runner.py`. Same
   rule for any future server / web wrapper.

8. **One running job at a time.** `bot/job_manager.py` enforces this. Don't
   parallelize — RapidAPI rate limits already bit us today.

9. **No new top-level dirs without reason.** Repo is flat outside `bot/`,
   `data/`, `resultados/`. Keep it that way.

## Models in use

- `claude-haiku-4-5-20251001` — first_name inference, lead qualification.
- `claude-sonnet-4-6` — personalized opener generation.
- Prompts in `ai_prompts.py` are versioned (`_VERSION = "v2"`). Bump the
  version when editing a prompt — the suffix participates in the cache key.

## Cost reference (verified 2026-05-19)

| Feature | Model | $ per 10 leads |
|---|---|---|
| first_name | Haiku | $0.002 |
| opener | Sonnet | $0.010 |
| qualify | Haiku | $0.002 |
| **All three** | mixed | **~$0.014** |

≈ $1.40 per 1000 leads with everything on. ≈ $0.40 / 1000 if opener disabled.

## Env vars (full list)

Required:
- `RAPIDAPI_KEY` — `local-business-data` subscription key.
- `TELEGRAM_BOT_TOKEN` — from `@BotFather`. Bot won't start without it.
- `WEBHOOK_BASE_URL` — public HTTPS base, e.g. `https://dotco-telegram-bot.onrender.com`.

Optional:
- `ANTHROPIC_API_KEY` — enables `/enrich` and the CLI's AI prompt. Empty = AI off.
- `WEBHOOK_SECRET_TOKEN` — Telegram echoes it back so we can reject spoofed POSTs.
  Telegram allows only `A-Z a-z 0-9 _ -`; Render's `generateValue` can produce
  invalid chars on the first try — regenerate if so.
- `PORT` — Render injects automatically; local dev defaults to 10000.
- `RENDER_API_KEY` — used only for the manual redeploy curl (see below).

## Render deployment

- Service id: `srv-d86c128g4nts73b7gu8g` (`dotco-telegram-bot`, oregon, free plan).
- Owner: `tea-d86bc03eo5us73e69rd0` ("My Workspace", `dotcoswag@gmail.com`).
- Public URL: `https://dotco-telegram-bot.onrender.com`.
- Dashboard: `https://dashboard.render.com/web/srv-d86c128g4nts73b7gu8g`.
- GitHub repo: `https://github.com/dotcoswag/dotco-telegram-bot` (public).
- `render.yaml` is committed; mirrors the dashboard config.

### Manual redeploy after `git push`

The service was created via the Render API using a public git URL, **not via
the GitHub App OAuth flow**. Render has no webhook to receive push events, so
`autoDeploy: yes` doesn't fire on push. After every `git push`:

```bash
set -a && source .env && set +a
curl -X POST "https://api.render.com/v1/services/srv-d86c128g4nts73b7gu8g/deploys" \
  -H "Authorization: Bearer $RENDER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"clearCache":"do_not_clear"}'
```

To fix permanently: install Render's GitHub App on the repo via the Render
dashboard (interactive OAuth). See the `project-render-deployment` memory.

### Free tier caveats

- Service sleeps after ~15 min idle; first message after sleep has a 30–60s
  cold start. Acceptable for occasional B2B use.
- Disk is ephemeral — `resultados/*.csv` is lost on redeploy / restart. The
  bot uploads every produced CSV to Telegram chat immediately, which serves
  as the persistent store.
- Wall-clock per request is short, but `run_webhook` keeps a long-lived
  process so long scrapes (minutes) are fine; the work runs in a
  background task in `bot/scrape_runner.py`.

## Common workflows

### CLI

- Interactive scrape: `python main.py`
- Smoke test (1 API call): `python smoketest.py`
- Enrich existing CSV: `python enrich.py resultados/<file>.csv [--features ...]`
- Smartlead export: `python export_smartlead.py resultados/<file>.csv [--min-score N] [--require-qualified]`
- Regenerate cities: `python build_data.py`

### Bot

- Local dev: ngrok HTTPS tunnel → `WEBHOOK_BASE_URL=<ngrok-url>` in `.env`
  → `python -m bot.app`. Telegram POSTs land in the local process.
- Production: `git push` to GitHub → run the redeploy curl above → watch
  logs via `https://dashboard.render.com/web/srv-d86c128g4nts73b7gu8g`.
- Commands the bot exposes:
  `/start`, `/help`, `/scrape`, `/enrich`, `/export_smartlead`,
  `/export_excel`, `/list`, `/status`, `/cancel`.

## Known issues (do not "fix" without asking)

- **Providence under Massachusetts** in `build_data.US_CITIES` (it's actually
  in Rhode Island, and also correctly listed there). Pre-existing duplicate,
  low impact.
- **Sitka & Ketchikan below the tier floor** — pop 8.5k / 8.2k are under the
  `tiny_towns` 10k minimum, so they're invisible to market-tier filters.
- **Zero-leads run trips CLI Smartlead export.** If a scrape returns 0
  leads, no CSV is written, but `correr_scraping` still calls the Smartlead
  export and it errors `file not found`. The bot doesn't have this bug
  because Smartlead export there is a separate `/export_smartlead` command.
- **`/cancel` mid-combo** can't interrupt the current RapidAPI call (it's
  running in a thread executor and can't be killed cleanly). The cancel
  takes effect at the next combo boundary; the partial CSV is sent.

## When the user says things

- "fix X" — they almost always mean *make the lead output better*, not
  *clean up the code*. Confirm interpretation if ambiguous.
- "test it" / "run it" — fine to spend 1–2 RapidAPI calls or a few cents of
  Claude. Anything bigger, confirm cost first.
- "debug" — assume they have an output problem (wrong data, missing column,
  weird score), not a crash. Run a smoke test before theorizing.
- "push the latest code" / "why isn't my change live on the bot" — the
  answer is almost always *the deploy needs to be triggered manually* via
  the curl above. Render doesn't auto-pull from this repo.

## Project memory location

`/Users/facundomontero/.claude/projects/-Users-facundomontero-Desktop-Proyect-file-Merch-Project-Dotco-Scraper-scraper-dotco/memory/`

Index: `MEMORY.md`. Key entries:
- `user-dotco-owner.md` — who the user is and what success looks like
- `project-dotco-strategy.md` — small-city targeting thesis + score formula
- `project-known-gotchas.md` — non-obvious bugs left in the repo
- `project-render-deployment.md` — Render service ids + manual redeploy procedure
- `feedback-ai-optional.md` — AI must always be opt-in
- `feedback-direct-recommendations.md` — communication style
