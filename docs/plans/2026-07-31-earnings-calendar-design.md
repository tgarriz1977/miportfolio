# Calendario de balances — diseño

Fecha: 2026-07-31

## Problema

El dashboard no dice cuándo reportan resultados las empresas en cartera. El
dato existe por ticker (el panel ⓘ ya muestra próximo balance e histórico),
pero no hay una vista agregada que responda "¿qué reporta esta semana?".

## Objetivo

Una ventana con los próximos balances de la cartera, precargada al abrir la
página y cacheada por día, con una tarjeta compacta en el dashboard para
verlos de un vistazo.

## Fuera de alcance

**El panel ⓘ ya trae próximo balance e histórico.** Verificado contra el
endpoint vivo el 2026-07-31: `/api/insight/AMD` devuelve `earnings_calendar`
con fecha y EPS estimado, y 8 filas de `earnings_history`, renderizadas en
`index.html` bajo "Próximo balance" y "Balances anteriores". No se construye
de nuevo. Si el usuario no lo ve, es un bug a diagnosticar por separado.

Lo que sí cambia para ese panel, como efecto de la agrupación de ADRs: PAMP
pasará a mostrar los números del ADR (PAM, en USD) en vez de los de BYMA (en
pesos).

## Hallazgo que motiva la agrupación de ADRs

Contra Yahoo real, el ADR y su acción local devuelven **el mismo balance dos
veces**, con el EPS en monedas distintas:

```
PAM      → 2026-08-04, EPS est. 2.52      (USD)
PAMP.BA  → 2026-08-04, EPS est. 145.62    (ARS)
YPF      → 2026-08-10        YPFD.BA → 2026-08-10
```

Sin agrupar, la ventana muestra la misma fecha dos veces por empresa. La
agrupación es un requisito de corrección, no una mejora cosmética.

(`ALUA.BA` no devuelve calendario — sí histórico viejo, de 2023. Los símbolos
sin fecha próxima se excluyen, decisión del usuario.)

## Diseño

### 1. ADRs: agrupación y marcado

`sources.py` gana un mapa ticker local BYMA → símbolo del ADR:

```python
ADR_MAP = {"PAMP": "PAM", "YPFD": "YPF"}
```

`resolve_insight_symbol()` lo consulta antes de la rama ARS:

```python
def resolve_insight_symbol(ticker, is_cedear, is_crypto, currency):
    if is_crypto:
        return f"{ticker}-USD"
    if is_cedear:
        return ticker
    if ticker in ADR_MAP:
        return ADR_MAP[ticker]
    if currency == "ARS":
        return f"{ticker}.BA"
    return ticker
```

Así `PAMP` y `PAM` resuelven ambos a `"PAM"` y colapsan en una fila, igual
que ya lo hacen un CEDEAR y su tenencia directa. Agregar un ADR nuevo es una
línea en el mapa — mismo patrón que el `YF_TICKER_MAP` que ya existe en
`app.py`.

**La columna `is_adr` se deriva del mapa, no se carga a mano.**
`ensure_schema()` agrega la columna si falta y luego marca las filas cuyo
ticker es un valor de `ADR_MAP`:

```sql
-- solo si la columna no existe
ALTER TABLE holdings ADD COLUMN is_adr INTEGER DEFAULT 0;

-- en cada arranque, con los valores de ADR_MAP como parámetros
UPDATE holdings SET is_adr = 0 WHERE is_adr = 1;
UPDATE holdings SET is_adr = 1
 WHERE ticker IN ('PAM', 'YPF') AND is_cedear = 0;
```

El primer `UPDATE` limpia marcas viejas, para que sacar una entrada del mapa
también desmarque la fila.

Corre en cada arranque, es idempotente y sigue la convención aditiva que ya
usa la migración de `prices.is_cedear`. Consecuencia: `ADR_MAP` es la única
fuente de verdad. Se agrega la línea, el flag se actualiza solo.

`is_adr` no afecta precios: `resolve_yf_symbol()` queda igual, porque PAM
cotiza en NYSE en dólares y eso ya es correcto. El flag es para presentación
y para documentar que PAM no es una acción estadounidense común.

`api_portfolio()` incluye `is_adr` en cada holding, y el frontend etiqueta
"(ADR)" en las etiquetas del gráfico igual que hace con "(CEDEAR)".

### 2. Caché por día

Tabla nueva, misma forma que `insights`:

```sql
CREATE TABLE IF NOT EXISTS earnings (
    symbol     TEXT PRIMARY KEY,
    payload    TEXT,            -- JSON, o 'null' si el símbolo no tiene fecha próxima
    fetched_on TEXT NOT NULL    -- fecha local 'YYYY-MM-DD'
)
```

Una entrada es válida cuando `fetched_on = date('now','localtime')`. Se usa
la fecha local y no UTC porque en Argentina (UTC-3) el corte UTC caería a las
21:00 y el caché parecería vencer a media tarde.

**Los símbolos sin datos también se cachean** (payload `null`). Si no, los
símbolos sin cobertura (las acciones BYMA puras y el ETF ARKK) se
re-consultarían a Yahoo en cada carga, que es exactamente el costo que el
caché existe para evitar.

### 3. Fetcher

