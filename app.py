#!/usr/bin/env python3
"""
Portfolio Dashboard — Web panel for stock holdings visualization.
Reads from portfolio.db, fetches live prices via yfinance,
and serves a Bootstrap + Chart.js dashboard.
"""

import json
import os
import sqlite3
import logging
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import yfinance as yf
from flask import Flask, jsonify, request, send_file

import llm
import sources
import youtube

# ── Config ────────────────────────────────────────────────────────────
DB_PATH = Path(os.environ.get("PORTFOLIO_DB", "/data/portfolio.db"))
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", 5050))

# How many upcoming balances /api/earnings returns by default.
DEFAULT_EARNINGS_LIMIT = 5

# Map local tickers to Yahoo Finance symbols — only for non-CEDEAR holdings.
# CEDEARs (is_cedear=1) are resolved dynamically to "<ticker>.BA" by
# resolve_yf_symbol(), since they trade on BYMA in ARS under that symbol —
# not to be confused with the underlying US ticker, which trades in USD.
YF_TICKER_MAP = {
    # BECA Vestiva — US stocks (direct)
    "AMD": "AMD", "AMZN": "AMZN", "AVGO": "AVGO", "GOOG": "GOOG",
    "INTC": "INTC", "META": "META", "MSFT": "MSFT", "MU": "MU",
    "NU": "NU", "PLTR": "PLTR", "QCOM": "QCOM", "YPF": "YPF",
    "VIST": "VIST", "PAM": "PAM",
    # TM Inversiones — Argentina stocks on BYMA (.BA)
    "ALUA": "ALUA.BA", "CEPU": "CEPU.BA", "ECOG": "ECOG.BA",
    "PAMP": "PAMP.BA", "TGNO4": "TGNO4.BA", "YPFD": "YPFD.BA",
    # Belo — crypto
    "BTC": "BTC-USD", "ETH": "ETH-USD",
}


def resolve_yf_symbol(ticker, is_cedear):
    """Return the Yahoo Finance symbol for a holding.

    CEDEARs trade on BYMA in ARS under "<ticker>.BA" — a different
    instrument from the underlying US stock, so they can't share an entry
    in YF_TICKER_MAP with the direct (USD) version of the same ticker
    (e.g. AMD is held directly at BECA Vestiva and as a CEDEAR at TM
    Inversiones).
    """
    if is_cedear:
        return f"{ticker}.BA"
    return YF_TICKER_MAP.get(ticker)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__)


# ── DB helpers ────────────────────────────────────────────────────────
def ensure_schema():
    """Bring an older DB up to date. Additive only, safe on every startup."""
    conn = sqlite3.connect(str(DB_PATH))
    # Tells apart a ticker's direct holding (USD) from its CEDEAR (ARS) —
    # see resolve_yf_symbol().
    cols = [row[1] for row in conn.execute("PRAGMA table_info(prices)").fetchall()]
    if "is_cedear" not in cols:
        conn.execute("ALTER TABLE prices ADD COLUMN is_cedear INTEGER DEFAULT 0")
        conn.commit()

    holding_cols = [row[1] for row in conn.execute("PRAGMA table_info(holdings)").fetchall()]
    if "is_adr" not in holding_cols:
        conn.execute("ALTER TABLE holdings ADD COLUMN is_adr INTEGER DEFAULT 0")
        conn.commit()

    # Derived from sources.ADR_MAP on every startup rather than loaded by
    # hand, so adding a mapping is the only edit needed to mark a new ADR.
    # Clearing first is what makes dropping a mapping unmark it too.
    adr_symbols = sorted(set(sources.ADR_MAP.values()))
    conn.execute("UPDATE holdings SET is_adr = 0 WHERE is_adr = 1")
    if adr_symbols:
        conn.execute(
            "UPDATE holdings SET is_adr = 1 WHERE is_cedear = 0 AND ticker IN "
            f"({','.join('?' * len(adr_symbols))})",
            adr_symbols,
        )
    conn.commit()

    # Cache for /api/insight, keyed by the resolved company symbol so a
    # CEDEAR and its direct holding share one entry.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS insights (
            symbol TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    # Cache for /api/earnings, one row per company symbol per local day. A
    # symbol with nothing scheduled is stored as JSON null rather than left
    # out, so it isn't re-fetched on every page load.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS earnings (
            symbol TEXT PRIMARY KEY,
            payload TEXT,
            fetched_on TEXT NOT NULL
        )
    """)
    # YouTube results, same shape and same per-day rule. Empty results are
    # stored too: a symbol with no whitelisted coverage would otherwise spend
    # 100 quota units every time the panel opens.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            symbol TEXT PRIMARY KEY,
            payload TEXT,
            fetched_on TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def get_holdings():
    """Return all holdings with latest price per (ticker, is_cedear)."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT h.ticker, h.company, h.shares, h.sector, h.broker,
               h.is_cedear, h.is_crypto, h.is_adr, h.cedear_ratio,
               p.price, p.currency, p.recorded_at
        FROM holdings h
        LEFT JOIN (
            SELECT ticker, is_cedear, price, currency, recorded_at
            FROM prices
            WHERE (ticker, is_cedear, recorded_at) IN (
                SELECT ticker, is_cedear, MAX(recorded_at)
                FROM prices
                GROUP BY ticker, is_cedear
            )
        ) p ON h.ticker = p.ticker AND h.is_cedear = p.is_cedear
        ORDER BY h.broker, h.ticker
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_ticker_pairs():
    """Return distinct (ticker, is_cedear) pairs across all holdings."""
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT ticker, is_cedear FROM holdings")
    pairs = [(row[0], bool(row[1])) for row in cur.fetchall()]
    conn.close()
    return pairs


