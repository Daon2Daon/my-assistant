import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.services.youtube.settings_manager import PollingSettings
from app.services.youtube.youtube_api import (
    YouTubeAPIClient,
    YouTubeQuotaExceededError,
)


def _mock_transport(handler):
    return httpx.MockTransport(handler)


def _make_client(handler, quota: int = 10000) -> YouTubeAPIClient:
    polling = PollingSettings(
        master_interval_min=12,
        default_channel_interval_min=720,
        youtube_api_key="yt-api-key",
        youtube_daily_quota=quota,
        window_hours=24,
        max_concurrent_channels=5,
        max_concurrent_analyses=3,
    )
    transport = _mock_transport(handler)
    http = httpx.AsyncClient(transport=transport, timeout=5.0)
    return YouTubeAPIClient(polling=polling, client=http)


@pytest.mark.asyncio
async def test_resolve_channel_by_uc_id_calls_channels_list():
    async def handler(request: httpx.Request) -> httpx.Response:
        p = urlparse(str(request.url))
        qs = parse_qs(p.query)
        assert p.path.endswith("/youtube/v3/channels")
        assert qs["id"][0] == "UC12345678901234567890"
        body = {
            "items": [
                {
                    "id": "UC12345678901234567890",
                    "snippet": {
                        "title": "채널명",
                        "customUrl": "@chan",
                        "thumbnails": {"high": {"url": "http://thumb"}},
                        "description": "desc",
                    },
                    "contentDetails": {"relatedPlaylists": {"uploads": "UUUPLOADS"}},
                }
            ]
        }
        return httpx.Response(200, json=body)

    c = _make_client(handler)
    try:
        meta = await c.resolve_channel("UC12345678901234567890")
        assert meta.upload_playlist_id == "UUUPLOADS"
        assert meta.channel_name == "채널명"
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_resolve_channel_by_handle_calls_forhandle_then_meta():
    calls = {"channels_id": 0, "channels_meta": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        p = urlparse(str(request.url))
        qs = parse_qs(p.query)
        if p.path.endswith("/youtube/v3/channels") and "forHandle" in qs:
            calls["channels_id"] += 1
            assert qs["forHandle"][0] == "@johndoe"
            return httpx.Response(200, json={"items": [{"id": "UC_HANDLE_ID"}]})
        if p.path.endswith("/youtube/v3/channels") and "id" in qs:
            calls["channels_meta"] += 1
            assert qs["id"][0] == "UC_HANDLE_ID"
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "UC_HANDLE_ID",
                            "snippet": {"title": "H", "thumbnails": {}},
                            "contentDetails": {"relatedPlaylists": {"uploads": "UUH"}},
                        }
                    ]
                },
            )
        return httpx.Response(404, text="unexpected")

    c = _make_client(handler)
    try:
        meta = await c.resolve_channel("@johndoe")
        assert meta.channel_id == "UC_HANDLE_ID"
        assert meta.upload_playlist_id == "UUH"
        assert calls["channels_id"] == 1
        assert calls["channels_meta"] == 1
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_resolve_channel_custom_url_uses_search_list_quota_100():
    async def handler(request: httpx.Request) -> httpx.Response:
        p = urlparse(str(request.url))
        qs = parse_qs(p.query)
        if p.path.endswith("/youtube/v3/search"):
            assert qs["q"][0] == "customName"
            return httpx.Response(
                200,
                json={"items": [{"snippet": {"channelId": "UC_FROM_SEARCH"}}]},
            )
        if p.path.endswith("/youtube/v3/channels"):
            assert qs["id"][0] == "UC_FROM_SEARCH"
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "UC_FROM_SEARCH",
                            "snippet": {"title": "S", "thumbnails": {}},
                            "contentDetails": {"relatedPlaylists": {"uploads": "UUS"}},
                        }
                    ]
                },
            )
        return httpx.Response(404, text="unexpected")

    # quota=100이면 search(100) + channels(1)에서 초과되어야 함
    c = _make_client(handler, quota=100)
    try:
        with pytest.raises(YouTubeQuotaExceededError):
            await c.resolve_channel("https://www.youtube.com/c/customName")
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_get_latest_playlist_items_parses_video_ids():
    async def handler(request: httpx.Request) -> httpx.Response:
        p = urlparse(str(request.url))
        assert p.path.endswith("/youtube/v3/playlistItems")
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "contentDetails": {"videoId": "v1"},
                        "snippet": {"publishedAt": "2026-01-01T00:00:00Z", "title": "t1"},
                    },
                    {
                        "contentDetails": {"videoId": "v2"},
                        "snippet": {"publishedAt": "2026-01-02T00:00:00Z", "title": "t2"},
                    },
                ]
            },
        )

    c = _make_client(handler)
    try:
        items = await c.get_latest_playlist_items("UUUPLOADS", max_results=5)
        assert [i.video_id for i in items] == ["v1", "v2"]
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_get_video_details_parses_counts_and_thumbnails():
    async def handler(request: httpx.Request) -> httpx.Response:
        p = urlparse(str(request.url))
        assert p.path.endswith("/youtube/v3/videos")
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "v1",
                        "snippet": {
                            "title": "A",
                            "description": "D",
                            "publishedAt": "2026-01-01T00:00:00Z",
                            "thumbnails": {"high": {"url": "http://t"}},
                        },
                        "contentDetails": {"duration": "PT5M"},
                        "statistics": {"viewCount": "10", "likeCount": "3"},
                    }
                ]
            },
        )

    c = _make_client(handler)
    try:
        vids = await c.get_video_details(["v1"])
        assert vids[0].video_url.endswith("watch?v=v1")
        assert vids[0].view_count == 10
        assert vids[0].like_count == 3
        assert vids[0].thumbnail_url == "http://t"
    finally:
        await c.aclose()

