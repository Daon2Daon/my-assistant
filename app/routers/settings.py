"""
Settings API 라우터
알림 설정 CRUD 엔드포인트
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.crud import (
    get_or_create_user,
    get_settings,
    get_setting_by_category,
    create_setting,
    update_setting,
)
from app.services.scheduler import scheduler_service


router = APIRouter(prefix="/api/settings", tags=["Settings"])


class SettingResponse(BaseModel):
    """설정 응답"""

    setting_id: int
    category: str
    notification_time: str
    is_active: bool
    config_json: Optional[str] = None

    class Config:
        from_attributes = True


class SettingUpdateRequest(BaseModel):
    """설정 업데이트 요청"""

    notification_time: Optional[str] = None
    is_active: Optional[bool] = None
    config_json: Optional[str] = None


@router.get("", response_model=List[SettingResponse])
async def list_settings(db: Session = Depends(get_db)):
    """
    모든 설정 조회
    """
    try:
        user = get_or_create_user(db)
        settings_list = get_settings(db, user.user_id)

        # 기본 설정이 없으면 생성
        default_settings = [
            ("weather", "06:30"),
            ("finance", "08:00"),
            ("calendar", "07:00"),
        ]

        existing_categories = {s.category for s in settings_list}

        for category, default_time in default_settings:
            if category not in existing_categories:
                setting = create_setting(
                    db, user.user_id, category, default_time
                )
                settings_list.append(setting)

        return [
            SettingResponse(
                setting_id=s.setting_id,
                category=s.category,
                notification_time=s.notification_time,
                is_active=s.is_active,
                config_json=s.config_json,
            )
            for s in settings_list
        ]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"설정 조회 실패: {str(e)}")


@router.get("/{category}", response_model=SettingResponse)
async def get_setting(category: str, db: Session = Depends(get_db)):
    """
    카테고리별 설정 조회

    Args:
        category: 설정 카테고리 (weather, finance, calendar)
    """
    try:
        user = get_or_create_user(db)
        setting = get_setting_by_category(db, user.user_id, category)

        if not setting:
            # 기본 설정 생성
            default_times = {
                "weather": "06:30",
                "finance": "08:00",
                "calendar": "07:00",
            }
            default_time = default_times.get(category, "08:00")
            setting = create_setting(db, user.user_id, category, default_time)

        return SettingResponse(
            setting_id=setting.setting_id,
            category=setting.category,
            notification_time=setting.notification_time,
            is_active=setting.is_active,
            config_json=setting.config_json,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"설정 조회 실패: {str(e)}")


@router.put("/{category}")
async def update_setting_by_category(
    category: str,
    request: SettingUpdateRequest,
    db: Session = Depends(get_db)
):
    """
    카테고리별 설정 업데이트

    Args:
        category: 설정 카테고리 (weather, finance, calendar)
        request: 업데이트할 설정 값
    """
    try:
        user = get_or_create_user(db)
        setting = get_setting_by_category(db, user.user_id, category)

        if not setting:
            # 기본 설정 생성
            default_times = {
                "weather": "06:30",
                "finance": "08:00",
                "calendar": "07:00",
            }
            default_time = default_times.get(category, "08:00")
            setting = create_setting(db, user.user_id, category, default_time)

        # 설정 업데이트
        updated_setting = update_setting(
            db,
            setting.setting_id,
            notification_time=request.notification_time,
            config_json=request.config_json,
            is_active=request.is_active,
        )

        # 설정 변경 시 스케줄러 Job 업데이트
        if category == "weather":
            try:
                scheduler_service.update_weather_job()
            except Exception as e:
                print(f"⚠️  Weather Job 업데이트 실패: {e}")
        elif category == "calendar":
            try:
                scheduler_service.update_calendar_job()
            except Exception as e:
                print(f"⚠️  Calendar Job 업데이트 실패: {e}")
        elif category == "finance":
            try:
                scheduler_service.update_finance_jobs()
            except Exception as e:
                print(f"⚠️  Finance Job 업데이트 실패: {e}")

        return JSONResponse(
            content={
                "message": "설정 업데이트 완료",
                "setting": {
                    "setting_id": updated_setting.setting_id,
                    "category": updated_setting.category,
                    "notification_time": updated_setting.notification_time,
                    "is_active": updated_setting.is_active,
                }
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"설정 업데이트 실패: {str(e)}")
