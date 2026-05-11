"""
YouTube 설정 API 라우터 단위 테스트.

민감 정보 마스킹 / 설정 조회·수정·연결테스트 검증.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ──────────────────────────────────────────────────────────────────────────────
# 픽스처
# ──────────────────────────────────────────────────────────────────────────────

async def _no_auth_dispatch(self, request, call_next):
    return await call_next(request)


@pytest.fixture()
def app_client():
    from app.main import app
    from app.routers.youtube import get_pg_session
    from app.middleware.auth import AuthMiddleware
    from app.services.scheduler import scheduler_service
    from app.services.bots.memo_bot import memo_bot

    async def override_pg_session():
        session = AsyncMock()
        yield session

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


def _make_db_cfg(**kwargs) -> SimpleNamespace:
    defaults = dict(
        host="db.example.com",
        port=5432,
        dbname="youtube",
        username="user",
        password="supersecretpassword",
        schema="youtube",
        sslmode="prefer",
        is_configured=True,
    )
    defaults.update(kwargs)
    is_configured = defaults.pop("is_configured")
    ns = SimpleNamespace(**defaults)
    ns.is_configured = is_configured
    return ns


def _make_ai_cfg(**kwargs) -> SimpleNamespace:
    defaults = dict(
        base_url="http://litellm:4000",
        api_key="sk-longapikey1234",
        primary_model="gemini/gemini-2.5-flash",
        fallback_model="gemini/gemini-2.5-flash",
        tagging_model="gemini/gemini-2.5-flash",
        temperature=0.3,
        max_tokens=8192,
        daily_budget_usd=2.0,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_polling_cfg(**kwargs) -> SimpleNamespace:
    defaults = dict(
        master_interval_min=12,
        default_channel_interval_min=720,
        youtube_api_key="AIzaTestKey1234",
        youtube_daily_quota=10000,
        window_hours=24,
        max_concurrent_channels=5,
        max_concurrent_analyses=3,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_notif_cfg(**kwargs) -> SimpleNamespace:
    defaults = dict(
        telegram_enabled=True,
        wait_between_messages_sec=30,
        low_confidence_threshold=0.5,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ──────────────────────────────────────────────────────────────────────────────
# 데이터베이스 설정
# ──────────────────────────────────────────────────────────────────────────────

def test_get_database_settings_masks_password(app_client):
    """GET /api/youtube/settings/database — password 마스킹 확인."""
    mock_mgr = MagicMock()
    mock_mgr.get_database.return_value = _make_db_cfg()

    with patch("app.routers.youtube.get_youtube_settings_manager", return_value=mock_mgr):
        resp = app_client.get("/api/youtube/settings/database")

    assert resp.status_code == 200
    body = resp.json()
    assert body["host"] == "db.example.com"
    assert body["username"] == "user"
    # 비밀번호 마지막 4자만 노출
    assert body["password_masked"].endswith("word")
    assert body["password_masked"].startswith("*")
    assert "supersecret" not in body["password_masked"]


def test_get_database_settings_unconfigured(app_client):
    """GET /api/youtube/settings/database — 미설정 상태 반환."""
    mock_mgr = MagicMock()
    mock_mgr.get_database.return_value = _make_db_cfg(host="", is_configured=False)

    with patch("app.routers.youtube.get_youtube_settings_manager", return_value=mock_mgr):
        resp = app_client.get("/api/youtube/settings/database")

    assert resp.status_code == 200
    assert resp.json()["is_configured"] is False


# ──────────────────────────────────────────────────────────────────────────────
# AI Gateway 설정
# ──────────────────────────────────────────────────────────────────────────────

def test_get_ai_gateway_masks_api_key(app_client):
    """GET /api/youtube/settings/ai_gateway — api_key 마스킹 확인."""
    mock_mgr = MagicMock()
    mock_mgr.get_ai_gateway.return_value = _make_ai_cfg()

    with patch("app.routers.youtube.get_youtube_settings_manager", return_value=mock_mgr):
        resp = app_client.get("/api/youtube/settings/ai_gateway")

    assert resp.status_code == 200
    body = resp.json()
    assert body["base_url"] == "http://litellm:4000"
    masked = body["api_key_masked"]
    assert masked.endswith("1234")
    assert "longapikey" not in masked


# ──────────────────────────────────────────────────────────────────────────────
# 런타임 설정
# ──────────────────────────────────────────────────────────────────────────────

def test_get_runtime_settings_masks_youtube_api_key(app_client):
    """GET /api/youtube/settings/runtime — youtube_api_key 마스킹."""
    mock_mgr = MagicMock()
    mock_mgr.get_polling.return_value = _make_polling_cfg()
    mock_mgr.get_notification.return_value = _make_notif_cfg()

    with patch("app.routers.youtube.get_youtube_settings_manager", return_value=mock_mgr):
        resp = app_client.get("/api/youtube/settings/runtime")

    assert resp.status_code == 200
    body = resp.json()
    assert body["master_interval_min"] == 12
    assert body["telegram_enabled"] is True
    masked = body["youtube_api_key_masked"]
    assert masked.endswith("1234")
    assert "TestKey" not in masked


# ──────────────────────────────────────────────────────────────────────────────
# 연결 테스트
# ──────────────────────────────────────────────────────────────────────────────

def test_test_database_connection_success(app_client):
    """POST /api/youtube/settings/database/test_connection — 성공 응답."""
    from contextlib import asynccontextmanager

    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()

    @asynccontextmanager
    async def _fake_connect():
        yield mock_conn

    mock_engine = MagicMock()
    mock_engine.connect = _fake_connect

    with patch(
        "app.services.youtube.db_engine.db_engine_manager.get_engine",
        AsyncMock(return_value=mock_engine),
    ):
        resp = app_client.post("/api/youtube/settings/database/test_connection")

    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_test_ai_gateway_connection_success(app_client):
    """POST /api/youtube/settings/ai_gateway/test_connection — 성공."""
    mock_mgr = MagicMock()
    mock_mgr.get_ai_gateway.return_value = _make_ai_cfg()

    mock_client = AsyncMock()
    mock_client.get_models = AsyncMock(return_value=[{"id": "gemini/gemini-2.5-flash"}])

    with patch("app.routers.youtube.get_youtube_settings_manager", return_value=mock_mgr):
        with patch("app.services.youtube.llm_client.LiteLLMClient", return_value=mock_client):
            resp = app_client.post("/api/youtube/settings/ai_gateway/test_connection")

    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert "1" in resp.json()["message"]


def test_list_ai_gateway_models(app_client):
    """GET /api/youtube/settings/ai_gateway/models — 모델 목록."""
    mock_mgr = MagicMock()
    mock_mgr.get_ai_gateway.return_value = _make_ai_cfg()

    mock_client = AsyncMock()
    mock_client.get_models = AsyncMock(
        return_value=[{"id": "gemini/gemini-2.5-flash"}, {"id": "openai/gpt-4o"}]
    )

    with patch("app.routers.youtube.get_youtube_settings_manager", return_value=mock_mgr):
        with patch("app.services.youtube.llm_client.LiteLLMClient", return_value=mock_client):
            resp = app_client.get("/api/youtube/settings/ai_gateway/models")

    assert resp.status_code == 200
    models = resp.json()["models"]
    assert len(models) == 2
    assert models[0]["model_id"] == "gemini/gemini-2.5-flash"
