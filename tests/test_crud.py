"""
CRUD 함수 단위 테스트
데이터베이스 CRUD 작업 테스트
"""

import pytest
from datetime import datetime
from app.models import User, Setting, Reminder, Log
from app import crud


class TestUserCRUD:
    """User CRUD 테스트"""

    def test_get_user_exists(self, db_session, test_user):
        """존재하는 사용자 조회"""
        user = crud.get_user(db_session, test_user.user_id)
        assert user is not None
        assert user.user_id == test_user.user_id

    def test_get_user_not_exists(self, db_session):
        """존재하지 않는 사용자 조회"""
        user = crud.get_user(db_session, 9999)
        assert user is None

    def test_get_or_create_user_create(self, db_session):
        """사용자 생성 테스트"""
        user = crud.get_or_create_user(db_session)
        assert user is not None
        assert user.user_id == 1

    def test_get_or_create_user_get(self, db_session, test_user):
        """기존 사용자 조회 테스트"""
        user = crud.get_or_create_user(db_session)
        assert user.user_id == test_user.user_id

    def test_update_user_kakao_tokens(self, db_session, test_user):
        """카카오 토큰 업데이트 테스트"""
        new_access_token = "new_access_token"
        new_refresh_token = "new_refresh_token"

        updated_user = crud.update_user_kakao_tokens(
            db_session, test_user.user_id, new_access_token, new_refresh_token
        )

        assert updated_user.kakao_access_token == new_access_token
        assert updated_user.kakao_refresh_token == new_refresh_token

    def test_update_user_google_tokens(self, db_session, test_user):
        """구글 토큰 업데이트 테스트"""
        new_access_token = "new_google_access"
        new_refresh_token = "new_google_refresh"
        new_expiry = datetime(2100, 1, 1, 0, 0, 0)

        updated_user = crud.update_user_google_tokens(
            db_session,
            test_user.user_id,
            new_access_token,
            new_refresh_token,
            new_expiry,
        )

        assert updated_user.google_access_token == new_access_token
        assert updated_user.google_refresh_token == new_refresh_token
        assert updated_user.google_token_expiry == new_expiry


class TestSettingCRUD:
    """Setting CRUD 테스트"""

    def test_get_settings(self, db_session, test_setting):
        """설정 목록 조회 테스트"""
        settings = crud.get_settings(db_session, test_setting.user_id)
        assert len(settings) == 1
        assert settings[0].category == "weather"

    def test_get_settings_empty(self, db_session, test_user):
        """설정이 없는 경우 테스트"""
        settings = crud.get_settings(db_session, test_user.user_id)
        assert len(settings) == 0

    def test_get_setting_by_category(self, db_session, test_setting):
        """카테고리별 설정 조회 테스트"""
        setting = crud.get_setting_by_category(
            db_session, test_setting.user_id, "weather"
        )
        assert setting is not None
        assert setting.category == "weather"

    def test_get_setting_by_category_not_found(self, db_session, test_user):
        """존재하지 않는 카테고리 조회 테스트"""
        setting = crud.get_setting_by_category(db_session, test_user.user_id, "finance")
        assert setting is None

    def test_is_setting_active_true(self, db_session, test_setting):
        """설정 활성화 상태 확인 테스트 (활성화)"""
        is_active = crud.is_setting_active(
            db_session, test_setting.user_id, "weather"
        )
        assert is_active is True

    def test_is_setting_active_false(self, db_session, test_user):
        """설정 활성화 상태 확인 테스트 (비활성화)"""
        # 비활성화된 설정 생성
        setting = crud.create_setting(
            db_session, test_user.user_id, "finance", "09:00"
        )
        crud.update_setting(db_session, setting.setting_id, is_active=False)

        is_active = crud.is_setting_active(db_session, test_user.user_id, "finance")
        assert is_active is False

    def test_is_setting_active_no_setting(self, db_session, test_user):
        """설정이 없는 경우 기본 활성화 테스트"""
        is_active = crud.is_setting_active(db_session, test_user.user_id, "calendar")
        assert is_active is True  # 설정이 없으면 기본 활성화

    def test_create_setting(self, db_session, test_user):
        """설정 생성 테스트"""
        setting = crud.create_setting(
            db_session,
            test_user.user_id,
            "finance",
            "09:00",
            '{"markets": ["KOSPI", "NASDAQ"]}',
        )

        assert setting.setting_id is not None
        assert setting.category == "finance"
        assert setting.notification_time == "09:00"
        assert setting.is_active is True

    def test_update_setting(self, db_session, test_setting):
        """설정 업데이트 테스트"""
        updated = crud.update_setting(
            db_session,
            test_setting.setting_id,
            notification_time="08:00",
            is_active=False,
        )

        assert updated.notification_time == "08:00"
        assert updated.is_active is False


