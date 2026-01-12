"""
Calendar API 라우터
캘린더 알림 전용 API 엔드포인트
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from app.database import get_db
from app.crud import get_or_create_user, get_setting_by_category, get_logs
from app.services.bots.calendar_bot import calendar_bot
from app.services.auth.google_auth import google_auth_service
from app.services.scheduler import scheduler_service


router = APIRouter(prefix="/api/calendar", tags=["Calendar"])


class CalendarStatusResponse(BaseModel):
    """캘린더 모듈 상태 응답"""

    is_active: bool
    notification_time: str
    google_connected: bool
    next_run_time: Optional[str] = None
    last_run_time: Optional[str] = None
    last_status: Optional[str] = None


@router.get("/status")
async def get_calendar_status(db: Session = Depends(get_db)):
    """
    캘린더 모듈 상태 조회

    Returns:
        활성화 상태, 알림 시간, Google 연동 상태, 다음 실행 시간, 마지막 실행 결과
    """
    try:
        user = get_or_create_user(db)
        setting = get_setting_by_category(db, user.user_id, "calendar")

        # Google 연동 상태 확인
        google_connected = bool(user.google_access_token and user.google_refresh_token)

        if not setting:
            return JSONResponse(
                content={
                    "is_active": False,
                    "notification_time": "08:00",
                    "google_connected": google_connected,
                    "next_run_time": None,
                    "last_run_time": None,
                    "last_status": None,
                }
            )

        # 스케줄러에서 다음 실행 시간 조회
        jobs = scheduler_service.get_all_jobs()
        calendar_job = next((job for job in jobs if job["id"] == "calendar_daily"), None)
        next_run_time = calendar_job["next_run_time"] if calendar_job else None

        # 마지막 로그 조회
        logs = get_logs(db, category="calendar", limit=1)
        last_log = logs[0] if logs else None

        return JSONResponse(
            content={
                "is_active": setting.is_active,
                "notification_time": setting.notification_time,
                "google_connected": google_connected,
                "next_run_time": next_run_time,
                "last_run_time": last_log.created_at.isoformat() if last_log else None,
                "last_status": last_log.status if last_log else None,
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/preview")
async def get_calendar_preview(db: Session = Depends(get_db)):
    """
    오늘 일정 미리보기

    Returns:
        포맷팅된 오늘의 일정 메시지
    """
    try:
        user = get_or_create_user(db)

        # Google 토큰 확인
        if not user.google_access_token or not user.google_refresh_token:
            raise HTTPException(
                status_code=400,
                detail="Google 계정 연동이 필요합니다"
            )

        # Google Credentials 생성
        try:
            credentials = google_auth_service.create_credentials(
                access_token=user.google_access_token,
                refresh_token=user.google_refresh_token,
                token_expiry=user.google_token_expiry,
            )

            # 토큰 만료 시 갱신
            if credentials.expired and credentials.refresh_token:
                credentials = google_auth_service.refresh_credentials(credentials)
                # 갱신된 토큰 DB 저장
                from app.crud import update_user_google_tokens

                update_user_google_tokens(
                    db,
                    user.user_id,
                    credentials.token,
                    credentials.refresh_token,
                    credentials.expiry,
                )

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Google 인증 실패: {str(e)}"
            )

        # 일정 조회
        events = calendar_bot.get_today_events(credentials)

        if events is None:
            raise HTTPException(
                status_code=500,
                detail="일정 조회에 실패했습니다"
            )

        # 메시지 포맷팅
        message = calendar_bot.format_calendar_message(events)

        return JSONResponse(
            content={
                "message": message,
                "event_count": len(events),
                "timestamp": datetime.now().isoformat(),
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test")
async def test_calendar_notification():
    """
    캘린더 알림 테스트 발송

    Returns:
        발송 결과
    """
    try:
        # 캘린더 알림 즉시 발송
        await calendar_bot.send_calendar_notification()

        return JSONResponse(
            content={
                "message": "캘린더 알림 테스트 발송 완료",
                "timestamp": datetime.now().isoformat(),
            }
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"캘린더 알림 발송 실패: {str(e)}"
        )


@router.get("/logs")
async def get_calendar_logs(limit: int = 20, db: Session = Depends(get_db)):
    """
    캘린더 관련 로그 조회

    Args:
        limit: 조회할 로그 개수 (기본값: 20)

    Returns:
        캘린더 카테고리 로그 목록
    """
    try:
        logs = get_logs(db, category="calendar", limit=limit)

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
