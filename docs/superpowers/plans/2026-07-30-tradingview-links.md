# TradingView Chart Links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the ticker text in all three holdings tables a link that opens that exact instrument's chart on TradingView.

**Architecture:** Pure frontend change in `index.html`. Two small helpers derive the TradingView symbol per holding from the `is_cedear` / `is_crypto` / `currency` flags already present in the `/api/portfolio` JSON, mirroring the shape of the backend's `resolve_yf_symbol()`. No backend change, no new API field.

**Tech Stack:** Vanilla JS inline in `index.html` (no build step), Bootstrap 5 dark theme, Playwright + system Chrome for verification.

## Global Constraints

- Design of record: `docs/plans/2026-07-30-tradingview-links-design.md`.
- The TradingView symbol MUST be derived per-holding from `is_cedear` / `is_crypto` / `currency`. Deriving it from the ticker string alone reintroduces the CEDEAR-vs-underlying bug fixed in commit `08a4ff2`.
- URL form: `https://www.tradingview.com/symbols/<symbol>/` — trailing slash included.
- Links open in a new tab: `target="_blank" rel="noopener noreferrer"`.
- The `CEDEAR` badge stays **outside** the anchor.
- Repo root: `/media/tgarriz/Nuevo vol/lab/miportfolio`.
- Scratchpad venv (has flask, yfinance, playwright): `/tmp/claude-1000/-media-tgarriz-Nuevo-vol-lab-miportfolio/f0084847-2415-494b-a05f-7760458336ea/scratchpad/venv/bin/python3`.
- Chrome for Playwright: `executable_path="/usr/bin/google-chrome"`, `headless=True`, `args=["--no-sandbox"]`.
- The pre-existing `favicon.ico` 404 is expected and is already filtered out of the console-error assertion in `test_ui.py`.

---

### Task 1: TradingView links in all three holdings tables

**Files:**
- Modify: `index.html` (CSS block ~line 29; helpers near the `CATEGORIES` constant ~line 190; three render sites in `renderDetailPanel()`, `renderHoldingsTable()`, and the broker-cards loop inside `render()`)
- Test: `/tmp/claude-1000/-media-tgarriz-Nuevo-vol-lab-miportfolio/f0084847-2415-494b-a05f-7760458336ea/scratchpad/test_ui.py`

**Interfaces:**
- Consumes: holding objects as returned by `/api/portfolio`, each with `ticker`, `company`, `shares`, `price`, `currency`, `value`, `is_cedear`, `is_crypto`.
- Produces: `tradingViewSymbol(h) -> string` (the URL path segment, e.g. `"BCBA-AMD"`) and `tickerLink(h) -> string` (anchor HTML). Both are used by all three render functions.

- [ ] **Step 1: Write the failing test**

Append to `test_ui.py`, immediately before the `# ---- 9. Console errors check` section:

