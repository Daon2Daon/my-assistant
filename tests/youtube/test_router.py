"""
YouTube API 라우터 단위 테스트.

FastAPI TestClient를 사용하되,
- PG AsyncSession 의존성을 mock으로 교체
- AuthMiddleware를 패치하여 인증 우회
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ──────────────────────────────────────────────────────────────────────────────
# 픽스처
# ──────────────────────────────────────────────────────────────────────────────

def _make_channel(pk: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        channel_pk=pk,
        channel_id=f"UC_test_{pk}",
        channel_name=f"Test Channel {pk}",
        channel_handle=f"@test{pk}",
        thumbnail_url=None,
        description="desc",
        category="tech",
        poll_interval_min=720,
        is_active=True,
        notify_enabled=True,
        last_checked_at=None,
        last_video_id=None,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _make_video(pk: int = 1, channel_pk: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        video_pk=pk,
        channel_pk=channel_pk,
        video_id=f"vid_{pk}",
        video_url=f"https://www.youtube.com/watch?v=vid_{pk}",
        title=f"Video {pk}",
        description="desc",
        thumbnail_url=None,
        published_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        duration_seconds=300,
        view_count=1000,
        like_count=50,
        sequence_in_channel=1,
        analysis_status="done",
        analysis_error=None,
        retry_count=0,
        notified_at=None,
        created_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
    )


@pytest.fixture()
def mock_pg_session():
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session


async def _no_auth_dispatch(self, request, call_next):
    return await call_next(request)


@pytest.fixture()
def app_client(mock_pg_session):
    from app.main import app
    from app.routers.youtube import get_pg_session
    from app.middleware.auth import AuthMiddleware
    from app.services.scheduler import scheduler_service
    from app.services.bots.memo_bot import memo_bot

    async def override_pg_session():
        yield mock_pg_session

    app.dependency_overrides[get_pg_session] = override_pg_session

    original_restore = memo_bot.restore_pending_reminders
    original_get_all_jobs = scheduler_service.get_all_jobs
    memo_bot.restore_pending_reminders = lambda: 0
    scheduler_service.get_all_jobs = lambda: []

    def _mock_start():
        scheduler_service._running = True

    def _mock_shutdown():
        scheduler_service._running = False

    scheduler_service.start = _mock_start
    scheduler_service.shutdown = _mock_shutdown

    with patch("app.main.init_db"), \
         patch("app.main.run_migrations"), \
         patch.object(AuthMiddleware, "dispatch", _no_auth_dispatch):
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client

    app.dependency_overrides.clear()
    memo_bot.restore_pending_reminders = original_restore
    scheduler_service.get_all_jobs = original_get_all_jobs


# ──────────────────────────────────────────────────────────────────────────────
# 채널 API
# ──────────────────────────────────────────────────────────────────────────────

def test_list_channels_returns_list(app_client, mock_pg_session):
    """GET /api/youtube/channels — 채널 목록 반환."""
    channels = [_make_channel(1), _make_channel(2)]
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = channels
    mock_pg_session.execute = AsyncMock(return_value=mock_result)

    resp = app_client.get("/api/youtube/channels")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["channel_pk"] == 1
    assert data[1]["channel_pk"] == 2


def test_update_channel_not_found_returns_404(app_client, mock_pg_session):
    """PATCH /api/youtube/channels/{pk} — 존재하지 않는 채널 404."""
    mock_pg_session.get = AsyncMock(return_value=None)

    resp = app_client.patch("/api/youtube/channels/999", json={"is_active": False})
    assert resp.status_code == 404


def test_delete_channel_not_found_returns_404(app_client, mock_pg_session):
    """DELETE /api/youtube/channels/{pk} — 존재하지 않는 채널 404."""
    mock_pg_session.get = AsyncMock(return_value=None)

    resp = app_client.delete("/api/youtube/channels/999")
    assert resp.status_code == 404


def test_delete_channel_success_returns_204(app_client, mock_pg_session):
    """DELETE /api/youtube/channels/{pk} — 성공 시 204."""
    ch = _make_channel(1)
    mock_pg_session.get = AsyncMock(return_value=ch)
    mock_pg_session.delete = AsyncMock()

    resp = app_client.delete("/api/youtube/channels/1")
    assert resp.status_code == 204


def test_trigger_poll_not_found_returns_404(app_client, mock_pg_session):
    """POST /api/youtube/channels/{pk}/poll — 없는 채널 404."""
    mock_pg_session.get = AsyncMock(return_value=None)
    resp = app_client.post("/api/youtube/channels/999/poll")
    assert resp.status_code == 404


def test_trigger_poll_accepted(app_client, mock_pg_session):
    """POST /api/youtube/channels/{pk}/poll — 정상 202."""
    ch = _make_channel(1)
    mock_pg_session.get = AsyncMock(return_value=ch)

    with patch("app.routers.youtube.asyncio.create_task"):
        resp = app_client.post("/api/youtube/channels/1/poll")
    assert resp.status_code == 202
    assert "job_id" in resp.json()


# ──────────────────────────────────────────────────────────────────────────────
# 영상 API
# ──────────────────────────────────────────────────────────────────────────────

def test_list_videos_pagination(app_client, mock_pg_session):
    """GET /api/youtube/videos — 페이지네이션 구조 확인."""
    videos = [_make_video(1), _make_video(2)]

    count_result = MagicMock()
    count_result.scalar_one.return_value = 2

    video_result = MagicMock()
    video_result.scalars.return_value.all.return_value = videos

    summary_result = MagicMock()
    summary_result.scalars.return_value.all.return_value = []

    mock_pg_session.execute = AsyncMock(
        side_effect=[count_result, video_result, summary_result]
    )

    resp = app_client.get("/api/youtube/videos?page=1&page_size=20")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["page"] == 1
    assert len(body["items"]) == 2


def test_get_video_detail_not_found_returns_404(app_client, mock_pg_session):
    """GET /api/youtube/videos/{pk} — 없는 영상 404."""
    mock_pg_session.get = AsyncMock(return_value=None)
    resp = app_client.get("/api/youtube/videos/9999")
    assert resp.status_code == 404


def test_reanalyze_not_found_returns_404(app_client, mock_pg_session):
    """POST /api/youtube/videos/{pk}/reanalyze — 없는 영상 404."""
    mock_pg_session.get = AsyncMock(return_value=None)
    resp = app_client.post("/api/youtube/videos/9999/reanalyze")
    assert resp.status_code == 404


def test_reanalyze_accepted(app_client, mock_pg_session):
    """POST /api/youtube/videos/{pk}/reanalyze — 202 반환."""
    v = _make_video(1)
    mock_pg_session.get = AsyncMock(return_value=v)
    exec_result = MagicMock()
    mock_pg_session.execute = AsyncMock(return_value=exec_result)

    with patch("app.routers.youtube.asyncio.create_task"):
        resp = app_client.post("/api/youtube/videos/1/reanalyze")
    assert resp.status_code == 202
    assert "job_id" in resp.json()


# ──────────────────────────────────────────────────────────────────────────────
# 통계 API
# ──────────────────────────────────────────────────────────────────────────────

def test_stats_returns_counts(app_client, mock_pg_session):
    """GET /api/youtube/stats — 카운트 필드 구조 확인."""
    scalars = [10, 8, 100, 90, 5, 3, 80, 50, None]
    results = []
    for val in scalars:
        r = MagicMock()
        r.scalar_one.return_value = val
        results.append(r)

    mock_pg_session.execute = AsyncMock(side_effect=results)

    resp = app_client.get("/api/youtube/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_channels"] == 10
    assert body["active_channels"] == 8
    assert body["total_videos"] == 100
