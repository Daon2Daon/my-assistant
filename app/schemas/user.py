"""
User Pydantic 스키마
API 요청/응답을 위한 데이터 검증 및 직렬화
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class UserBase(BaseModel):
    """User 기본 스키마"""

    pass


class UserCreate(UserBase):
    """User 생성 요청 스키마"""

    kakao_access_token: Optional[str] = None
    kakao_refresh_token: Optional[str] = None
    google_access_token: Optional[str] = None
    google_refresh_token: Optional[str] = None


class UserUpdate(BaseModel):
    """User 업데이트 요청 스키마"""

    kakao_access_token: Optional[str] = None
    kakao_refresh_token: Optional[str] = None
    google_access_token: Optional[str] = None
    google_refresh_token: Optional[str] = None
    google_token_expiry: Optional[datetime] = None


class UserResponse(UserBase):
    """User 응답 스키마"""

    user_id: int
    kakao_access_token: Optional[str] = None
    kakao_refresh_token: Optional[str] = None
    google_access_token: Optional[str] = None
    google_refresh_token: Optional[str] = None
    google_token_expiry: Optional[datetime] = None
    updated_at: datetime

    class Config:
        from_attributes = True  # ORM 모드 활성화 (SQLAlchemy 모델과 호환)
