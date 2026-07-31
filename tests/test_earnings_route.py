import sqlite3

import pytest


def insert_holding(db, ticker, broker, is_cedear=0, is_crypto=0, company=None):
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO holdings (ticker, company, shares, broker, is_cedear, is_crypto) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (ticker, company or ticker, 10, broker, is_cedear, is_crypto),
    )
    conn.commit()
    conn.close()


# ---- is_adr, derived from sources.ADR_MAP ----

def test_is_adr_is_derived_from_the_map(app_module):
    insert_holding(app_module.DB_PATH, "PAM", "BECA Vestiva")
    insert_holding(app_module.DB_PATH, "PAMP", "TM Inversiones")
    app_module.ensure_schema()

    flags = {h["ticker"]: h["is_adr"] for h in app_module.get_holdings()}
    assert flags["PAM"] == 1
    # The local share is not the ADR — only the US listing carries the flag.
    assert flags["PAMP"] == 0


def test_removing_a_mapping_unmarks_the_holding(app_module, monkeypatch):
    # The flag is derived, so the map staying the only place to edit depends
    # on stale marks being cleared.
    insert_holding(app_module.DB_PATH, "PAM", "BECA Vestiva")
    app_module.ensure_schema()

    monkeypatch.setattr(app_module.sources, "ADR_MAP", {})
    app_module.ensure_schema()
    assert app_module.get_holdings()[0]["is_adr"] == 0


# ---- /api/earnings ----

@pytest.fixture
def asked(app_module, monkeypatch):
    """Records the symbols looked up, and answers from a fixed table.

    Returns the call list so tests can assert on what reached the network
    layer — that is how caching and the crypto skip are checked.
    """
    calls = []
    answers = {
        "AMD": {"next_date": "2099-08-04", "eps_estimate": 1.61,
                "last_date": "2026-05-05", "last_eps_reported": 1.37,
                "last_surprise_pct": 5.82},
        "PAM": {"next_date": "2099-08-10", "eps_estimate": 2.52,
                "last_date": "2026-05-06", "last_eps_reported": 3.9,
                "last_surprise_pct": 139.88},
        "MSFT": {"next_date": "2099-10-28", "eps_estimate": 4.68,
                 "last_date": "2026-07-29", "last_eps_reported": 4.74,
                 "last_surprise_pct": 11.81},
    }

    def fake(symbol):
        calls.append(symbol)
        return answers.get(symbol)

    monkeypatch.setattr(app_module.sources, "fetch_earnings_summary", fake)
    return calls


def test_rows_come_back_nearest_first(app_module, client, asked):
    insert_holding(app_module.DB_PATH, "MSFT", "BECA Vestiva")
    insert_holding(app_module.DB_PATH, "AMD", "BECA Vestiva")
    rows = client.get("/api/earnings").get_json()["rows"]
    assert [r["ticker"] for r in rows] == ["AMD", "MSFT"]


def test_symbols_without_a_date_are_excluded(app_module, client, asked):
    insert_holding(app_module.DB_PATH, "AMD", "BECA Vestiva")
    insert_holding(app_module.DB_PATH, "ALUA", "TM Inversiones")
    rows = client.get("/api/earnings").get_json()["rows"]
    assert [r["ticker"] for r in rows] == ["AMD"]


def test_crypto_is_never_asked(app_module, client, asked):
    insert_holding(app_module.DB_PATH, "BTC", "Belo", is_crypto=1)
    client.get("/api/earnings")
    assert asked == []


def test_cedear_and_direct_holding_make_one_row(app_module, client, asked):
    insert_holding(app_module.DB_PATH, "AMD", "BECA Vestiva")
    insert_holding(app_module.DB_PATH, "AMD", "TM Inversiones", is_cedear=1)
    rows = client.get("/api/earnings").get_json()["rows"]
    assert len(rows) == 1
    assert asked == ["AMD"]


def test_adr_and_local_share_make_one_row_shown_as_the_adr(app_module, client, asked):
    insert_holding(app_module.DB_PATH, "PAM", "BECA Vestiva", company="Pampa")
    insert_holding(app_module.DB_PATH, "PAMP", "TM Inversiones", company="Pampa Energia")
    rows = client.get("/api/earnings").get_json()["rows"]
    assert len(rows) == 1
    assert rows[0]["ticker"] == "PAM"
    assert rows[0]["symbol"] == "PAM"


