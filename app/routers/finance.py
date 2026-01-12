"""
Finance API 라우터
금융 알림 전용 API 엔드포인트
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from app.database import get_db
from app.crud import get_or_create_user, get_setting_by_category, get_logs
from app.services.bots.finance_bot import finance_bot
from app.services.scheduler import scheduler_service


router = APIRouter(prefix="/api/finance", tags=["Finance"])


class FinanceStatusResponse(BaseModel):
    """금융 모듈 상태 응답"""

    is_active: bool
    notification_time: str
    us_next_run_time: Optional[str] = None
    kr_next_run_time: Optional[str] = None
    last_run_time: Optional[str] = None
    last_status: Optional[str] = None


@router.get("/status")
async def get_finance_status(db: Session = Depends(get_db)):
    """
    금융 모듈 상태 조회

    Returns:
        활성화 상태, 알림 시간, 다음 실행 시간, 마지막 실행 결과
    """
    try:
        user = get_or_create_user(db)
        setting = get_setting_by_category(db, user.user_id, "finance")

        if not setting:
            return JSONResponse(
                content={
                    "is_active": False,
                    "notification_time": "22:00",
                    "us_next_run_time": None,
                    "kr_next_run_time": None,
                    "last_run_time": None,
                    "last_status": None,
                }
            )

        # 스케줄러에서 다음 실행 시간 조회
        jobs = scheduler_service.get_all_jobs()
        us_job = next((job for job in jobs if job["id"] == "finance_us_daily"), None)
        kr_job = next((job for job in jobs if job["id"] == "finance_kr_daily"), None)

        us_next_run_time = us_job["next_run_time"] if us_job else None
        kr_next_run_time = kr_job["next_run_time"] if kr_job else None

        # 마지막 로그 조회
        logs = get_logs(db, category="finance", limit=1)
        last_log = logs[0] if logs else None

        return JSONResponse(
            content={
                "is_active": setting.is_active,
                "notification_time": setting.notification_time,
                "us_next_run_time": us_next_run_time,
                "kr_next_run_time": kr_next_run_time,
                "last_run_time": last_log.created_at.isoformat() if last_log else None,
                "last_status": last_log.status if last_log else None,
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/preview/us")
async def get_us_market_preview():
    """
    미국 시장 메시지 미리보기

    Returns:
        포맷팅된 미국 증시 메시지
    """
    try:
        # 증시 데이터 조회
        market_data = finance_bot.get_us_market_data()

        if not market_data:
            raise HTTPException(
                status_code=500,
                detail="미국 증시 데이터를 가져올 수 없습니다"
            )

        # 메시지 포맷팅
        message = finance_bot.format_us_market_message(market_data)

        return JSONResponse(
            content={
                "market": "US",
                "message": message,
                "timestamp": datetime.now().isoformat(),
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/preview/kr")
async def get_kr_market_preview():
    """
    한국 시장 메시지 미리보기

    Returns:
        포맷팅된 한국 증시 메시지
    """
    try:
        # 증시 데이터 조회
        market_data = finance_bot.get_kr_market_data()

        if not market_data:
            raise HTTPException(
                status_code=500,
                detail="한국 증시 데이터를 가져올 수 없습니다"
            )

        # 메시지 포맷팅
        message = finance_bot.format_kr_market_message(market_data)

        return JSONResponse(
            content={
                "market": "KR",
                "message": message,
                "timestamp": datetime.now().isoformat(),
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test/us")
async def test_us_market_notification():
    """
    미국 증시 알림 테스트 발송

    Returns:
        발송 결과
    """
    try:
        # 미국 증시 알림 즉시 발송
        await finance_bot.send_us_market_notification()

        return JSONResponse(
            content={
                "message": "미국 증시 알림 테스트 발송 완료",
                "timestamp": datetime.now().isoformat(),
            }
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"미국 증시 알림 발송 실패: {str(e)}"
        )


@router.post("/test/kr")
async def test_kr_market_notification():
    """
    한국 증시 알림 테스트 발송

    Returns:
        발송 결과
    """
    try:
        # 한국 증시 알림 즉시 발송
        await finance_bot.send_kr_market_notification()

        return JSONResponse(
            content={
                "message": "한국 증시 알림 테스트 발송 완료",
                "timestamp": datetime.now().isoformat(),
            }
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"한국 증시 알림 발송 실패: {str(e)}"
        )


@router.get("/logs")
async def get_finance_logs(limit: int = 20, db: Session = Depends(get_db)):
    """
    금융 관련 로그 조회

    Args:
        limit: 조회할 로그 개수 (기본값: 20)

    Returns:
        금융 카테고리 로그 목록
    """
    try:
        logs = get_logs(db, category="finance", limit=limit)

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
