"""
Reminders API 라우터
예약 메모 CRUD 및 스케줄링 엔드포인트
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.database import get_db
from app.crud import (
    get_or_create_user,
    get_reminders,
    get_reminder,
    create_reminder,
    delete_reminder,
    create_log,
)
from app.services.bots.memo_bot import memo_bot


router = APIRouter(prefix="/api/reminders", tags=["Reminders"])


class ReminderCreateRequest(BaseModel):
    """메모 생성 요청"""

    message_content: str = Field(..., description="메모 내용", min_length=1)
    target_datetime: datetime = Field(..., description="발송 예정 시간")


class ReminderResponse(BaseModel):
    """메모 응답"""

    reminder_id: int
    message_content: str
    target_datetime: datetime
    is_sent: bool
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("", response_model=List[ReminderResponse])
async def list_reminders(
    is_sent: Optional[bool] = None, db: Session = Depends(get_db)
):
    """
    예약 메모 목록 조회

    Args:
        is_sent: 발송 상태 필터 (None: 전체, True: 발송완료, False: 대기중)
    """
    try:
        user = get_or_create_user(db)
        reminders = get_reminders(db, user.user_id, is_sent=is_sent)

        # DB의 naive datetime을 UTC로 간주하고 KST로 변환하여 응답
        kst = ZoneInfo("Asia/Seoul")

        return [
            ReminderResponse(
                reminder_id=r.reminder_id,
                message_content=r.message_content,
                target_datetime=r.target_datetime.replace(tzinfo=timezone.utc).astimezone(kst) if r.target_datetime and not r.target_datetime.tzinfo else r.target_datetime.astimezone(kst),
                is_sent=r.is_sent,
                created_at=r.created_at.replace(tzinfo=timezone.utc).astimezone(kst) if r.created_at and not r.created_at.tzinfo else r.created_at.astimezone(kst),
            )
            for r in reminders
        ]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"메모 조회 실패: {str(e)}")


@router.get("/{reminder_id}", response_model=ReminderResponse)
async def get_reminder_detail(reminder_id: int, db: Session = Depends(get_db)):
    """
    예약 메모 상세 조회

    Args:
        reminder_id: 메모 ID
    """
    try:
        reminder = get_reminder(db, reminder_id)

        if not reminder:
            raise HTTPException(status_code=404, detail="메모를 찾을 수 없습니다")

        # DB의 naive datetime을 UTC로 간주하고 KST로 변환
        kst = ZoneInfo("Asia/Seoul")

        return ReminderResponse(
            reminder_id=reminder.reminder_id,
            message_content=reminder.message_content,
            target_datetime=reminder.target_datetime.replace(tzinfo=timezone.utc).astimezone(kst) if reminder.target_datetime and not reminder.target_datetime.tzinfo else reminder.target_datetime.astimezone(kst),
            is_sent=reminder.is_sent,
            created_at=reminder.created_at.replace(tzinfo=timezone.utc).astimezone(kst) if reminder.created_at and not reminder.created_at.tzinfo else reminder.created_at.astimezone(kst),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"메모 조회 실패: {str(e)}")


@router.post("", response_model=ReminderResponse)
async def create_new_reminder(
    request: ReminderCreateRequest, db: Session = Depends(get_db)
):
    """
    예약 메모 등록

    메모를 등록하고 지정된 시간에 발송되도록 스케줄링합니다.

    Args:
        request: 메모 생성 요청 (message_content, target_datetime)
    """
    try:
        # 받은 시간을 KST 시간대로 처리
        kst = ZoneInfo("Asia/Seoul")
        
        if request.target_datetime.tzinfo is None:
            # timezone 정보가 없으면 KST로 간주
            target_datetime_kst = request.target_datetime.replace(tzinfo=kst)
        else:
            # timezone 정보가 있으면 KST로 변환
            target_datetime_kst = request.target_datetime.astimezone(kst)

        # 과거 시간 체크 (한국 시간대 기준)
        kst_now = datetime.now(kst)
        if target_datetime_kst <= kst_now:
            raise HTTPException(
                status_code=400, detail="발송 시간은 현재 시간 이후여야 합니다"
            )

        user = get_or_create_user(db)

        # UTC로 변환하여 naive datetime으로 DB에 저장
        target_datetime_utc = target_datetime_kst.astimezone(timezone.utc)
        target_datetime_naive = target_datetime_utc.replace(tzinfo=None)
        
        reminder = create_reminder(
            db,
            user_id=user.user_id,
            message_content=request.message_content,
            target_datetime=target_datetime_naive,
        )

        # 스케줄러에 Job 등록 (KST 시간 사용)
        memo_bot.schedule_reminder(reminder.reminder_id, target_datetime_kst)

        # 로그 기록
        create_log(
            db,
            "memo",
            "CREATE",
            f"메모 등록 완료 (reminder_id: {reminder.reminder_id}, 발송예정: {target_datetime_kst})",
        )

        # DB의 naive datetime을 UTC로 간주하고 KST로 변환하여 응답
        return ReminderResponse(
            reminder_id=reminder.reminder_id,
            message_content=reminder.message_content,
            target_datetime=target_datetime_kst,
            is_sent=reminder.is_sent,
            created_at=reminder.created_at.replace(tzinfo=timezone.utc).astimezone(kst) if reminder.created_at and not reminder.created_at.tzinfo else reminder.created_at.astimezone(kst),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"메모 등록 실패: {str(e)}")


@router.delete("/{reminder_id}")
async def delete_reminder_by_id(reminder_id: int, db: Session = Depends(get_db)):
    """
    예약 메모 삭제

    메모를 삭제하고 스케줄링된 Job도 함께 취소합니다.

    Args:
        reminder_id: 삭제할 메모 ID
    """
    try:
        # 메모 조회
        reminder = get_reminder(db, reminder_id)

        if not reminder:
            raise HTTPException(status_code=404, detail="메모를 찾을 수 없습니다")

        # 이미 발송된 메모는 스케줄 취소 불필요
        if not reminder.is_sent:
            memo_bot.cancel_reminder(reminder_id)

        # 메모 삭제
        success = delete_reminder(db, reminder_id)

        if not success:
            raise HTTPException(status_code=500, detail="메모 삭제 실패")

        # 로그 기록
        create_log(db, "memo", "DELETE", f"메모 삭제 완료 (reminder_id: {reminder_id})")

        return JSONResponse(
            content={
                "message": "메모 삭제 완료",
                "reminder_id": reminder_id,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"메모 삭제 실패: {str(e)}")


@router.get("/pending/count")
async def get_pending_count(db: Session = Depends(get_db)):
    """
    대기 중인 메모 개수 조회
    """
    try:
        user = get_or_create_user(db)
        pending_reminders = get_reminders(db, user.user_id, is_sent=False)

        return JSONResponse(
            content={
                "pending_count": len(pending_reminders),
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")
