import pytest

import youtube


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """No test may depend on the developer's real YouTube configuration."""
    for name in ("YOUTUBE_API_KEY", "YOUTUBE_CHANNELS",
                 "YOUTUBE_MAX_RESULTS", "YOUTUBE_DAYS"):
        monkeypatch.delenv(name, raising=False)
    youtube._HANDLE_CACHE.clear()


def search_response(*items):
    """A search.list body with one entry per (video_id, title, channel_id)."""
    return {"items": [
        {
            "id": {"videoId": video_id},
            "snippet": {
                "title": title,
                "channelId": channel_id,
                "channelTitle": channel_id + " Name",
                "publishedAt": "2026-07-29T12:00:00Z",
            },
        }
        for video_id, title, channel_id in items
    ]}


# ---- Query building ----

def test_query_pairs_the_ticker_with_the_company():
    query = youtube.build_query("AMD", "Advanced Micro Devices")
    assert "AMD" in query
    assert "Advanced Micro Devices" in query


def test_query_drops_the_cedear_prefix():
    # Holdings store ALAB as "CEDEAR ASTERA LABS INC"; the prefix is a local
    # instrument label, not part of the company's name, and pollutes the search.
    query = youtube.build_query("ALAB", "CEDEAR ASTERA LABS INC")
    assert "CEDEAR" not in query
    assert "ASTERA LABS INC" in query


def test_query_survives_a_missing_company():
    assert youtube.build_query("AMD", None) == "AMD"


# ---- Channel allowlist ----

def test_plain_ids_pass_through_without_a_call(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("an ID needs no resolving")

    monkeypatch.setattr(youtube, "_get", fail)
    assert youtube.resolve_channel_ids(["UCaaa", "UCbbb"]) == ["UCaaa", "UCbbb"]


def test_handles_are_resolved_to_ids(monkeypatch):
    monkeypatch.setattr(
        youtube, "_get",
        lambda path, params: {"items": [{"id": "UCbloomberg"}]},
    )
    assert youtube.resolve_channel_ids(["@Bloomberg"]) == ["UCbloomberg"]


def test_a_handle_is_resolved_only_once(monkeypatch):
    calls = []

    def fake(path, params):
        calls.append(params)
        return {"items": [{"id": "UCbloomberg"}]}

    monkeypatch.setattr(youtube, "_get", fake)
    youtube.resolve_channel_ids(["@Bloomberg"])
    youtube.resolve_channel_ids(["@Bloomberg"])
    assert len(calls) == 1


def test_an_unresolvable_handle_is_dropped(monkeypatch):
    monkeypatch.setattr(youtube, "_get", lambda path, params: {"items": []})
    assert youtube.resolve_channel_ids(["@nosuchchannel"]) == []


# ---- fetch_videos ----

def test_no_api_key_raises_before_touching_the_network(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("must not reach the network without a key")

    monkeypatch.setattr(youtube, "_get", fail)
    with pytest.raises(youtube.NotConfigured):
        youtube.fetch_videos("AMD", "Advanced Micro Devices")


def test_allowlist_drops_other_channels(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "k")
    monkeypatch.setenv("YOUTUBE_CHANNELS", "UCallowed")
    monkeypatch.setattr(
        youtube, "_get",
        lambda path, params: search_response(
            ("v1", "Del canal permitido", "UCallowed"),
            ("v2", "De un canal cualquiera", "UCrandom"),
        ),
    )
    videos = youtube.fetch_videos("AMD", "Advanced Micro Devices")
    assert [v["title"] for v in videos] == ["Del canal permitido"]


def test_without_an_allowlist_everything_is_kept(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "k")
    monkeypatch.setattr(
        youtube, "_get",
        lambda path, params: search_response(
            ("v1", "Uno", "UCa"), ("v2", "Dos", "UCb"),
        ),
    )
    assert len(youtube.fetch_videos("AMD", "AMD Inc")) == 2


def test_results_are_capped(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "k")
    monkeypatch.setenv("YOUTUBE_MAX_RESULTS", "2")
    monkeypatch.setattr(
        youtube, "_get",
        lambda path, params: search_response(
            ("v1", "Uno", "UCa"), ("v2", "Dos", "UCa"), ("v3", "Tres", "UCa"),
        ),
    )
    assert len(youtube.fetch_videos("AMD", "AMD Inc")) == 2


def test_a_video_carries_what_the_panel_shows(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "k")
    monkeypatch.setattr(
        youtube, "_get",
        lambda path, params: search_response(("abc123", "Un título", "UCa")),
    )
    video = youtube.fetch_videos("AMD", "AMD Inc")[0]
    assert video["title"] == "Un título"
    assert video["channel"] == "UCa Name"
    assert video["published"] == "2026-07-29"
    assert video["url"] == "https://www.youtube.com/watch?v=abc123"


def test_entries_without_a_video_id_are_skipped(monkeypatch):
    # search.list also returns channel and playlist hits, whose id carries no
    # videoId; linking to watch?v=None would be a dead link.
    monkeypatch.setenv("YOUTUBE_API_KEY", "k")
    monkeypatch.setattr(
        youtube, "_get",
        lambda path, params: {"items": [
            {"id": {"channelId": "UCa"}, "snippet": {"title": "Un canal", "channelId": "UCa"}},
        ]},
    )
    assert youtube.fetch_videos("AMD", "AMD Inc") == []


def test_an_api_failure_becomes_a_youtube_error(monkeypatch):
    def boom(path, params):
        raise youtube.YouTubeError("cuota agotada")

    monkeypatch.setenv("YOUTUBE_API_KEY", "k")
    monkeypatch.setattr(youtube, "_get", boom)
    with pytest.raises(youtube.YouTubeError):
        youtube.fetch_videos("AMD", "AMD Inc")