def test_share_classes_make_one_row(app_module, client, monkeypatch):
    monkeypatch.setattr(
        app_module.sources, "fetch_earnings_summary",
        lambda symbol: {"next_date": "2099-10-28", "eps_estimate": 2.31,
                        "last_date": "2026-07-29", "last_eps_reported": 2.5,
                        "last_surprise_pct": 8.2} if symbol == "GOOG" else None,
    )
    insert_holding(app_module.DB_PATH, "GOOG", "BECA Vestiva", company="Alphabet")
    insert_holding(app_module.DB_PATH, "GOOGL", "TM Inversiones", is_cedear=1,
                   company="Alphabet Inc")
    rows = client.get("/api/earnings").get_json()["rows"]
    assert len(rows) == 1
    assert rows[0]["ticker"] == "GOOG"


def test_share_class_holdings_are_not_marked_as_adrs(app_module, client):
    insert_holding(app_module.DB_PATH, "GOOG", "BECA Vestiva")
    app_module.ensure_schema()
    assert app_module.get_holdings()[0]["is_adr"] == 0


def test_a_holding_with_no_price_row_still_resolves_to_byma(app_module, client, asked):
    # Currency comes from the latest price, which may not exist yet; falling
    # back to USD would turn ALUA into a US stock and ask Yahoo for "ALUA".
    insert_holding(app_module.DB_PATH, "ALUA", "TM Inversiones")
    client.get("/api/earnings")
    assert asked == ["ALUA.BA"]


def test_second_call_uses_the_cache(app_module, client, asked):
    insert_holding(app_module.DB_PATH, "AMD", "BECA Vestiva")
    client.get("/api/earnings")
    body = client.get("/api/earnings").get_json()
    assert asked == ["AMD"]
    assert body["cached"] is True


def test_symbols_without_a_date_are_cached_too(app_module, client, asked):
    # Otherwise every page load re-asks Yahoo for the uncovered symbols,
    # which is the cost the cache exists to avoid.
    insert_holding(app_module.DB_PATH, "ALUA", "TM Inversiones")
    client.get("/api/earnings")
    client.get("/api/earnings")
    assert asked == ["ALUA.BA"]


def test_a_stale_entry_is_refetched(app_module, client, asked):
    insert_holding(app_module.DB_PATH, "AMD", "BECA Vestiva")
    client.get("/api/earnings")

    conn = sqlite3.connect(app_module.DB_PATH)
    conn.execute("UPDATE earnings SET fetched_on = '2020-01-01'")
    conn.commit()
    conn.close()

    client.get("/api/earnings")
    assert asked == ["AMD", "AMD"]


def test_refresh_bypasses_a_fresh_cache(app_module, client, asked):
    insert_holding(app_module.DB_PATH, "AMD", "BECA Vestiva")
    client.get("/api/earnings")
    body = client.get("/api/earnings?refresh=true").get_json()
    assert asked == ["AMD", "AMD"]
    assert body["cached"] is False


def test_limit_trims_the_rows(app_module, client, asked):
    insert_holding(app_module.DB_PATH, "AMD", "BECA Vestiva")
    insert_holding(app_module.DB_PATH, "MSFT", "BECA Vestiva")
    rows = client.get("/api/earnings?limit=1").get_json()["rows"]
    assert [r["ticker"] for r in rows] == ["AMD"]


def test_dates_already_past_are_dropped(app_module, client, monkeypatch):
    # Yahoo sometimes still reports a date that has been and gone; it is not
    # an upcoming balance.
    monkeypatch.setattr(
        app_module.sources, "fetch_earnings_summary",
        lambda symbol: {"next_date": "2020-01-01", "eps_estimate": None,
                        "last_date": None, "last_eps_reported": None,
                        "last_surprise_pct": None},
    )
    insert_holding(app_module.DB_PATH, "AMD", "BECA Vestiva")
    assert client.get("/api/earnings").get_json()["rows"] == []


def test_days_until_is_counted_from_today(app_module, client, asked):
    from datetime import date
    insert_holding(app_module.DB_PATH, "AMD", "BECA Vestiva")
    row = client.get("/api/earnings").get_json()["rows"][0]
    assert row["days_until"] == (date(2099, 8, 4) - date.today()).days


# ---- ADR marking in /api/portfolio ----

def test_portfolio_marks_adr_holdings(app_module, client):
    insert_holding(app_module.DB_PATH, "PAM", "BECA Vestiva", company="Pampa")
    app_module.ensure_schema()

    body = client.get("/api/portfolio?refresh=false").get_json()
    holding = body["brokers"]["BECA Vestiva"]["holdings"][0]
    assert holding["is_adr"] is True
    assert "(ADR)" in body["pie"][0]["label"]


def test_portfolio_leaves_plain_us_stocks_unmarked(app_module, client):
    insert_holding(app_module.DB_PATH, "AMD", "BECA Vestiva")
    app_module.ensure_schema()

    body = client.get("/api/portfolio?refresh=false").get_json()
    assert body["brokers"]["BECA Vestiva"]["holdings"][0]["is_adr"] is False
    assert "(ADR)" not in body["pie"][0]["label"]
