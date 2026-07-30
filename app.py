#!/usr/bin/env python3
"""
Portfolio Dashboard — Web panel for stock holdings visualization.
Reads from portfolio.db, fetches live prices via yfinance,
and serves a Bootstrap + Chart.js dashboard.
"""

import os
import sqlite3
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf
from flask import Flask, jsonify, request, send_file

# ── Config ────────────────────────────────────────────────────────────
DB_PATH = Path(os.environ.get("PORTFOLIO_DB", "/data/portfolio.db"))
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", 5050))

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
    """Add the is_cedear column to prices if migrating from an older DB.

    Needed to tell apart a ticker's direct holding (USD) from its CEDEAR
    (ARS) — see resolve_yf_symbol(). Additive only, safe to run every startup.
    """
    conn = sqlite3.connect(str(DB_PATH))
    cols = [row[1] for row in conn.execute("PRAGMA table_info(prices)").fetchall()]
    if "is_cedear" not in cols:
        conn.execute("ALTER TABLE prices ADD COLUMN is_cedear INTEGER DEFAULT 0")
        conn.commit()
    conn.close()


def get_holdings():
    """Return all holdings with latest price per (ticker, is_cedear)."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT h.ticker, h.company, h.shares, h.sector, h.broker,
               h.is_cedear, h.is_crypto, h.cedear_ratio,
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


# ── Entry point ──────────────────────────────────────────────────────
if __name__ == "__main__":
    log.info("Starting portfolio dashboard on http://%s:%d", HOST, PORT)
    log.info("DB: %s", DB_PATH)
    ensure_schema()
    app.run(host=HOST, port=PORT, debug=False)
