"""
Bot 서비스 단위 테스트
날씨, 금융, 캘린더, 메모 봇 테스트
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.services.bots.weather_bot import WeatherBot


class TestWeatherBot:
    """WeatherBot 테스트"""

    def test_init(self):
        """WeatherBot 초기화 테스트"""
        bot = WeatherBot()
        assert bot.base_url == "https://api.openweathermap.org/data/2.5"

    def test_format_weather_message(self, mock_weather_data):
        """날씨 메시지 포맷팅 테스트"""
        bot = WeatherBot()
        message = bot.format_weather_message(mock_weather_data)

        assert "Seoul" in message
        assert "15.5" in message  # 현재 온도
        assert "12.0" in message  # 최저 온도
        assert "18.0" in message  # 최고 온도
        assert "맑음" in message  # 날씨 상태
        assert "불필요" in message  # 우산 불필요

    def test_format_weather_message_with_rain(self):
        """비 오는 날씨 메시지 테스트"""
        bot = WeatherBot()
        rain_data = {
            "name": "Seoul",
            "main": {
                "temp": 10.0,
                "feels_like": 8.0,
                "temp_min": 8.0,
                "temp_max": 12.0,
                "humidity": 90,
            },
            "weather": [{"main": "Rain", "description": "비"}],
            "wind": {"speed": 5.0},
            "clouds": {"all": 100},
        }

        message = bot.format_weather_message(rain_data)
        assert "필요" in message  # 우산 필요

    def test_format_weather_message_empty_data(self):
        """빈 데이터 처리 테스트"""
        bot = WeatherBot()
        message = bot.format_weather_message({})
        # 에러 없이 메시지가 생성되어야 함
        assert message is not None

    @pytest.mark.asyncio
    async def test_get_weather_success(self):
        """날씨 조회 성공 테스트"""
        bot = WeatherBot()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"name": "Seoul", "main": {"temp": 15}}

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await bot.get_weather("Seoul")
            assert result is not None
            assert result["name"] == "Seoul"

    @pytest.mark.asyncio
    async def test_get_weather_api_error(self):
        """날씨 API 오류 테스트"""
        bot = WeatherBot()

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await bot.get_weather("Seoul")
            assert result is None

    @pytest.mark.asyncio
    async def test_get_weather_network_error(self):
        """네트워크 오류 테스트"""
        bot = WeatherBot()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=Exception("Network Error")
            )

            result = await bot.get_weather("Seoul")
            assert result is None

    @pytest.mark.asyncio
    async def test_get_forecast_success(self):
        """예보 조회 성공 테스트"""
        bot = WeatherBot()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"list": [{"main": {"temp": 15}}]}

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await bot.get_forecast("Seoul")
            assert result is not None
            assert "list" in result


class TestWeatherBotNotification:
    """WeatherBot 알림 발송 테스트"""

    @pytest.mark.asyncio
    async def test_send_notification_setting_disabled(self, db_session, test_user):
        """설정 비활성화 시 알림 스킵 테스트"""
        from app.services.bots.weather_bot import weather_bot
        from app import crud

        # 날씨 설정 비활성화
        setting = crud.create_setting(db_session, test_user.user_id, "weather", "07:00")
        crud.update_setting(db_session, setting.setting_id, is_active=False)

        # 실제 DB 세션을 사용한 테스트는 통합 테스트로 분리
        # 여기서는 설정 생성 및 비활성화 동작만 확인
        is_active = crud.is_setting_active(db_session, test_user.user_id, "weather")
        assert is_active is False


class TestFinanceBot:
    """FinanceBot 관련 테스트"""

    def test_finance_bot_import(self):
        """FinanceBot 임포트 테스트"""
        from app.services.bots.finance_bot import FinanceBot, finance_bot

        assert FinanceBot is not None
        assert finance_bot is not None


class TestCalendarBot:
    """CalendarBot 관련 테스트"""

    def test_calendar_bot_import(self):
        """CalendarBot 임포트 테스트"""
        from app.services.bots.calendar_bot import CalendarBot, calendar_bot

        assert CalendarBot is not None
        assert calendar_bot is not None

    def test_format_calendar_message(self, mock_calendar_events):
        """캘린더 메시지 포맷팅 테스트"""
        from app.services.bots.calendar_bot import CalendarBot

        bot = CalendarBot()
        message = bot.format_calendar_message(mock_calendar_events)

        assert "오늘의 일정" in message
        assert "팀 미팅" in message
        assert "프로젝트 마감일" in message

    def test_format_calendar_message_empty(self):
        """빈 일정 메시지 테스트"""
        from app.services.bots.calendar_bot import CalendarBot

        bot = CalendarBot()
        message = bot.format_calendar_message([])

        assert "오늘의 일정" in message
        assert "없습니다" in message


class TestMemoBot:
    """MemoBot 관련 테스트"""

    def test_memo_bot_import(self):
        """MemoBot 임포트 테스트"""
        from app.services.bots.memo_bot import MemoBot, memo_bot

        assert MemoBot is not None
        assert memo_bot is not None

    def test_schedule_reminder(self, db_session, test_reminder):
        """메모 스케줄링 테스트"""
        from app.services.bots.memo_bot import memo_bot
        from app.services.scheduler import scheduler_service

        # 스케줄러가 실행 중이어야 함
        if not scheduler_service.is_running():
            scheduler_service.start()

        try:
            # schedule_reminder는 (reminder_id, target_datetime)만 받음
            memo_bot.schedule_reminder(
                test_reminder.reminder_id,
                test_reminder.target_datetime,
            )

            # Job이 등록되었는지 확인
            job = scheduler_service.get_job(f"reminder_{test_reminder.reminder_id}")
            assert job is not None

            # 정리
            memo_bot.cancel_reminder(test_reminder.reminder_id)

        finally:
            if scheduler_service.is_running():
                scheduler_service.shutdown()

    def test_cancel_reminder(self, db_session, test_reminder):
        """메모 취소 테스트"""
        from app.services.bots.memo_bot import memo_bot
        from app.services.scheduler import scheduler_service

        if not scheduler_service.is_running():
            scheduler_service.start()

        try:
            # 먼저 스케줄링 (reminder_id, target_datetime만 전달)
            memo_bot.schedule_reminder(
                test_reminder.reminder_id,
                test_reminder.target_datetime,
            )

            # 취소
            result = memo_bot.cancel_reminder(test_reminder.reminder_id)
            assert result is True

            # Job이 삭제되었는지 확인
            job = scheduler_service.get_job(f"reminder_{test_reminder.reminder_id}")
            assert job is None

        finally:
            if scheduler_service.is_running():
                scheduler_service.shutdown()

    def test_cancel_nonexistent_reminder(self):
        """존재하지 않는 메모 취소 테스트"""
        from app.services.bots.memo_bot import memo_bot
        from app.services.scheduler import scheduler_service

        if not scheduler_service.is_running():
            scheduler_service.start()

        try:
            result = memo_bot.cancel_reminder(99999)
            assert result is False
        finally:
            if scheduler_service.is_running():
                scheduler_service.shutdown()
