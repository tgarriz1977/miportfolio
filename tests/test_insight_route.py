import sqlite3

import pytest

import llm
import youtube


EMPTY = {"news": [], "earnings_calendar": None, "earnings_history": [], "fundamentals": []}

VIDEO = {"title": "AMD Q2", "channel": "Bloomberg",
         "published": "2026-07-29", "url": "https://www.youtube.com/watch?v=abc"}


class StubProvider:
    """Stands in for a real model — no credentials exist in this environment."""

    def __init__(self):
        self.calls = 0

    def summarize(self, system, user, max_tokens=4000):
        self.calls += 1
        return "resumen de prueba"


@pytest.fixture
def stub_sources(app_module, monkeypatch):
    """Keep route tests off the network and deterministic.

    YouTube defaults to unconfigured here — that is the state of the test
    environment, and the tests that care about videos override it.
    """
    monkeypatch.setattr(app_module.sources, "gather", lambda symbol: dict(EMPTY))
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    return app_module


@pytest.fixture
def stub_videos(stub_sources, monkeypatch):
    """Records the symbols searched, so caching can be asserted on."""
    calls = []

    def fake(symbol, company):
        calls.append(symbol)
        return [dict(VIDEO)]

    monkeypatch.setattr(stub_sources.youtube, "fetch_videos", fake)
    return calls


def test_returns_503_when_provider_unconfigured(stub_sources, client, monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    response = client.get("/api/insight/AMD?currency=USD")
    assert response.status_code == 503
    assert "LLM_PROVIDER" in response.get_json()["error"]


def test_503_still_returns_the_gathered_data(stub_sources, client, monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    body = client.get("/api/insight/AMD?currency=USD").get_json()
    # The panel can still show news and dates even with no model configured.
    assert body["symbol"] == "AMD"
    assert body["news"] == []


def test_provider_failure_returns_502(stub_sources, client, monkeypatch):
    class Failing:
        def summarize(self, system, user, max_tokens=4000):
            raise llm.ProviderError("conexión rechazada")

    monkeypatch.setattr(stub_sources.llm, "get_provider", lambda: Failing())
    response = client.get("/api/insight/AMD?currency=USD")
    assert response.status_code == 502
    assert "conexión rechazada" in response.get_json()["error"]


def test_happy_path_returns_summary(stub_sources, client, monkeypatch):
    monkeypatch.setattr(stub_sources.llm, "get_provider", lambda: StubProvider())
    body = client.get("/api/insight/AMD?currency=USD").get_json()
    assert body["summary"] == "resumen de prueba"
    assert body["cached"] is False
    assert body["generated_at"]


def test_cedear_and_direct_share_one_cache_entry(stub_sources, client, monkeypatch):
    stub = StubProvider()
    monkeypatch.setattr(stub_sources.llm, "get_provider", lambda: stub)

    first = client.get("/api/insight/AMD?currency=USD&is_cedear=0").get_json()
    assert first["cached"] is False

    # Same company, so the CEDEAR must hit the entry the direct holding wrote.
    second = client.get("/api/insight/AMD?currency=ARS&is_cedear=1").get_json()
    assert second["cached"] is True
    assert second["symbol"] == "AMD"
    assert stub.calls == 1


def test_byma_stock_does_not_share_the_us_cache_entry(stub_sources, client, monkeypatch):
    stub = StubProvider()
    monkeypatch.setattr(stub_sources.llm, "get_provider", lambda: stub)

    client.get("/api/insight/AMD?currency=USD&is_cedear=0")
    body = client.get("/api/insight/ALUA?currency=ARS&is_cedear=0").get_json()
    assert body["symbol"] == "ALUA.BA"
    assert body["cached"] is False
    assert stub.calls == 2


# ---- YouTube videos ----

def test_payload_carries_videos(stub_sources, client, stub_videos, monkeypatch):
    monkeypatch.setattr(stub_sources.llm, "get_provider", lambda: StubProvider())
    body = client.get("/api/insight/AMD?currency=USD").get_json()
    assert body["videos"] == [VIDEO]
    assert "videos_error" not in body


def test_missing_key_reports_it_without_losing_the_rest(stub_sources, client, monkeypatch):
    # The panel has to keep showing earnings and news; an unconfigured
    # secondary source is a note, not a failure.
    monkeypatch.setattr(stub_sources.llm, "get_provider", lambda: StubProvider())
    body = client.get("/api/insight/AMD?currency=USD").get_json()
    assert body["videos"] == []
    assert "YOUTUBE_API_KEY" in body["videos_error"]
    assert body["summary"] == "resumen de prueba"


def test_a_missing_key_is_not_cached(app_module, client, monkeypatch):
    # An unconfigured key is a state that can change between requests, unlike
    # an empty result — caching it would make a key added later look ignored
    # until the next day.
    monkeypatch.setattr(app_module.sources, "gather", lambda symbol: dict(EMPTY))
    monkeypatch.setattr(app_module.llm, "get_provider", lambda: StubProvider())
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    client.get("/api/insight/AMD?currency=USD")

    conn = sqlite3.connect(app_module.DB_PATH)
    rows = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    conn.close()
    assert rows == 0


def test_a_youtube_failure_keeps_the_status_code(stub_sources, client, monkeypatch):
    def boom(symbol, company):
        raise youtube.YouTubeError("cuota agotada")

    monkeypatch.setenv("YOUTUBE_API_KEY", "k")
    monkeypatch.setattr(stub_sources.youtube, "fetch_videos", boom)
    monkeypatch.setattr(stub_sources.llm, "get_provider", lambda: StubProvider())
    response = client.get("/api/insight/AMD?currency=USD")
    assert response.status_code == 200
    assert "cuota agotada" in response.get_json()["videos_error"]


def test_videos_are_cached_for_the_day(app_module, client, stub_videos, monkeypatch):
    monkeypatch.setattr(app_module.llm, "get_provider", lambda: StubProvider())
    client.get("/api/insight/AMD?currency=USD")
    # Clearing the insight cache isolates the videos cache from it.
    conn = sqlite3.connect(app_module.DB_PATH)
    conn.execute("DELETE FROM insights")
    conn.commit()
    conn.close()

    client.get("/api/insight/AMD?currency=USD")
    assert stub_videos == ["AMD"]


def test_a_stale_video_entry_is_refetched(app_module, client, stub_videos, monkeypatch):
    monkeypatch.setattr(app_module.llm, "get_provider", lambda: StubProvider())
    client.get("/api/insight/AMD?currency=USD")

    conn = sqlite3.connect(app_module.DB_PATH)
    conn.execute("DELETE FROM insights")
    conn.execute("UPDATE videos SET fetched_on = '2020-01-01'")
    conn.commit()
    conn.close()

    client.get("/api/insight/AMD?currency=USD")
    assert stub_videos == ["AMD", "AMD"]


def test_empty_results_are_cached_too(app_module, client, monkeypatch):
    # Otherwise a symbol with no allowlisted coverage burns 100 quota units
    # every time the panel opens.
    calls = []

    def fake(symbol, company):
        calls.append(symbol)
        return []

    monkeypatch.setattr(app_module.youtube, "fetch_videos", fake)
    monkeypatch.setattr(app_module.sources, "gather", lambda symbol: dict(EMPTY))
    monkeypatch.setattr(app_module.llm, "get_provider", lambda: StubProvider())

    client.get("/api/insight/AMD?currency=USD")
    conn = sqlite3.connect(app_module.DB_PATH)
    conn.execute("DELETE FROM insights")
    conn.commit()
    conn.close()
    client.get("/api/insight/AMD?currency=USD")
    assert calls == ["AMD"]