class TestReminderCRUD:
    """Reminder CRUD 테스트"""

    def test_get_reminders_all(self, db_session, test_reminder):
        """전체 메모 조회 테스트"""
        reminders = crud.get_reminders(db_session, test_reminder.user_id)
        assert len(reminders) == 1

    def test_get_reminders_pending(self, db_session, test_reminder):
        """대기 중인 메모 조회 테스트"""
        reminders = crud.get_reminders(db_session, test_reminder.user_id, is_sent=False)
        assert len(reminders) == 1
        assert reminders[0].is_sent is False

    def test_get_reminders_sent(self, db_session, test_reminder):
        """발송 완료 메모 조회 테스트"""
        reminders = crud.get_reminders(db_session, test_reminder.user_id, is_sent=True)
        assert len(reminders) == 0

    def test_get_reminder(self, db_session, test_reminder):
        """단일 메모 조회 테스트"""
        reminder = crud.get_reminder(db_session, test_reminder.reminder_id)
        assert reminder is not None
        assert reminder.message_content == "테스트 메모입니다"

    def test_get_reminder_not_found(self, db_session):
        """존재하지 않는 메모 조회 테스트"""
        reminder = crud.get_reminder(db_session, 9999)
        assert reminder is None

    def test_create_reminder(self, db_session, test_user):
        """메모 생성 테스트"""
        target_dt = datetime(2099, 6, 15, 10, 0, 0)
        reminder = crud.create_reminder(
            db_session, test_user.user_id, "새 메모입니다", target_dt
        )

        assert reminder.reminder_id is not None
        assert reminder.message_content == "새 메모입니다"
        assert reminder.target_datetime == target_dt
        assert reminder.is_sent is False

    def test_update_reminder_sent_status(self, db_session, test_reminder):
        """메모 발송 상태 업데이트 테스트"""
        updated = crud.update_reminder_sent_status(
            db_session, test_reminder.reminder_id, is_sent=True
        )

        assert updated.is_sent is True

    def test_delete_reminder(self, db_session, test_reminder):
        """메모 삭제 테스트"""
        result = crud.delete_reminder(db_session, test_reminder.reminder_id)
        assert result is True

        # 삭제 확인
        reminder = crud.get_reminder(db_session, test_reminder.reminder_id)
        assert reminder is None

    def test_delete_reminder_not_found(self, db_session):
        """존재하지 않는 메모 삭제 테스트"""
        result = crud.delete_reminder(db_session, 9999)
        assert result is False


class TestLogCRUD:
    """Log CRUD 테스트"""

    def test_create_log(self, db_session):
        """로그 생성 테스트"""
        log = crud.create_log(
            db_session, "weather", "SUCCESS", "날씨 알림 발송 성공"
        )

        assert log.log_id is not None
        assert log.category == "weather"
        assert log.status == "SUCCESS"
        assert log.message == "날씨 알림 발송 성공"
        assert log.created_at is not None

    def test_get_logs_all(self, db_session, test_log):
        """전체 로그 조회 테스트"""
        logs = crud.get_logs(db_session)
        assert len(logs) == 1

    def test_get_logs_by_category(self, db_session, test_log):
        """카테고리별 로그 조회 테스트"""
        logs = crud.get_logs(db_session, category="weather")
        assert len(logs) == 1
        assert logs[0].category == "weather"

    def test_get_logs_by_category_empty(self, db_session, test_log):
        """없는 카테고리 로그 조회 테스트"""
        logs = crud.get_logs(db_session, category="finance")
        assert len(logs) == 0

    def test_get_logs_limit(self, db_session, test_user):
        """로그 제한 조회 테스트"""
        # 여러 로그 생성
        for i in range(10):
            crud.create_log(db_session, "test", "SUCCESS", f"Log {i}")

        logs = crud.get_logs(db_session, limit=5)
        assert len(logs) == 5

    def test_get_logs_order(self, db_session):
        """로그 정렬 순서 테스트 (최신순)"""
        crud.create_log(db_session, "test", "SUCCESS", "First")
        crud.create_log(db_session, "test", "SUCCESS", "Second")

        logs = crud.get_logs(db_session)
        assert logs[0].message == "Second"  # 최신순
        assert logs[1].message == "First"
