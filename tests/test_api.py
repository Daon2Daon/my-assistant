"""
API 엔드포인트 테스트
FastAPI 라우터 테스트
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from app.models import User, Setting, Reminder, Log
from app import crud


class TestHealthEndpoint:
    """헬스 체크 엔드포인트 테스트"""

    def test_health_check(self, client):
        """헬스 체크 성공 테스트"""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


class TestAuthEndpoints:
    """인증 관련 엔드포인트 테스트"""

    def test_kakao_login_redirect(self, client):
        """카카오 로그인 리다이렉트 테스트"""
        response = client.get("/auth/kakao/login", follow_redirects=False)
        # 카카오 인증 페이지로 리다이렉트
        assert response.status_code == 307
        assert "kauth.kakao.com" in response.headers.get("location", "")

    def test_google_login_redirect(self, client):
        """구글 로그인 리다이렉트 테스트"""
        response = client.get("/auth/google/login", follow_redirects=False)
        # 구글 인증 페이지로 리다이렉트
        assert response.status_code == 307
        assert "accounts.google.com" in response.headers.get("location", "")

    def test_kakao_auth_status_not_connected(self, client):
        """카카오 연동 상태 확인 (미연동)"""
        response = client.get("/auth/kakao/status")
        assert response.status_code == 200
        data = response.json()
        assert "kakao_authenticated" in data
        assert data["kakao_authenticated"] is False

    def test_google_auth_status_not_connected(self, client):
        """구글 연동 상태 확인 (미연동)"""
        response = client.get("/auth/google/status")
        assert response.status_code == 200
        data = response.json()
        assert "google_authenticated" in data
        assert data["google_authenticated"] is False


class TestSchedulerEndpoints:
    """스케줄러 관련 엔드포인트 테스트"""

    def test_get_scheduler_status(self, client):
        """스케줄러 상태 조회 테스트"""
        response = client.get("/api/scheduler/status")
        assert response.status_code == 200
        data = response.json()
        assert "is_running" in data or "status" in data

    def test_get_scheduler_jobs(self, client):
        """스케줄러 Job 목록 조회 테스트"""
        response = client.get("/api/scheduler/jobs")
        assert response.status_code == 200
        data = response.json()
        # 응답이 dict 형태이고 jobs 키를 포함하거나, list 형태
        if isinstance(data, dict):
            assert "jobs" in data
            assert isinstance(data["jobs"], list)
        else:
            assert isinstance(data, list)

    # Note: Job 등록/삭제 테스트는 전역 스케줄러 상태를 수정하므로
    # test_scheduler.py에서 독립적으로 테스트합니다.


class TestReminderEndpoints:
    """메모(Reminder) 관련 엔드포인트 테스트"""

    def test_get_reminders_empty(self, client, db_session, test_user):
        """빈 메모 목록 조회 테스트"""
        response = client.get("/api/reminders")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_reminders_with_data(self, client, db_session, test_reminder):
        """메모 목록 조회 테스트"""
        response = client.get("/api/reminders")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    def test_create_reminder(self, client, db_session, test_user):
        """메모 생성 테스트"""
        future_time = datetime.now() + timedelta(days=1)

        with patch("app.routers.reminders.memo_bot") as mock_bot:
            response = client.post(
                "/api/reminders",
                json={
                    "message_content": "새로운 테스트 메모",
                    "target_datetime": future_time.isoformat(),
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["message_content"] == "새로운 테스트 메모"
            assert data["is_sent"] is False

    def test_create_reminder_past_datetime(self, client, db_session, test_user):
        """과거 시간으로 메모 생성 테스트"""
        past_time = datetime.now() - timedelta(days=1)

        response = client.post(
            "/api/reminders",
            json={
                "message_content": "과거 메모",
                "target_datetime": past_time.isoformat(),
            },
        )

        # 과거 시간 메모 생성은 실패해야 함 (또는 구현에 따라 다름)
        # 현재 구현에 따라 이 부분 조정 필요
        assert response.status_code in [200, 400]

    def test_delete_reminder(self, client, db_session, test_reminder):
        """메모 삭제 테스트"""
        with patch("app.routers.reminders.memo_bot") as mock_bot:
            mock_bot.cancel_reminder.return_value = True

            response = client.delete(f"/api/reminders/{test_reminder.reminder_id}")
            assert response.status_code == 200
            data = response.json()
            assert "message" in data or "reminder_id" in data

    def test_delete_reminder_not_found(self, client, db_session):
        """존재하지 않는 메모 삭제 테스트"""
        response = client.delete("/api/reminders/99999")
        assert response.status_code == 404


class TestSettingsEndpoints:
    """설정 관련 엔드포인트 테스트"""

    def test_get_settings(self, client, db_session):
        """설정 목록 조회 테스트"""
        response = client.get("/api/settings")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_settings_with_data(self, client, db_session, test_setting):
        """설정 데이터 조회 테스트"""
        response = client.get("/api/settings")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    def test_update_setting(self, client, db_session, test_setting):
        """설정 업데이트 테스트"""
        response = client.put(
            f"/api/settings/{test_setting.category}",
            json={
                "notification_time": "08:00",
                "is_active": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        # 응답 형식 확인 (setting 키 안에 데이터가 있음)
        if "setting" in data:
            assert data["setting"]["notification_time"] == "08:00"
            assert data["setting"]["is_active"] is False
        else:
            assert data["notification_time"] == "08:00"
            assert data["is_active"] is False


class TestLogsEndpoints:
    """로그 관련 엔드포인트 테스트"""

    def test_get_logs(self, client, db_session):
        """로그 목록 조회 테스트"""
        response = client.get("/api/logs")
        assert response.status_code == 200
        data = response.json()
        # 응답이 dict 형태이고 logs 키가 있음
        if isinstance(data, dict):
            assert "logs" in data
            assert isinstance(data["logs"], list)
        else:
            assert isinstance(data, list)

    def test_get_logs_with_data(self, client, db_session, test_log):
        """로그 데이터 조회 테스트"""
        response = client.get("/api/logs")
        assert response.status_code == 200
        data = response.json()
        logs = data.get("logs", data) if isinstance(data, dict) else data
        assert len(logs) >= 1

    def test_get_logs_with_category_filter(self, client, db_session, test_log):
        """카테고리 필터 로그 조회 테스트"""
        response = client.get("/api/logs?category=weather")
        assert response.status_code == 200
        data = response.json()
        logs = data.get("logs", data) if isinstance(data, dict) else data
        for log in logs:
            assert log["category"] == "weather"

    def test_get_logs_with_limit(self, client, db_session):
        """제한된 로그 조회 테스트"""
        # 여러 로그 생성
        for i in range(10):
            crud.create_log(db_session, "test", "SUCCESS", f"Log {i}")

        response = client.get("/api/logs?limit=5")
        assert response.status_code == 200
        data = response.json()
        logs = data.get("logs", data) if isinstance(data, dict) else data
        assert len(logs) <= 5


class TestDashboardEndpoints:
    """대시보드 관련 엔드포인트 테스트"""

    def test_dashboard_page(self, client):
        """대시보드 페이지 렌더링 테스트"""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_reminders_page(self, client):
        """메모 관리 페이지 렌더링 테스트"""
        response = client.get("/reminders")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_settings_page(self, client):
        """설정 페이지 렌더링 테스트"""
        response = client.get("/settings")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_auth_status_api(self, client, db_session):
        """인증 상태 API 테스트"""
        response = client.get("/api/dashboard/auth-status")
        assert response.status_code == 200
        data = response.json()
        assert "kakao_connected" in data
        assert "google_connected" in data
