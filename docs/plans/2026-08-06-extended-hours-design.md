# Extended hours: postmarket alongside premarket

**Date:** 2026-08-06
**Status:** approved

## Problem

The dashboard shows premarket prices (commit `92b8569`) but goes blind after
the close. Between 17:00 and 21:00 ART the US after-hours session is the only
thing moving, and it is exactly when the Argentine user is at a screen.

## Decision: generalize, don't duplicate

Yahoo's `marketState` is a single value — there is never a premarket and an
after-hours quote at the same time. So pre and post are not two features; they
are one "extended hours" session that changes label. `fetch_premarket()` becomes
`fetch_extended_hours()`, `premarketLine()` becomes `extendedHoursLine()`, and
the holdings table keeps showing exactly one extra line.

The rejected alternative was a parallel `fetch_postmarket()` with `post_*`
fields. It duplicates the symbol-collapsing loop, the CEDEAR rule and the
renderer, and every future change to one has to be mirrored in the other for no
benefit.

## Session mapping

| `marketState` | Fields read | ART window |
|---|---|---|
| `PRE` | `preMarketPrice`, `preMarketChangePercent`, `preMarketTime` | 05:00 – 10:30 |
| `POST` | `postMarketPrice`, `postMarketChangePercent`, `postMarketTime` | 17:00 – 21:00 |
| `POSTPOST` | same as `POST` (last after-hours print) | 21:00 – 05:00 |
| anything else | nothing shown | — |

`POSTPOST` is included on purpose: Yahoo keeps serving the last after-hours
price all night, and hiding it at 21:00 ART would drop the data at the hour it
is most likely to be read.

## Weekend cutoff

Including `POSTPOST` raises the question of what happens on Saturday. Rather
than special-casing the weekday, the fetcher drops any quote whose
`preMarketTime` / `postMarketTime` is more than **12 hours** old.

The last after-hours print lands at 20:00 ET; `POSTPOST` ends at 04:00 ET, so a
legitimate quote is never more than 8 hours old and the guard never fires during
the week. On Saturday morning the Friday print crosses 12 hours and disappears.

This is deliberately data-driven instead of calendar-driven: it needs no
assumption about which `marketState` Yahoo reports on a Sunday or a holiday,
which is not verifiable from a Thursday.

## API shape

Per-holding fields in `/api/portfolio` change from `pre_price` /
`pre_change_pct` to:

- `ext_session` — `"pre"` or `"post"`, drives the label
- `ext_price` — omitted for CEDEARs
- `ext_change_pct`

`fetch_extended_hours()` returns `{us_symbol: {session, price, change_pct}}`.

**The CEDEAR rule carries over unchanged:** a CEDEAR gets only the percentage,
never the price, because the underlying trades in USD and printing that figure
under an ARS holding reads as a currency error. Crypto and BYMA-only holdings
are skipped — Yahoo has no extended-hours session for them.

## Refresh cadence

The extended-hours quote arrives with `/api/portfolio`, so it updates on page
load and on "Actualizar precios" — same as premarket today. It does **not** join
the 10-second `/api/prices` loop.

Live updating was considered and deferred. `yf.download(prepost=True,
interval="1m")` can deliver extended-hours bars in one bulk call (~1.5s), but
the percentage would have to be derived against the regular close by hand and
the per-symbol bars arrive on unaligned timestamps with `NaN` padding. That is
materially more code and more failure surface than the `.info` path, which
returns the percentage already computed.

## Frontend

`extendedHoursLine(h)` renders `Pre:` or `Post:` from `ext_session`. CSS classes
`.premarket` / `.pre-up` / `.pre-down` become `.extended` / `.ext-up` /
`.ext-down`. The three call sites in the holdings tables are unchanged apart
from the function name.

## Tests

Premarket shipped untested. This adds offline tests that monkeypatch
`app.yf.Ticker` with a fake `info` payload, covering: `PRE`, `POST`, `POSTPOST`,
`REGULAR` (nothing returned), a stale timestamp (dropped), crypto and BYMA-only
skipped, and a CEDEAR receiving no `ext_price`.

## Deployment note

`docker compose up -d` reuses the existing image; the container must be rebuilt
with `--build` or the change never reaches it.
