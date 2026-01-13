"""
CRUD 유틸리티 함수
데이터베이스 작업을 위한 공통 함수 모음
"""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from app.models import User, Setting, Reminder, Log


# ============================================================
# User CRUD
# ============================================================


def get_user(db: Session, user_id: int) -> Optional[User]:
    """
    사용자 ID로 사용자 조회
    """
    return db.query(User).filter(User.user_id == user_id).first()


def get_or_create_user(db: Session) -> User:
    """
    사용자 조회 또는 생성
    현재는 단일 사용자 시스템이므로 user_id=1 사용
    """
    user = db.query(User).filter(User.user_id == 1).first()
    if not user:
        user = User(user_id=1)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def update_user_kakao_tokens(
    db: Session, user_id: int, access_token: str, refresh_token: str
) -> User:
    """
    카카오 토큰 업데이트
    """
    user = get_user(db, user_id)
    if user:
        user.kakao_access_token = access_token
        user.kakao_refresh_token = refresh_token
        user.updated_at = datetime.now()
        db.commit()
        db.refresh(user)
    return user


def update_user_google_tokens(
    db: Session,
    user_id: int,
    access_token: str,
    refresh_token: str,
    token_expiry: datetime,
) -> User:
    """
    구글 토큰 업데이트
    """
    user = get_user(db, user_id)
    if user:
        user.google_access_token = access_token
        user.google_refresh_token = refresh_token
        user.google_token_expiry = token_expiry
        user.updated_at = datetime.now()
        db.commit()
        db.refresh(user)
    return user


def update_user_telegram_chat_id(db: Session, user_id: int, chat_id: str) -> User:
    """
    텔레그램 chat_id 업데이트

    Args:
        db: 데이터베이스 세션
        user_id: 사용자 ID
        chat_id: 텔레그램 chat_id

    Returns:
        User: 업데이트된 사용자 객체
    """
    user = get_user(db, user_id)
    if user:
        user.telegram_chat_id = chat_id
        user.updated_at = datetime.now()
        db.commit()
        db.refresh(user)
    return user


def disconnect_user_telegram(db: Session, user_id: int) -> User:
    """
    텔레그램 연동 해제

    Args:
        db: 데이터베이스 세션
        user_id: 사용자 ID

    Returns:
        User: 업데이트된 사용자 객체
    """
    user = get_user(db, user_id)
    if user:
        user.telegram_chat_id = None
        user.updated_at = datetime.now()
        db.commit()
        db.refresh(user)
    return user


# ============================================================
# Setting CRUD
# ============================================================


def get_settings(db: Session, user_id: int) -> list[Setting]:
    """
    사용자의 모든 설정 조회
    """
    return db.query(Setting).filter(Setting.user_id == user_id).all()


def get_setting_by_category(
    db: Session, user_id: int, category: str
) -> Optional[Setting]:
    """
    카테고리별 설정 조회
    """
    return (
        db.query(Setting)
        .filter(Setting.user_id == user_id, Setting.category == category)
        .first()
    )


def is_setting_active(db: Session, user_id: int, category: str) -> bool:
    """
    특정 카테고리의 알림이 활성화되어 있는지 확인

    Args:
        db: 데이터베이스 세션
        user_id: 사용자 ID
        category: 카테고리 ('weather', 'finance', 'calendar')

    Returns:
        bool: 활성화 여부 (설정이 없으면 True 반환 - 기본 활성화)
    """
    setting = get_setting_by_category(db, user_id, category)
    if setting is None:
        return True  # 설정이 없으면 기본적으로 활성화
    return setting.is_active


def create_setting(
    db: Session,
    user_id: int,
    category: str,
    notification_time: str,
    config_json: Optional[str] = None,
) -> Setting:
    """
    설정 생성
    """
    setting = Setting(
        user_id=user_id,
        category=category,
        notification_time=notification_time,
        config_json=config_json,
        is_active=True,
    )
    db.add(setting)
    db.commit()
    db.refresh(setting)
    return setting


def update_setting(
    db: Session,
    setting_id: int,
    notification_time: Optional[str] = None,
    config_json: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> Optional[Setting]:
    """
    설정 업데이트
    """
    setting = db.query(Setting).filter(Setting.setting_id == setting_id).first()
    if setting:
        if notification_time is not None:
            setting.notification_time = notification_time
        if config_json is not None:
            setting.config_json = config_json
        if is_active is not None:
            setting.is_active = is_active
        db.commit()
        db.refresh(setting)
    return setting


# ============================================================
# Reminder CRUD
# ============================================================


def get_reminders(db: Session, user_id: int, is_sent: Optional[bool] = None) -> list[Reminder]:
    """
    사용자의 예약 메모 조회
    is_sent: None(전체), True(발송완료), False(대기중)
    """
    query = db.query(Reminder).filter(Reminder.user_id == user_id)
    if is_sent is not None:
        query = query.filter(Reminder.is_sent == is_sent)
    reminders = query.order_by(Reminder.target_datetime).all()

    # Ensure datetime has UTC timezone
    for reminder in reminders:
        if reminder.target_datetime and reminder.target_datetime.tzinfo is None:
            reminder.target_datetime = reminder.target_datetime.replace(tzinfo=timezone.utc)
        if reminder.created_at and reminder.created_at.tzinfo is None:
            reminder.created_at = reminder.created_at.replace(tzinfo=timezone.utc)

    return reminders


def get_reminder(db: Session, reminder_id: int) -> Optional[Reminder]:
    """
    예약 메모 ID로 조회
    """
    reminder = db.query(Reminder).filter(Reminder.reminder_id == reminder_id).first()

    # Ensure datetime has UTC timezone
    if reminder:
        if reminder.target_datetime and reminder.target_datetime.tzinfo is None:
            reminder.target_datetime = reminder.target_datetime.replace(tzinfo=timezone.utc)
        if reminder.created_at and reminder.created_at.tzinfo is None:
            reminder.created_at = reminder.created_at.replace(tzinfo=timezone.utc)

    return reminder


def create_reminder(
    db: Session, user_id: int, message_content: str, target_datetime: datetime
) -> Reminder:
    """
    예약 메모 생성
    """
    reminder = Reminder(
        user_id=user_id,
        message_content=message_content,
        target_datetime=target_datetime,
        is_sent=False,
    )
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return reminder


def update_reminder_sent_status(db: Session, reminder_id: int, is_sent: bool = True) -> Optional[Reminder]:
    """
    예약 메모 발송 상태 업데이트
    """
    reminder = get_reminder(db, reminder_id)
    if reminder:
        reminder.is_sent = is_sent
        db.commit()
        db.refresh(reminder)
    return reminder


def delete_reminder(db: Session, reminder_id: int) -> bool:
    """
    예약 메모 삭제
    """
    reminder = get_reminder(db, reminder_id)
    if reminder:
        db.delete(reminder)
        db.commit()
        return True
    return False


# ============================================================
# Log CRUD
# ============================================================


def create_log(db: Session, category: str, status: str, message: str) -> Log:
    """
    로그 생성
    """
    log = Log(category=category, status=status, message=message)
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def get_logs(
    db: Session, category: Optional[str] = None, limit: int = 100
) -> list[Log]:
    """
    로그 조회
    """
    query = db.query(Log)
    if category:
        query = query.filter(Log.category == category)
    return query.order_by(Log.created_at.desc()).limit(limit).all()