```python
    # ---- 8b. TradingView links ----
    def tenencias_rows():
        out = []
        for tr in page.query_selector_all("#holdingsBody tr"):
            tds = tr.query_selector_all("td")
            link = tds[0].query_selector("a.ticker-link")
            out.append({
                "ticker": tds[0].inner_text().split()[0],
                "broker": tds[2].inner_text().strip(),
                "href": link.get_attribute("href") if link else None,
                "target": link.get_attribute("target") if link else None,
                "rel": link.get_attribute("rel") if link else None,
            })
        return out

    rows_tv = tenencias_rows()
    assert rows_tv, "no rows in Tenencias table"

    def find_row(ticker, broker):
        m = [r for r in rows_tv if r["ticker"] == ticker and r["broker"] == broker]
        assert len(m) == 1, f"expected exactly one {ticker}@{broker}, got {m}"
        return m[0]

    TV = "https://www.tradingview.com/symbols/"

    # The regression guard: same ticker string, different instruments.
    cases = [
        ("AMD", "BECA Vestiva", TV + "AMD/"),
        ("AMD", "TM Inversiones", TV + "BCBA-AMD/"),
        ("INTC", "BECA Vestiva", TV + "INTC/"),
        ("INTC", "TM Inversiones", TV + "BCBA-INTC/"),
        ("MSFT", "BECA Vestiva", TV + "MSFT/"),
        ("MSFT", "Balanz", TV + "BCBA-MSFT/"),
        ("MU", "BECA Vestiva", TV + "MU/"),
        ("MU", "Balanz", TV + "BCBA-MU/"),
        ("BTC", "Belo", TV + "BTCUSD/"),
        ("ETH", "Belo", TV + "ETHUSD/"),
        ("ALUA", "TM Inversiones", TV + "BCBA-ALUA/"),
        ("JPM", "Balanz", TV + "BCBA-JPM/"),
    ]
    for ticker, broker, expected in cases:
        r = find_row(ticker, broker)
        assert r["href"] == expected, f"{ticker}@{broker}: got {r['href']}, want {expected}"
        assert r["target"] == "_blank", f"{ticker}@{broker}: target={r['target']}"
        assert "noopener" in (r["rel"] or ""), f"{ticker}@{broker}: rel={r['rel']}"
    log(f"TradingView links verified on {len(cases)} rows (incl. 4 duplicated tickers)")

    # Every row in every table must have a link.
    missing = [r for r in rows_tv if not r["href"]]
    assert not missing, f"rows without a TradingView link: {missing}"

    for sel, label in (("#detailBody", "detail panel"), ("#brokerCards", "broker cards")):
        cells = page.query_selector_all(f"{sel} tr td:first-child")
        assert cells, f"no rows found in {label}"
        no_link = [c.inner_text() for c in cells if not c.query_selector("a.ticker-link")]
        assert not no_link, f"{label} rows without link: {no_link}"
    log("TradingView links present in detail panel and broker cards")
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd "/media/tgarriz/Nuevo vol/lab/miportfolio"
SCRATCH=/tmp/claude-1000/-media-tgarriz-Nuevo-vol-lab-miportfolio/f0084847-2415-494b-a05f-7760458336ea/scratchpad
PORTFOLIO_DB="$(pwd)/data/portfolio.db" PORT=5099 $SCRATCH/venv/bin/python3 app.py > $SCRATCH/app_tv.log 2>&1 &
echo $! > $SCRATCH/app_tv.pid
sleep 3
$SCRATCH/venv/bin/python3 $SCRATCH/test_ui.py
```

Expected: FAIL on the first `find_row` assertion or on `r["href"] == expected` with `got None` — no `a.ticker-link` exists yet.

- [ ] **Step 3: Add the link CSS**

In `index.html`, in the `<style>` block, immediately after the `th.sortable:hover` rule:

```css
        .ticker-link { color: #6ea8fe; text-decoration: none; }
        .ticker-link:hover { color: #9dc4fb; text-decoration: underline; }
```

- [ ] **Step 4: Add the two helpers**

In `index.html`, in the inline `<script>`, immediately after the `CATEGORIES` constant closing `];`:

```javascript
// TradingView symbol, derived per holding — NEVER from the ticker string
// alone. A CEDEAR and its underlying US stock share a ticker but are
// different instruments on different exchanges in different currencies
// (see resolve_yf_symbol() in app.py for the same distinction).
function tradingViewSymbol(h) {
    if (h.is_crypto) return h.ticker + 'USD';
    if (h.is_cedear || h.currency === 'ARS') return 'BCBA-' + h.ticker;
    return h.ticker;
}

function tickerLink(h) {
    return '<a class="ticker-link" target="_blank" rel="noopener noreferrer" href="' +
        'https://www.tradingview.com/symbols/' + tradingViewSymbol(h) + '/">' + h.ticker + '</a>';
}
```

- [ ] **Step 5: Wire the link into the detail panel**

In `renderDetailPanel()`, replace:

```javascript
            '<td>' + h.ticker + '</td>' +
            '<td>' + h.company + '</td>' +
            '<td><span class="badge badge-broker">' + h.broker + '</span></td>' +
```

with:

```javascript
            '<td>' + tickerLink(h) + '</td>' +
            '<td>' + h.company + '</td>' +
            '<td><span class="badge badge-broker">' + h.broker + '</span></td>' +
```

