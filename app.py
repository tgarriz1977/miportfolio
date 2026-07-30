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

# Map local tickers to Yahoo Finance symbols
YF_TICKER_MAP = {
    # BECA Vestiva — US stocks (direct)
    "AMD": "AMD", "AMZN": "AMZN", "AVGO": "AVGO", "GOOG": "GOOG",
    "INTC": "INTC", "META": "META", "MSFT": "MSFT", "MU": "MU",
    "NU": "NU", "PLTR": "PLTR", "QCOM": "QCOM", "YPF": "YPF",
    "VIST": "VIST", "PAM": "PAM",
    # Balanz — CEDEARs (underlying US ticker)
    "ALAB": "ALAB", "ARM": "ARM", "ASTS": "ASTS", "IBM": "IBM",
    "RKLB": "RKLB", "MRVL": "MRVL",
    # TM Inversiones — CEDEARs (underlying US ticker)
    "ARKK": "ARKK", "GOOGL": "GOOGL",
    # TM Inversiones — Argentina stocks on BYMA (.BA)
    "ALUA": "ALUA.BA", "CEPU": "CEPU.BA", "ECOG": "ECOG.BA",
    "PAMP": "PAMP.BA", "TGNO4": "TGNO4.BA", "YPFD": "YPFD.BA",
    # Belo — crypto
    "BTC": "BTC-USD", "ETH": "ETH-USD",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__)


# ── DB helpers ────────────────────────────────────────────────────────
def get_holdings():
    """Return all holdings with latest price per ticker."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT h.ticker, h.company, h.shares, h.sector, h.broker,
               h.is_cedear, h.cedear_ratio,
               p.price, p.currency, p.recorded_at
        FROM holdings h
        LEFT JOIN (
            SELECT ticker, price, currency, recorded_at
            FROM prices
            WHERE (ticker, recorded_at) IN (
                SELECT ticker, MAX(recorded_at)
                FROM prices
                GROUP BY ticker
            )
        ) p ON h.ticker = p.ticker
        ORDER BY h.broker, h.ticker
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def save_price(ticker, price, currency="USD"):
    """Insert a fresh price record."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "INSERT INTO prices (ticker, price, currency) VALUES (?, ?, ?)",
        (ticker, price, currency),
    )
    conn.commit()
    conn.close()


# ── Price update ──────────────────────────────────────────────────────
def refresh_prices(all_tickers=None):
    """Fetch latest prices from Yahoo Finance for all known tickers."""
    if all_tickers is None:
        all_tickers = list(YF_TICKER_MAP.keys())

    results = {}
    errors = []
    yf_symbols = [YF_TICKER_MAP[t] for t in all_tickers if t in YF_TICKER_MAP]

    if not yf_symbols:
        return results, errors

    log.info("Refreshing %d tickers via yfinance …", len(yf_symbols))
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

            if price is not None and price > 0:
                local_ticker = [k for k, v in YF_TICKER_MAP.items() if v == symbol][0]
                currency = "USD" if ".BA" not in symbol else "ARS"
                save_price(local_ticker, price, currency)
                results[local_ticker] = price
            else:
                errors.append(symbol)
    except Exception as e:
        log.warning("yfinance bulk failed: %s — trying individual fetches", e)
        for ticker in all_tickers:
            symbol = YF_TICKER_MAP.get(ticker, ticker)
            try:
                tk = yf.Ticker(symbol)
                price = tk.fast_info.last_price
                if price is not None and price > 0:
                    currency = "USD" if ".BA" not in symbol else "ARS"
                    save_price(ticker, price, currency)
                    results[ticker] = price
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
        tickers = list({h["ticker"] for h in holdings if h["ticker"] in YF_TICKER_MAP})
        refresh_prices(tickers)
        holdings = get_holdings()

    # Build response
    brokers = {}
    for h in holdings:
        broker = h["broker"] or "Sin broker"
        if broker not in brokers:
            brokers[broker] = {"holdings": [], "total_value": 0.0}
        value = (h["shares"] or 0) * (h["price"] or 0)
        brokers[broker]["holdings"].append({
            "ticker": h["ticker"],
            "company": h["company"] or h["ticker"],
            "shares": h["shares"] or 0,
            "sector": h["sector"] or "—",
            "price": round(h["price"], 2) if h["price"] else 0,
            "currency": h["currency"] or "USD",
            "value": round(value, 2),
            "is_cedear": bool(h["is_cedear"]),
            "updated_at": h["recorded_at"] or "—",
        })
        brokers[broker]["total_value"] += value

    # Pie chart data — aggregate by ticker across brokers
    pie_agg = {}
    pie_labels = {}
    for h in holdings:
        t = h["ticker"]
        value = (h["shares"] or 0) * (h["price"] or 0)
        pie_agg[t] = pie_agg.get(t, 0) + value
        if t not in pie_labels:
            pie_labels[t] = h.get("company") or t
            if h.get("is_cedear"):
                pie_labels[t] += " (CEDEAR)"

    return jsonify({
        "brokers": {
            name: {
                "holdings": data["holdings"],
                "total_value": round(data["total_value"], 2),
            }
            for name, data in brokers.items()
        },
        "pie": [
            {"label": f"{t} ({pie_labels[t]})", "value": round(v, 2)}
            for t, v in sorted(pie_agg.items(), key=lambda x: -x[1])
        ],
        "grand_total": round(sum(b["total_value"] for b in brokers.values()), 2),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })


@app.route("/api/refresh")
def api_refresh():
    """Force a price refresh for all tickers."""
    tickers = list(YF_TICKER_MAP.keys())
    results, errors = refresh_prices(tickers)
    return jsonify({
        "ok": True,
        "updated": list(results.keys()),
        "failed": errors,
        "count": len(results),
    })


# ── Entry point ──────────────────────────────────────────────────────
if __name__ == "__main__":
    log.info("Starting portfolio dashboard on http://%s:%d", HOST, PORT)
    log.info("DB: %s", DB_PATH)
    app.run(host=HOST, port=PORT, debug=False)
