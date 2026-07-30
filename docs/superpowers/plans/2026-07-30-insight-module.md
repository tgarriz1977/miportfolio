# Per-Ticker Insight Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user open a per-holding panel showing recent news, the next earnings date and past earnings results, summarized in Spanish by a configurable LLM provider.

**Architecture:** Three decoupled layers. `sources.py` gathers data in-process via yfinance (provider-independent, because a local model cannot use any provider's server-side web search). `llm.py` puts two adapters — the Anthropic SDK and one generic OpenAI-compatible HTTP client — behind a single `summarize()` call. `app.py` adds a cached route that wires them together.

**Tech Stack:** Flask, SQLite, yfinance + lxml, the `anthropic` SDK, vanilla JS in a single `index.html` (no build step), pytest for the new unit tests.

## Global Constraints

- Design of record: `docs/plans/2026-07-30-insight-module-design.md`.
- **Never emit buy/sell/hold recommendations or price targets.** The system prompt forbids it explicitly; the UI shows a visible "no es asesoramiento financiero" note. A recommendation slipping through is a bug in the prompt, not a feature.
- `resolve_insight_symbol()` deliberately **inverts** `resolve_yf_symbol()`: a CEDEAR resolves to the **bare US ticker**, not `<ticker>.BA`, because news and earnings are about the company and a CEDEAR shares them with the direct holding.
- **Every source degrades on its own.** Verified: `ALUA.BA` returns 0 news and no earnings date; `BTC-USD` has news but its `income_stmt` raises a 404. A missing source returns an empty result; it never aborts the request.
- **Values must be JSON-serializable.** pandas emits `NaN` for missing numbers and `NaN` breaks `jsonify` — strip it via `_clean_number()`.
- Do **not** pass `temperature`, `top_p`, `top_k`, or `thinking.budget_tokens` to the Anthropic SDK — all are rejected on `claude-opus-5`. Check `stop_reason == "refusal"` before reading `content`.
- No credentials exist in this environment (`ANTHROPIC_API_KEY` unset, no local model running), so the real LLM call cannot be exercised end-to-end. Route tests use a stub provider.
- Repo root: `/media/tgarriz/Nuevo vol/lab/miportfolio`.
- Scratchpad venv (flask, yfinance, lxml, playwright): `/tmp/claude-1000/-media-tgarriz-Nuevo-vol-lab-miportfolio/f0084847-2415-494b-a05f-7760458336ea/scratchpad/venv/bin/python3`. Referred to below as `$PY`.
- Existing conventions: module-level helpers with docstrings; comments state constraints, not mechanics; `ensure_schema()` does additive migrations; `data/portfolio_dump.sql` is hand-maintained and mirrors the schema.

## File Structure

| File | Responsibility |
|---|---|
| `sources.py` (new) | Symbol resolution + four yfinance fetchers + `gather()`. No LLM, no Flask. |
| `llm.py` (new) | Provider selection, two adapters, prompt construction. No Flask, no yfinance. |
| `app.py` (modify) | `insights` table in `ensure_schema()`, cache helpers, `GET /api/insight/<ticker>`. |
| `index.html` (modify) | Per-row button + result panel. |
| `tests/conftest.py` (new) | Isolated-SQLite fixture so tests never touch `data/portfolio.db`. |
| `tests/test_sources.py` (new) | Symbol resolution (offline) + degradation and JSON-safety (network). |
| `tests/test_llm.py` (new) | Provider config and prompt rules. Fully offline. |
| `tests/test_insight_route.py` (new) | 503 path, happy path, shared-cache behavior. Stubbed provider, stubbed gather. |
| `requirements.txt` / `requirements-dev.txt` (modify/new) | `lxml`, `anthropic`; `pytest` for dev. |

---

### Task 1: `sources.py` — symbol resolution and data gathering

**Files:**
- Create: `sources.py`
- Create: `tests/conftest.py`
- Create: `tests/test_sources.py`
- Modify: `requirements.txt`, `requirements-dev.txt`

**Interfaces:**
- Produces: `resolve_insight_symbol(ticker, is_cedear, is_crypto, currency) -> str`; `fetch_news(symbol, limit=8) -> list[dict]`; `fetch_earnings_calendar(symbol) -> dict | None`; `fetch_earnings_history(symbol, limit=8) -> list[dict]`; `fetch_fundamentals(symbol, limit=4) -> list[dict]`; `gather(symbol) -> dict` with exactly the keys `news`, `earnings_calendar`, `earnings_history`, `fundamentals`.

- [ ] **Step 1: Add dependencies**

In `requirements.txt`, append:

```
lxml>=5.0
anthropic>=0.40
```

Create `requirements-dev.txt`:

```
pytest>=8.0
```

- [ ] **Step 2: Write the failing tests**

Create `tests/conftest.py`:

```python
import os
import sqlite3
import sys

import pytest

# Make the app package importable — tests live one level below the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def app_module(monkeypatch, tmp_path):
    """app.py bound to a throwaway SQLite so tests never touch data/portfolio.db."""
    import app as mod

    db = tmp_path / "test.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE holdings (
            ticker TEXT NOT NULL, company TEXT, shares REAL NOT NULL, sector TEXT,
            broker TEXT, cedear_ratio REAL, is_cedear INTEGER DEFAULT 0,
            is_crypto INTEGER DEFAULT 0, updated_at TEXT,
            PRIMARY KEY (ticker, broker)
        );
        CREATE TABLE prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT NOT NULL,
            price REAL NOT NULL, currency TEXT DEFAULT 'USD',
            recorded_at TEXT DEFAULT (datetime('now')), is_cedear INTEGER DEFAULT 0
        );
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(mod, "DB_PATH", db)
    mod.ensure_schema()
    return mod


@pytest.fixture
def client(app_module):
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()
```

Create `tests/test_sources.py`:

```python
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
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
cd "/media/tgarriz/Nuevo vol/lab/miportfolio"
PY=/tmp/claude-1000/-media-tgarriz-Nuevo-vol-lab-miportfolio/f0084847-2415-494b-a05f-7760458336ea/scratchpad/venv/bin/python3
$PY -m pip install --quiet pytest
$PY -m pytest tests/test_sources.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'sources'`.

- [ ] **Step 4: Write `sources.py`**

```python
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


def resolve_insight_symbol(ticker, is_cedear, is_crypto, currency):
    """Return the Yahoo Finance symbol for the underlying *company*.

    This deliberately inverts resolve_yf_symbol() in app.py: for prices, a
    CEDEAR and its direct US holding are different instruments in different
    currencies, but for news and earnings they are the same company — so a
    CEDEAR resolves to the bare US ticker rather than "<ticker>.BA".
    """
    if is_crypto:
        return f"{ticker}-USD"
    if is_cedear:
        return ticker
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
```

- [ ] **Step 5: Register the `network` marker**

Create `pytest.ini` at the repo root:

```ini
[pytest]
markers =
    network: test reaches the public internet (Yahoo Finance)
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
cd "/media/tgarriz/Nuevo vol/lab/miportfolio"
PY=/tmp/claude-1000/-media-tgarriz-Nuevo-vol-lab-miportfolio/f0084847-2415-494b-a05f-7760458336ea/scratchpad/venv/bin/python3
$PY -m pytest tests/test_sources.py -v
```

Expected: all pass. Offline resolution tests must pass regardless; if a network test fails on a Yahoo hiccup, re-run once before investigating.

- [ ] **Step 7: Commit**

```bash
cd "/media/tgarriz/Nuevo vol/lab/miportfolio"
git add sources.py tests/conftest.py tests/test_sources.py pytest.ini requirements.txt requirements-dev.txt
git commit -m "Add sources.py: news and earnings retrieval for the insight module

Gathers news, the next earnings date, past earnings surprises and basic
fundamentals via yfinance. Retrieval runs in-process rather than through a
provider's server-side web search so a local model works the same as a
hosted one.

resolve_insight_symbol() inverts resolve_yf_symbol(): a CEDEAR resolves to
the bare US ticker because news and earnings are about the company, which a
CEDEAR shares with the direct holding.

Coverage is uneven (ALUA.BA has no news, BTC-USD no income statement), so
each fetcher degrades independently. NaN is stripped because it is not
JSON-serializable."
```

---

### Task 2: `llm.py` — pluggable provider and prompt

**Files:**
- Create: `llm.py`
- Create: `tests/test_llm.py`

**Interfaces:**
- Consumes: nothing from Task 1 at import time; `build_insight_prompt()` accepts the dict shape produced by `sources.gather()`.
- Produces: `ProviderNotConfigured`, `ProviderError`; `get_provider() -> AnthropicProvider | OpenAICompatProvider`; both expose `summarize(system, user, max_tokens=4000) -> str`; `build_insight_prompt(symbol, data) -> tuple[str, str]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_llm.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd "/media/tgarriz/Nuevo vol/lab/miportfolio"
PY=/tmp/claude-1000/-media-tgarriz-Nuevo-vol-lab-miportfolio/f0084847-2415-494b-a05f-7760458336ea/scratchpad/venv/bin/python3
$PY -m pytest tests/test_llm.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'llm'`.

- [ ] **Step 3: Write `llm.py`**

```python
#!/usr/bin/env python3
"""Pluggable LLM provider for the insight module.

Two adapters cover every target: the Anthropic SDK, and one generic
OpenAI-compatible HTTP client that serves Ollama, LM Studio, vLLM, OpenAI and
Gemini's compatibility endpoint. Because sources.py does the retrieval, no
provider's built-in web search is needed and the three stay interchangeable.

Configuration comes from the environment with no default provider: with
nothing set the dashboard keeps working and only the insight route reports
that it is unconfigured.
"""

import json
import os
import urllib.error
import urllib.request

DEFAULT_ANTHROPIC_MODEL = "claude-opus-5"
REQUEST_TIMEOUT_SECONDS = 180


class ProviderNotConfigured(RuntimeError):
    """No usable LLM_PROVIDER — the route turns this into an HTTP 503."""


class ProviderError(RuntimeError):
    """The provider was reachable but the call failed."""


def _env(name, default=None):
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else default


class AnthropicProvider:
    """Anthropic via the official SDK."""

    def __init__(self, model=None, api_key=None):
        self.model = model or DEFAULT_ANTHROPIC_MODEL
        self.api_key = api_key

    def summarize(self, system, user, max_tokens=4000):
        try:
            import anthropic
        except ImportError as exc:
            raise ProviderError("falta el paquete 'anthropic' (pip install anthropic)") from exc

        client = anthropic.Anthropic(api_key=self.api_key) if self.api_key else anthropic.Anthropic()
        try:
            # No temperature/top_p/top_k and no thinking budget: all are
            # rejected on claude-opus-5.
            response = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except Exception as exc:
            raise ProviderError(f"Anthropic: {exc}") from exc

        # A safety decline returns HTTP 200 with empty or partial content, so
        # stop_reason has to be checked before indexing into content.
        if getattr(response, "stop_reason", None) == "refusal":
            raise ProviderError("el modelo rechazó la consulta por políticas de seguridad")

        return "".join(
            block.text for block in response.content
            if getattr(block, "type", None) == "text"
        )


class OpenAICompatProvider:
    """Any endpoint speaking /chat/completions.

    Covers Ollama, LM Studio, vLLM, OpenAI itself and Gemini's compatibility
    endpoint, which is why there is no separate Gemini adapter.
    """

    def __init__(self, model, base_url, api_key=None):
        if not model:
            raise ProviderNotConfigured("falta LLM_MODEL")
        if not base_url:
            raise ProviderNotConfigured("falta LLM_BASE_URL")
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def summarize(self, system, user, max_tokens=4000):
        body = json.dumps({
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        request = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=body, headers=headers
        )
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise ProviderError(f"{exc.code} {exc.reason}: {detail}") from exc
        except Exception as exc:
            raise ProviderError(str(exc)) from exc

        try:
            return payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"respuesta inesperada: {str(payload)[:300]}") from exc


def get_provider():
    """Build the configured provider, or explain what is missing."""
    name = (_env("LLM_PROVIDER") or "").lower()
    if not name:
        raise ProviderNotConfigured(
            "definí LLM_PROVIDER (anthropic | openai_compat) para habilitar el análisis"
        )
    if name == "anthropic":
        return AnthropicProvider(model=_env("LLM_MODEL"), api_key=_env("LLM_API_KEY"))
    if name == "openai_compat":
        return OpenAICompatProvider(
            model=_env("LLM_MODEL"),
            base_url=_env("LLM_BASE_URL"),
            api_key=_env("LLM_API_KEY"),
        )
    raise ProviderNotConfigured(f"LLM_PROVIDER desconocido: {name}")


SYSTEM_PROMPT = """Sos un asistente que resume información pública sobre empresas que cotizan en bolsa.

Reglas estrictas:
- Resumí únicamente la información que se te pasa abajo. No uses conocimiento previo ni completes huecos con suposiciones.
- Si una fuente vino sin datos, decilo explícitamente en vez de omitirla.
- Cuando menciones una noticia, citá el medio y la fecha.
- NUNCA recomiendes comprar, vender ni mantener una posición.
- NUNCA des precios objetivo ni pronósticos de precio, ni opines sobre si está cara o barata.
- Respondé en español rioplatense, en prosa clara, en un máximo de cuatro párrafos cortos.
"""


def _format_news(items):
    if not items:
        return "Noticias: sin datos disponibles."
    lines = ["Noticias recientes:"]
    for item in items:
        lines.append(
            f"- [{item.get('published') or 's/f'}] {item.get('title')} "
            f"({item.get('publisher') or 'fuente desconocida'})"
        )
        if item.get("summary"):
            lines.append(f"  {item['summary']}")
    return "\n".join(lines)


def _format_calendar(calendar):
    if not calendar:
        return "Próximo balance: sin datos disponibles."
    return (
        f"Próximo balance: {calendar['date']}"
        f" | EPS estimado: {calendar.get('eps_estimate')}"
        f" | Ingresos estimados: {calendar.get('revenue_estimate')}"
    )


def _format_history(rows):
    if not rows:
        return "Historial de balances: sin datos disponibles."
    lines = ["Historial de balances (EPS estimado vs real):"]
    for row in rows:
        lines.append(
            f"- {row['date']}: estimado {row.get('eps_estimate')}, "
            f"real {row.get('eps_reported')}, sorpresa {row.get('surprise_pct')}%"
        )
    return "\n".join(lines)


def _format_fundamentals(rows):
    if not rows:
        return "Fundamentales: sin datos disponibles."
    lines = ["Ingresos y ganancia neta por período:"]
    for row in rows:
        lines.append(
            f"- {row['period']}: ingresos {row.get('total_revenue')}, "
            f"ganancia neta {row.get('net_income')}"
        )
    return "\n".join(lines)


def build_insight_prompt(symbol, data):
    """Return (system, user) for one symbol's gathered data."""
    sections = [
        f"Símbolo: {symbol}",
        "",
        _format_calendar(data.get("earnings_calendar")),
        "",
        _format_history(data.get("earnings_history") or []),
        "",
        _format_fundamentals(data.get("fundamentals") or []),
        "",
        _format_news(data.get("news") or []),
        "",
        "Resumí lo anterior siguiendo las reglas del sistema.",
    ]
    return SYSTEM_PROMPT, "\n".join(sections)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd "/media/tgarriz/Nuevo vol/lab/miportfolio"
PY=/tmp/claude-1000/-media-tgarriz-Nuevo-vol-lab-miportfolio/f0084847-2415-494b-a05f-7760458336ea/scratchpad/venv/bin/python3
$PY -m pytest tests/test_llm.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
cd "/media/tgarriz/Nuevo vol/lab/miportfolio"
git add llm.py tests/test_llm.py
git commit -m "Add llm.py: pluggable provider for the insight summary

Two adapters cover every target — the Anthropic SDK, and one generic
OpenAI-compatible HTTP client serving Ollama, LM Studio, vLLM, OpenAI and
Gemini's compatibility endpoint. Configured by environment variables with no
default provider, so an unconfigured install leaves the rest of the dashboard
untouched and only the insight route reports it.

The system prompt forbids buy/sell/hold recommendations and price targets,
and requires missing sources to be stated rather than omitted."
```

---

### Task 3: Flask route, schema and cache

**Files:**
- Modify: `app.py` (imports; `ensure_schema()`; new helpers and route)
- Modify: `data/portfolio_dump.sql` (mirror the new table)
- Create: `tests/test_insight_route.py`

**Interfaces:**
- Consumes: `sources.resolve_insight_symbol`, `sources.gather`, `llm.get_provider`, `llm.build_insight_prompt`, `llm.ProviderNotConfigured`, `llm.ProviderError`.
- Produces: `GET /api/insight/<ticker>` returning `{symbol, summary, news, earnings_calendar, earnings_history, fundamentals, cached, generated_at}`; `read_insight_cache(symbol)`; `write_insight_cache(symbol, payload)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_insight_route.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd "/media/tgarriz/Nuevo vol/lab/miportfolio"
PY=/tmp/claude-1000/-media-tgarriz-Nuevo-vol-lab-miportfolio/f0084847-2415-494b-a05f-7760458336ea/scratchpad/venv/bin/python3
$PY -m pytest tests/test_insight_route.py -v
```

Expected: FAIL — `AttributeError: module 'app' has no attribute 'sources'` (the fixture patches `app_module.sources` before it exists).

- [ ] **Step 3: Add the imports to `app.py`**

In the import block near the top of `app.py`, after `import sqlite3` add `import json`, and after the `from flask import ...` line add the two new modules:

```python
import llm
import sources
```

- [ ] **Step 4: Create the `insights` table in `ensure_schema()`**

In `ensure_schema()`, immediately before `conn.close()`, insert:

```python
    # Cache for /api/insight, keyed by the resolved company symbol so a
    # CEDEAR and its direct holding share one entry.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS insights (
            symbol TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
```

- [ ] **Step 5: Add the cache helpers**

Add after `save_price()` in `app.py`:

```python
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
```

- [ ] **Step 6: Add the route**

Add after `api_refresh()` in `app.py`:

```python
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

    # The gathered data is returned even on failure so the panel can still
    # show news and earnings dates without a working model.
    try:
        provider = llm.get_provider()
    except llm.ProviderNotConfigured as exc:
        return jsonify({"error": str(exc), "symbol": symbol, **data}), 503

    system, user = llm.build_insight_prompt(symbol, data)
    try:
        summary = provider.summarize(system, user)
    except llm.ProviderError as exc:
        return jsonify({"error": str(exc), "symbol": symbol, **data}), 502

    payload = {
        "symbol": symbol,
        "summary": summary,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        **data,
    }
    write_insight_cache(symbol, payload)
    payload["cached"] = False
    return jsonify(payload)
```

- [ ] **Step 7: Mirror the table in the dump**

In `data/portfolio_dump.sql`, append at the end of the file:

```sql

CREATE TABLE insights (
    symbol TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

- [ ] **Step 8: Run the tests to verify they pass**

```bash
cd "/media/tgarriz/Nuevo vol/lab/miportfolio"
PY=/tmp/claude-1000/-media-tgarriz-Nuevo-vol-lab-miportfolio/f0084847-2415-494b-a05f-7760458336ea/scratchpad/venv/bin/python3
$PY -m pytest tests/ -v -m "not network"
```

Expected: every offline test passes, including the six route tests.

- [ ] **Step 9: Migrate the live database**

`ensure_schema()` runs on startup and creates the table, but run it once now so the committed database matches:

```bash
cd "/media/tgarriz/Nuevo vol/lab/miportfolio"
PY=/tmp/claude-1000/-media-tgarriz-Nuevo-vol-lab-miportfolio/f0084847-2415-494b-a05f-7760458336ea/scratchpad/venv/bin/python3
PORTFOLIO_DB="$(pwd)/data/portfolio.db" $PY -c "import app; app.ensure_schema(); print('insights table ready')"
```

Expected: `insights table ready`.

- [ ] **Step 10: Commit**

```bash
cd "/media/tgarriz/Nuevo vol/lab/miportfolio"
git add app.py data/portfolio_dump.sql data/portfolio.db tests/test_insight_route.py
git commit -m "Add /api/insight route with SQLite cache

Resolves the holding to its underlying company symbol, gathers news and
earnings, and has the configured provider summarize them. Cached in a new
insights table keyed by the resolved symbol, so AMD held directly and AMD
held as a CEDEAR share one entry and one model call. TTL via
INSIGHT_TTL_HOURS, default 6.

An unconfigured provider returns 503 and a failing one 502, both carrying
the gathered data so the panel still shows news and dates without a model."
```

---

### Task 4: Insight panel in the UI

**Files:**
- Modify: `index.html` (CSS, panel markup, `tickerLink`-adjacent button, JS)

**Interfaces:**
- Consumes: `GET /api/insight/<ticker>?is_cedear=&is_crypto=&currency=` from Task 3.
- Produces: nothing consumed downstream.

- [ ] **Step 1: Add the panel CSS**

In the `<style>` block, after the `.ticker-link:hover` rule:

```css
        .insight-btn { background: none; border: none; color: #6c8aa0; cursor: pointer; padding: 0 .25rem; font-size: .8rem; }
        .insight-btn:hover { color: #6ea8fe; }
        .insight-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.6); z-index: 1050; display: flex; align-items: center; justify-content: center; padding: 1rem; }
        .insight-panel { background: #15202b; border: 1px solid #1e2d3d; border-radius: .75rem; max-width: 760px; width: 100%; max-height: 85vh; overflow-y: auto; }
        .insight-body { white-space: pre-wrap; line-height: 1.55; }
        .insight-disclaimer { background: #2d2410; border: 1px solid #5c4813; color: #f5d78e; border-radius: .5rem; padding: .5rem .75rem; font-size: .85rem; }
```

- [ ] **Step 2: Add the overlay container**

Immediately before the closing `</div>` of `container-lg` (just before `<script>`), add:

```html
    <div id="insightOverlay" class="insight-overlay" style="display:none" onclick="closeInsight(event)">
        <div class="insight-panel" onclick="event.stopPropagation()">
            <div class="card-header d-flex justify-content-between align-items-center">
                <span id="insightTitle">Análisis</span>
                <button class="btn btn-outline-secondary btn-sm" onclick="closeInsight()">Cerrar</button>
            </div>
            <div class="card-body" id="insightContent"></div>
        </div>
    </div>
```

- [ ] **Step 3: Add the button to the Tenencias rows**

In `renderHoldingsTable()`, replace this line:

```javascript
            '<td>' + tickerLink(h) + cedi + '</td>' +
```

with:

```javascript
            '<td>' + tickerLink(h) + cedi + insightButton(h) + '</td>' +
```

- [ ] **Step 4: Add the button to the detail panel rows**

In `renderDetailPanel()`, replace this line:

```javascript
            '<td>' + tickerLink(h) + '</td>' +
```

with:

```javascript
            '<td>' + tickerLink(h) + insightButton(h) + '</td>' +
```

- [ ] **Step 5: Add the JavaScript**

After the `tickerLink` function, add:

```javascript
function insightButton(h) {
    var args = [h.ticker, !!h.is_cedear, !!h.is_crypto, h.currency]
        .map(function(v) { return JSON.stringify(v); }).join(',');
    return ' <button class="insight-btn" title="Ver noticias y balances" ' +
        'onclick=\'openInsight(' + args + ')\'>&#9432;</button>';
}

function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
}

function closeInsight(evt) {
    if (evt && evt.target !== document.getElementById('insightOverlay')) return;
    document.getElementById('insightOverlay').style.display = 'none';
}

function renderInsight(data, errorMessage) {
    var parts = ['<div class="insight-disclaimer mb-3">Resumen informativo generado por un modelo de lenguaje. ' +
        'No es asesoramiento financiero ni una recomendación de compra o venta.</div>'];

    if (errorMessage) {
        parts.push('<div class="alert alert-warning py-2">' + escapeHtml(errorMessage) + '</div>');
    }
    if (data.summary) {
        parts.push('<div class="insight-body mb-3">' + escapeHtml(data.summary) + '</div>');
    }

    var cal = data.earnings_calendar;
    parts.push('<h6 class="text-info">Próximo balance</h6><p>' +
        (cal ? escapeHtml(cal.date) + (cal.eps_estimate != null ? ' — EPS estimado ' + cal.eps_estimate : '')
             : 'Sin datos disponibles.') + '</p>');

    var hist = data.earnings_history || [];
    if (hist.length) {
        var rows = hist.map(function(r) {
            return '<tr><td>' + escapeHtml(r.date) + '</td><td class="text-end">' + (r.eps_estimate != null ? r.eps_estimate : '—') +
                '</td><td class="text-end">' + (r.eps_reported != null ? r.eps_reported : '—') +
                '</td><td class="text-end">' + (r.surprise_pct != null ? r.surprise_pct.toFixed(1) + '%' : '—') + '</td></tr>';
        }).join('');
        parts.push('<h6 class="text-info">Balances anteriores</h6>' +
            '<table class="table table-sm"><thead><tr><th>Fecha</th><th class="text-end">EPS est.</th>' +
            '<th class="text-end">EPS real</th><th class="text-end">Sorpresa</th></tr></thead><tbody>' +
            rows + '</tbody></table>');
    } else {
        parts.push('<h6 class="text-info">Balances anteriores</h6><p>Sin datos disponibles.</p>');
    }

    var news = data.news || [];
    if (news.length) {
        parts.push('<h6 class="text-info">Noticias</h6><ul>' + news.map(function(n) {
            var title = escapeHtml(n.title);
            var link = n.url ? '<a class="ticker-link" target="_blank" rel="noopener noreferrer" href="' +
                escapeHtml(n.url) + '">' + title + '</a>' : title;
            return '<li>' + link + ' <span class="text-secondary">(' +
                escapeHtml(n.publisher || 'fuente desconocida') + ')</span></li>';
        }).join('') + '</ul>');
    } else {
        parts.push('<h6 class="text-info">Noticias</h6><p>Sin noticias disponibles para este símbolo.</p>');
    }

    document.getElementById('insightContent').innerHTML = parts.join('');
}

function openInsight(ticker, isCedear, isCrypto, currency) {
    var overlay = document.getElementById('insightOverlay');
    document.getElementById('insightTitle').textContent = 'Análisis — ' + ticker;
    document.getElementById('insightContent').innerHTML =
        '<p class="text-secondary">Consultando noticias y balances…</p>';
    overlay.style.display = 'flex';

    var qs = 'is_cedear=' + (isCedear ? 1 : 0) + '&is_crypto=' + (isCrypto ? 1 : 0) +
        '&currency=' + encodeURIComponent(currency || 'USD');

    fetch('/api/insight/' + encodeURIComponent(ticker) + '?' + qs)
        .then(function(r) { return r.json().then(function(body) { return { ok: r.ok, body: body }; }); })
        .then(function(res) { renderInsight(res.body, res.ok ? null : res.body.error); })
        .catch(function(e) {
            document.getElementById('insightContent').innerHTML =
                '<div class="alert alert-danger py-2">No se pudo consultar: ' + escapeHtml(e.message) + '</div>';
        });
}
```

- [ ] **Step 6: Check JS syntax**

```bash
cd "/media/tgarriz/Nuevo vol/lab/miportfolio"
SCRATCH=/tmp/claude-1000/-media-tgarriz-Nuevo-vol-lab-miportfolio/f0084847-2415-494b-a05f-7760458336ea/scratchpad
python3 -c "
import re
html = open('index.html').read()
m = re.search(r'<script>\n(.*)</script>', html, re.S)
open('$SCRATCH/inline.js','w').write(m.group(1))
"
node --check $SCRATCH/inline.js && echo "JS SYNTAX OK"
```

Expected: `JS SYNTAX OK`

- [ ] **Step 7: Verify in the browser**

Start the app with **no** `LLM_PROVIDER` set — the 503 path is what this environment can actually exercise, and it is the state a new user lands in:

```bash
cd "/media/tgarriz/Nuevo vol/lab/miportfolio"
SCRATCH=/tmp/claude-1000/-media-tgarriz-Nuevo-vol-lab-miportfolio/f0084847-2415-494b-a05f-7760458336ea/scratchpad
PORTFOLIO_DB="$(pwd)/data/portfolio.db" PORT=5099 $SCRATCH/venv/bin/python3 app.py > $SCRATCH/app_insight.log 2>&1 &
echo $! > $SCRATCH/app_insight.pid
sleep 3
$SCRATCH/venv/bin/python3 - <<'EOF'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome", headless=True, args=["--no-sandbox"])
    page = b.new_page(viewport={"width": 1400, "height": 1000})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("http://127.0.0.1:5099/", wait_until="networkidle", timeout=30000)
    page.wait_for_selector("#holdingsBody .insight-btn", timeout=15000)
    page.query_selector("#holdingsBody .insight-btn").click()
    page.wait_for_selector("#insightOverlay", state="visible", timeout=10000)
    page.wait_for_timeout(6000)
    text = page.inner_text("#insightContent")
    print("PANEL:", text[:400].replace("\n", " | "))
    assert "No es asesoramiento financiero" in text, "falta el aviso"
    assert "LLM_PROVIDER" in text, "deberia explicar que falta configurar el proveedor"
    page.click("#insightOverlay button.btn-outline-secondary")
    page.wait_for_timeout(300)
    assert not page.is_visible("#insightOverlay"), "el panel no cerro"
    assert not errors, errors
    print("UI OK")
    b.close()
EOF
kill $(cat $SCRATCH/app_insight.pid) 2>/dev/null; sleep 1
```

Expected: `UI OK`, with the panel showing the disclaimer, the news and earnings sections, and the "definí LLM_PROVIDER" message.

- [ ] **Step 8: Run the whole offline suite once more**

```bash
cd "/media/tgarriz/Nuevo vol/lab/miportfolio"
PY=/tmp/claude-1000/-media-tgarriz-Nuevo-vol-lab-miportfolio/f0084847-2415-494b-a05f-7760458336ea/scratchpad/venv/bin/python3
$PY -m pytest tests/ -v -m "not network"
```

Expected: all pass.

- [ ] **Step 9: Commit**

```bash
cd "/media/tgarriz/Nuevo vol/lab/miportfolio"
git add index.html
git commit -m "Add insight panel to the dashboard

A button on each holding opens a panel with the model's summary plus the
raw earnings dates and news links, so the data is readable even when no
provider is configured. Shows a standing note that this is informational
and not investment advice, and surfaces the 503 explaining how to configure
a provider rather than failing silently."
```

---

## Self-Review

**Spec coverage.** Every section of the design doc maps to a task: the no-advice constraint lands in Task 2's `SYSTEM_PROMPT` (asserted by `test_system_prompt_forbids_recommendations`) and Task 4's disclaimer (asserted in Step 7); the four data sources are Task 1; uneven-coverage degradation is Task 1's fetchers with `test_fetch_news_degrades_when_uncovered` and `test_fetch_fundamentals_degrades_for_crypto`; the inverted symbol resolution is Task 1 with five dedicated tests plus Task 3's `test_cedear_and_direct_share_one_cache_entry`; the two-adapter provider layer and env config are Task 2; the cache with `INSIGHT_TTL_HOURS` and the 503 path are Task 3; the UI is Task 4. Out-of-scope items (X, Reddit, YouTube, streaming, any buy/sell signal) have no task, as intended.

**Placeholder scan.** No TBDs, no "add error handling", no "similar to Task N". Every code step is literal and complete.

**Type consistency.** `sources.gather()` returns exactly `{news, earnings_calendar, earnings_history, fundamentals}`; `llm.build_insight_prompt()` reads those same four keys with `.get()`; the Task 3 route spreads that dict into its response and the Task 4 renderer reads the same names. `resolve_insight_symbol(ticker, is_cedear, is_crypto, currency)` has the same four-parameter signature at its definition (Task 1), its tests (Task 1), and its call site (Task 3). `summarize(system, user, max_tokens=4000)` matches across both real adapters, the `StubProvider`, and the `Failing` stub. `ProviderNotConfigured` and `ProviderError` are defined in Task 2 and caught by name in Task 3.

**One gap found and closed during review:** the Task 3 fixture patches `app_module.sources`, which requires the `import sources` from Step 3 to exist — so Step 2's expected failure is an `AttributeError`, not a passing test. Noted explicitly in that step.
