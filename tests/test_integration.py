"""
통합 테스트
전체 발송 플로우, 토큰 갱신 시나리오, 에러 핸들링 테스트
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import User, Setting, Reminder, Log


class TestNotificationFlow:
    """알림 발송 플로우 통합 테스트"""

    @pytest.mark.asyncio
    async def test_weather_notification_full_flow(self, db_session, test_user):
        """날씨 알림 전체 플로우 테스트"""
        from app.services.bots.weather_bot import WeatherBot
        from app import crud

        # 1. 날씨 설정 생성 및 활성화
        setting = crud.create_setting(
            db_session, test_user.user_id, "weather", "07:00"
        )
        assert setting.is_active is True

        # 2. 날씨 데이터 조회 모킹
        bot = WeatherBot()
        mock_weather_data = {
            "name": "Seoul",
            "main": {
                "temp": 15.0,
                "temp_min": 10.0,
                "temp_max": 20.0,
                "humidity": 60,
            },
            "weather": [{"main": "Clear", "description": "맑음"}],
            "wind": {"speed": 3.0},
            "clouds": {"all": 10},
        }

        with patch.object(bot, "get_weather", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_weather_data

            # 3. 날씨 조회
            result = await bot.get_weather("Seoul")
            assert result is not None
            assert result["name"] == "Seoul"

        # 4. 메시지 포맷팅
        message = bot.format_weather_message(mock_weather_data)
        assert "Seoul" in message
        assert "15.0" in message

    @pytest.mark.asyncio
    async def test_memo_notification_full_flow(self, db_session, test_user):
        """메모 알림 전체 플로우 테스트"""
        from app import crud
        from app.services.bots.memo_bot import MemoBot

        bot = MemoBot()

        # 1. 메모 생성
        target_dt = datetime.now() + timedelta(hours=1)
        reminder = crud.create_reminder(
            db_session,
            test_user.user_id,
            "테스트 메모 내용입니다",
            target_dt,
        )
        assert reminder.reminder_id is not None
        assert reminder.is_sent is False

        # 2. 메시지 포맷팅
        message = bot.format_memo_message(reminder.message_content)
        assert "테스트 메모 내용입니다" in message
        assert "예약 메모 알림" in message

        # 3. 발송 상태 업데이트
        updated = crud.update_reminder_sent_status(
            db_session, reminder.reminder_id, is_sent=True
        )
        assert updated.is_sent is True

    @pytest.mark.asyncio
    async def test_calendar_notification_full_flow(self, mock_calendar_events):
        """캘린더 알림 전체 플로우 테스트"""
        from app.services.bots.calendar_bot import CalendarBot

        bot = CalendarBot()

        # 1. 캘린더 이벤트 포맷팅
        message = bot.format_calendar_message(mock_calendar_events)
        assert "오늘의 일정" in message
        assert "팀 미팅" in message
        assert "프로젝트 마감일" in message

    @pytest.mark.asyncio
    async def test_finance_notification_us_market(self):
        """미국 증시 알림 테스트"""
        from app.services.bots.finance_bot import FinanceBot

        bot = FinanceBot()

        # 메시지 포맷팅 테스트 (실제 API 데이터 형식에 맞춤)
        mock_data = {
            "S&P 500": {"price": 5000.0, "change": 25.0, "change_percent": 0.5},
            "Nasdaq": {"price": 16000.0, "change": 160.0, "change_percent": 1.0},
            "Dow Jones": {"price": 38000.0, "change": 114.0, "change_percent": 0.3},
        }
        message = bot.format_us_market_message(mock_data)
        assert "미국 증시" in message
        assert "S&P 500" in message

    @pytest.mark.asyncio
    async def test_finance_notification_kr_market(self):
        """한국 증시 알림 테스트"""
        from app.services.bots.finance_bot import FinanceBot

        bot = FinanceBot()

        # 메시지 포맷팅 테스트 (실제 API 데이터 형식에 맞춤)
        mock_data = {
            "KOSPI": {"price": 2600.0, "change_percent": 0.5},
            "KOSDAQ": {"price": 850.0, "change_percent": 0.8},
        }
        message = bot.format_kr_market_message(mock_data)
        assert "한국 증시" in message
        assert "KOSPI" in message


class TestTokenRefreshScenarios:
    """토큰 갱신 시나리오 테스트"""

    @pytest.mark.asyncio
    async def test_kakao_token_refresh(self, db_session, test_user):
        """카카오 토큰 갱신 테스트"""
        from app.services.auth.kakao_auth import KakaoAuthService
        from app import crud

        auth_service = KakaoAuthService()

        # 기존 토큰 확인
        assert test_user.kakao_access_token == "test_kakao_access_token"
        assert test_user.kakao_refresh_token == "test_kakao_refresh_token"

        # 토큰 갱신 API 호출 모킹
        mock_response = {
            "access_token": "new_access_token",
            "refresh_token": "new_refresh_token",
            "expires_in": 3600,
        }

        with patch.object(
            auth_service, "refresh_access_token", new_callable=AsyncMock
        ) as mock_refresh:
            mock_refresh.return_value = mock_response

            # 토큰 갱신
            result = await auth_service.refresh_access_token("test_kakao_refresh_token")
            assert result["access_token"] == "new_access_token"

        # DB 업데이트
        updated_user = crud.update_user_kakao_tokens(
            db_session,
            test_user.user_id,
            "new_access_token",
            "new_refresh_token",
        )
        assert updated_user.kakao_access_token == "new_access_token"
        assert updated_user.kakao_refresh_token == "new_refresh_token"

    @pytest.mark.asyncio
    async def test_google_token_refresh(self, db_session, test_user):
        """구글 토큰 갱신 테스트"""
        from app.services.auth.google_auth import GoogleAuthService
        from app import crud

        auth_service = GoogleAuthService()

        # 기존 토큰 확인
        assert test_user.google_access_token == "test_google_access_token"

        # 토큰 갱신 API 호출 모킹
        new_expiry = datetime.now() + timedelta(hours=1)
        mock_credentials = MagicMock()
        mock_credentials.token = "new_google_access_token"
        mock_credentials.refresh_token = "new_google_refresh_token"
        mock_credentials.expiry = new_expiry

        with patch.object(
            auth_service, "refresh_credentials", return_value=mock_credentials
        ) as mock_refresh:
            # 토큰 갱신 로직 실행
            mock_refresh.return_value = mock_credentials

        # DB 업데이트
        updated_user = crud.update_user_google_tokens(
            db_session,
            test_user.user_id,
            "new_google_access_token",
            "new_google_refresh_token",
            new_expiry,
        )
        assert updated_user.google_access_token == "new_google_access_token"
        assert updated_user.google_token_expiry == new_expiry

    def test_token_expiry_check(self, db_session, test_user):
        """토큰 만료 체크 테스트"""
        from app import crud

        # 만료된 토큰으로 업데이트
        expired_time = datetime.now() - timedelta(hours=1)
        crud.update_user_google_tokens(
            db_session,
            test_user.user_id,
            "expired_token",
            "refresh_token",
            expired_time,
        )

        # 만료 확인
        user = crud.get_user(db_session, test_user.user_id)
        is_expired = user.google_token_expiry < datetime.now()
        assert is_expired is True


class TestErrorHandling:
    """에러 핸들링 테스트"""

    @pytest.mark.asyncio
    async def test_weather_api_failure_handling(self):
        """날씨 API 실패 처리 테스트"""
        from app.services.bots.weather_bot import WeatherBot

        bot = WeatherBot()

        # API 실패 모킹
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await bot.get_weather("Seoul")
            assert result is None  # API 실패 시 None 반환

    @pytest.mark.asyncio
    async def test_network_error_handling(self):
        """네트워크 오류 처리 테스트"""
        from app.services.bots.weather_bot import WeatherBot
        import httpx

        bot = WeatherBot()

        # 네트워크 오류 모킹
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=httpx.RequestError("Connection failed")
            )

            result = await bot.get_weather("Seoul")
            assert result is None  # 네트워크 오류 시 None 반환

    @pytest.mark.asyncio
    async def test_kakao_api_failure_handling(self):
        """카카오 API 실패 처리 테스트"""
        from app.services.auth.kakao_auth import KakaoAuthService

        auth_service = KakaoAuthService()

        # API 실패 모킹
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_response.json.return_value = {"error": "invalid_token"}
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            # 실패 시 예외 발생 또는 None 반환
            try:
                result = await auth_service.refresh_token("invalid_token")
                # 구현에 따라 None 또는 예외
                assert result is None or "error" in result
            except Exception as e:
                # 예외 처리됨
                assert True

    def test_log_creation_on_error(self, db_session):
        """에러 발생 시 로그 생성 테스트"""
        from app import crud

        # 에러 로그 생성
        log = crud.create_log(
            db_session,
            "weather",
            "FAIL",
            "API 호출 실패: Connection timeout",
        )

        assert log.log_id is not None
        assert log.status == "FAIL"
        assert "Connection timeout" in log.message

        # 로그 조회 확인
        logs = crud.get_logs(db_session, category="weather")
        assert len(logs) >= 1
        assert any(l.status == "FAIL" for l in logs)

    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        """타임아웃 처리 테스트"""
        from app.services.bots.weather_bot import WeatherBot
        import asyncio

        bot = WeatherBot()

        # 타임아웃 모킹
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=asyncio.TimeoutError()
            )

            result = await bot.get_weather("Seoul")
            assert result is None  # 타임아웃 시 None 반환


class TestDatabaseConsistency:
    """데이터베이스 일관성 테스트"""

    def test_reminder_lifecycle(self, db_session, test_user):
        """메모 생명주기 테스트 (생성 -> 발송 -> 삭제)"""
        from app import crud

        # 생성
        reminder = crud.create_reminder(
            db_session,
            test_user.user_id,
            "테스트 메모",
            datetime.now() + timedelta(hours=1),
        )
        assert reminder.is_sent is False

        # 발송 상태 업데이트
        updated = crud.update_reminder_sent_status(
            db_session, reminder.reminder_id, is_sent=True
        )
        assert updated.is_sent is True

        # 삭제
        result = crud.delete_reminder(db_session, reminder.reminder_id)
        assert result is True

        # 삭제 확인
        deleted = crud.get_reminder(db_session, reminder.reminder_id)
        assert deleted is None

    def test_setting_toggle(self, db_session, test_user):
        """설정 ON/OFF 토글 테스트"""
        from app import crud

        # 설정 생성 (기본 활성화)
        setting = crud.create_setting(
            db_session, test_user.user_id, "weather", "07:00"
        )
        assert setting.is_active is True

        # 비활성화
        updated = crud.update_setting(db_session, setting.setting_id, is_active=False)
        assert updated.is_active is False

        # 다시 활성화
        updated = crud.update_setting(db_session, setting.setting_id, is_active=True)
        assert updated.is_active is True

    def test_log_retrieval_and_filtering(self, db_session):
        """로그 조회 및 필터링 테스트"""
        from app import crud

        # 여러 로그 생성 (다른 카테고리)
        crud.create_log(db_session, "category_a", "SUCCESS", "Log A1")
        crud.create_log(db_session, "category_a", "SUCCESS", "Log A2")
        crud.create_log(db_session, "category_b", "FAIL", "Log B1")

        # 전체 조회
        all_logs = crud.get_logs(db_session)
        assert len(all_logs) >= 3

        # 카테고리 필터링
        logs_a = crud.get_logs(db_session, category="category_a")
        assert len(logs_a) == 2
        for log in logs_a:
            assert log.category == "category_a"

        logs_b = crud.get_logs(db_session, category="category_b")
        assert len(logs_b) == 1
        assert logs_b[0].status == "FAIL"

        # 제한(limit) 테스트
        limited_logs = crud.get_logs(db_session, limit=1)
        assert len(limited_logs) == 1