def save_price(ticker, is_cedear, price, currency="USD"):
    """Insert a fresh price record."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "INSERT INTO prices (ticker, is_cedear, price, currency) VALUES (?, ?, ?, ?)",
        (ticker, int(is_cedear), price, currency),
    )
    conn.commit()
    conn.close()


def read_insight_cache(symbol):
    """Cached insight payload for a symbol, or None when absent or stale."""
    ttl_hours = float(os.environ.get("INSIGHT_TTL_HOURS", 6))
    conn = sqlite3.connect(str(DB_PATH))
    row = conn.execute(
        "SELECT payload FROM insights WHERE symbol = ? "
        "AND created_at > datetime('now', ?)",
        (symbol, f"-{ttl_hours} hours"),
    ).fetchone()
    conn.close()
    return json.loads(row[0]) if row else None


def write_insight_cache(symbol, payload):
    """Store an insight payload, replacing any previous one for the symbol."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "INSERT INTO insights (symbol, payload, created_at) "
        "VALUES (?, ?, datetime('now')) "
        "ON CONFLICT(symbol) DO UPDATE SET "
        "payload = excluded.payload, created_at = excluded.created_at",
        (symbol, json.dumps(payload)),
    )
    conn.commit()
    conn.close()


def read_earnings_cache(symbol):
    """(hit, summary) for today's entry, if there is one.

    The hit flag is separate from the value because a cached None — a symbol
    with nothing scheduled — is an answer, not a miss.
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
    """Store a summary against today, replacing any earlier entry."""
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
    """ARS or USD for a holding, without needing a price row to exist.

    Currency normally comes from the latest price, but a holding added
    before its first refresh has none — and defaulting to USD there would
    turn ALUA into a US stock, so fall back to what the ticker maps to.
    """
    if holding["currency"]:
        return holding["currency"]
    symbol = resolve_yf_symbol(holding["ticker"], bool(holding["is_cedear"]))
    return "ARS" if symbol and symbol.endswith(".BA") else "USD"


def earnings_symbols():
    """Company symbol → the ticker and name to display for it.

    Crypto is skipped outright; it has no balance sheet. Holdings that
    resolve to the same symbol collapse into one entry — a CEDEAR with its
    direct holding, an ADR with its local BYMA share — preferring the
    holding whose ticker *is* the symbol, so PAM/PAMP displays as "PAM".
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


def read_videos_cache(symbol):
    """(hit, videos) for today's entry — same rule as read_earnings_cache."""
    conn = sqlite3.connect(str(DB_PATH))
    row = conn.execute(
        "SELECT payload FROM videos WHERE symbol = ? "
        "AND fetched_on = date('now', 'localtime')",
        (symbol,),
    ).fetchone()
    conn.close()
    return (True, json.loads(row[0])) if row else (False, None)


