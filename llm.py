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
