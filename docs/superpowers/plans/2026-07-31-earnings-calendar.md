# Earnings Calendar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a window listing the next 5 earnings dates for the portfolio, auto-loaded on page load and cached once per calendar day, with ADRs grouped onto a single row with their local BYMA shares.

**Architecture:** `sources.ADR_MAP` extends the existing symbol-resolution rule so an ADR and its BYMA listing resolve to one company symbol. A new `earnings` table caches one summary per symbol per local day, negatives included. `GET /api/earnings` resolves, fetches what is stale, and returns the nearest N. The frontend fetches it alongside the portfolio and renders a dashboard card plus an overlay.

**Tech Stack:** Flask, SQLite, yfinance, pytest, vanilla JS + Bootstrap 5 (no build step).

## Global Constraints

- Spec: `docs/plans/2026-07-31-earnings-calendar-design.md`.
- No new dependencies. `requirements.txt` stays as is.
- `index.html` stays a single plain file with inline `<script>`/`<style>` — no build step, no framework.
- Comments explain *why*, matching the density of the surrounding code. No comment restates what the line already says.
- Migrations in `ensure_schema()` are additive and idempotent — safe on every startup.
- ARS and USD amounts are never summed. Existing rule, unchanged by this work.
- Tests that reach Yahoo Finance carry `@pytest.mark.network`.
- Run tests with `python3 -m pytest`; the environment with `yfinance` installed is the running container (`docker exec portfolio-dashboard`).

---

### Task 1: ADR symbol resolution

**Files:**
- Modify: `sources.py:21-35` (`resolve_insight_symbol`)
- Test: `tests/test_sources.py`

**Interfaces:**
- Produces: `sources.ADR_MAP: dict[str, str]` — local BYMA ticker → US ADR symbol. `sources.resolve_insight_symbol(ticker, is_cedear, is_crypto, currency) -> str` keeps its signature.

- [ ] **Step 1: Write the failing tests**

Append to the offline section of `tests/test_sources.py`:

```python
def test_adr_and_local_share_resolve_to_one_symbol():
    # Yahoo returns the same balance for both listings (PAM in USD,
    # PAMP.BA in ARS), so they must collapse or the window shows it twice.
    assert sources.resolve_insight_symbol("PAMP", False, False, "ARS") == \
           sources.resolve_insight_symbol("PAM", False, False, "USD")


def test_local_share_resolves_to_the_adr():
    assert sources.resolve_insight_symbol("PAMP", False, False, "ARS") == "PAM"
    assert sources.resolve_insight_symbol("YPFD", False, False, "ARS") == "YPF"


def test_byma_stock_without_an_adr_keeps_the_ba_suffix():
    # Regression: the ADR map must not swallow ordinary BYMA tickers.
    assert sources.resolve_insight_symbol("ALUA", False, False, "ARS") == "ALUA.BA"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker exec portfolio-dashboard python3 -m pytest tests/test_sources.py -m "not network" -v`
Expected: the two ADR tests FAIL (`'PAMP.BA' != 'PAM'`), the regression test passes.

- [ ] **Step 3: Implement**

Add above `resolve_insight_symbol` in `sources.py`:

```python
# Local BYMA ticker -> US ADR symbol. An ADR and its local share are one
# company filing one balance, but Yahoo answers for both listings with the
# same date and the EPS in each listing's currency (PAM 2.52 USD vs PAMP.BA
# 145.62 ARS), so without this map the same balance appears twice.
ADR_MAP = {
    "PAMP": "PAM",
    "YPFD": "YPF",
}
```

Add the lookup to `resolve_insight_symbol`, after the `is_cedear` branch and before the ARS branch:

```python
    if ticker in ADR_MAP:
        return ADR_MAP[ticker]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `docker exec portfolio-dashboard python3 -m pytest tests/test_sources.py -m "not network" -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add sources.py tests/test_sources.py
