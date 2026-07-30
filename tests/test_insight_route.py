import pytest

import llm


EMPTY = {"news": [], "earnings_calendar": None, "earnings_history": [], "fundamentals": []}


class StubProvider:
    """Stands in for a real model — no credentials exist in this environment."""

    def __init__(self):
        self.calls = 0

    def summarize(self, system, user, max_tokens=4000):
        self.calls += 1
        return "resumen de prueba"


@pytest.fixture
def stub_sources(app_module, monkeypatch):
    """Keep route tests off the network and deterministic."""
    monkeypatch.setattr(app_module.sources, "gather", lambda symbol: dict(EMPTY))
    return app_module


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
