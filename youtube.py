#!/usr/bin/env python3
"""YouTube search for the insight module.

Shaped like llm.py: standard library only, no new dependency, and its own
"not configured" exception so the panel can report a missing key instead of
failing the whole request.

The quota is what shapes this module. search.list costs 100 of the 10,000
free daily units, so restricting a search by channel — one call per channel —
would allow roughly a dozen lookups a day. Instead there is exactly one
search per symbol and the channel allowlist is applied here, on the results.
The trade-off is real: a whitelisted channel is not guaranteed to appear in a
general search, so the section is often empty. That is the cost of preferring
signal over coverage.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API_ROOT = "https://www.googleapis.com/youtube/v3"
REQUEST_TIMEOUT_SECONDS = 20

# Handle -> channel ID, so a handle costs one unit per process rather than
# one per lookup. Channel IDs never change, so this never needs invalidating.
_HANDLE_CACHE = {}


class NotConfigured(RuntimeError):
    """No YOUTUBE_API_KEY — the panel says so instead of showing an error."""


class YouTubeError(RuntimeError):
    """The API was reachable but the call failed."""


def _env(name, default=None):
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else default


def _int_env(name, default):
    try:
        return int(_env(name, default))
    except (TypeError, ValueError):
        return default


def _get(path, params):
    """One GET against the API. Raises YouTubeError on anything but a 200."""
    key = _env("YOUTUBE_API_KEY")
    if not key:
        raise NotConfigured("falta YOUTUBE_API_KEY")

    url = f"{API_ROOT}/{path}?" + urllib.parse.urlencode({**params, "key": key})
    try:
        with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise YouTubeError(f"YouTube HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise YouTubeError(f"YouTube: {exc}") from exc


def build_query(symbol, company):
    """Search text for one company.

    The CEDEAR prefix is stripped because holdings store the local instrument
    name ("CEDEAR ASTERA LABS INC"); it labels how the share is traded in
    Argentina, not who the company is, and it drags the search off-topic.
    """
    name = (company or "").strip()
    if name.upper().startswith("CEDEAR "):
        name = name[len("CEDEAR "):].strip()
    return f"{symbol} {name}".strip() if name else symbol


def resolve_channel_ids(entries):
    """Turn a mix of handles (@Bloomberg) and IDs (UC…) into IDs.

    Handles are accepted because they are what YouTube shows; channel IDs are
    opaque strings that are easy to copy wrong, and a wrong one fails silently
    — it simply never matches, making the allowlist look broken.
    """
    resolved = []
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        if not entry.startswith("@"):
            resolved.append(entry)
            continue
        if entry not in _HANDLE_CACHE:
            body = _get("channels", {"part": "id", "forHandle": entry})
            items = body.get("items") or []
            _HANDLE_CACHE[entry] = items[0]["id"] if items else None
        if _HANDLE_CACHE[entry]:
            resolved.append(_HANDLE_CACHE[entry])
    return resolved


def allowed_channel_ids():
    """The configured allowlist, or [] when there is none."""
    configured = _env("YOUTUBE_CHANNELS")
    if not configured:
        return []
    return resolve_channel_ids(configured.split(","))


def _published_after():
    days = _int_env("YOUTUBE_DAYS", 30)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    return since.strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_videos(symbol, company):
    """Recent videos about one company, newest-relevant first.

    An empty list means the search returned nothing that passed the
    allowlist. Missing configuration raises instead, so the panel can tell
    "nothing found" apart from "not set up".
    """
    if not _env("YOUTUBE_API_KEY"):
        raise NotConfigured("falta YOUTUBE_API_KEY")

    allowed = allowed_channel_ids()
    # 50 is the per-call maximum. Asking for fewer would save no quota and
    # would leave fewer candidates for the allowlist to match against.
    body = _get("search", {
        "part": "snippet",
        "q": build_query(symbol, company),
        "type": "video",
        "order": "relevance",
        "publishedAfter": _published_after(),
        "maxResults": 50,
    })

    limit = _int_env("YOUTUBE_MAX_RESULTS", 5)
    videos = []
    for item in body.get("items") or []:
        video_id = (item.get("id") or {}).get("videoId")
        if not video_id:
            continue
        snippet = item.get("snippet") or {}
        if allowed and snippet.get("channelId") not in allowed:
            continue
        videos.append({
            "title": snippet.get("title"),
            "channel": snippet.get("channelTitle"),
            "published": (snippet.get("publishedAt") or "")[:10] or None,
            "url": f"https://www.youtube.com/watch?v={video_id}",
        })
        if len(videos) >= limit:
            break
    return videos
