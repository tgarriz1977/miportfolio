# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A self-hosted stock portfolio dashboard. Flask backend (`app.py`) serves a single static frontend page (`index.html`, Bootstrap 5 dark mode + Chart.js) and two JSON endpoints. Holdings live in a SQLite database; live prices are pulled from Yahoo Finance via `yfinance`. There are no tests, no build step, and no JS/CSS framework tooling — `index.html` is a plain file with inline `<script>`/`<style>`.

## Running locally

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

Serves on `http://localhost:5050` by default. `app.py` reads `DB_PATH` from `PORTFOLIO_DB` (default `/data/portfolio.db`), so for local runs without Docker set `PORTFOLIO_DB=data/portfolio.db` or symlink `data/` to `/data`.

Via Docker Compose (mounts `./data` to `/data` in the container):

```bash
docker compose up -d
```

There is no test suite and no linter configured in this repo.

## Architecture

- **`app.py`** — the entire backend. Everything (routes, DB access, price refresh, ticker mapping) lives in this one file.
  - `YF_TICKER_MAP` — maps local tickers (as stored in `holdings.ticker`) to Yahoo Finance symbols. Argentine BYMA stocks get a `.BA` suffix (priced in ARS); crypto gets a `-USD` suffix; everything else maps 1:1. When adding a new holding, it must be added here or its price will never refresh.
  - `sources.COMPANY_ALIASES` — the *other* ticker map, and the one that is easy to confuse with the above. `YF_TICKER_MAP` is about **prices**, where two listings of a company are different instruments in different currencies; `COMPANY_ALIASES` is about **earnings and news**, where they are one company filing one balance. Yahoo answers for each listing with the same date (PAM and PAMP.BA both report 2026-08-04, quoting EPS in USD and ARS respectively), so without it one balance reads as two rows. It is built from two maps kept apart on purpose: `ADR_MAP` (BYMA ticker → US ADR) also drives `holdings.is_adr`, while `SHARE_CLASS_MAP` (GOOGL → GOOG) must not — GOOG is not an ADR. Adding an alias is one line in whichever map fits; `is_adr` is derived on every startup and must never be edited by hand.
  - `resolve_insight_symbol()` checks the aliases **before** the `is_cedear` branch. Reordering these breaks the GOOGL CEDEAR, which would short-circuit to its bare ticker and never collapse onto GOOG.
  - `get_holdings()` — joins `holdings` with the *latest* row per ticker from `prices` (via a `MAX(recorded_at)` subquery), not a separate `latest_price` column.
  - `refresh_prices()` — bulk-fetches via `yf.download()` for all tickers at once (fast path); on any exception it falls back to fetching each ticker individually via `yf.Ticker(...).fast_info`. Writes one new row per ticker into `prices` per refresh — `prices` is an append-only history table, not upserted.
  - `GET /api/portfolio` — default behavior triggers a live price refresh (`?refresh=true` by default) before reading from the DB, so every dashboard load hits Yahoo Finance for every ticker. Pass `?refresh=false` to read cached prices only. Response groups holdings by `broker`, and separately aggregates value by `ticker` (across brokers) for the pie chart.
  - `GET /api/refresh` — force-refreshes all tickers in `YF_TICKER_MAP` regardless of what's actually held.
  - `GET /api/earnings` — upcoming earnings dates, nearest first, `limit=5` by default. Cached per **local calendar day** (`fetched_on = date('now','localtime')`), not on an hours TTL — UTC would roll the cache over at 21:00 Argentine time. Symbols with nothing scheduled are cached as JSON `null` rather than skipped, so the ones Yahoo doesn't cover aren't re-fetched on every page load. `limit` only trims the response; every symbol is fetched regardless, since which are nearest isn't known until all have answered.
  - `GET /` — just serves `index.html` as a static file; there's no templating engine.
- **`index.html`** — single-page frontend. Fetches `/api/portfolio?refresh=true` on load (`loadData()`) and re-renders summary cards, the pie chart, and per-broker tables (`render()`). The "Actualizar precios" button calls `/api/refresh` then reloads data.
- **Database schema** (`holdings`, `prices`) — documented in `README.md` and materialized in `data/portfolio_dump.sql`. Key points not obvious from `app.py`:
  - `holdings` has a **composite primary key** `(ticker, broker)` — the same ticker can appear under multiple brokers (e.g. as a direct holding at one broker and a CEDEAR at another), and these are tracked as separate rows with independent share counts.
  - `is_cedear` flags CEDEAR holdings (Argentine depositary receipts tracking a foreign stock); the frontend appends "(CEDEAR)" to the pie chart label for these.
  - `prices` has no uniqueness constraint — every refresh appends rows; `get_holdings()` always picks the most recent one per ticker.
  - To restore/seed the DB from the tracked dump: `sqlite3 data/portfolio.db < data/portfolio_dump.sql`.

## Notes

- `data/portfolio.db` is tracked in git (it's the live data store for this personal deployment), while `dump_db.py` (a presumed helper for regenerating `portfolio_dump.sql`) is gitignored.
- No secrets/API keys are involved — Yahoo Finance data is fetched anonymously through `yfinance`.
