# Videos de YouTube en el panel de análisis — diseño

Fecha: 2026-07-31

## Problema

El panel de análisis por ticker muestra balances, fundamentales y noticias de
texto. No hay forma de llegar a la cobertura en video de una acción, que para
algunas empresas es donde está el análisis más reciente.

## Objetivo

Una sección "Videos" en el panel de análisis con los videos recientes sobre la
empresa, restringidos a una lista blanca de canales configurable.

## Fuera de alcance

- **Carga de la API key por interfaz gráfica.** Se evaluó y se descartó: la
  key va en `.env` y se documenta en el README. Guardarla desde el navegador
  habría requerido un almacén aparte del `portfolio.db` (que se commitea) y un
  endpoint de escritura de credenciales sin autenticación delante.
- **Los videos no se le pasan al modelo.** El modelo no puede ver un video;
  solo recibiría títulos y descripciones, y `SYSTEM_PROMPT` le pide resumir lo
  que se le pasa, así que terminaría afirmando cosas sobre contenido que nadie
  miró. Los videos se listan como enlaces y el resumen sigue basándose en
  balances, fundamentales y noticias.
- **Autenticación del dashboard.** Sigue publicado en todas las interfaces sin
  login, por decisión explícita del usuario.

## Restricción que define el diseño: la cuota

`search.list` cuesta 100 unidades de las 10.000 diarias del tier gratuito.

Restringir la búsqueda por canal (`channelId=...`) obliga a una llamada por
canal: con 8 canales serían 800 unidades por símbolo, o sea 12 consultas por
día en total. Inviable.

Por eso el diseño hace **una sola búsqueda general por símbolo** y filtra por
la lista blanca del lado de la aplicación. Con caché por día y 22 tickers, el
peor caso es 2.200 unidades.

**Consecuencia aceptada:** con lista blanca dura la sección va a quedar vacía
seguido. Que un canal de la lista aparezca entre los primeros 50 resultados de
una búsqueda general no está garantizado, y para tickers chicos (ALAB, ECOG,
TGNO4) no va a haber nada. Es el intercambio elegido: señal sobre cobertura.
La lista es configurable para poder ampliarla cuando falte cobertura.

## Diseño

### 1. Módulo nuevo `youtube.py`

Misma forma que `llm.py`: solo `urllib` de la stdlib, sin dependencias nuevas,
excepción propia para el caso "no configurado".

```python
class NotConfigured(RuntimeError):
    """No hay YOUTUBE_API_KEY — la sección lo informa en vez de fallar."""


class YouTubeError(RuntimeError):
    """La API respondió con error o no se pudo alcanzar."""
```

Funciones:

| Función | Qué hace |
|---------|----------|
| `resolve_channel_ids(entries)` | Convierte una lista de handles (`@Bloomberg`) e IDs (`UC...`) a IDs. Los handles se resuelven con `channels.list?forHandle` (1 unidad) y se cachean en un dict de módulo |
| `build_query(symbol, company)` | Arma el texto de búsqueda |
| `search_videos(query, published_after, max_results)` | Una llamada a `search.list` |
| `fetch_videos(symbol, company)` | Orquesta: arma query, busca, filtra por lista blanca, recorta |

`fetch_videos` devuelve una lista de dicts con `title`, `channel`, `published`
y `url`. Lista vacía significa "no hubo resultados"; para "no configurado"
levanta `NotConfigured`.

**El query saca el prefijo `CEDEAR ` del nombre de la empresa.** En los datos
reales, ALAB figura como `"CEDEAR ASTERA LABS INC"`, y ese prefijo ensucia la
búsqueda.

### 2. Configuración

| Variable | Default | Efecto |
|----------|---------|--------|
| `YOUTUBE_API_KEY` | — | Sin ella, la sección muestra un aviso y no se hace ninguna llamada de red |
| `YOUTUBE_CHANNELS` | vacío | Handles o IDs separados por coma. Vacío = búsqueda abierta, sin lista blanca |
| `YOUTUBE_MAX_RESULTS` | 5 | Cuántos videos se muestran |
| `YOUTUBE_DAYS` | 30 | Ventana de antigüedad |

