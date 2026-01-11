"""
테스트 설정 및 공통 픽스처
pytest 테스트를 위한 설정
"""

import os
import sys
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# 프로젝트 루트 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Base
from app.models import User, Setting, Reminder, Log


# 테스트용 SQLite 데이터베이스 (공유 메모리 모드로 연결 간 데이터 공유)
TEST_DATABASE_URL = "sqlite:///file::memory:?cache=shared&uri=true"

# 테스트용 엔진 및 세션
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# 공유 메모리 DB가 유지되도록 하는 연결 (모든 테스트에서 열린 상태 유지)
_keepalive_connection = test_engine.connect()


@pytest.fixture(scope="function")
def db_session():
    """
    테스트용 데이터베이스 세션 픽스처
    각 테스트마다 새로운 DB 세션 생성
    """
    # 테이블 생성
    Base.metadata.create_all(bind=test_engine)

    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        # 테이블 삭제 (각 테스트 후 초기화)
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def test_user(db_session):
    """
    테스트용 사용자 픽스처
    """
    user = User(
        user_id=1,
        kakao_access_token="test_kakao_access_token",
        kakao_refresh_token="test_kakao_refresh_token",
        google_access_token="test_google_access_token",
        google_refresh_token="test_google_refresh_token",
        google_token_expiry=datetime(2099, 12, 31, 23, 59, 59),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def test_setting(db_session, test_user):
    """
    테스트용 설정 픽스처
    """
    setting = Setting(
        user_id=test_user.user_id,
        category="weather",
        notification_time="07:00",
        config_json='{"city": "Seoul"}',
        is_active=True,
    )
    db_session.add(setting)
    db_session.commit()
    db_session.refresh(setting)
    return setting


@pytest.fixture(scope="function")
def test_reminder(db_session, test_user):
    """
    테스트용 메모 픽스처
    """
    reminder = Reminder(
        user_id=test_user.user_id,
        message_content="테스트 메모입니다",
        target_datetime=datetime(2099, 12, 31, 12, 0, 0),
        is_sent=False,
    )
    db_session.add(reminder)
    db_session.commit()
    db_session.refresh(reminder)
    return reminder


@pytest.fixture(scope="function")
def test_log(db_session):
    """
    테스트용 로그 픽스처
    """
    log = Log(
        category="weather",
        status="SUCCESS",
        message="테스트 로그 메시지",
    )
    db_session.add(log)
    db_session.commit()
    db_session.refresh(log)
    return log


@pytest.fixture(scope="function")
def client(db_session):
    """
    테스트용 FastAPI 클라이언트 픽스처
    startup/shutdown 이벤트를 모킹하여 테스트 환경에서 안정적으로 실행
    """
    from app.database import get_db
    from app.main import app
    from app.services.scheduler import scheduler_service
    from app.services.bots.memo_bot import memo_bot

    # 원본 함수 백업
    original_restore = memo_bot.restore_pending_reminders
    original_start = scheduler_service.start
    original_shutdown = scheduler_service.shutdown
    original_get_all_jobs = scheduler_service.get_all_jobs

    # 테스트용 함수로 교체
    memo_bot.restore_pending_reminders = lambda: 0

    def mock_start():
        scheduler_service._running = True

    def mock_shutdown():
        scheduler_service._running = False

    scheduler_service.start = mock_start
    scheduler_service.shutdown = mock_shutdown

    # 의존성 오버라이드
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        # 의존성 오버라이드 초기화 및 원본 복원
        app.dependency_overrides.clear()
        memo_bot.restore_pending_reminders = original_restore
        scheduler_service.start = original_start
        scheduler_service.shutdown = original_shutdown
        scheduler_service.get_all_jobs = original_get_all_jobs

        # 스케줄러 상태 초기화
        if hasattr(scheduler_service, '_running'):
            scheduler_service._running = False


@pytest.fixture
def mock_weather_data():
    """
    테스트용 날씨 데이터 픽스처
    OpenWeatherMap API 응답 형식
    """
    return {
        "name": "Seoul",
        "main": {
            "temp": 15.5,
            "feels_like": 14.2,
            "temp_min": 12.0,
            "temp_max": 18.0,
            "humidity": 65,
        },
        "weather": [
            {
                "main": "Clear",
                "description": "맑음",
            }
        ],
        "wind": {
            "speed": 3.5,
        },
        "clouds": {
            "all": 20,
        },
    }


@pytest.fixture
def mock_calendar_events():
    """
    테스트용 캘린더 이벤트 픽스처
    Google Calendar API 응답 형식
    """
    return [
        {
            "summary": "팀 미팅",
            "start": {"dateTime": "2024-01-15T09:00:00+09:00"},
            "end": {"dateTime": "2024-01-15T10:00:00+09:00"},
        },
        {
            "summary": "프로젝트 마감일",
            "start": {"date": "2024-01-15"},
            "end": {"date": "2024-01-16"},
        },
    ]