`sources.fetch_earnings_summary(symbol)` compone las dos funciones que ya
existen y devuelve `None` cuando no hay fecha próxima — el criterio de
exclusión queda en un solo lugar:

```python
def fetch_earnings_summary(symbol):
    calendar = fetch_earnings_calendar(symbol)
    if not calendar:
        return None
    history = fetch_earnings_history(symbol, limit=1)
    last = history[0] if history else None
    return {
        "next_date": calendar["date"],
        "eps_estimate": calendar["eps_estimate"],
        "last_date": last["date"] if last else None,
        "last_eps_reported": last["eps_reported"] if last else None,
        "last_surprise_pct": last["surprise_pct"] if last else None,
    }
```

### 4. Endpoint

`GET /api/earnings?limit=5&refresh=false`

1. Lee holdings, saltea los `is_crypto` sin consultarlos (no tienen balances).
2. Resuelve cada uno con `resolve_insight_symbol()` y deduplica por símbolo.
3. Para el nombre a mostrar, entre los holdings que comparten símbolo prefiere
   aquel cuyo ticker es igual al símbolo (así PAM/PAMP muestra "PAM"); si
   ninguno coincide, el primero.
4. Por símbolo: si el caché es de hoy lo usa; si no, llama a
   `fetch_earnings_summary()` y lo guarda. `refresh=true` ignora el caché.
5. Descarta los `None`, ordena por `next_date` ascendente y devuelve los
   primeros `limit`.

```json
{
  "rows": [
    {"ticker": "AMD", "company": "AMD Inc.", "symbol": "AMD",
     "next_date": "2026-08-04", "days_until": 4, "eps_estimate": 1.61,
     "last_date": "2026-05-05", "last_eps_reported": 1.37,
     "last_surprise_pct": 5.82}
  ],
  "fetched_on": "2026-07-31",
  "cached": true
}
```

`days_until` se calcula en el servidor contra la fecha local, para que no
dependa del reloj del navegador.

El límite es de presentación: hay que consultar todos los símbolos igual,
porque no se sabe cuáles son los 5 más próximos sin preguntarle a cada uno.
Ese costo se paga una vez por día.

### 5. Frontend

**Carga automática.** `loadData()` dispara `/api/earnings` en paralelo, sin
encadenarlo al fetch del portfolio. La primera carga del día tarda 20-40s
(una llamada de red por símbolo, secuencial) y ocurre en background; el
dashboard se muestra normalmente mientras tanto. No se paraleliza con threads:
agregar concurrencia a Flask por algo que corre una vez al día no justifica la
complejidad.

**Tarjeta en el dashboard.** Fila nueva antes de `brokerCards`, compacta:
ticker, fecha y días que faltan para los 5 próximos. Estado de carga mientras
el fetch está en vuelo. Click en la tarjeta abre la ventana.

**Ventana.** Botón "Balances" en el header, al lado de "Actualizar precios".
Overlay `earningsOverlay` reutilizando el CSS `.insight-overlay` /
`.insight-panel` que ya existe para el panel ⓘ. Tabla con Ticker, Empresa,
Fecha, Faltan, EPS est., Último balance y Sorpresa. Botón "Actualizar" que
llama al endpoint con `refresh=true`. Los que reportan dentro de 7 días van
resaltados.

Ambas superficies muestran los mismos 5 balances y se diferencian por las
columnas: la tarjeta es un vistazo (ticker, fecha, días), la ventana agrega
empresa, EPS estimado, último balance y sorpresa. El fetch se hace una sola
vez y se guarda en una variable de módulo, como ya hace `lastData`.

## Tests

Siguiendo los patrones de `tests/test_insight_route.py` y
`tests/test_sources.py`.

`test_sources.py` (offline, sin red):
- `PAMP` resuelve a `PAM`.
- `PAMP` y `PAM` resuelven al mismo símbolo.
- `YPFD` resuelve a `YPF`.
- Un ticker ARS fuera de `ADR_MAP` sigue recibiendo el sufijo `.BA`
  (regresión: el mapa no debe romper `ALUA`).

`test_earnings_route.py` (con `sources.fetch_earnings_summary` monkeypatcheado):
- Las filas salen ordenadas por fecha ascendente.
- Los símbolos que devuelven `None` se excluyen.
- Nunca se consulta un holding de crypto.
- Un CEDEAR y su tenencia directa producen una sola fila.
- PAM y PAMP producen una sola fila, mostrada como "PAM".
- La segunda llamada usa el caché (el stub se invoca una vez).
- Un caché de ayer se considera vencido y se vuelve a consultar.
- `refresh=true` ignora un caché de hoy.
- Se respeta `limit`.
- `is_adr` se deriva de `ADR_MAP` al correr `ensure_schema()`.

El fixture `app_module` de `conftest.py` crea la tabla `holdings` sin la
columna `is_adr`, así que la migración se ejerce en cada test — no hace falta
tocar el fixture.

## Documentación

- `README.md`: la tabla `earnings` y la columna `holdings.is_adr` en la
  sección de esquema; el endpoint `/api/earnings`.
- `CLAUDE.md`: `ADR_MAP` junto a la descripción de `YF_TICKER_MAP`, y la
  regla de que `is_adr` se deriva del mapa en vez de cargarse a mano.
