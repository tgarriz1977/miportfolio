# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A self-hosted stock portfolio dashboard. Flask backend (`app.py` plus three helper modules) serves a single static frontend page (`index.html`, Bootstrap 5 dark mode + Chart.js) and four JSON endpoints. Holdings live in a SQLite database; prices, news and earnings come from Yahoo Finance via `yfinance`; an optional LLM writes the per-ticker summary and an optional YouTube key fills the videos section. There is no build step and no JS/CSS framework tooling — `index.html` is a plain file with inline `<script>`/`<style>`. UI copy and user-facing error strings are in Rioplatense Spanish; code, comments and docs are in English.

## Running locally

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
PORTFOLIO_DB=data/portfolio.db python3 app.py
```

Serves on `http://localhost:5050` by default. `DB_PATH` comes from `PORTFOLIO_DB` and defaults to `/data/portfolio.db` (the container path), so a local run without Docker must override it or symlink `data/` to `/data`.

Via Docker Compose (mounts `./data` to `/data`, reads `.env` for the optional keys):

```bash
docker compose up -d
```

`Dockerfile` copies app files by name (`COPY app.py sources.py llm.py youtube.py index.html ./`). A new module has to be added to that line or the image builds fine and only fails at container start.

## Tests

```bash
pip install -r requirements-dev.txt
pytest                      # everything
pytest -m "not network"     # offline; this is the default one to run
pytest tests/test_youtube.py::test_allowlist_drops_other_channels   # one test
```

There is no linter or formatter configured.

`pytest.ini` defines one marker, `network`, for the tests in `tests/test_sources.py` that really call Yahoo Finance — they check that fetchers degrade to empty results on symbols with no coverage, and that payloads survive `jsonify` (pandas emits `NaN`, which is not JSON-serializable). Everything else is offline and deterministic: route tests use the `client` fixture and a fake LLM provider, so no credentials are needed.

`tests/conftest.py` provides `app_module` and `client`. The `app_module` fixture monkeypatches `app.DB_PATH` to a `tmp_path` SQLite and runs `ensure_schema()` — never point tests at `data/portfolio.db`. Note the fixture creates `holdings`/`prices` with the *old* column set on purpose and lets `ensure_schema()` migrate them, which is what keeps the migration path covered.

## Configuration

Everything optional is environment-driven; with nothing set the dashboard still works and only the affected panel section reports what is missing. `.env` is gitignored and `.env.example` documents every variable with the reasoning behind the defaults — read it before changing provider settings.

- `LLM_PROVIDER` (`anthropic` | `openai_compat`), `LLM_MODEL`, `LLM_BASE_URL`, `LLM_API_KEY`, `INSIGHT_TTL_HOURS`
- `YOUTUBE_API_KEY`, `YOUTUBE_CHANNELS`, `YOUTUBE_MAX_RESULTS`, `YOUTUBE_DAYS`

## Architecture

### `app.py` — routes, DB access, price refresh

