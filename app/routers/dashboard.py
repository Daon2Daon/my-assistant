"""
Dashboard 라우터
Web UI 페이지 렌더링 및 대시보드 관련 API
"""

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.crud import get_or_create_user

templates = Jinja2Templates(directory="app/templates")

router = APIRouter(tags=["Dashboard"])


@router.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """
    대시보드 메인 페이지
    """
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "active_page": "dashboard"}
    )


@router.get("/reminders", response_class=HTMLResponse)
async def reminders_page(request: Request):
    """
    Reminders 페이지
    """
    return templates.TemplateResponse(
        "reminders.html",
        {"request": request, "active_page": "reminders"}
    )


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """
    Settings 페이지
    """
    return templates.TemplateResponse(
        "settings.html",
        {"request": request, "active_page": "settings"}
    )


@router.get("/api/dashboard/auth-status")
async def get_auth_status(db: Session = Depends(get_db)):
    """
    인증 상태 조회 API
    카카오/구글 연동 상태 반환
    """
    try:
        user = get_or_create_user(db)

        return JSONResponse(
            content={
                "kakao_connected": bool(user.kakao_access_token),
                "google_connected": bool(user.google_access_token),
            }
        )
    except Exception as e:
        return JSONResponse(
            content={
                "kakao_connected": False,
                "google_connected": False,
                "error": str(e)
            }
        )
