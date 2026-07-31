# YouTube Videos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Videos" section to the per-ticker insight panel listing recent YouTube coverage of the company, restricted to a configurable channel allowlist.

**Architecture:** A new stdlib-only `youtube.py` mirrors `llm.py` — its own not-configured exception, `urllib` for HTTP, no new dependencies. One `search.list` call per symbol, filtered against the allowlist locally, cached per local calendar day in a `videos` table shaped like `earnings`. `app.py` orchestrates and merges into the `/api/insight` payload; `sources.py` is untouched.

**Tech Stack:** Flask, SQLite, stdlib `urllib`, pytest, vanilla JS + Bootstrap 5.

## Global Constraints

- Spec: `docs/plans/2026-07-31-youtube-videos-design.md`.
- No new pip dependencies. `youtube.py` uses only the standard library.
- Never hardcode channel IDs. `YOUTUBE_CHANNELS` takes handles or IDs; handles resolve through the API.
- A YouTube failure must never change `/api/insight`'s status code — it is a secondary source, and the panel has to keep showing earnings and news.
- Videos never enter the LLM prompt.
- Comments explain *why*, matching the density of the surrounding code.
- Run tests from the local venv: `./venv/bin/python3 -m pytest`.
- Tests reaching the network carry `@pytest.mark.network`. Every test in this plan is offline.

---

### Task 1: `youtube.py` — query, allowlist, search

**Files:**
- Create: `youtube.py`
- Test: `tests/test_youtube.py`

**Interfaces:**
- Produces: `NotConfigured`, `YouTubeError`, `build_query(symbol, company) -> str`, `resolve_channel_ids(entries) -> list[str]`, `fetch_videos(symbol, company) -> list[dict]` with keys `title`, `channel`, `published`, `url`.

- [ ] **Step 1: Write the failing tests** — see the test file content in Step 3's companion block below; it covers query building, the CEDEAR prefix, allowlist filtering, handle resolution and caching, `NotConfigured`, max results, and API errors.

- [ ] **Step 2: Run to verify they fail**

Run: `./venv/bin/python3 -m pytest tests/test_youtube.py -q`
Expected: collection error — no module named `youtube`.

- [ ] **Step 3: Implement `youtube.py`**

Key decisions to encode:
- `_env()` helper matching `llm.py`.
- `build_query` strips a leading `CEDEAR ` from the company name.
- An entry starting with `@` is a handle; anything else is treated as an ID.
- `_HANDLE_CACHE` module dict so a handle costs one unit per process.
- `fetch_videos` raises `NotConfigured` before any network call when the key is missing.

- [ ] **Step 4: Run to verify they pass**

Run: `./venv/bin/python3 -m pytest tests/test_youtube.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add youtube.py tests/test_youtube.py
git commit -m "Add the YouTube search module"
```

---

### Task 2: `videos` cache and the insight payload

**Files:**
- Modify: `app.py` (`ensure_schema`, cache helpers next to the earnings ones, `api_insight`)
- Test: `tests/test_insight_route.py`

**Interfaces:**
- Produces: table `videos (symbol TEXT PRIMARY KEY, payload TEXT, fetched_on TEXT NOT NULL)`; `read_videos_cache(symbol) -> (hit, list|None)`; `write_videos_cache(symbol, videos)`; `company_for_symbol(symbol) -> str|None`; `/api/insight` payload gains `videos` and optionally `videos_error`.

- [ ] **Step 1: Write the failing tests** covering: payload includes `videos`; missing key yields `videos_error` with the rest of the payload intact and no network call; second call hits the cache; a yesterday entry is stale; empty results are cached; a YouTube failure leaves the status code alone.

- [ ] **Step 2: Run to verify they fail**

Run: `./venv/bin/python3 -m pytest tests/test_insight_route.py -q`
Expected: `KeyError: 'videos'`.

- [ ] **Step 3: Implement** — mirror the earnings cache helpers exactly; wrap the `youtube` call so `NotConfigured` and `YouTubeError` both become `videos_error` rather than an HTTP error.

- [ ] **Step 4: Run the whole suite**

Run: `./venv/bin/python3 -m pytest tests/ -m "not network" -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_insight_route.py
git commit -m "Cache videos per day and merge them into the insight payload"
```

---

### Task 3: The panel section

**Files:**
- Modify: `index.html` (`renderInsight`)

No test — `index.html` has no test harness. Verified by rendering the preview page with headless Chrome, as with the previous panel work.

- [ ] **Step 1: Add the Videos section** after the news block, reusing the `<h6>` + list markup so it inherits the divider styling.
- [ ] **Step 2: Render the preview and screenshot it** to confirm both the populated and the not-configured states.
- [ ] **Step 3: Commit**

---

### Task 4: Packaging and documentation

**Files:**
- Modify: `Dockerfile`, `.env.example`, `README.md`, `CLAUDE.md`

- [ ] **Step 1: Add `youtube.py` to the Dockerfile `COPY`** — a missing module only fails at container start, which the file already warns about.
- [ ] **Step 2: Add the four variables to `.env.example`** in the style of the LLM block, including where to get the key.
- [ ] **Step 3: Document in `README.md`** — the quota arithmetic, why the allowlist leaves the section empty often, and how to build `YOUTUBE_CHANNELS` from handles.
- [ ] **Step 4: Document in `CLAUDE.md`** — the module, the `videos` table, and the quota constraint behind searching once and filtering locally.
- [ ] **Step 5: Rebuild the container and commit.**