- `YF_TICKER_MAP` / `resolve_yf_symbol()` — the **price** symbol map, and it only covers non-CEDEAR holdings. CEDEARs are resolved dynamically to `<ticker>.BA` because they trade on BYMA in ARS: a CEDEAR and the direct US holding of the same ticker are different instruments in different currencies (AMD is held both ways, at different brokers) and cannot share a map entry. A new *direct* holding must be added to `YF_TICKER_MAP` or its price never refreshes; a new CEDEAR needs nothing.
- `ensure_schema()` — additive, idempotent, runs on every startup. Adds `prices.is_cedear` and `holdings.is_adr` if absent, creates the `insights`/`earnings`/`videos` cache tables, and **re-derives `holdings.is_adr` from `sources.ADR_MAP` every time** (clearing first, so dropping a mapping unmarks the holding). Never edit `is_adr` by hand.
- `get_holdings()` — joins `holdings` against the latest `prices` row per **`(ticker, is_cedear)` pair**, via a `MAX(recorded_at)` subquery. There is no `latest_price` column, and keying on ticker alone would cross the CEDEAR and direct prices of the same ticker.
- `refresh_prices(pairs)` — bulk-fetches all symbols in one `yf.download()` (fast path); on any exception it falls back to per-symbol `yf.Ticker(...).fast_info`. Appends one new row per pair into `prices` — that table is append-only history, never upserted. Currency is inferred from the symbol: `.BA` → ARS, else USD.
- `holding_currency()` — falls back to the ticker's mapped symbol when no price row exists yet. Defaulting to USD there would silently turn ALUA into a US stock.
- `fetch_extended_hours()` — premarket **and** after-hours in one function, because Yahoo's `marketState` is a single value and the two sessions can never both apply. `PRE` reads the `preMarket*` fields, `POST`/`POSTPOST` the `postMarket*` ones; anything else shows nothing. `POSTPOST` is included on purpose so the last after-hours print stays visible overnight, and `EXTENDED_HOURS_MAX_AGE` (12h) is what stops Friday's quote from still being on screen on Saturday — a timestamp check, not a weekday check, so it needs no assumption about what `marketState` Yahoo reports on a holiday. CEDEARs get the percentage but never the price: the underlying trades in USD and that figure under an ARS holding reads as a currency error. Crypto and BYMA-only holdings are skipped. Costs one `yf.Ticker().info` call per symbol, so it runs on `/api/portfolio` only, never in the 10-second `/api/prices` loop.
- `earnings_symbols()` — the portfolio's holdings collapsed to one entry per company symbol (skipping crypto), preferring the holding whose ticker *is* the symbol so PAM/PAMP displays as "PAM". `company_for_symbol()` reuses it so the collapsing rule lives in exactly one place.

### `sources.py` — Yahoo data for news, earnings and fundamentals

- `COMPANY_ALIASES` is the *other* ticker map and the one that's easy to confuse with `YF_TICKER_MAP`. `YF_TICKER_MAP` is about **prices**, where two listings are different instruments in different currencies; `COMPANY_ALIASES` is about **earnings and news**, where they are one company filing one balance. Yahoo answers for each listing with the same date (PAM and PAMP.BA both report 2026-08-04, quoting EPS in USD and ARS respectively), so without it one balance reads as two rows. It is built from two maps kept apart on purpose: `ADR_MAP` (BYMA ticker → US ADR) also drives `holdings.is_adr`, while `SHARE_CLASS_MAP` (GOOGL → GOOG) must not — GOOG is not an ADR. Adding an alias is one line in whichever map fits.
- `resolve_insight_symbol()` deliberately inverts `resolve_yf_symbol()`: for news and earnings a CEDEAR resolves to the bare US ticker, not `<ticker>.BA`. It checks the aliases **before** the `is_cedear` branch — reordering these breaks the GOOGL CEDEAR, which would short-circuit to its bare ticker and never collapse onto GOOG.
- Every fetcher swallows its own exceptions and returns an empty/`None` result. Coverage across this portfolio is genuinely uneven (ALUA.BA has no news, BTC-USD has no income statement), so one dead source must not abort the request. `_clean_number()` exists because pandas `NaN` breaks `jsonify`.

### `llm.py` — pluggable provider for the insight summary

Two adapters cover every target: the Anthropic SDK, and one generic OpenAI-compatible HTTP client that serves Ollama, LM Studio, vLLM, OpenAI and Gemini's compatibility endpoint (hence no separate Gemini adapter). Retrieval happens in `sources.py`, never through a provider's server-side web search — that is what keeps the layer interchangeable, since a local model has no such tool. There is **no default provider**: unset config raises `ProviderNotConfigured` and the route degrades rather than guessing.

`SYSTEM_PROMPT` forbids buy/sell/hold recommendations and price targets. If a summary ever gives one, the fix goes in `SYSTEM_PROMPT`, not in the UI.

### `youtube.py` — the "Videos" section

Standard library only, shaped like `llm.py`. The quota is what shaped it: `search.list` costs 100 of the 10,000 free daily units, so filtering by channel through the API (one call per channel) would allow about a dozen lookups a day. There is exactly one search per symbol and the `YOUTUBE_CHANNELS` allowlist is applied to the results locally. **Expect the section to be empty often — that is the design, not a bug**, since a whitelisted channel isn't guaranteed to land in the top 50 of a general search. Handles (`@Bloomberg`) are accepted alongside raw channel IDs and cached per process.

### Routes

