import json

import pytest

import sources


# ---- Symbol resolution (offline) ----

def test_cedear_resolves_to_bare_us_ticker():
    # Inverts resolve_yf_symbol(): for news/earnings a CEDEAR is the same
    # company as the direct holding, so no .BA suffix here.
    assert sources.resolve_insight_symbol("AMD", True, False, "ARS") == "AMD"


def test_direct_us_stock_resolves_to_itself():
    assert sources.resolve_insight_symbol("AMD", False, False, "USD") == "AMD"


def test_byma_stock_gets_ba_suffix():
    assert sources.resolve_insight_symbol("ALUA", False, False, "ARS") == "ALUA.BA"


def test_crypto_gets_usd_pair():
    assert sources.resolve_insight_symbol("BTC", False, True, "USD") == "BTC-USD"


def test_cedear_and_direct_share_one_symbol():
    # This is what lets both AMD holdings share a single cache entry.
    assert sources.resolve_insight_symbol("AMD", True, False, "ARS") == \
           sources.resolve_insight_symbol("AMD", False, False, "USD")


# ---- Fetchers (network) ----

@pytest.mark.network
def test_fetch_news_returns_shaped_items():
    items = sources.fetch_news("AMD")
    assert items, "AMD should have news coverage"
    first = items[0]
    assert set(first) == {"title", "summary", "published", "publisher", "url"}
    assert first["title"]


@pytest.mark.network
def test_fetch_news_degrades_when_uncovered():
    # ALUA.BA has no Yahoo news coverage — must return [], not raise.
    assert sources.fetch_news("ALUA.BA") == []


@pytest.mark.network
def test_fetch_fundamentals_degrades_for_crypto():
    # income_stmt 404s for BTC-USD; the fetcher swallows it.
    assert sources.fetch_fundamentals("BTC-USD") == []


@pytest.mark.network
def test_earnings_history_excludes_unreported_quarters():
    rows = sources.fetch_earnings_history("AMD")
    assert rows
    assert all(r["eps_reported"] is not None for r in rows)


@pytest.mark.network
def test_gather_is_json_serializable():
    # pandas emits NaN for missing numbers and NaN breaks jsonify —
    # _clean_number must strip it before the payload reaches Flask.
    json.dumps(sources.gather("AMD"))


@pytest.mark.network
def test_gather_never_raises_on_thin_symbol():
    data = sources.gather("ALUA.BA")
    assert set(data) == {"news", "earnings_calendar", "earnings_history", "fundamentals"}
