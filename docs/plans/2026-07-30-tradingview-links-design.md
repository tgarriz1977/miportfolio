# Links a TradingView en las tablas de tenencias

Fecha: 2026-07-30

## Contexto

Cada fila de las tablas muestra un ticker pero no ofrece forma de ver su
gráfico. La idea es que el ticker sea clickeable y abra el gráfico
correspondiente en TradingView.

El punto delicado es cuál gráfico. Un CEDEAR y su acción subyacente en
EE.UU. son instrumentos distintos, en mercados y monedas distintas, y
comparten el mismo string de ticker: `AMD` existe como acción directa en
BECA Vestiva (USD, NASDAQ) y como CEDEAR en TM Inversiones (ARS, BYMA).
Lo mismo pasa con `INTC`, `MSFT` y `MU`. Resolver el símbolo a partir del
ticker solo reintroduciría exactamente la clase de bug que se corrigió en
`resolve_yf_symbol()` (ver commit "Fix CEDEAR pricing and split totals by
currency").

## Resolución del símbolo

Se deriva **por holding**, usando los flags que el JSON de
`/api/portfolio` ya expone (`is_cedear`, `is_crypto`, `currency`) — nunca
a partir del ticker aislado:

| Condición | Símbolo TradingView | Ejemplo |
|-----------|---------------------|---------|
| `is_crypto` | `{ticker}USD` | BTC → `BTCUSD` |
| `is_cedear` o `currency === 'ARS'` | `BCBA-{ticker}` | AMD CEDEAR → `BCBA-AMD` |
| resto (acción de EE.UU.) | `{ticker}` | AMD directa → `AMD` |

URL final: `https://www.tradingview.com/symbols/<símbolo>/`

Para las acciones de EE.UU. no hace falta guardar el exchange: TradingView
resuelve el ticker pelado al mercado correcto por su cuenta
(`AMZN` → NASDAQ, `NU`/`YPF`/`PAM`/`VIST` → NYSE). Los 39 holdings
actuales fueron verificados uno por uno contra TradingView antes de
escribir este diseño, incluyendo un símbolo de control inventado que
devuelve "Page not found" para confirmar que un 200 no es falso positivo.

## Dónde se aplica

El texto del ticker se convierte en `<a>` en las tres tablas:

1. Panel de detalle (al lado de la torta de categorías)
2. Tabla "Tenencias" completa
3. Cards por broker

El badge "CEDEAR" queda **fuera** del link. Los links abren en pestaña
nueva (`target="_blank"` con `rel="noopener noreferrer"`).

## Decisión de arquitectura

La resolución vive en el frontend (`index.html`), no en el backend.

El link es presentación, no dato: agregar un campo `tv_symbol` a cada
holding en la API cargaría el payload por algo puramente visual. Además,
el frontend ya clasifica cada holding con estos mismos tres flags para
armar las pestañas de la torta (constante `CATEGORIES`), así que derivar
el símbolo del mismo modo es consistente con el patrón ya establecido.

La alternativa considerada era un `tradingview_symbol()` en `app.py` junto
a `resolve_yf_symbol()`, que tendría la ventaja de dejar las dos tablas de
símbolos a la vista en el mismo archivo. Se descartó por YAGNI, pero es la
opción a retomar si en el futuro el backend necesita el símbolo (por
ejemplo para exportar o para un webhook).

## Testing

Se extiende el test de Playwright existente para verificar los `href`
por categoría, con foco en los cuatro tickers duplicados: la fila de AMD
en BECA Vestiva debe apuntar a `/symbols/AMD/` y la de AMD en TM
Inversiones a `/symbols/BCBA-AMD/`. Ese es el guardarraíl contra la
regresión descrita en Contexto.

## Fuera de alcance

- Embeber el gráfico de TradingView dentro del dashboard (widget iframe).
- Guardar el exchange (NASDAQ/NYSE) por holding en la base.