- [ ] **Step 6: Wire the link into the Tenencias table**

In `renderHoldingsTable()`, replace:

```javascript
            '<td>' + h.ticker + cedi + '</td>' +
```

with:

```javascript
            '<td>' + tickerLink(h) + cedi + '</td>' +
```

The `cedi` badge stays outside the anchor, as required.

- [ ] **Step 7: Wire the link into the broker cards**

In the broker-cards loop inside `render()`, replace:

```javascript
            rows += '<tr>' +
                '<td>' + h.ticker + '</td>' +
```

with:

```javascript
            rows += '<tr>' +
                '<td>' + tickerLink(h) + '</td>' +
```

- [ ] **Step 8: Check JS syntax**

```bash
cd "/media/tgarriz/Nuevo vol/lab/miportfolio"
SCRATCH=/tmp/claude-1000/-media-tgarriz-Nuevo-vol-lab-miportfolio/f0084847-2415-494b-a05f-7760458336ea/scratchpad
python3 -c "
import re
html = open('index.html').read()
m = re.search(r'<script>\n(.*)</script>', html, re.S)
open('$SCRATCH/inline.js','w').write(m.group(1))
"
node --check $SCRATCH/inline.js && echo "JS SYNTAX OK"
```

Expected: `JS SYNTAX OK`

- [ ] **Step 9: Run the test to verify it passes**

```bash
SCRATCH=/tmp/claude-1000/-media-tgarriz-Nuevo-vol-lab-miportfolio/f0084847-2415-494b-a05f-7760458336ea/scratchpad
$SCRATCH/venv/bin/python3 $SCRATCH/test_ui.py
```

Expected: PASS, ending in `[TEST] ALL TESTS PASSED`, including the two new log lines about TradingView links.

- [ ] **Step 10: Stop the test server**

```bash
SCRATCH=/tmp/claude-1000/-media-tgarriz-Nuevo-vol-lab-miportfolio/f0084847-2415-494b-a05f-7760458336ea/scratchpad
kill $(cat $SCRATCH/app_tv.pid) 2>/dev/null; sleep 1; echo stopped
```

- [ ] **Step 11: Commit**

`data/portfolio.db` will show as modified because the running app appended price rows during the test — that is expected churn, unrelated to this change. Stage only `index.html`.

```bash
cd "/media/tgarriz/Nuevo vol/lab/miportfolio"
git add index.html
git commit -m "Add TradingView chart links to holdings tables

Ticker text is now a link in the detail panel, the Tenencias table and
the broker cards. The symbol is derived per holding from is_cedear /
is_crypto / currency, so AMD at BECA Vestiva opens the NASDAQ chart in
USD while AMD at TM Inversiones opens the BCBA CEDEAR chart in ARS.
Deriving it from the ticker string alone would reintroduce the bug fixed
in 08a4ff2.

Design: docs/plans/2026-07-30-tradingview-links-design.md
Verified with Playwright against real Chrome, asserting hrefs on all
four duplicated tickers plus crypto and BYMA stocks."
```

---

## Self-Review

**Spec coverage:**
- Symbol resolution table (crypto / CEDEAR-or-ARS / US) → Step 4, `tradingViewSymbol()`.
- URL form with trailing slash → Step 4, `tickerLink()`.
- Applied to all three tables → Steps 5, 6, 7.
- CEDEAR badge outside the link → Step 6, `cedi` left outside the anchor.
- New tab with `noopener noreferrer` → Step 4, asserted in Step 1.
- CSS for dark theme → Step 3.
- Test covering the four duplicated tickers → Step 1, `cases` list.
- Crypto and BYMA coverage → Step 1, `BTC`/`ETH`/`ALUA` cases.

**Placeholder scan:** No TBDs, no "add error handling", no "similar to Task N". All code blocks are literal.

**Type consistency:** `tradingViewSymbol(h)` returns a string used only by `tickerLink(h)`; `tickerLink(h)` returns an HTML string used at three call sites, all of which currently concatenate `h.ticker` in the same position. The test selects `a.ticker-link`, matching the class emitted in Step 4 and styled in Step 3.
