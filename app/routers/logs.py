"""
Logs API 라우터
시스템 로그 조회 엔드포인트
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from app.database import get_db
from app.crud import get_logs


router = APIRouter(prefix="/api/logs", tags=["Logs"])


class LogResponse(BaseModel):
    """로그 응답"""

    log_id: int
    category: str
    status: str
    message: str
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("")
async def list_logs(
    category: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """
    로그 목록 조회 (페이지네이션 지원)

    Args:
        category: 필터할 카테고리 (weather, finance, calendar, memo)
        status: 필터할 상태 (SUCCESS, FAIL, SKIP)
        limit: 조회할 로그 개수 (기본값: 100)
        offset: 건너뛸 로그 개수 (기본값: 0)
    """
    try:
        from app.models.log import Log
        from sqlalchemy import desc

        # 쿼리 빌드
        query = db.query(Log)

        # 카테고리 필터
        if category:
            query = query.filter(Log.category == category)

        # 상태 필터
        if status:
            query = query.filter(Log.status == status)

        # 전체 개수 조회
        total_count = query.count()

        # 정렬 및 페이지네이션
        logs = query.order_by(desc(Log.created_at)).offset(offset).limit(limit).all()

        return JSONResponse(
            content={
                "total": total_count,
                "count": len(logs),
                "offset": offset,
                "limit": limit,
                "logs": [
                    {
                        "log_id": log.log_id,
                        "category": log.category,
                        "status": log.status,
                        "message": log.message,
                        "created_at": log.created_at.isoformat() if log.created_at else None,
                        "created_at_kst": log.created_at.astimezone(ZoneInfo("Asia/Seoul")).isoformat() if log.created_at and log.created_at.tzinfo else None,
                    }
                    for log in logs
                ]
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"로그 조회 실패: {str(e)}")


@router.get("/stats")
async def get_logs_stats(db: Session = Depends(get_db)):
    """
    로그 통계 조회

    Returns:
        카테고리별, 상태별 로그 통계
    """
    try:
        from app.models.log import Log
        from sqlalchemy import func

        # 카테고리별 통계
        category_stats = db.query(
            Log.category,
            func.count(Log.log_id).label("count")
        ).group_by(Log.category).all()

        # 상태별 통계
        status_stats = db.query(
            Log.status,
            func.count(Log.log_id).label("count")
        ).group_by(Log.status).all()

        # 카테고리 + 상태별 통계
        category_status_stats = db.query(
            Log.category,
            Log.status,
            func.count(Log.log_id).label("count")
        ).group_by(Log.category, Log.status).all()

        # 전체 로그 개수
        total_logs = db.query(func.count(Log.log_id)).scalar()

        return JSONResponse(
            content={
                "total_logs": total_logs,
                "by_category": {
                    stat.category: stat.count for stat in category_stats
                },
                "by_status": {
                    stat.status: stat.count for stat in status_stats
                },
                "by_category_status": [
                    {
                        "category": stat.category,
                        "status": stat.status,
                        "count": stat.count
                    }
                    for stat in category_status_stats
                ]
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"통계 조회 실패: {str(e)}")
