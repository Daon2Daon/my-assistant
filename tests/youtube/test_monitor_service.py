"""
MonitorService 단위 테스트.
DB(AsyncSession)와 YouTubeAPIClient를 모두 mock 처리.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.youtube.monitor_service import (
    MonitorService,
    _parse_duration,
    _parse_iso,
)
from app.services.youtube.settings_manager import PollingSettings
from app.services.youtube.youtube_api import PlaylistItemMeta, VideoMeta


# ── 공통 헬퍼 ─────────────────────────────────────────────────────────────────

def _make_polling(window_hours: int = 24, interval: int = 720) -> PollingSettings:
    return PollingSettings(
        master_interval_min=12,
        default_channel_interval_min=interval,
        youtube_api_key="key",
        youtube_daily_quota=10000,
        window_hours=window_hours,
        max_concurrent_channels=5,
        max_concurrent_analyses=3,
    )


def _make_channel(
    pk: int = 1,
    playlist_id: str = "UUTEST",
    last_checked_at=None,
    poll_interval_min: int = 720,
) -> MagicMock:
    ch = MagicMock()
    ch.channel_pk = pk
    ch.channel_id = "UC_TEST"
    ch.channel_name = "테스트 채널"
    ch.upload_playlist_id = playlist_id
    ch.is_active = True
    ch.poll_interval_min = poll_interval_min
    ch.last_checked_at = last_checked_at
    return ch


def _make_video_meta(video_id: str = "v1", published_at: str | None = None) -> VideoMeta:
    pub = published_at or datetime.now(timezone.utc).isoformat()
    return VideoMeta(
        video_id=video_id,
        video_url=f"https://www.youtube.com/watch?v={video_id}",
        title=f"영상 {video_id}",
        description=None,
        thumbnail_url=None,
        published_at=pub,
        duration="PT5M",
        view_count=100,
        like_count=10,
    )


def _make_playlist_item(video_id: str) -> PlaylistItemMeta:
    return PlaylistItemMeta(
        video_id=video_id,
        published_at=datetime.now(timezone.utc).isoformat(),
        title=f"영상 {video_id}",
    )


# ── 유틸 함수 ─────────────────────────────────────────────────────────────────

def test_parse_duration_returns_seconds():
    assert _parse_duration("PT5M33S") == 333
    assert _parse_duration("PT1H") == 3600
    assert _parse_duration(None) is None
    assert _parse_duration("INVALID") is None


def test_parse_iso_handles_z_suffix():
    dt = _parse_iso("2026-05-11T06:00:00Z")
    assert dt.tzinfo is not None
    assert dt.year == 2026


# ── list_due_channels ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_due_channels_includes_null_last_checked():
    svc = MonitorService(_make_polling())
    ch = _make_channel(last_checked_at=None)

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [ch]
    session.execute = AsyncMock(return_value=mock_result)

    due = await svc.list_due_channels(session)
    assert ch in due


@pytest.mark.asyncio
async def test_list_due_channels_excludes_recently_checked():
    svc = MonitorService(_make_polling(interval=720))
    # 10분 전에 체크 → 720분 주기이므로 미포함
    ch = _make_channel(
        last_checked_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        poll_interval_min=720,
    )

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [ch]
    session.execute = AsyncMock(return_value=mock_result)

    due = await svc.list_due_channels(session)
    assert ch not in due


@pytest.mark.asyncio
async def test_list_due_channels_includes_overdue():
    svc = MonitorService(_make_polling(interval=12))
    # 15분 전에 체크 → 12분 주기이므로 포함
    ch = _make_channel(
        last_checked_at=datetime.now(timezone.utc) - timedelta(minutes=15),
        poll_interval_min=12,
    )

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [ch]
    session.execute = AsyncMock(return_value=mock_result)

    due = await svc.list_due_channels(session)
    assert ch in due


# ── process_channel ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_process_channel_inserts_new_video_and_returns_pk():
    svc = MonitorService(_make_polling())
    channel = _make_channel(pk=1)

    api = AsyncMock()
    api.get_latest_playlist_items.return_value = [_make_playlist_item("v1")]
    api.get_video_details.return_value = [_make_video_meta("v1")]

    session = AsyncMock()
    # _filter_new_videos: "v1"이 존재하지 않으므로 신규로 처리
    existing_result = MagicMock()
    existing_result.scalars.return_value = iter([])
    # _next_sequence: max = None → 1부터 시작
    seq_result = MagicMock()
    seq_result.scalar.return_value = None
    # INSERT RETURNING pk
    insert_result = MagicMock()
    insert_result.scalar.return_value = 101

    session.execute = AsyncMock(
        side_effect=[existing_result, seq_result, insert_result, None]
    )
    session.flush = AsyncMock()

    new_pks = await svc.process_channel(
        channel=channel,
        session=session,
        api_client=api,
        backfill=True,
    )

    assert 101 in new_pks


@pytest.mark.asyncio
async def test_process_channel_skips_existing_video():
    svc = MonitorService(_make_polling())
    channel = _make_channel(pk=1)

    api = AsyncMock()
    api.get_latest_playlist_items.return_value = [_make_playlist_item("v_existing")]
    api.get_video_details.return_value = []

    session = AsyncMock()
    # _filter_new_videos: "v_existing"이 이미 존재
    existing_result = MagicMock()
    existing_result.scalars.return_value = iter(["v_existing"])
    # _update_last_checked
    update_result = MagicMock()

    session.execute = AsyncMock(side_effect=[existing_result, update_result])
    session.flush = AsyncMock()

    new_pks = await svc.process_channel(
        channel=channel,
        session=session,
        api_client=api,
    )
    assert new_pks == []


@pytest.mark.asyncio
async def test_process_channel_backfill_bypasses_window_filter():
    """backfill=True 이면 오래된 영상도 처리."""
    svc = MonitorService(_make_polling(window_hours=1))
    channel = _make_channel(pk=1)

    # 2일 전 영상 (window_hours=1 이면 window filter로 제외되어야 하지만 backfill=True로 우회)
    old_pub = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    api = AsyncMock()
    api.get_latest_playlist_items.return_value = [_make_playlist_item("v_old")]
    api.get_video_details.return_value = [_make_video_meta("v_old", published_at=old_pub)]

    session = AsyncMock()
    existing_result = MagicMock()
    existing_result.scalars.return_value = iter([])
    seq_result = MagicMock()
    seq_result.scalar.return_value = 5
    insert_result = MagicMock()
    insert_result.scalar.return_value = 200

    session.execute = AsyncMock(
        side_effect=[existing_result, seq_result, insert_result, None]
    )
    session.flush = AsyncMock()

    new_pks = await svc.process_channel(
        channel=channel,
        session=session,
        api_client=api,
        backfill=True,
    )
    assert 200 in new_pks
