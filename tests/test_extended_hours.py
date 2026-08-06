import time

import pytest


def holding(ticker, is_cedear=0, is_crypto=0):
    return {"ticker": ticker, "is_cedear": is_cedear, "is_crypto": is_crypto}


class FakeTicker:
    """Stands in for yf.Ticker, serving a canned .info per symbol."""

    infos = {}
    asked = []

    def __init__(self, symbol):
        self.symbol = symbol
        FakeTicker.asked.append(symbol)

    @property
    def info(self):
        return FakeTicker.infos.get(self.symbol, {})


@pytest.fixture
def fake_yf(app_module, monkeypatch):
    FakeTicker.infos = {}
    FakeTicker.asked = []
    monkeypatch.setattr(app_module.yf, "Ticker", FakeTicker)
    return FakeTicker


def info(state, price, pct, age_hours=0.0, has_data=True):
    """A Yahoo .info payload for the given session state."""
    stamp = int(time.time() - age_hours * 3600)
    payload = {"hasPrePostMarketData": has_data, "marketState": state}
    if state == "PRE":
        payload.update(
            {"preMarketPrice": price, "preMarketChangePercent": pct, "preMarketTime": stamp}
        )
    elif state in ("POST", "POSTPOST"):
        payload.update(
            {"postMarketPrice": price, "postMarketChangePercent": pct, "postMarketTime": stamp}
        )
    return payload


def test_premarket_session_is_reported(app_module, fake_yf):
    fake_yf.infos["MSFT"] = info("PRE", 313.98, 0.9582029)

    out = app_module.fetch_extended_hours([holding("MSFT")])

    assert out == {"MSFT": {"session": "pre", "price": 313.98, "change_pct": 0.96}}


def test_postmarket_session_is_reported(app_module, fake_yf):
    fake_yf.infos["MSFT"] = info("POST", 305.5, -1.7712)

    out = app_module.fetch_extended_hours([holding("MSFT")])

    assert out == {"MSFT": {"session": "post", "price": 305.5, "change_pct": -1.77}}


def test_postpost_still_reports_the_last_after_hours_print(app_module, fake_yf):
    """Yahoo serves the closing after-hours quote all night; we keep showing it."""
    fake_yf.infos["MSFT"] = info("POSTPOST", 305.5, -1.77, age_hours=6)

    out = app_module.fetch_extended_hours([holding("MSFT")])

    assert out["MSFT"]["session"] == "post"


def test_regular_session_reports_nothing(app_module, fake_yf):
    fake_yf.infos["MSFT"] = info("PRE", 313.98, 0.95)
    fake_yf.infos["MSFT"]["marketState"] = "REGULAR"

    assert app_module.fetch_extended_hours([holding("MSFT")]) == {}


def test_closed_state_reports_nothing(app_module, fake_yf):
    fake_yf.infos["MSFT"] = {"hasPrePostMarketData": True, "marketState": "CLOSED"}

    assert app_module.fetch_extended_hours([holding("MSFT")]) == {}


def test_stale_quote_is_dropped(app_module, fake_yf):
    """Friday's after-hours print must not still be on screen on Saturday."""
    fake_yf.infos["MSFT"] = info("POSTPOST", 305.5, -1.77, age_hours=40)

    assert app_module.fetch_extended_hours([holding("MSFT")]) == {}


def test_quote_without_a_timestamp_is_kept(app_module, fake_yf):
    """Missing metadata shouldn't hide a quote Yahoo is actively serving."""
    payload = info("POST", 305.5, -1.77)
    del payload["postMarketTime"]
    fake_yf.infos["MSFT"] = payload

    assert app_module.fetch_extended_hours([holding("MSFT")])["MSFT"]["price"] == 305.5


def test_missing_percent_leaves_change_pct_none(app_module, fake_yf):
    payload = info("POST", 305.5, None)
    fake_yf.infos["MSFT"] = payload

    assert app_module.fetch_extended_hours([holding("MSFT")])["MSFT"]["change_pct"] is None


def test_symbols_without_prepost_coverage_are_skipped(app_module, fake_yf):
    fake_yf.infos["MSFT"] = info("POST", 305.5, -1.77, has_data=False)

    assert app_module.fetch_extended_hours([holding("MSFT")]) == {}


def test_crypto_and_byma_only_holdings_are_never_queried(app_module, fake_yf):
    holdings = [holding("BTC", is_crypto=1), holding("ALUA"), holding("MSFT")]
    fake_yf.infos["MSFT"] = info("POST", 305.5, -1.77)

    app_module.fetch_extended_hours(holdings)

    assert fake_yf.asked == ["MSFT"]


def test_cedear_resolves_to_its_us_underlying(app_module, fake_yf):
    """AAPL isn't in YF_TICKER_MAP — a CEDEAR doesn't need to be."""
    fake_yf.infos["AAPL"] = info("POST", 305.5, -1.77)

    out = app_module.fetch_extended_hours([holding("AAPL", is_cedear=1)])

    assert fake_yf.asked == ["AAPL"]
    assert out["AAPL"]["session"] == "post"


def test_a_symbol_held_twice_is_queried_once(app_module, fake_yf):
    """AMD is held directly and as a CEDEAR; that's one Yahoo lookup, not two."""
    fake_yf.infos["AMD"] = info("POST", 475.0, -1.2)

    app_module.fetch_extended_hours([holding("AMD"), holding("AMD", is_cedear=1)])

    assert fake_yf.asked == ["AMD"]


def test_a_failing_symbol_doesnt_abort_the_others(app_module, fake_yf):
    class Exploding(FakeTicker):
        @property
        def info(self):
            if self.symbol == "MSFT":
                raise RuntimeError("Yahoo said no")
            return FakeTicker.infos.get(self.symbol, {})

    fake_yf.infos["AMD"] = info("POST", 475.0, -1.2)
    app_module.yf.Ticker = Exploding

    out = app_module.fetch_extended_hours([holding("MSFT"), holding("AMD")])

    assert list(out) == ["AMD"]
