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
-   **Calendario de balances** — Los cinco próximos balances de la cartera, en una tarjeta del panel y en una ventana con el detalle (EPS estimado, último balance y sorpresa). Se consulta solo la primera vez de cada día. Ver [Calendario de balances](#calendario-de-balances).
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

Las cuatro variables `LLM_*` se configuran en un archivo `.env` en la raíz (ver `.env.example`), que está en `.gitignore` para que la API key no entre al repositorio. Docker Compose lo lee solo.

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
| is_adr       | INTEGER  | 1 si es el ADR de una empresa argentina. **No se carga a mano**: se deriva de `ADR_MAP` en cada arranque (ver [Calendario de balances](#calendario-de-balances)) |
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

### earnings

Caché del calendario de balances. Igual que `insights`, la clave es el símbolo resuelto de la empresa, así el CEDEAR de AMD, la acción directa y el ADR de una empresa argentina comparten una sola entrada.

| Columna     | Tipo     | Descripción                     |
|------------|----------|---------------------------------|
| symbol     | TEXT PK  | Símbolo resuelto de la empresa  |
| payload    | TEXT     | Resumen en JSON, o `null` si el símbolo no tiene fecha publicada |
| fetched_on | TEXT     | Fecha local `YYYY-MM-DD` de la consulta |

Una entrada vale mientras `fetched_on` sea la fecha local de hoy. Los símbolos sin fecha se guardan como `null` en vez de omitirse: si no, los que Yahoo no cubre se volverían a consultar en cada carga de la página, que es justo el costo que el caché evita.

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

## Calendario de balances

`GET /api/earnings` devuelve los balances más próximos de la cartera, del más cercano al más lejano.

| Parámetro | Default | Efecto                                                        |
|-----------|---------|---------------------------------------------------------------|
| `limit`   | 5       | Cuántas filas devuelve. Solo recorta la respuesta: hay que consultar todos los símbolos igual, porque no se sabe cuáles son los más próximos sin preguntarle a cada uno |
| `refresh` | `false` | `true` ignora el caché del día y vuelve a consultar todo      |

El frontend lo dispara al cargar la página, en paralelo con `/api/portfolio` y no encadenado: la primera consulta del día tarda decenas de segundos (una llamada de red por símbolo) y no debe demorar el panel. El resto del día se responde desde el caché.

Se excluyen la crypto (no tiene balances, ni se consulta) y los símbolos sin fecha publicada, como las acciones puramente de BYMA.

### Una empresa, un balance

Yahoo responde por cada cotización por separado, con la **misma fecha de balance** y el EPS en la moneda de cada plaza:

```
PAM      → 2026-08-04, EPS est. 2.52     (USD, NYSE)
PAMP.BA  → 2026-08-04, EPS est. 145.62   (ARS, BYMA)
```

Sin agrupar, un mismo balance aparecería dos veces. Pasa por dos motivos distintos, y `sources.py` los mantiene separados porque solo el primero es un ADR:

```python
# Ticker local en BYMA -> su ADR en EE.UU.
ADR_MAP = {"PAMP": "PAM", "YPFD": "YPF"}

# Clase de acción secundaria -> bajo cuál reporta la empresa.
SHARE_CLASS_MAP = {"GOOGL": "GOOG"}

COMPANY_ALIASES = {**ADR_MAP, **SHARE_CLASS_MAP}
```

`resolve_insight_symbol()` consulta `COMPANY_ALIASES` **antes** de la rama de CEDEAR: si no, un CEDEAR devolvería su ticker pelado y nunca colapsaría (el CEDEAR de GOOGL tiene que llegar a GOOG).

**Agregar un alias nuevo es una línea**, en el mapa que corresponda. La columna `holdings.is_adr` se deriva de los valores de `ADR_MAP` en cada arranque (`ensure_schema()`) y se desmarca sola si se saca una entrada, así que no hay que tocar la base de datos a mano. Los alias de clase de acción quedan fuera de ese marcado a propósito: GOOG no es el ADR de nada.

## Módulo de análisis

Cada tenencia tiene un botón que abre un panel con noticias recientes, la fecha del próximo balance y el historial de resultados (EPS estimado vs. real y el porcentaje de sorpresa). Todo eso sale de `yfinance` y **no requiere ninguna API key**, así que el panel funciona aunque no configures ningún modelo. Si configurás uno, arriba de esos datos aparece además un resumen redactado.

> El resumen es informativo. El prompt le prohíbe explícitamente al modelo recomendar comprar, vender o mantener, y dar precios objetivo. No es asesoramiento financiero.

### Proveedores

La recolección de datos ocurre en la aplicación, no a través de la búsqueda web integrada de ningún proveedor — porque un modelo local no tiene esa herramienta. Eso es lo que hace que los tres sean intercambiables.

Dos adaptadores (`llm.py`) cubren los tres casos. La configuración va en un archivo `.env` en la raíz, que está en `.gitignore` para que la API key no entre al repositorio:

```bash
cp .env.example .env
# editar .env y poner la key
docker compose up -d
```

`.env.example` trae los tres bloques listos para descomentar:

| Proveedor | `LLM_PROVIDER` | `LLM_BASE_URL` | Dónde sacar la key |
|-----------|----------------|----------------|--------------------|
| Gemini | `openai_compat` | `https://generativelanguage.googleapis.com/v1beta/openai` | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| DeepSeek | `openai_compat` | `https://api.deepseek.com/v1` | [platform.deepseek.com](https://platform.deepseek.com/api_keys) |
| Anthropic | `anthropic` | — | [console.anthropic.com](https://console.anthropic.com/settings/keys) |
| Local (Ollama, LM Studio, vLLM) | `openai_compat` | `http://host.docker.internal:11434/v1` | no lleva |

Cualquier servicio que hable el protocolo de OpenAI entra por `openai_compat` sin tocar código — solo cambian `LLM_BASE_URL` y `LLM_MODEL`.

Desde el contenedor, un modelo local en tu máquina se alcanza por `host.docker.internal`, **no** por `localhost` — `localhost` dentro del contenedor es el contenedor mismo.

Sin `LLM_PROVIDER` definido, `/api/insight` responde HTTP 503 con un mensaje explicando qué falta, y el panel igual muestra las noticias y los balances. El resto del dashboard no se ve afectado.

### Qué datos salen hacia el proveedor

El prompt se arma exclusivamente con lo que devuelve `sources.gather()`: el símbolo, noticias públicas, fechas y resultados de balances, e ingresos por período. **Tu tenencia no se envía** — ni la cantidad de acciones, ni el broker, ni el valor de la posición, ni los totales de la cartera. Nada de eso se consulta al construir el prompt.

Lo único que revela la consulta es **qué ticker estás mirando**. Si eso importa en tu caso, un modelo local no manda nada afuera.

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

### Nombres de modelo que se retiran

Google retira modelos sin previo aviso y el nombre viejo deja de funcionar. Ya pasó con `gemini-2.0-flash` y `gemini-2.5-flash`. Por eso `.env.example` usa **`gemini-flash-latest`**, un alias que sigue al modelo vigente.

Dos cosas que confunden al diagnosticar esto:

- El error llega como **HTTP 429 "quota exceeded"**, y recién más adelante en el cuerpo dice que el modelo fue retirado. Si ves un 429 con una key nueva, leé el mensaje completo antes de asumir que es un problema de cuota.
- El endpoint de listado **sigue devolviendo modelos retirados**. Si uno falla, probalo con un request real antes de descartar el resto de la configuración.

### Revisar en la primera consulta

El modelo puede desobedecer el prompt. Vale la pena leer los primeros resúmenes y confirmar que **no recomiende comprar ni vender**. Si aparece una recomendación, el arreglo va en `SYSTEM_PROMPT` (`llm.py`), no en la UI.

Caso de borde observado: el modelo reporta correctamente noticias del tipo "tal banco subió su precio objetivo", citando la fuente. Eso es resumir una noticia, no emitir un precio objetivo propio — dentro de lo permitido. Si igual preferís que ni las mencione, hay que endurecer el prompt.

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