git commit -m "Resolve ADRs and their local shares to one symbol"
```

---

### Task 2: The earnings summary fetcher

**Files:**
- Modify: `sources.py` (after `fetch_earnings_history`)
- Test: `tests/test_sources.py`

**Interfaces:**
- Consumes: `fetch_earnings_calendar`, `fetch_earnings_history` (existing).
- Produces: `sources.fetch_earnings_summary(symbol) -> dict | None` with keys `next_date`, `eps_estimate`, `last_date`, `last_eps_reported`, `last_surprise_pct`. `None` means no upcoming date.

- [ ] **Step 1: Write the failing tests**

Append to the network section of `tests/test_sources.py`:

```python
@pytest.mark.network
def test_earnings_summary_has_the_window_columns():
    summary = sources.fetch_earnings_summary("AMD")
    assert set(summary) == {
        "next_date", "eps_estimate",
        "last_date", "last_eps_reported", "last_surprise_pct",
    }
    assert summary["next_date"]


@pytest.mark.network
def test_earnings_summary_is_none_without_an_upcoming_date():
    # ALUA.BA has old history but no scheduled date — the window excludes it.
    assert sources.fetch_earnings_summary("ALUA.BA") is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker exec portfolio-dashboard python3 -m pytest tests/test_sources.py -m network -k earnings_summary -v`
Expected: FAIL with `AttributeError: module 'sources' has no attribute 'fetch_earnings_summary'`.

- [ ] **Step 3: Implement**

```python
def fetch_earnings_summary(symbol):
    """Next earnings date plus the last reported quarter, or None.

    None means the symbol has no scheduled date — the one place the
    calendar window's exclusion rule is decided.
    """
    calendar = fetch_earnings_calendar(symbol)
    if not calendar:
        return None

    history = fetch_earnings_history(symbol, limit=1)
    last = history[0] if history else None
    return {
        "next_date": calendar["date"],
        "eps_estimate": calendar["eps_estimate"],
        "last_date": last["date"] if last else None,
        "last_eps_reported": last["eps_reported"] if last else None,
        "last_surprise_pct": last["surprise_pct"] if last else None,
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `docker exec portfolio-dashboard python3 -m pytest tests/test_sources.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add sources.py tests/test_sources.py
git commit -m "Add the earnings summary fetcher"
```

---

### Task 3: Schema — `is_adr` column and `earnings` table

**Files:**
- Modify: `app.py:65-87` (`ensure_schema`), `app.py:90-113` (`get_holdings`)
- Test: `tests/test_earnings_route.py` (create)

**Interfaces:**
- Produces: `holdings.is_adr` column, derived from `sources.ADR_MAP`; table `earnings (symbol TEXT PRIMARY KEY, payload TEXT, fetched_on TEXT NOT NULL)`. `get_holdings()` rows gain an `is_adr` key.

- [ ] **Step 1: Write the failing test**

Create `tests/test_earnings_route.py`:

```python
import sqlite3


def insert_holding(db, ticker, broker, is_cedear=0, is_crypto=0, company=None):
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO holdings (ticker, company, shares, broker, is_cedear, is_crypto) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (ticker, company or ticker, 10, broker, is_cedear, is_crypto),
    )
    conn.commit()
    conn.close()


def test_is_adr_is_derived_from_the_map(app_module):
    insert_holding(app_module.DB_PATH, "PAM", "BECA Vestiva")
    insert_holding(app_module.DB_PATH, "PAMP", "TM Inversiones")
    app_module.ensure_schema()

    flags = {h["ticker"]: h["is_adr"] for h in app_module.get_holdings()}
    assert flags["PAM"] == 1
    assert flags["PAMP"] == 0


def test_removing_a_mapping_unmarks_the_holding(app_module, monkeypatch):
    insert_holding(app_module.DB_PATH, "PAM", "BECA Vestiva")
    app_module.ensure_schema()

    monkeypatch.setattr(app_module.sources, "ADR_MAP", {})
    app_module.ensure_schema()
    assert app_module.get_holdings()[0]["is_adr"] == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker exec portfolio-dashboard python3 -m pytest tests/test_earnings_route.py -v`
Expected: FAIL — `is_adr` is not a key of the holdings rows.

- [ ] **Step 3: Implement**

In `ensure_schema()`, after the `prices.is_cedear` migration:

```python
    holding_cols = [row[1] for row in conn.execute("PRAGMA table_info(holdings)").fetchall()]
    if "is_adr" not in holding_cols:
        conn.execute("ALTER TABLE holdings ADD COLUMN is_adr INTEGER DEFAULT 0")
        conn.commit()

    # Derived from sources.ADR_MAP on every startup rather than loaded by
    # hand, so adding a mapping is the only edit needed to mark a new ADR —
    # and dropping one unmarks it. Clearing first is what makes that true.
    adr_symbols = sorted(set(sources.ADR_MAP.values()))
    conn.execute("UPDATE holdings SET is_adr = 0 WHERE is_adr = 1")
    if adr_symbols:
        conn.execute(
            "UPDATE holdings SET is_adr = 1 WHERE is_cedear = 0 AND ticker IN "
            f"({','.join('?' * len(adr_symbols))})",
            adr_symbols,
        )
    conn.commit()
```

And, next to the `insights` table:

```python
    # Earnings calendar cache, one row per company symbol per local day.
    # A symbol with no scheduled date is cached as JSON null so it is not
    # re-fetched on every page load.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS earnings (
            symbol TEXT PRIMARY KEY,
            payload TEXT,
            fetched_on TEXT NOT NULL
        )
    """)
```

In `get_holdings()`, add `h.is_adr,` to the SELECT list next to `h.is_cedear`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `docker exec portfolio-dashboard python3 -m pytest tests/test_earnings_route.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_earnings_route.py
git commit -m "Add the is_adr column and the earnings cache table"
```

---

### Task 4: The `/api/earnings` endpoint

**Files:**
- Modify: `app.py` (helpers after `write_insight_cache`, route after `api_insight`)
- Test: `tests/test_earnings_route.py`

**Interfaces:**
- Consumes: `sources.fetch_earnings_summary`, `sources.resolve_insight_symbol`, `get_holdings`, `resolve_yf_symbol`.
- Produces: `GET /api/earnings?limit=5&refresh=false` → `{"rows": [...], "fetched_on": "YYYY-MM-DD", "cached": bool}`. Each row: `ticker`, `company`, `symbol`, `next_date`, `days_until`, `eps_estimate`, `last_date`, `last_eps_reported`, `last_surprise_pct`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_earnings_route.py`:

```python
import pytest


@pytest.fixture
def stub_summary(app_module, monkeypatch):
    """Records which symbols were asked for, and answers from a fixed table."""
    calls = []
    answers = {
        "AMD": {"next_date": "2026-08-04", "eps_estimate": 1.61,
                "last_date": "2026-05-05", "last_eps_reported": 1.37,
                "last_surprise_pct": 5.82},
        "PAM": {"next_date": "2026-08-10", "eps_estimate": 2.52,
                "last_date": "2026-05-06", "last_eps_reported": 3.9,
                "last_surprise_pct": 139.88},
        "MSFT": {"next_date": "2026-10-28", "eps_estimate": 4.68,
                 "last_date": "2026-07-29", "last_eps_reported": 4.74,
                 "last_surprise_pct": 11.81},
    }

    def fake(symbol):
        calls.append(symbol)
        return answers.get(symbol)

    monkeypatch.setattr(app_module.sources, "fetch_earnings_summary", fake)
    return calls


def test_rows_come_back_nearest_first(app_module, client, stub_summary):
    insert_holding(app_module.DB_PATH, "MSFT", "BECA Vestiva")
    insert_holding(app_module.DB_PATH, "AMD", "BECA Vestiva")
    rows = client.get("/api/earnings").get_json()["rows"]
    assert [r["ticker"] for r in rows] == ["AMD", "MSFT"]


def test_symbols_without_a_date_are_excluded(app_module, client, stub_summary):
    insert_holding(app_module.DB_PATH, "AMD", "BECA Vestiva")
    insert_holding(app_module.DB_PATH, "ALUA", "TM Inversiones")
    rows = client.get("/api/earnings").get_json()["rows"]
    assert [r["ticker"] for r in rows] == ["AMD"]


def test_crypto_is_never_asked(app_module, client, stub_summary):
    insert_holding(app_module.DB_PATH, "BTC", "Belo", is_crypto=1)
    client.get("/api/earnings")
    assert stub_summary == []


def test_cedear_and_direct_holding_make_one_row(app_module, client, stub_summary):
    insert_holding(app_module.DB_PATH, "AMD", "BECA Vestiva")
    insert_holding(app_module.DB_PATH, "AMD", "TM Inversiones", is_cedear=1)
    rows = client.get("/api/earnings").get_json()["rows"]
    assert len(rows) == 1
    assert stub_summary == ["AMD"]


def test_adr_and_local_share_make_one_row_shown_as_the_adr(app_module, client, stub_summary):
    insert_holding(app_module.DB_PATH, "PAM", "BECA Vestiva", company="Pampa")
    insert_holding(app_module.DB_PATH, "PAMP", "TM Inversiones", company="Pampa Energia")
    rows = client.get("/api/earnings").get_json()["rows"]
    assert len(rows) == 1
    assert rows[0]["ticker"] == "PAM"
    assert rows[0]["symbol"] == "PAM"


def test_second_call_uses_the_cache(app_module, client, stub_summary):
    insert_holding(app_module.DB_PATH, "AMD", "BECA Vestiva")
    client.get("/api/earnings")
    body = client.get("/api/earnings").get_json()
    assert stub_summary == ["AMD"]
    assert body["cached"] is True


def test_a_stale_entry_is_refetched(app_module, client, stub_summary):
    insert_holding(app_module.DB_PATH, "AMD", "BECA Vestiva")
    client.get("/api/earnings")

    conn = sqlite3.connect(app_module.DB_PATH)
    conn.execute("UPDATE earnings SET fetched_on = '2020-01-01'")
    conn.commit()
    conn.close()

    client.get("/api/earnings")
    assert stub_summary == ["AMD", "AMD"]


def test_refresh_bypasses_a_fresh_cache(app_module, client, stub_summary):
    insert_holding(app_module.DB_PATH, "AMD", "BECA Vestiva")
    client.get("/api/earnings")
    body = client.get("/api/earnings?refresh=true").get_json()
    assert stub_summary == ["AMD", "AMD"]
    assert body["cached"] is False


def test_limit_trims_the_rows(app_module, client, stub_summary):
    insert_holding(app_module.DB_PATH, "AMD", "BECA Vestiva")
    insert_holding(app_module.DB_PATH, "MSFT", "BECA Vestiva")
    rows = client.get("/api/earnings?limit=1").get_json()["rows"]
    assert [r["ticker"] for r in rows] == ["AMD"]


def test_symbols_without_a_date_are_cached_too(app_module, client, stub_summary):
    # Otherwise every page load re-asks Yahoo for the uncovered symbols,
    # which is the cost the cache exists to avoid.
    insert_holding(app_module.DB_PATH, "ALUA", "TM Inversiones")
    client.get("/api/earnings")
    client.get("/api/earnings")
    assert stub_summary == ["ALUA.BA"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker exec portfolio-dashboard python3 -m pytest tests/test_earnings_route.py -v`
Expected: FAIL with 404 on `/api/earnings`.

- [ ] **Step 3: Implement**

Change the import at `app.py:12` to `from datetime import date, datetime`.

Add near `DEFAULT_ANTHROPIC_MODEL`-style config, after `PORT`:

```python
DEFAULT_EARNINGS_LIMIT = 5
```

Add after `write_insight_cache`:

```python
def read_earnings_cache(symbol):
    """(hit, summary) for today's cache entry.

    The hit flag is separate because a cached None — a symbol with no
    scheduled date — is a real answer, not a miss.
    """
    conn = sqlite3.connect(str(DB_PATH))
    row = conn.execute(
        "SELECT payload FROM earnings WHERE symbol = ? "
        "AND fetched_on = date('now', 'localtime')",
        (symbol,),
    ).fetchone()
    conn.close()
    return (True, json.loads(row[0])) if row else (False, None)


def write_earnings_cache(symbol, summary):
    """Store a summary for today, replacing any previous entry."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "INSERT INTO earnings (symbol, payload, fetched_on) "
        "VALUES (?, ?, date('now', 'localtime')) "
        "ON CONFLICT(symbol) DO UPDATE SET "
        "payload = excluded.payload, fetched_on = excluded.fetched_on",
        (symbol, json.dumps(summary)),
    )
    conn.commit()
    conn.close()


def holding_currency(holding):
    """ARS or USD, without needing a price row to exist yet.

    A holding with no price recorded still has to resolve to the right
    symbol, so this falls back to what the ticker maps to rather than
    defaulting to USD and turning ALUA into a US stock.
    """
    if holding["currency"]:
        return holding["currency"]
    symbol = resolve_yf_symbol(holding["ticker"], bool(holding["is_cedear"]))
    return "ARS" if symbol and symbol.endswith(".BA") else "USD"


def earnings_symbols():
    """Company symbol -> the ticker and name to show for it.

    Crypto is skipped outright; it has no balance sheet. Holdings that
    resolve to the same symbol collapse into one entry — a CEDEAR with its
    direct holding, an ADR with its local BYMA share — preferring the
    holding whose ticker *is* the symbol so PAM/PAMP shows as "PAM".
    """
    entries = {}
    for holding in get_holdings():
        if holding["is_crypto"]:
            continue
        symbol = sources.resolve_insight_symbol(
            holding["ticker"],
            bool(holding["is_cedear"]),
            False,
            holding_currency(holding),
        )
        chosen = entries.get(symbol)
        if chosen is None or (chosen["ticker"] != symbol and holding["ticker"] == symbol):
            entries[symbol] = {
                "ticker": holding["ticker"],
                "company": holding["company"] or holding["ticker"],
            }
    return entries


def days_until(date_text, today):
    """Whole days from today to an ISO date, or None when unparseable."""
    try:
        return (date.fromisoformat(str(date_text)[:10]) - today).days
    except (TypeError, ValueError):
        return None
```

Add the route after `api_insight`:

```python
@app.route("/api/earnings")
def api_earnings():
    """Upcoming earnings dates across the portfolio, nearest first.

    Every symbol has to be asked before the nearest ones are known, so the
    whole portfolio is fetched and cached for the day; `limit` only trims
    what is returned, it does not save any requests.
    """
    refresh = request.args.get("refresh", "false").lower() == "true"
    try:
        limit = int(request.args.get("limit", DEFAULT_EARNINGS_LIMIT))
    except ValueError:
        limit = DEFAULT_EARNINGS_LIMIT

    today = date.today()
    rows = []
    all_cached = True

    for symbol, meta in earnings_symbols().items():
        hit, summary = (False, None) if refresh else read_earnings_cache(symbol)
        if not hit:
            all_cached = False
            summary = sources.fetch_earnings_summary(symbol)
            write_earnings_cache(symbol, summary)
        if not summary:
            continue

        remaining = days_until(summary["next_date"], today)
        # A date Yahoo has not rolled forward yet is in the past — it is not
        # an upcoming balance, so it does not belong in this list.
        if remaining is not None and remaining < 0:
            continue
        rows.append({"symbol": symbol, "days_until": remaining, **meta, **summary})

    rows.sort(key=lambda row: row["next_date"])
    return jsonify({
        "rows": rows[:limit] if limit > 0 else rows,
        "fetched_on": today.isoformat(),
        "cached": all_cached,
    })
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `docker exec portfolio-dashboard python3 -m pytest tests/ -m "not network" -v`
Expected: all PASS, including the pre-existing insight tests.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_earnings_route.py
git commit -m "Add the /api/earnings endpoint"
```

---

### Task 5: Expose `is_adr` through `/api/portfolio`

**Files:**
- Modify: `app.py:260-288` (`api_portfolio`)
- Test: `tests/test_earnings_route.py`

**Interfaces:**
- Produces: each holding in the `/api/portfolio` response gains `"is_adr": bool`; pie labels append `" (ADR)"` the way they already append `" (CEDEAR)"`.

- [ ] **Step 1: Write the failing test**

```python
def test_portfolio_marks_adr_holdings(app_module, client, monkeypatch):
    monkeypatch.setattr(app_module, "refresh_prices", lambda pairs=None: ({}, []))
    insert_holding(app_module.DB_PATH, "PAM", "BECA Vestiva", company="Pampa")
    app_module.ensure_schema()

    body = client.get("/api/portfolio?refresh=false").get_json()
    holding = body["brokers"]["BECA Vestiva"]["holdings"][0]
    assert holding["is_adr"] is True
    assert "(ADR)" in body["pie"][0]["label"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `docker exec portfolio-dashboard python3 -m pytest tests/test_earnings_route.py::test_portfolio_marks_adr_holdings -v`
Expected: FAIL with `KeyError: 'is_adr'`.

- [ ] **Step 3: Implement**

In the holding dict built by `api_portfolio`, next to `"is_cedear"`:

```python
            "is_adr": bool(h["is_adr"]),
```

In the pie-label block, after the CEDEAR suffix:

```python
            elif h.get("is_adr"):
                pie_labels[key] += " (ADR)"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `docker exec portfolio-dashboard python3 -m pytest tests/ -m "not network" -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_earnings_route.py
git commit -m "Mark ADR holdings in the portfolio response"
```

---

### Task 6: Frontend — card, window, and auto-load

**Files:**
- Modify: `index.html` (style block, header, new dashboard row, new overlay, script)

**Interfaces:**
- Consumes: `GET /api/earnings`, `holding.is_adr`.
- Produces: `loadEarnings()`, `renderEarningsCard()`, `renderEarningsWindow()`, `openEarnings()`, `closeEarnings()`, `refreshEarnings()`, module-level `earningsData`.

No test — `index.html` has no test harness in this repo. Verified by loading the page.

- [ ] **Step 1: Add the styles**

After the `.badge-cedear` rule:

```css
        .badge-adr { background: #4a5c2d; color: #d8e9b0; }
        .earnings-row { cursor: pointer; }
        .earnings-row:hover { background: #1a2c3d; }
        .earnings-soon { color: #facc15; font-weight: 600; }
```

- [ ] **Step 2: Add the header button**

Before the "Actualizar precios" button:

```html
            <button class="btn btn-outline-secondary btn-sm me-2" onclick="openEarnings()">
                &#128197; Balances
            </button>
```

- [ ] **Step 3: Add the dashboard card**

Between the main content row and `<div class="row g-3 mt-2" id="brokerCards">`:

```html
    <!-- Upcoming earnings — filled by loadEarnings(), opens the window on click -->
    <div class="row g-3 mt-2">
        <div class="col-12">
            <div class="card earnings-row" onclick="openEarnings()">
                <div class="card-header">Próximos balances</div>
                <div class="card-body py-2" id="earningsCard">
                    <span class="text-secondary">Cargando…</span>
                </div>
            </div>
        </div>
    </div>
```

- [ ] **Step 4: Add the overlay**

After the insight overlay:

```html
    <!-- Earnings window -->
    <div id="earningsOverlay" class="insight-overlay" style="display:none" onclick="closeEarnings(event)">
        <div class="insight-panel" onclick="event.stopPropagation()">
            <div class="card-header d-flex justify-content-between align-items-center">
                <span>Próximos balances</span>
                <div>
                    <button class="btn btn-outline-info btn-sm me-2" onclick="refreshEarnings()">&#x21bb; Actualizar</button>
                    <button class="btn btn-outline-secondary btn-sm" onclick="closeEarnings()">Cerrar</button>
                </div>
            </div>
            <div class="card-body" id="earningsContent"></div>
        </div>
    </div>
```

- [ ] **Step 5: Add the script**

After `openInsight()`:

```javascript
let earningsData = null;

// The first load of the day asks Yahoo once per symbol and takes a while;
// after that the server answers from its daily cache.
function loadEarnings(force) {
    earningsData = null;
    renderEarningsCard();
    renderEarningsWindow();
    return fetch('/api/earnings' + (force ? '?refresh=true' : ''))
        .then(function(r) { return r.json(); })
        .then(function(data) {
            earningsData = data;
            renderEarningsCard();
            renderEarningsWindow();
        })
        .catch(function() {
            earningsData = { rows: [], error: true };
            renderEarningsCard();
            renderEarningsWindow();
        });
}

function daysLabel(days) {
    if (days == null) return '—';
    if (days === 0) return 'hoy';
    return days === 1 ? 'mañana' : 'en ' + days + ' días';
}

function renderEarningsCard() {
    var el = document.getElementById('earningsCard');
    if (!earningsData) {
        el.innerHTML = '<span class="text-secondary">Cargando…</span>';
        return;
    }
    if (!earningsData.rows.length) {
        el.innerHTML = '<span class="text-secondary">Sin balances próximos.</span>';
        return;
    }
    el.innerHTML = '<div class="d-flex flex-wrap gap-3">' + earningsData.rows.map(function(r) {
        var soon = r.days_until != null && r.days_until <= 7 ? ' earnings-soon' : '';
        return '<div><span class="fw-semibold">' + escapeHtml(r.ticker) + '</span> ' +
            '<span class="text-secondary">' + escapeHtml(r.next_date) + '</span> ' +
            '<span class="' + soon.trim() + '">(' + daysLabel(r.days_until) + ')</span></div>';
    }).join('') + '</div>';
}

function renderEarningsWindow() {
    var el = document.getElementById('earningsContent');
    if (!earningsData) {
        el.innerHTML = '<p class="text-secondary">Consultando calendarios… la primera vez del día puede tardar un minuto.</p>';
        return;
    }
    if (earningsData.error) {
        el.innerHTML = '<div class="alert alert-danger py-2">No se pudo consultar el calendario.</div>';
        return;
    }
    if (!earningsData.rows.length) {
        el.innerHTML = '<p class="text-secondary">Ningún ticker de la cartera tiene una fecha de balance publicada.</p>';
        return;
    }

    var rows = earningsData.rows.map(function(r) {
        var soon = r.days_until != null && r.days_until <= 7 ? ' class="earnings-soon"' : '';
        var surprise = r.last_surprise_pct != null ? r.last_surprise_pct.toFixed(1) + '%' : '—';
        return '<tr><td>' + escapeHtml(r.ticker) + '</td>' +
            '<td>' + escapeHtml(r.company) + '</td>' +
            '<td>' + escapeHtml(r.next_date) + '</td>' +
            '<td' + soon + '>' + daysLabel(r.days_until) + '</td>' +
            '<td class="text-end">' + (r.eps_estimate != null ? r.eps_estimate.toFixed(2) : '—') + '</td>' +
            '<td>' + escapeHtml(r.last_date || '—') + '</td>' +
            '<td class="text-end">' + surprise + '</td></tr>';
    }).join('');

    el.innerHTML = '<table class="table table-sm"><thead><tr>' +
        '<th>Ticker</th><th>Empresa</th><th>Fecha</th><th>Faltan</th>' +
        '<th class="text-end">EPS est.</th><th>Último</th><th class="text-end">Sorpresa</th>' +
        '</tr></thead><tbody>' + rows + '</tbody></table>' +
        '<p class="text-secondary small mb-0">Calendario consultado el ' +
        escapeHtml(earningsData.fetched_on) + '.</p>';
}

function openEarnings() {
    document.getElementById('earningsOverlay').style.display = 'flex';
    renderEarningsWindow();
}

function closeEarnings(evt) {
    if (evt && evt.target !== document.getElementById('earningsOverlay')) return;
    document.getElementById('earningsOverlay').style.display = 'none';
}

function refreshEarnings() {
    loadEarnings(true);
}
```

In `renderHoldingsTable`, extend the badge line:

```javascript
        var cedi = h.is_cedear ? ' <span class="badge badge-cedear">CEDEAR</span>'
                 : (h.is_adr ? ' <span class="badge badge-adr">ADR</span>' : '');
```

In `loadData()`, fire the earnings fetch alongside the portfolio fetch so a slow
first-of-the-day calendar never delays the dashboard.

- [ ] **Step 6: Verify in the browser**

```bash
docker compose up -d --build
```

Load `http://localhost:5050`, confirm the card fills in, the window opens with
the table, "Actualizar" re-queries, and PAM shows an ADR badge with no PAMP
duplicate row in the window.

- [ ] **Step 7: Commit**

```bash
git add index.html
git commit -m "Show upcoming earnings in a card and a window"
```

---

### Task 7: Documentation

**Files:**
- Modify: `README.md`, `CLAUDE.md`

- [ ] **Step 1: Update `README.md`**

Add the `earnings` table and `holdings.is_adr` to the schema section, and
`GET /api/earnings` to the endpoint list with its `limit` and `refresh`
parameters and the once-per-day cache behaviour.

- [ ] **Step 2: Update `CLAUDE.md`**

Document `ADR_MAP` next to `YF_TICKER_MAP`, the rule that `is_adr` is derived
from the map at startup rather than edited by hand, and that `/api/earnings`
caches per local calendar day including negative results.

- [ ] **Step 3: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "Document the earnings calendar"
```
