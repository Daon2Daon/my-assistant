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
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    로그 목록 조회

    Args:
        category: 필터할 카테고리 (weather, finance, calendar, memo)
        limit: 조회할 로그 개수 (기본값: 100)
    """
    try:
        logs = get_logs(db, category=category, limit=limit)

        return JSONResponse(
            content={
                "count": len(logs),
                "logs": [
                    {
                        "log_id": log.log_id,
                        "category": log.category,
                        "status": log.status,
                        "message": log.message,
                        "created_at": log.created_at.isoformat() if log.created_at else None,
                    }
                    for log in logs
                ]
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"로그 조회 실패: {str(e)}")
