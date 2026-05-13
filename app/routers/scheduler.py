"""
스케줄러 API 라우터
스케줄러 상태 조회 및 Job 관리 엔드포인트
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from app.services.scheduler import scheduler_service
from app.services.bots import (
    send_weather_notification_sync,
    send_us_market_notification_sync,
    send_kr_market_notification_sync,
    send_calendar_notification_sync,
)

router = APIRouter(prefix="/api/scheduler", tags=["Scheduler"])


@router.get("/status")
async def get_scheduler_status():
    """
    스케줄러 상태 확인
    """
    is_running = scheduler_service.is_running()

    return JSONResponse(
        content={
            "status": "running" if is_running else "stopped",
            "is_running": is_running,
        }
    )


@router.get("/jobs")
async def get_all_jobs():
    """
    모든 Job 목록 조회
    """
    try:
        jobs = scheduler_service.get_all_jobs()

        return JSONResponse(
            content={
                "message": f"총 {len(jobs)}개의 Job이 등록되어 있습니다",
                "count": len(jobs),
                "jobs": jobs,
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Job 조회 실패: {str(e)}")


@router.post("/jobs/weather")
async def register_weather_job(hour: int = 6, minute: int = 30):
    """
    날씨 알림 Job 등록
    매일 지정된 시간에 날씨 알림 발송

    Args:
        hour: 시 (0-23, 기본값: 6)
        minute: 분 (0-59, 기본값: 30)
    """
    try:
        if not (0 <= hour <= 23):
            raise HTTPException(status_code=400, detail="시간은 0-23 사이여야 합니다")
        if not (0 <= minute <= 59):
            raise HTTPException(status_code=400, detail="분은 0-59 사이여야 합니다")

        # Job 등록
        scheduler_service.add_cron_job(
            func=send_weather_notification_sync,
            job_id="weather_notification",
            hour=hour,
            minute=minute,
            args=("Seoul",),
        )

        return JSONResponse(
            content={
                "message": "날씨 알림 Job 등록 완료",
                "job_id": "weather_notification",
                "schedule": f"매일 {hour:02d}:{minute:02d}",
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Job 등록 실패: {str(e)}")


@router.post("/jobs/finance/us")
async def register_us_market_job(hour: int = 8, minute: int = 0):
    """
    미국 증시 알림 Job 등록
    매일 지정된 시간에 미국 증시 정보 발송

    Args:
        hour: 시 (0-23, 기본값: 8)
        minute: 분 (0-59, 기본값: 0)
    """
    try:
        if not (0 <= hour <= 23):
            raise HTTPException(status_code=400, detail="시간은 0-23 사이여야 합니다")
        if not (0 <= minute <= 59):
            raise HTTPException(status_code=400, detail="분은 0-59 사이여야 합니다")

        # Job 등록
        scheduler_service.add_cron_job(
            func=send_us_market_notification_sync,
            job_id="us_market_notification",
            hour=hour,
            minute=minute,
        )

        return JSONResponse(
            content={
                "message": "미국 증시 알림 Job 등록 완료",
                "job_id": "us_market_notification",
                "schedule": f"매일 {hour:02d}:{minute:02d}",
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Job 등록 실패: {str(e)}")


@router.post("/jobs/finance/kr")
async def register_kr_market_job(hour: int = 17, minute: int = 0):
    """
    한국 증시 알림 Job 등록
    매일 지정된 시간에 한국 증시 정보 발송

    Args:
        hour: 시 (0-23, 기본값: 17)
        minute: 분 (0-59, 기본값: 0)
    """
    try:
        if not (0 <= hour <= 23):
            raise HTTPException(status_code=400, detail="시간은 0-23 사이여야 합니다")
        if not (0 <= minute <= 59):
            raise HTTPException(status_code=400, detail="분은 0-59 사이여야 합니다")

        # Job 등록
        scheduler_service.add_cron_job(
            func=send_kr_market_notification_sync,
            job_id="kr_market_notification",
            hour=hour,
            minute=minute,
        )

        return JSONResponse(
            content={
                "message": "한국 증시 알림 Job 등록 완료",
                "job_id": "kr_market_notification",
                "schedule": f"매일 {hour:02d}:{minute:02d}",
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Job 등록 실패: {str(e)}")


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """
    Job 삭제

    Args:
        job_id: 삭제할 Job ID
    """
    try:
        success = scheduler_service.remove_job(job_id)

        if not success:
            raise HTTPException(status_code=404, detail="Job을 찾을 수 없습니다")

        return JSONResponse(
            content={
                "message": "Job 삭제 완료",
                "job_id": job_id,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Job 삭제 실패: {str(e)}")


@router.post("/jobs/{job_id}/pause")
async def pause_job(job_id: str):
    """
    Job 일시 정지

    Args:
        job_id: 정지할 Job ID
    """
    try:
        success = scheduler_service.pause_job(job_id)

        if not success:
            raise HTTPException(status_code=404, detail="Job을 찾을 수 없습니다")

        return JSONResponse(
            content={
                "message": "Job 일시 정지 완료",
                "job_id": job_id,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Job 정지 실패: {str(e)}")


@router.post("/jobs/{job_id}/resume")
async def resume_job(job_id: str):
    """
    Job 재개

    Args:
        job_id: 재개할 Job ID
    """
    try:
        success = scheduler_service.resume_job(job_id)

        if not success:
            raise HTTPException(status_code=404, detail="Job을 찾을 수 없습니다")

        return JSONResponse(
            content={
                "message": "Job 재개 완료",
                "job_id": job_id,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Job 재개 실패: {str(e)}")


@router.post("/test/weather")
async def test_weather_notification():
    """
    날씨 알림 즉시 테스트
    """
    try:
        send_weather_notification_sync("Seoul")

        return JSONResponse(
            content={
                "message": "날씨 알림 테스트 실행 완료",
                "note": "메시지 발송 결과는 로그를 확인하세요",
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"테스트 실행 실패: {str(e)}")


@router.post("/test/finance/us")
async def test_us_market_notification():
    """
    미국 증시 알림 즉시 테스트
    """
    try:
        send_us_market_notification_sync()

        return JSONResponse(
            content={
                "message": "미국 증시 알림 테스트 실행 완료",
                "note": "메시지 발송 결과는 로그를 확인하세요",
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"테스트 실행 실패: {str(e)}")


@router.post("/test/finance/kr")
async def test_kr_market_notification():
    """
    한국 증시 알림 즉시 테스트
    """
    try:
        send_kr_market_notification_sync()

        return JSONResponse(
            content={
                "message": "한국 증시 알림 테스트 실행 완료",
                "note": "메시지 발송 결과는 로그를 확인하세요",
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"테스트 실행 실패: {str(e)}")


@router.post("/jobs/calendar")
async def register_calendar_job(hour: int = 7, minute: int = 0):
    """
    캘린더 브리핑 Job 등록
    매일 지정된 시간에 오늘의 일정 알림 발송

    Args:
        hour: 시 (0-23, 기본값: 7)
        minute: 분 (0-59, 기본값: 0)
    """
    try:
        if not (0 <= hour <= 23):
            raise HTTPException(status_code=400, detail="시간은 0-23 사이여야 합니다")
        if not (0 <= minute <= 59):
            raise HTTPException(status_code=400, detail="분은 0-59 사이여야 합니다")

        # Job 등록
        scheduler_service.add_cron_job(
            func=send_calendar_notification_sync,
            job_id="calendar_notification",
            hour=hour,
            minute=minute,
        )

        return JSONResponse(
            content={
                "message": "캘린더 브리핑 Job 등록 완료",
                "job_id": "calendar_notification",
                "schedule": f"매일 {hour:02d}:{minute:02d}",
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Job 등록 실패: {str(e)}")


@router.post("/test/calendar")
async def test_calendar_notification():
    """
    캘린더 브리핑 즉시 테스트
    """
    try:
        send_calendar_notification_sync()

        return JSONResponse(
            content={
                "message": "캘린더 브리핑 테스트 실행 완료",
                "note": "메시지 발송 결과는 로그를 확인하세요",
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"테스트 실행 실패: {str(e)}")