def write_videos_cache(symbol, videos):
    """Store a video list against today, replacing any earlier entry."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "INSERT INTO videos (symbol, payload, fetched_on) "
        "VALUES (?, ?, date('now', 'localtime')) "
        "ON CONFLICT(symbol) DO UPDATE SET "
        "payload = excluded.payload, fetched_on = excluded.fetched_on",
        (symbol, json.dumps(videos)),
    )
    conn.commit()
    conn.close()


def company_for_symbol(symbol):
    """Display name for a resolved symbol, or None when it isn't held.

    Reuses earnings_symbols() so the symbol-to-company rule — including the
    CEDEAR and ADR collapsing — lives in exactly one place.
    """
    return (earnings_symbols().get(symbol) or {}).get("company")


def gather_videos(symbol):
    """(videos, error) for one symbol, cached for the local day.

    Returns an error string rather than raising: YouTube is a secondary
    source, and the panel must keep showing earnings and news whether or not
    it is configured or reachable.
    """
    hit, cached = read_videos_cache(symbol)
    if hit:
        return cached, None

    # youtube.py reports what broke; the wording the panel shows is decided
    # here, so the module is not in the business of writing UI copy.
    try:
        videos = youtube.fetch_videos(symbol, company_for_symbol(symbol))
    except youtube.NotConfigured:
        # Not cached: a key added later should take effect on the next
        # request, not the next day.
        return [], "Configurá YOUTUBE_API_KEY en .env para ver videos."
    except youtube.YouTubeError as exc:
        log.warning("YouTube failed for %s: %s", symbol, exc)
        return [], f"No se pudieron consultar los videos: {exc}"

    write_videos_cache(symbol, videos)
    return videos, None


def days_until(date_text, today):
    """Whole days from today to an ISO date, or None when unparseable."""
    try:
        return (date.fromisoformat(str(date_text)[:10]) - today).days
    except (TypeError, ValueError):
        return None


# ── Price update ──────────────────────────────────────────────────────
def refresh_prices(pairs=None):
    """Fetch latest prices from Yahoo Finance for the given (ticker, is_cedear) pairs."""
    if pairs is None:
        pairs = get_ticker_pairs()

    results = {}
    errors = []
    symbol_to_pair = {}
    for ticker, is_cedear in pairs:
        symbol = resolve_yf_symbol(ticker, is_cedear)
        if symbol:
            symbol_to_pair[symbol] = (ticker, is_cedear)

    yf_symbols = list(symbol_to_pair.keys())
    if not yf_symbols:
        return results, errors

    log.info("Refreshing %d symbols via yfinance …", len(yf_symbols))
    try:
        data = yf.download(yf_symbols, period="1d", progress=False, auto_adjust=True, group_by="ticker")
        is_multi = isinstance(data.columns, pd.MultiIndex)

        for symbol in yf_symbols:
            try:
                if is_multi and data.columns.nlevels >= 2:
                    close_col = "Adj Close" if "Adj Close" in data.columns.levels[1] else "Close"
                    if (symbol, close_col) in data.columns:
                        series = data[(symbol, close_col)].dropna()
                    elif (symbol, "Close") in data.columns:
                        series = data[(symbol, "Close")].dropna()
                    else:
                        series = None
                else:
                    series = data.get(symbol, pd.Series(dtype=float)).dropna()

                price = float(series.iloc[-1]) if series is not None and not series.empty else None
            except Exception as exc:
                log.debug("Error parsing %s: %s", symbol, exc)
                price = None

            ticker, is_cedear = symbol_to_pair[symbol]
            if price is not None and price > 0:
                currency = "USD" if ".BA" not in symbol else "ARS"
                save_price(ticker, is_cedear, price, currency)
                results[(ticker, is_cedear)] = price
            else:
                errors.append(symbol)
    except Exception as e:
        log.warning("yfinance bulk failed: %s — trying individual fetches", e)
        for symbol, (ticker, is_cedear) in symbol_to_pair.items():
            try:
                tk = yf.Ticker(symbol)
                price = tk.fast_info.last_price
                if price is not None and price > 0:
                    currency = "USD" if ".BA" not in symbol else "ARS"
                    save_price(ticker, is_cedear, price, currency)
                    results[(ticker, is_cedear)] = price
                else:
                    errors.append(symbol)
            except Exception as e2:
                log.warning("Failed to fetch %s: %s", symbol, e2)
                errors.append(symbol)

    if errors:
        log.warning("Could not fetch prices for: %s", ", ".join(errors))
    return results, errors


# ── Routes ────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_file(os.path.join(os.path.dirname(__file__), "index.html"))


@app.route("/api/portfolio")
def api_portfolio():
    holdings = get_holdings()
    auto_refresh = request.args.get("refresh", "true").lower() == "true"

    if auto_refresh:
        pairs = list({(h["ticker"], bool(h["is_cedear"])) for h in holdings})
        refresh_prices(pairs)
        holdings = get_holdings()

    # Build response. Totals are kept per currency, never summed together —
    # a USD balance and an ARS balance aren't the same unit, so adding them
    # would produce a number that doesn't represent real money.
    brokers = {}
    totals_by_currency = {}
    for h in holdings:
        broker = h["broker"] or "Sin broker"
        currency = h["currency"] or "USD"
        if broker not in brokers:
            brokers[broker] = {"holdings": [], "totals": {}}
        value = (h["shares"] or 0) * (h["price"] or 0)
        brokers[broker]["holdings"].append({
            "ticker": h["ticker"],
            "company": h["company"] or h["ticker"],
            "shares": h["shares"] or 0,
            "sector": h["sector"] or "—",
            "price": round(h["price"], 2) if h["price"] else 0,
            "currency": currency,
            "value": round(value, 2),
            "is_cedear": bool(h["is_cedear"]),
            "is_crypto": bool(h["is_crypto"]),
            "is_adr": bool(h["is_adr"]),
            "updated_at": h["recorded_at"] or "—",
        })
        brokers[broker]["totals"][currency] = brokers[broker]["totals"].get(currency, 0) + value
        totals_by_currency[currency] = totals_by_currency.get(currency, 0) + value

    # Pie chart data — aggregate by (ticker, is_cedear) across brokers.
    # A ticker held both directly (USD) and as a CEDEAR (ARS) — e.g. AMD at
    # BECA Vestiva vs. TM Inversiones — is a different instrument in a
    # different currency, so it must not collapse into one slice.
    pie_agg = {}
    pie_labels = {}
    for h in holdings:
        key = (h["ticker"], bool(h["is_cedear"]))
        value = (h["shares"] or 0) * (h["price"] or 0)
        pie_agg[key] = pie_agg.get(key, 0) + value
        if key not in pie_labels:
            pie_labels[key] = h.get("company") or h["ticker"]
            if h.get("is_cedear"):
                pie_labels[key] += " (CEDEAR)"
            elif h.get("is_adr"):
                pie_labels[key] += " (ADR)"

    return jsonify({
        "brokers": {
            name: {
                "holdings": data["holdings"],
                "totals": {cur: round(v, 2) for cur, v in data["totals"].items()},
            }
            for name, data in brokers.items()
        },
        "pie": [
            {"label": f"{t} ({pie_labels[(t, c)]})", "value": round(v, 2)}
            for (t, c), v in sorted(pie_agg.items(), key=lambda x: -x[1])
        ],
        "totals": {cur: round(v, 2) for cur, v in totals_by_currency.items()},
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })


@app.route("/api/refresh")
def api_refresh():
    """Force a price refresh for all holdings."""
    pairs = get_ticker_pairs()
    results, errors = refresh_prices(pairs)
    return jsonify({
        "ok": True,
        "updated": [f"{t}.BA" if c else t for (t, c) in results.keys()],
        "failed": errors,
        "count": len(results),
    })


@app.route("/api/insight/<ticker>")
def api_insight(ticker):
    """News and earnings for one holding, summarized by the configured model.

    The flags come from the caller because the frontend already knows them;
    they decide which company the ticker refers to (see
    sources.resolve_insight_symbol).
    """
    is_cedear = request.args.get("is_cedear", "").lower() in ("1", "true")
    is_crypto = request.args.get("is_crypto", "").lower() in ("1", "true")
    currency = request.args.get("currency") or "USD"
    symbol = sources.resolve_insight_symbol(ticker, is_cedear, is_crypto, currency)

    cached = read_insight_cache(symbol)
    if cached is not None:
        cached["cached"] = True
        return jsonify(cached)

    data = sources.gather(symbol)

    # Videos are deliberately kept out of `data`: `data` is what goes to the
    # model, and a model cannot watch a video. It would receive only titles
    # and end up asserting things about content nobody saw.
    videos, videos_error = gather_videos(symbol)
    extra = {"videos": videos}
    if videos_error:
        extra["videos_error"] = videos_error

    # The gathered data is returned even on failure so the panel can still
    # show news and earnings dates without a working model.
    try:
        provider = llm.get_provider()
    except llm.ProviderNotConfigured as exc:
        return jsonify({"error": str(exc), "symbol": symbol, **data, **extra}), 503

    system, user = llm.build_insight_prompt(symbol, data)
    try:
        summary = provider.summarize(system, user)
    except llm.ProviderError as exc:
        return jsonify({"error": str(exc), "symbol": symbol, **data, **extra}), 502

    payload = {
        "symbol": symbol,
        "summary": summary,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        **data,
        **extra,
    }
    write_insight_cache(symbol, payload)
    payload["cached"] = False
    return jsonify(payload)


@app.route("/api/earnings")
def api_earnings():
    """Upcoming earnings dates across the portfolio, nearest first.

    Every symbol has to be asked before the nearest ones are known, so the
    whole portfolio is fetched and cached for the day; `limit` only trims
    what comes back, it saves no requests.
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
        # Yahoo sometimes serves a date it has not rolled forward yet; a
        # balance already reported is not an upcoming one.
        if remaining is not None and remaining < 0:
            continue
        rows.append({"symbol": symbol, "days_until": remaining, **meta, **summary})

    rows.sort(key=lambda row: row["next_date"])
    return jsonify({
        "rows": rows[:limit] if limit > 0 else rows,
        "fetched_on": today.isoformat(),
        "cached": all_cached,
    })


# ── Entry point ──────────────────────────────────────────────────────
if __name__ == "__main__":
    log.info("Starting portfolio dashboard on http://%s:%d", HOST, PORT)
    log.info("DB: %s", DB_PATH)
    ensure_schema()
    app.run(host=HOST, port=PORT, debug=False)
