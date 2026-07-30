# Portfolio Dashboard

Panel web auto-actualizable para visualizar tenencias de acciones agrupadas por broker, con precios en vivo desde Yahoo Finance y un módulo de análisis por ticker basado en modelos de lenguaje.

## Stack

- **Backend:** Python + Flask
- **Frontend:** Bootstrap 5 (dark mode) + Chart.js
- **Precios y datos:** Yahoo Finance (vía `yfinance`)
- **Análisis:** Anthropic, Gemini o cualquier modelo local compatible con OpenAI
- **Datos:** SQLite (`portfolio.db`)
- **Infra:** Docker Compose

## Funcionalidades

-   **Auto-actualización** — Al entrar al panel o presionar "Actualizar precios", obtiene cotizaciones vía Yahoo Finance para todos los tickers.
-   **Totales separados por moneda** — La cartera se reporta en ARS y en USD por separado, nunca sumados entre sí. Un saldo en pesos y uno en dólares no son la misma unidad.
-   **Gráfico por categoría** — Cuatro pestañas (CEDEARs, Acciones USA, Acciones BA, Crypto), cada una de una sola moneda, así las porciones son comparables entre sí. Clickear una porción filtra el panel de detalle.
-   **Tabla de tenencias ordenable** — Ticker, empresa, broker, shares, precio, valor y porcentaje, con ordenamiento por cualquier columna.
-   **Links a TradingView** — Cada ticker abre el gráfico del instrumento correcto: un CEDEAR abre su gráfico en pesos de BYMA, la acción directa abre el de EE.UU. en dólares.
-   **Análisis por ticker** — Noticias recientes, fecha del próximo balance e historial de resultados, con un resumen redactado por el modelo que configures. Ver [Módulo de análisis](#módulo-de-análisis).
-   **Cards por broker** — Desglose individual de cada broker con sus propias tablas y subtotales.
-   **Multi-activo** — Soporta acciones US, acciones argentinas (BYMA, con sufijo `.BA`), CEDEARs, y crypto (BTC/ETH).

## Requisitos

- Docker y Docker Compose

## Quick Start

```bash
git clone <repo-url> portfolio-dashboard
cd portfolio-dashboard

# Copiar tu base de datos (o usar la de ejemplo)
cp ruta/a/tu/portfolio.db data/portfolio.db

# Iniciar
docker compose up -d
```

Abrir [http://localhost:5050](http://localhost:5050)

## Estructura

```
portfolio-dashboard/
├── app.py                  # Backend Flask: rutas, precios, caché
├── sources.py              # Noticias y balances (independiente del modelo)
├── llm.py                  # Proveedor de modelo intercambiable
├── index.html              # Frontend (Bootstrap + Chart.js)
├── Dockerfile              # Imagen Docker
├── docker-compose.yml      # Orquestación
├── requirements.txt        # Dependencias Python
├── requirements-dev.txt    # Dependencias de test
├── data/
│   ├── portfolio.db        # Base SQLite (con precios)
│   └── portfolio_dump.sql  # Dump SQL de la base
├── tests/                  # pytest
├── docs/plans/             # Documentos de diseño
└── README.md
```

## Configuración

| Variable     | Default                | Descripción                     |
|-------------|------------------------|--------------------------------|
| `PORTFOLIO_DB` | `/data/portfolio.db` | Ruta a la base SQLite          |
| `HOST`        | `0.0.0.0`            | Interfaz de red del servidor    |
| `PORT`        | `5050`               | Puerto del servidor             |
| `LLM_PROVIDER` | *(sin default)*     | `anthropic` o `openai_compat`. Sin definir, el análisis queda deshabilitado |
| `LLM_MODEL`   | `claude-opus-5` (solo Anthropic) | Identificador del modelo |
| `LLM_BASE_URL` | —                   | Endpoint, requerido por `openai_compat` |
| `LLM_API_KEY` | —                    | Credencial, si el proveedor la pide |
| `INSIGHT_TTL_HOURS` | `6`            | Vida de la caché de análisis    |

## Base de datos

### holdings

| Columna       | Tipo     | Descripción                              |
|--------------|----------|------------------------------------------|
| ticker       | TEXT PK  | Símbolo de la acción                     |
| company      | TEXT     | Nombre de la empresa                     |
| shares       | REAL     | Cantidad de acciones                     |
| sector       | TEXT     | Sector                                   |
| broker       | TEXT PK  | Nombre del broker                        |
| cedear_ratio | REAL     | Ratio de conversión CEDEAR               |
| is_cedear    | INTEGER  | 1 si es CEDEAR                           |
| is_crypto    | INTEGER  | 1 si es crypto                           |
| updated_at   | TEXT     | Última actualización                     |

### prices

| Columna     | Tipo     | Descripción                                                     |
|------------|----------|-------------------------------------------------------------------|
| id         | INTEGER  | PK autoincremental                                              |
| ticker     | TEXT     | Símbolo (referencia a holdings)                                 |
| price      | REAL     | Precio de cierre                                                 |
| currency   | TEXT     | USD o ARS                                                        |
| recorded_at| TEXT     | Timestamp de la cotización                                       |
| is_cedear  | INTEGER  | 1 si el precio corresponde al CEDEAR (ARS), no a la acción directa (USD) — junto con `ticker` identifica de forma única qué instrumento cotiza, ya que un mismo ticker puede tener versión directa y CEDEAR |

### insights

Caché del módulo de análisis. La clave es el **símbolo resuelto de la empresa**, no el ticker local, así el CEDEAR de AMD y las acciones directas comparten una sola entrada y una sola llamada al modelo.

| Columna     | Tipo     | Descripción                     |
|------------|----------|---------------------------------|
| symbol     | TEXT PK  | Símbolo resuelto (ver más abajo)|
| payload    | TEXT     | Respuesta completa en JSON      |
| created_at | TEXT     | Timestamp, comparado contra `INSIGHT_TTL_HOURS` |

### Restaurar desde dump

```bash
sqlite3 data/portfolio.db < data/portfolio_dump.sql
```

## Mapa de tickers a Yahoo Finance

| Origen                  | Ticker local | Yahoo Finance     | Moneda |
|------------------------|-------------|-------------------|--------|
| Acción directa (`is_cedear=0`, ej. BECA Vestiva) | AMD, MSFT…  | directo (AMD)     | USD    |
| Acción argentina en BYMA (`is_cedear=0`, ej. TM Inversiones) | ALUA, PAMP… | +.BA (ALUA.BA)    | ARS    |
| CEDEAR (`is_cedear=1`, ej. TM Inversiones, Balanz) | ALAB, AMD…  | +.BA (ALAB.BA)    | ARS    |
| Crypto (Belo)           | BTC, ETH    | -USD (BTC-USD)    | USD    |

Un mismo ticker (ej. `AMD`) puede tener versión directa en un broker y CEDEAR en otro — son instrumentos distintos con precio y moneda distintos, resueltos por `is_cedear` (ver `resolve_yf_symbol()` en `app.py`), no por el ticker solo.

## Módulo de análisis

Cada tenencia tiene un botón que abre un panel con noticias recientes, la fecha del próximo balance y el historial de resultados (EPS estimado vs. real y el porcentaje de sorpresa). Todo eso sale de `yfinance` y **no requiere ninguna API key**, así que el panel funciona aunque no configures ningún modelo. Si configurás uno, arriba de esos datos aparece además un resumen redactado.

> El resumen es informativo. El prompt le prohíbe explícitamente al modelo recomendar comprar, vender o mantener, y dar precios objetivo. No es asesoramiento financiero.

### Proveedores

La recolección de datos ocurre en la aplicación, no a través de la búsqueda web integrada de ningún proveedor — porque un modelo local no tiene esa herramienta. Eso es lo que hace que los tres sean intercambiables.

Dos adaptadores cubren todo (`llm.py`):

```bash
# Modelo local — Ollama, LM Studio, vLLM. Costo cero, sin credencial.
LLM_PROVIDER=openai_compat
LLM_MODEL=llama3
LLM_BASE_URL=http://localhost:11434/v1

# Anthropic
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-ant-...

# Gemini, por su endpoint compatible con OpenAI
LLM_PROVIDER=openai_compat
LLM_MODEL=gemini-2.0-flash
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
LLM_API_KEY=...
```

Sin `LLM_PROVIDER` definido, `/api/insight` responde HTTP 503 con un mensaje explicando qué falta, y el panel igual muestra las noticias y los balances. El resto del dashboard no se ve afectado.

### Resolución de símbolo — se invierte respecto de los precios

Para **precios**, un CEDEAR y su acción directa son instrumentos distintos. Para **noticias y balances** son la misma empresa: comparten los mismos resultados trimestrales. Por eso `resolve_insight_symbol()` en `sources.py` resuelve distinto que `resolve_yf_symbol()`:

| Condición | Símbolo | Ejemplo |
|-----------|---------|---------|
| Crypto | `{ticker}-USD` | BTC → `BTC-USD` |
| CEDEAR | `{ticker}` — el subyacente de EE.UU., **no** `.BA` | AMD CEDEAR → `AMD` |
| Acción argentina | `{ticker}.BA` | ALUA → `ALUA.BA` |
| Acción de EE.UU. | `{ticker}` | AMD directa → `AMD` |

### Cobertura despareja

Yahoo no cubre todo por igual: `ALUA.BA` no tiene noticias ni fecha de balance (sí fundamentales), y las crypto tienen noticias pero no balances. Cada fuente se resuelve por separado y su ausencia se informa como "sin datos" — nunca aborta la consulta ni se inventa el faltante.

### Fuentes no incluidas

Reddit y YouTube requieren registrar credenciales gratuitas (una app OAuth y una key de Google Cloud). X requiere el plan pago de su API. Ninguna está implementada; la capa de fuentes está preparada para agregarlas como funciones nuevas en `sources.py` sin tocar el resto.

## Desarrollo local (sin Docker)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp ~/.hermes/portfolio.db data/
PORTFOLIO_DB=data/portfolio.db python3 app.py
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest                      # todo
pytest -m "not network"     # sin salir a internet
```

Los tests marcados `network` consultan Yahoo Finance de verdad — verifican que las fuentes degraden bien cuando un símbolo no tiene cobertura y que el payload sea serializable a JSON (pandas emite `NaN`, que rompe `jsonify`). Los de la ruta usan un proveedor falso, así que no necesitan credenciales.

## Próximos pasos

### Verificación pendiente

**La llamada real al modelo nunca se ejecutó de punta a punta.** El módulo de análisis se desarrolló sin credencial ni modelo local disponible, así que `AnthropicProvider.summarize()` y `OpenAICompatProvider.summarize()` están cubiertos por tests unitarios de configuración, pero nunca hablaron con un proveedor real. Lo primero al configurar uno es abrir el panel de cualquier ticker y confirmar que el resumen aparece y respeta las reglas del prompt (que no recomiende comprar ni vender).

Es lo más probable que falle y lo más rápido de verificar.

### Fuentes de datos pendientes

La capa de `sources.py` está preparada para recibirlas: cada una entra como una función nueva con la misma forma de retorno, sin tocar `llm.py` ni la ruta.

| Fuente | Qué hace falta | Costo |
|--------|----------------|-------|
| Reddit | Registrar una app OAuth (el JSON público devuelve 403) | Gratis |
| YouTube | Key de Google Cloud, Data API v3 | Gratis, con cupo diario |
| X | Plan pago de su API (devuelve 401 sin credencial) | ~US$100/mes |

### Mejoras conocidas

- **Streaming de la respuesta.** Hoy el panel espera la respuesta completa con un "Consultando…". Con un modelo local lento eso puede ser medio minuto de spinner. Si terminás usando Ollama en CPU, conviene.
- **Cobertura de acciones argentinas.** Yahoo no tiene noticias ni fecha de balance para `ALUA.BA` (sí fundamentales). Para esas posiciones haría falta otra fuente si el análisis les importa.
- **Costo por consulta.** Con Anthropic ronda los US$0,10–0,15 por ticker. La caché de 6 horas amortigua, pero si consultás mucho conviene medir antes de subir el TTL o cambiar de modelo.

### Decisiones abiertas

Dos cosas sobre los datos que quedaron sin resolver y afectan los números que muestra el panel:

- **PAM, VIST e YPF en Vestiva** figuran como mercado BA en el último export, pero hoy se cotizan en dólares tomando el precio del ADR en NYSE. Si en realidad se tienen en BYMA, hay que pasarlos a pesos — y ahí PAM sería el mismo instrumento que el PAMP de TM Inversiones, e YPF el mismo que YPFD.
- **Belo (BTC y ETH)** no aparece en el último export de tenencias. Se dejaron cargados asumiendo que el export cubre solo acciones y CEDEARs, no crypto.