No se hardcodean IDs de canal. Son cadenas como `UCIALMKvObZNtJ6AmdCLP7Lg`,
imposibles de verificar sin la API, y una mal copiada no falla: simplemente no
matchea nunca y la lista blanca parece rota. La config acepta handles, que es
lo que se ve en YouTube.

### 3. Caché

Tabla nueva, idéntica en forma a `earnings`:

```sql
CREATE TABLE IF NOT EXISTS videos (
    symbol     TEXT PRIMARY KEY,
    payload    TEXT,            -- JSON: lista de videos, o [] si no hubo
    fetched_on TEXT NOT NULL    -- fecha local 'YYYY-MM-DD'
)
```

Válida mientras `fetched_on` sea la fecha local de hoy.

**Se cachean también los resultados vacíos.** Sin eso, un símbolo sin cobertura
gasta 100 unidades cada vez que se abre el panel. Y aunque `insights` ya cachea
el payload completo 6 horas, con ese TTL solo serían 4 búsquedas por símbolo
por día en vez de 1.

### 4. Orquestación en `app.py`

`sources.py` queda intacto: es el módulo de yfinance y `gather()` no tiene
acceso a la base ni al nombre de la empresa.

`api_insight()` mergea los videos junto a `sources.gather()`. Los helpers
`read_videos_cache` / `write_videos_cache` van al lado de los de `earnings`,
que ya tienen exactamente esa forma.

El nombre de la empresa sale de reusar `earnings_symbols()`, que ya resuelve
símbolo → `{ticker, company}`:

```python
def company_for_symbol(symbol):
    """Nombre a mostrar para un símbolo resuelto, o None si no está en cartera."""
    return (earnings_symbols().get(symbol) or {}).get("company")
```

El payload de `/api/insight` gana dos claves:

- `videos` — lista, posiblemente vacía
- `videos_error` — texto cuando falta la key o la API falló; ausente si todo salió bien

La ruta no cambia su código de estado por un fallo de YouTube: es una fuente
secundaria y el panel tiene que seguir mostrando balances y noticias, igual que
ya hace cuando no hay modelo configurado.

### 5. Panel

Sección "Videos" después de "Noticias", con el mismo tratamiento visual que ya
tienen las demás: `<h6>` con la línea divisoria y una lista de texto con el
título enlazado, el canal y la fecha.

Sin key configurada, en lugar de la lista aparece una línea:

> Configurá `YOUTUBE_API_KEY` en `.env` para ver videos.

### 6. Dockerfile

`youtube.py` se agrega al `COPY`. El Dockerfile ya advierte que cada módulo que
importa `app.py` tiene que estar listado, porque si falta, el contenedor recién
falla al arrancar y no al construir.

## Tests

`tests/test_youtube.py`, todo offline con `_get` stubbeado:

- El query incluye ticker y empresa.
- El query saca el prefijo `CEDEAR ` del nombre de la empresa.
- La lista blanca descarta los videos de canales que no están en ella.
- Sin `YOUTUBE_CHANNELS`, no se filtra nada.
- Los handles se distinguen de los IDs y se resuelven; los IDs pasan directo.
- La resolución de un handle se hace una sola vez (se cachea).
- Sin `YOUTUBE_API_KEY`, `fetch_videos` levanta `NotConfigured` sin tocar la red.
- Se respeta `YOUTUBE_MAX_RESULTS`.
- Un error de la API se convierte en `YouTubeError`.

`tests/test_insight_route.py`:

- El payload incluye `videos`.
- Sin key, el payload trae `videos_error` y `videos` vacío, y el resto del
  contenido sigue presente.
- La segunda llamada usa el caché de videos (el stub se invoca una vez).
- Una entrada de ayer se considera vencida.
- Los resultados vacíos también se cachean.
- Un fallo de YouTube no cambia el código de estado de la ruta.

## Documentación

- `README.md`: sección de configuración de YouTube — cómo sacar la key, cómo
  armar `YOUTUBE_CHANNELS` con handles, el costo en cuota y por qué la lista
  blanca deja la sección vacía seguido.
- `.env.example`: las cuatro variables con comentarios, siguiendo el estilo de
  las de LLM.
- `CLAUDE.md`: el módulo `youtube.py`, la tabla `videos` y la restricción de
  cuota que explica por qué se busca una sola vez y se filtra localmente.
