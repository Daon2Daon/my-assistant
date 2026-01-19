"""
Pages 라우터
모든 Web UI 페이지 렌더링 통합 관리
"""

from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.crud import get_or_create_user

templates = Jinja2Templates(directory="app/templates")

router = APIRouter(tags=["Pages"])


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = Query(None)):
    """
    로그인 페이지
    이미 로그인된 경우 메인 페이지로 리다이렉트

    Args:
        request: FastAPI Request 객체
        error: 로그인 실패 시 전달되는 에러 파라미터

    Returns:
        HTMLResponse: 로그인 페이지 또는 리다이렉트
    """
    # 이미 로그인된 경우 메인 페이지로 리다이렉트
    if request.session.get("authenticated"):
        return RedirectResponse(url="/", status_code=303)

    # 로그인 페이지 렌더링
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": error}
    )


@router.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    """
    홈 페이지 - 시스템 상태 개요
    """
    return templates.TemplateResponse(
        "home.html",
        {"request": request, "active_page": "home"}
    )


@router.get("/weather", response_class=HTMLResponse)
async def weather_page(request: Request):
    """
    날씨 알림 관리 페이지
    """
    return templates.TemplateResponse(
        "weather.html",
        {"request": request, "active_page": "weather"}
    )


@router.get("/finance", response_class=HTMLResponse)
async def finance_page(request: Request):
    """
    금융 알림 관리 페이지
    """
    return templates.TemplateResponse(
        "finance.html",
        {"request": request, "active_page": "finance"}
    )


@router.get("/calendar", response_class=HTMLResponse)
async def calendar_page(request: Request):
    """
    캘린더 알림 관리 페이지
    """
    return templates.TemplateResponse(
        "calendar.html",
        {"request": request, "active_page": "calendar"}
    )


@router.get("/reminders", response_class=HTMLResponse)
async def reminders_page(request: Request):
    """
    예약 메모 관리 페이지
    """
    return templates.TemplateResponse(
        "reminders.html",
        {"request": request, "active_page": "reminders"}
    )


@router.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request):
    """
    전체 로그 조회 페이지
    """
    return templates.TemplateResponse(
        "logs.html",
        {"request": request, "active_page": "logs"}
    )


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """
    전역 설정 및 인증 관리 페이지
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
