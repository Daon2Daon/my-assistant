"""
Reminder 모델
예약 메모 데이터를 관리하는 테이블
"""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.sql import func
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from app.database import Base


class Reminder(Base):
    """
    예약 메모 테이블
    사용자가 예약한 메시지를 저장하고 발송 상태를 관리
    """

    __tablename__ = "reminders"

    reminder_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)

    # 메모 내용
    message_content = Column(String, nullable=False)

    # 발송 예정 시간 (한국 시간대, naive datetime으로 저장)
    target_datetime = Column(DateTime(timezone=False), nullable=False, index=True,
                            default=lambda: datetime.now(ZoneInfo("Asia/Seoul")))

    # 발송 완료 여부 (0: 대기, 1: 발송완료)
    is_sent = Column(Boolean, default=False)

    # 메타데이터
    created_at = Column(DateTime(timezone=False), default=lambda: datetime.now(ZoneInfo("Asia/Seoul")))

    def __repr__(self):
        return f"<Reminder(id={self.reminder_id}, sent={self.is_sent}, target={self.target_datetime})>"
