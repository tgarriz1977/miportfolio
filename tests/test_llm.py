import pytest

import llm


def test_missing_provider_raises_not_configured(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    with pytest.raises(llm.ProviderNotConfigured):
        llm.get_provider()


def test_unknown_provider_raises_not_configured(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "hal9000")
    with pytest.raises(llm.ProviderNotConfigured):
        llm.get_provider()


def test_openai_compat_requires_base_url(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai_compat")
    monkeypatch.setenv("LLM_MODEL", "llama3")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    with pytest.raises(llm.ProviderNotConfigured):
        llm.get_provider()


def test_openai_compat_builds_from_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai_compat")
    monkeypatch.setenv("LLM_MODEL", "llama3")
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434/v1/")
    provider = llm.get_provider()
    assert provider.model == "llama3"
    # Trailing slash stripped so the joined URL has exactly one separator.
    assert provider.base_url == "http://localhost:11434/v1"


def test_anthropic_defaults_to_opus_5(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    assert llm.get_provider().model == "claude-opus-5"


EMPTY = {"news": [], "earnings_calendar": None, "earnings_history": [], "fundamentals": []}


def test_system_prompt_forbids_recommendations():
    system, _ = llm.build_insight_prompt("AMD", EMPTY)
    assert "NUNCA recomiendes" in system
    assert "precios objetivo" in system


def test_prompt_states_missing_sources_explicitly():
    _, user = llm.build_insight_prompt("AMD", EMPTY)
    assert "sin datos" in user.lower()


def test_prompt_includes_provided_news():
    data = dict(EMPTY, news=[{
        "title": "AMD sube tras resultados",
        "summary": "resumen",
        "published": "2026-07-29T13:03:52Z",
        "publisher": "Yahoo Finance",
        "url": "https://example.com/a",
    }])
    _, user = llm.build_insight_prompt("AMD", data)
    assert "AMD sube tras resultados" in user
    assert "Yahoo Finance" in user
