"""
Weather API 라우터
날씨 알림 전용 API 엔드포인트
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from app.database import get_db
from app.crud import get_or_create_user, get_setting_by_category, get_logs
from app.services.bots.weather_bot import weather_bot
from app.services.scheduler import scheduler_service


router = APIRouter(prefix="/api/weather", tags=["Weather"])


class WeatherStatusResponse(BaseModel):
    """날씨 모듈 상태 응답"""

    is_active: bool
    notification_time: str
    next_run_time: Optional[str] = None
    last_run_time: Optional[str] = None
    last_status: Optional[str] = None


@router.get("/status")
async def get_weather_status(db: Session = Depends(get_db)):
    """
    날씨 모듈 상태 조회

    Returns:
        활성화 상태, 알림 시간, 다음 실행 시간, 마지막 실행 결과
    """
    try:
        user = get_or_create_user(db)
        setting = get_setting_by_category(db, user.user_id, "weather")

        if not setting:
            return JSONResponse(
                content={
                    "is_active": False,
                    "notification_time": "07:00",
                    "next_run_time": None,
                    "last_run_time": None,
                    "last_status": None,
                }
            )

        # 스케줄러에서 다음 실행 시간 조회
        jobs = scheduler_service.get_all_jobs()
        weather_job = next((job for job in jobs if job["id"] == "weather_daily"), None)
        next_run_time = weather_job["next_run_time"] if weather_job else None

        # 마지막 로그 조회
        logs = get_logs(db, category="weather", limit=1)
        last_log = logs[0] if logs else None

        return JSONResponse(
            content={
                "is_active": setting.is_active,
                "notification_time": setting.notification_time,
                "next_run_time": next_run_time,
                "last_run_time": last_log.created_at.isoformat() if last_log else None,
                "last_status": last_log.status if last_log else None,
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/preview")
async def get_weather_preview(city: str = "Seoul"):
    """
    날씨 메시지 미리보기

    Args:
        city: 도시명 (기본값: Seoul)

    Returns:
        포맷팅된 날씨 메시지
    """
    try:
        # 날씨 정보 조회
        weather_data = await weather_bot.get_weather(city)

        if not weather_data:
            raise HTTPException(
                status_code=500,
                detail=f"날씨 정보를 가져올 수 없습니다 - {city}"
            )

        # 메시지 포맷팅
        message = weather_bot.format_weather_message(weather_data)

        return JSONResponse(
            content={
                "city": city,
                "message": message,
                "timestamp": datetime.now().isoformat(),
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test")
async def test_weather_notification(city: str = "Seoul"):
    """
    날씨 알림 테스트 발송

    Args:
        city: 도시명 (기본값: Seoul)

    Returns:
        발송 결과
    """
    try:
        # 날씨 알림 즉시 발송
        await weather_bot.send_weather_notification(city)

        return JSONResponse(
            content={
                "message": f"날씨 알림 테스트 발송 완료 - {city}",
                "timestamp": datetime.now().isoformat(),
            }
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"날씨 알림 발송 실패: {str(e)}"
        )


@router.get("/logs")
async def get_weather_logs(limit: int = 20, db: Session = Depends(get_db)):
    """
    날씨 관련 로그 조회

    Args:
        limit: 조회할 로그 개수 (기본값: 20)

    Returns:
        날씨 카테고리 로그 목록
    """
    try:
        logs = get_logs(db, category="weather", limit=limit)

        return JSONResponse(
            content={
                "logs": [
                    {
                        "log_id": log.log_id,
                        "category": log.category,
                        "status": log.status,
                        "message": log.message,
                        "created_at": log.created_at.isoformat(),
                    }
                    for log in logs
                ],
                "count": len(logs),
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
