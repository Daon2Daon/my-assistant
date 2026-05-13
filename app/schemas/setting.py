"""
Setting Pydantic 스키마
API 요청/응답을 위한 설정 데이터 검증 및 직렬화
"""

from typing import Optional
from pydantic import BaseModel, Field


class SettingBase(BaseModel):
    """Setting 기본 스키마"""

    category: str = Field(..., description="알림 카테고리 (weather, finance, calendar)")
    notification_time: str = Field(..., description="알림 시간 (HH:MM 형식)")
    config_json: Optional[str] = Field(None, description="추가 설정 JSON")
    is_active: bool = Field(default=True, description="활성화 여부")


class SettingCreate(SettingBase):
    """Setting 생성 요청 스키마"""

    user_id: int


class SettingUpdate(BaseModel):
    """Setting 업데이트 요청 스키마"""

    notification_time: Optional[str] = None
    config_json: Optional[str] = None
    is_active: Optional[bool] = None


class SettingResponse(SettingBase):
    """Setting 응답 스키마"""

    setting_id: int
    user_id: int

    class Config:
        from_attributes = True  # ORM 모드 활성화
