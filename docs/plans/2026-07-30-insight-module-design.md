# Módulo de análisis por ticker (noticias, balances, IA multi-proveedor)

Fecha: 2026-07-30

## Objetivo

Que desde el dashboard se pueda pedir, por cada tenencia, un resumen de qué
está pasando con esa empresa: noticias recientes, cuándo presenta el próximo
balance y cómo le fue en los anteriores. El resumen lo redacta un modelo de
lenguaje configurable — Anthropic, Gemini, o un modelo local.

## Restricción de alcance: no es asesoramiento financiero

El prompt le pide al modelo **resumir y citar fuentes**, y explícitamente
**no** recomendar comprar, vender ni mantener. El panel muestra los links a
las fuentes para que la decisión sea del usuario. La UI lo indica de forma
visible. Si el modelo emite una recomendación de todos modos, eso es un bug
a corregir en el prompt, no una funcionalidad a conservar.

## Hallazgo que define la arquitectura

El requisito de soportar **modelos locales** obliga a que la recolección de
datos ocurra del lado de la aplicación.

Anthropic ofrece búsqueda web ejecutada en su propio servidor, y Gemini algo
equivalente, pero un modelo corriendo en Ollama no tiene forma de buscar
nada. Si las tres opciones tienen que funcionar igual, no se puede depender
de la búsqueda integrada de ningún proveedor.

Esto resulta conveniente: la capa de datos queda independiente del
proveedor, y al modelo le queda una única tarea de síntesis sobre texto ya
provisto — barata (una sola llamada, sin ciclo de herramientas) y al alcance
de un modelo chico.

## Fuentes de datos disponibles

Verificado contra `yfinance`, que ya es dependencia del proyecto. Requiere
sumar `lxml` (necesaria para `earnings_dates`). Sin ninguna API key nueva.

| Dato | Método | Contenido |
|------|--------|-----------|
| Noticias | `Ticker.news` | ~10 artículos: título, resumen, fecha, medio |
| Próximo balance | `Ticker.calendar` | Fecha + EPS e ingresos estimados por analistas |
| Histórico de balances | `Ticker.earnings_dates` | EPS estimado vs. real y % de sorpresa por trimestre |
| Fundamentales | `Ticker.income_stmt` | Ingresos y ganancia neta por año |

### La cobertura es despareja — degradar por fuente

Medido sobre tickers reales de la cartera:

| Ticker | Noticias | Próx. balance | Fundamentales |
|--------|----------|---------------|---------------|
| AMD | 10 | sí | sí |
| PAMP.BA | 10 | sí | sí |
| YPFD.BA | 10 | sí | sí |
| ALUA.BA | **0** | **no** | sí |
| BTC-USD | 10 | n/a | n/a |

Cada fuente se resuelve de forma independiente y su ausencia se informa como
"sin datos" en la respuesta. Nunca se aborta la consulta completa porque una
fuente vino vacía, y el prompt le indica al modelo que no invente lo que no
recibió.

### Fuentes descartadas en esta etapa

Verificadas y bloqueadas: **Reddit** devuelve 403 sin autenticar (requiere
registrar una app OAuth, gratis), **StockTwits** 403, y **X** 401 — su API es
paga, del orden de US$100 mensuales. **YouTube** necesita una key de Google
Cloud con cupo diario gratuito.

Ninguna se implementa ahora. La capa de fuentes se diseña para que se
agreguen como funciones nuevas con la misma forma de retorno, sin modificar
las capas superiores.

## Resolución de símbolo — se invierte respecto de los precios

Para **precios**, un CEDEAR y su acción directa son instrumentos distintos en
mercados y monedas distintas (ver `resolve_yf_symbol()`). Para **noticias y
balances** son **la misma empresa**: el CEDEAR de AMD y las acciones directas
de AMD comparten los mismos resultados trimestrales.

Por eso la resolución acá es diferente, y deliberadamente no reutiliza
`resolve_yf_symbol()`:

| Condición | Símbolo | Ejemplo |
|-----------|---------|---------|
| `is_crypto` | `{ticker}-USD` | BTC → `BTC-USD` |
| `is_cedear` | `{ticker}` — el subyacente de EE.UU., **no** `.BA` | AMD CEDEAR → `AMD` |
| moneda ARS, no CEDEAR | `{ticker}.BA` | ALUA → `ALUA.BA` |
| resto | `{ticker}` | AMD directa → `AMD` |

Consecuencia deseable: las dos tenencias de AMD (Vestiva y TM Inversiones)
comparten una sola entrada de caché, porque son la misma empresa.

## Arquitectura

Tres capas desacopladas.

### 1. `sources.py` — recolección, independiente del modelo

Funciones puras que devuelven diccionarios estructurados:
`fetch_news()`, `fetch_earnings_calendar()`, `fetch_earnings_history()`,
`fetch_fundamentals()`. Cada una captura sus propias excepciones y devuelve
un marcador de "sin datos" antes que propagar el error.

### 2. `llm.py` — proveedor intercambiable

Interfaz común `summarize(system, user) -> str`, con dos adaptadores:

- **`AnthropicProvider`** — SDK oficial `anthropic`. Modelo por defecto
  `claude-opus-5`.
- **`OpenAICompatProvider`** — HTTP contra `/v1/chat/completions`. Cubre en
  un solo adaptador Ollama, LM Studio, vLLM, OpenAI y Gemini (que expone un
  endpoint compatible — a verificar al implementar).

Dos adaptadores, no tres: el endpoint compatible de Gemini evita sumar un
tercer SDK. Como la recolección es propia, no se pierde nada por no usar el
grounding nativo de Gemini.

Configuración por variables de entorno, **sin default fuerte**:

| Variable | Descripción |
|----------|-------------|
| `LLM_PROVIDER` | `anthropic` \| `openai_compat` |
| `LLM_MODEL` | Identificador del modelo |
| `LLM_BASE_URL` | Endpoint (para modelos locales / compatibles) |
| `LLM_API_KEY` | Credencial, si el proveedor la requiere |

Sin configuración, `/api/insight` responde un error explicativo con HTTP 503.
El resto del dashboard sigue funcionando sin cambios.

### 3. Endpoint y UI

`GET /api/insight/<ticker>` — resuelve el símbolo, junta las fuentes, arma el
prompt, llama al proveedor y devuelve el resumen junto con los datos crudos
(para que el panel muestre las fechas y los links sin depender de que el
modelo los repita bien).

En la UI, un botón por fila abre un panel con el resultado.

### Caché

Tabla nueva `insights` en la misma SQLite, con TTL configurable (por defecto
6 horas). Evita volver a pagar tokens y a golpear las fuentes al consultar el
mismo ticker dos veces en el día. La clave es el símbolo resuelto, no el
ticker local.

## Fuera de alcance

- X, Reddit y YouTube (la capa queda preparada).
- Streaming de la respuesta — se agrega si el modelo local elegido resulta
  lento.
- Cualquier señal, puntaje o recomendación de compra/venta.
