#!/usr/bin/env python3
"""Data sources for the per-ticker insight module.

Everything here runs in-process rather than through a provider's server-side
web search, because a locally-hosted model has no such tool — that is what
keeps the LLM layer interchangeable.

Coverage is uneven across the portfolio (ALUA.BA has no news, BTC-USD has no
income statement), so each fetcher degrades on its own and returns an empty
result instead of aborting the whole request.
"""

import logging
import math

import yfinance as yf

log = logging.getLogger(__name__)


# Local BYMA ticker -> US ADR symbol. An ADR and its local share are one
# company filing one balance, but Yahoo answers for both listings with the
# same date and the EPS in each listing's currency (PAM 2.52 USD against
# PAMP.BA 145.62 ARS), so without this map one balance reads as two.
ADR_MAP = {
    "PAMP": "PAM",
    "YPFD": "YPF",
}


def resolve_insight_symbol(ticker, is_cedear, is_crypto, currency):
    """Return the Yahoo Finance symbol for the underlying *company*.

    This deliberately inverts resolve_yf_symbol() in app.py: for prices, a
    CEDEAR and its direct US holding are different instruments in different
    currencies, but for news and earnings they are the same company — so a
    CEDEAR resolves to the bare US ticker rather than "<ticker>.BA".
    ADR_MAP extends the same idea to Argentine companies listed in both
    places under different tickers.
    """
    if is_crypto:
        return f"{ticker}-USD"
    if is_cedear:
        return ticker
    if ticker in ADR_MAP:
        return ADR_MAP[ticker]
    if currency == "ARS":
        return f"{ticker}.BA"
    return ticker


def _clean_number(value):
    """Float, or None for missing/NaN — NaN is not JSON-serializable."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def _first_url(content):
    """Pull a link out of a news item — yfinance moves the key around."""
    for key in ("canonicalUrl", "clickThroughUrl", "previewUrl", "link"):
        value = content.get(key)
        if isinstance(value, dict):
            value = value.get("url")
        if value:
            return value
    return None


def fetch_news(symbol, limit=8):
    """Recent news items. Empty list when the symbol has no coverage."""
    try:
        raw = yf.Ticker(symbol).news or []
    except Exception as exc:
        log.warning("news fetch failed for %s: %s", symbol, exc)
        return []

    items = []
    for entry in raw[:limit]:
        # Current yfinance nests the payload under "content"; older versions
        # return it flat.
        content = entry.get("content") or entry
        provider = content.get("provider")
        items.append({
            "title": content.get("title"),
            "summary": content.get("summary") or content.get("description"),
            "published": content.get("pubDate") or content.get("displayTime"),
            "publisher": provider.get("displayName") if isinstance(provider, dict) else provider,
            "url": _first_url(content),
        })
    return items


def fetch_earnings_calendar(symbol):
    """Next earnings date plus analyst estimates, or None if unavailable."""
    try:
        calendar = yf.Ticker(symbol).calendar or {}
    except Exception as exc:
        log.warning("calendar fetch failed for %s: %s", symbol, exc)
        return None

    dates = calendar.get("Earnings Date") or []
    if not dates:
        return None
    return {
        "date": str(dates[0]),
        "eps_estimate": _clean_number(calendar.get("Earnings Average")),
        "revenue_estimate": _clean_number(calendar.get("Revenue Average")),
    }


def fetch_earnings_history(symbol, limit=8):
    """Past quarters: estimated vs reported EPS and the surprise.

    Rows with a NaN reported EPS are quarters that have not reported yet;
    they are dropped because fetch_earnings_calendar() already covers what
    is coming.
    """
    try:
        frame = yf.Ticker(symbol).earnings_dates
    except Exception as exc:
        log.warning("earnings history fetch failed for %s: %s", symbol, exc)
        return []
    if frame is None or frame.empty:
        return []

    rows = []
    for index, row in frame.iterrows():
        reported = _clean_number(row.get("Reported EPS"))
        if reported is None:
            continue
        rows.append({
            "date": str(index.date()) if hasattr(index, "date") else str(index),
            "eps_estimate": _clean_number(row.get("EPS Estimate")),
            "eps_reported": reported,
            "surprise_pct": _clean_number(row.get("Surprise(%)")),
        })
        if len(rows) >= limit:
            break
    return rows


def fetch_earnings_summary(symbol):
    """Next earnings date plus the last reported quarter, or None.

    None means nothing is scheduled — the single place where the calendar
    window's rule for dropping a symbol is decided.
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


def fetch_fundamentals(symbol, limit=4):
    """Revenue and net income per reported period."""
    try:
        frame = yf.Ticker(symbol).income_stmt
    except Exception as exc:
        log.warning("fundamentals fetch failed for %s: %s", symbol, exc)
        return []
    if frame is None or frame.empty:
        return []

    rows = []
    for period in list(frame.columns)[:limit]:
        rows.append({
            "period": str(period.date()) if hasattr(period, "date") else str(period),
            "total_revenue": (
                _clean_number(frame.loc["Total Revenue", period])
                if "Total Revenue" in frame.index else None
            ),
            "net_income": (
                _clean_number(frame.loc["Net Income", period])
                if "Net Income" in frame.index else None
            ),
        })
    return rows


def gather(symbol):
    """Every source for one symbol. Never raises."""
    return {
        "news": fetch_news(symbol),
        "earnings_calendar": fetch_earnings_calendar(symbol),
        "earnings_history": fetch_earnings_history(symbol),
        "fundamentals": fetch_fundamentals(symbol),
    }
