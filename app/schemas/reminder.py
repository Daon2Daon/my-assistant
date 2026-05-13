"""
Reminder Pydantic 스키마
API 요청/응답을 위한 예약 메모 데이터 검증 및 직렬화
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ReminderBase(BaseModel):
    """Reminder 기본 스키마"""

    message_content: str = Field(..., description="메모 내용", min_length=1)
    target_datetime: datetime = Field(..., description="발송 예정 시간")


class ReminderCreate(ReminderBase):
    """Reminder 생성 요청 스키마"""

    user_id: int


class ReminderUpdate(BaseModel):
    """Reminder 업데이트 요청 스키마"""

    message_content: Optional[str] = None
    target_datetime: Optional[datetime] = None
    is_sent: Optional[bool] = None


class ReminderResponse(ReminderBase):
    """Reminder 응답 스키마"""

    reminder_id: int
    user_id: int
    is_sent: bool
    created_at: datetime

    class Config:
        from_attributes = True  # ORM 모드 활성화