- `GET /` — serves `index.html` as a static file; there's no templating engine.
- `GET /api/portfolio` — refreshes prices first by default (`?refresh=true`), so every dashboard load hits Yahoo for every holding; `?refresh=false` reads cached prices only. Groups holdings by broker. **Totals are kept per currency and never summed across them** — adding an ARS balance to a USD one produces a number that isn't real money. The response's `pie` array (aggregated by `(ticker, is_cedear)`) is legacy: the frontend now builds its pies client-side from `brokers[*].holdings` and ignores that field.
- `GET /api/refresh` — force-refreshes every `(ticker, is_cedear)` pair actually held, ignoring the cache.
- `GET /api/insight/<ticker>` — news, earnings, fundamentals and videos for one holding, plus the model's summary. `is_cedear`/`is_crypto`/`currency` come in as query params because the frontend already knows them, and they decide which company the ticker refers to. Cached in `insights` on an `INSIGHT_TTL_HOURS` TTL. On a missing (503) or failing (502) provider it **still returns the gathered data**, so the panel shows news and balances without a working model.
  - **Videos never enter the LLM prompt.** `api_insight()` keeps them out of the dict passed to `llm.build_insight_prompt` on purpose: a model cannot watch a video, so it would receive only titles and assert things about content nobody saw. If you add a source, decide which side of that line it falls on.
- `GET /api/earnings` — upcoming earnings dates, nearest first, `limit=5` by default. Cached per **local calendar day** (`fetched_on = date('now','localtime')`), not on an hours TTL — UTC would roll the cache over at 21:00 Argentine time. Symbols with nothing scheduled are cached as JSON `null` rather than skipped, so the ones Yahoo doesn't cover aren't re-fetched on every page load. `limit` only trims the response; every symbol is fetched regardless, since which are nearest isn't known until all have answered. Dates already in the past are dropped — Yahoo sometimes serves a date it hasn't rolled forward.

### `index.html` — single-page frontend

`loadData()` fetches `/api/portfolio?refresh=true` on load and `render()` redraws summary cards, the pie, the detail panel and per-broker tables. "Actualizar precios" calls `/api/refresh` then reloads.

- `CATEGORIES` splits every holding into exactly one **mono-currency** bucket (CEDEARs / Acciones USA / Acciones BA / Crypto), one pie per tab. This is why there's no single combined pie: ARS and USD slices on one nominal scale aren't comparable.
- `tradingViewSymbol(h)` is derived from the holding's flags, **never from the ticker string alone** — same CEDEAR-vs-underlying distinction as `resolve_yf_symbol()`.
- Anything from an external source goes through `escapeHtml()` before reaching `innerHTML`.

### Database

Schema is documented in `README.md` and materialized in `data/portfolio_dump.sql`. Restore/seed with `sqlite3 data/portfolio.db < data/portfolio_dump.sql`. Points not obvious from the code:

- `holdings` has a **composite primary key** `(ticker, broker)` — the same ticker can be held at multiple brokers (directly at one, as a CEDEAR at another) with independent share counts.
- `prices` has no uniqueness constraint; every refresh appends. `get_holdings()` picks the most recent row per `(ticker, is_cedear)`.
- `insights`, `earnings` and `videos` are caches created by `ensure_schema()`, all keyed by resolved company symbol. `earnings` and `videos` expire per local day; `insights` on a TTL.

## Notes

- `data/portfolio.db` is tracked in git (it's the live data store for this personal deployment), so a price refresh dirties the working tree. `dump_db.py` (helper for regenerating `portfolio_dump.sql`) is gitignored.
- `.env` holds real API keys and is gitignored. Yahoo Finance itself is still fetched anonymously.
- **Deploying a change needs `docker compose up -d --build`.** Without `--build`, Compose reuses the existing image and the container keeps running the old `app.py`/`index.html` — the code looks correct in the repo while the dashboard silently serves the previous version. Symptom: a new endpoint 404s and new fields are missing from `/api/portfolio`.
- Google retires model names without notice and the error arrives as **HTTP 429 "quota exceeded"** — the retirement message is buried further in the body. If you see a 429 with a valid key, read the full response before assuming it's a quota problem.
- Design docs for each feature live in `docs/plans/`, with the corresponding implementation plans in `docs/superpowers/plans/`. Worth reading before reworking a feature — they record the trade-offs that were considered and rejected.
