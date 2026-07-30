# Torta por categoría + panel de detalle + tabla ordenable

Fecha: 2026-07-30

## Contexto

Hoy la "Distribución por ticker" es una sola torta que mezcla el valor de
CEDEARs (ARS), acciones argentinas directas en BYMA (ARS), acciones de
EE.UU. directas (USD) y crypto (USD) en la misma escala numérica sin
convertir moneda. Como resultado, las porciones no son comparables entre sí
cuando cruzan monedas — una posición grande en dólares se ve minúscula al
lado de una posición chica en pesos, solo porque los pesos son un número
nominal mucho más grande.

Este documento describe cómo separar la torta por categoría de instrumento,
agregar un panel de detalle que sincroniza con la torta, y mover/mejorar la
tabla de tenencias existente.

## 1. Categorías

El backend ya guarda `is_cedear` y `currency` por holding, pero no expone
`is_crypto` en `/api/portfolio`. Se agrega ese campo a `get_holdings()` (SQL)
y al diccionario de holding devuelto por `api_portfolio()`.

Con `is_cedear`, `is_crypto` y `currency` ya presentes, el frontend clasifica
cada holding en exactamente una categoría, sin lógica nueva en el backend:

| Categoría      | Condición                                          | Moneda |
|----------------|-----------------------------------------------------|--------|
| CEDEARs        | `is_cedear`                                         | ARS    |
| Acciones USA   | `!is_cedear && !is_crypto && currency === 'USD'`    | USD    |
| Acciones BA    | `!is_cedear && !is_crypto && currency === 'ARS'`    | ARS    |
| Crypto         | `is_crypto`                                         | USD    |

No hay conversión de moneda en ningún punto del sistema. Cada categoría es
mono-moneda, así que las porciones dentro de una misma torta son comparables
entre sí de forma válida (a diferencia de la torta única actual).

## 2. Torta con 4 pestañas

- Pestañas Bootstrap (`nav-tabs`) arriba del `<canvas>` de la torta: CEDEARs,
  Acciones USA, Acciones BA, Crypto.
- Cambiar de pestaña reconstruye el doughnut de Chart.js usando solo los
  holdings de esa categoría, agregados por ticker a través de brokers (mismo
  criterio de agregación que hoy, pero ahora sin cruzar categorías).
- El título de la card ("Distribución por...") se actualiza según la
  pestaña activa.
- Cambiar de pestaña también resetea el panel de detalle a su estado
  "tabla completa" (ver sección 3).

## 3. Panel de detalle

Ocupa el espacio donde hoy está la tabla "Tenencias", al lado de la torta.

- **Estado por defecto** (sin porción clickeada): tabla completa de la
  categoría activa. Columnas: Ticker, Empresa, Broker, Shares, Precio,
  Valor ARS, Valor USD, %.
  - Cada holding llena solo la columna de su moneda nativa; la otra
    columna muestra "—". No se inventa ni fetchea ningún tipo de cambio.
  - El % se calcula sobre el total de **esa categoría/pestaña**, no sobre
    el total general de la cartera (que además ya está separado por moneda
    desde el cambio anterior).
- **Al clickear una porción de la torta**: la tabla se filtra a las filas
  de ese ticker dentro de la categoría activa (puede haber más de una fila
  si el ticker está en más de un broker, ej. MRVL CEDEAR en TM Inversiones
  y en Balanz).
- **Botón "Ver todo"**: aparece arriba de la tabla filtrada; al clickearlo
  vuelve al estado por defecto (tabla completa de la pestaña activa).

## 4. Tabla "Tenencias" reubicada y ordenable

- Se mueve de su posición actual (al lado de la torta) a una fila propia,
  debajo de torta+detalle y arriba de las cards por broker.
- Mismo contenido que hoy: todos los holdings, todas las categorías y
  brokers juntos, mismas columnas (Ticker, Empresa, Broker, Shares, Precio,
  Valor, %).
- Los headers de columna pasan a ser clickeables: clickear ordena
  ascendente/descendente por esa columna, con un indicador visual (flecha)
  de cuál es la columna activa y en qué dirección. El orden no persiste
  entre refrescos de precios — cada `render()` reaplica el sort activo en
  memoria.

## Fuera de alcance

- Conversión de moneda / tipo de cambio para mostrar equivalentes — se
  decidió explícitamente no convertir, ni acá ni en los totales generales.
- Cambios al schema de base de datos o a `/api/refresh`.
