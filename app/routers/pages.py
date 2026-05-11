"""
Pages 라우터
모든 Web UI 페이지 렌더링 통합 관리
"""

from pathlib import Path

from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
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
        request=request,
        name="login.html",
        context={"request": request, "error": error},
    )


@router.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    """
    홈 페이지 - 시스템 상태 개요
    """
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={"request": request, "active_page": "home"},
    )


@router.get("/weather", response_class=HTMLResponse)
async def weather_page(request: Request):
    """
    날씨 알림 관리 페이지
    """
    return templates.TemplateResponse(
        request=request,
        name="weather.html",
        context={"request": request, "active_page": "weather"},
    )


@router.get("/finance", response_class=HTMLResponse)
async def finance_page(request: Request):
    """
    금융 알림 관리 페이지
    """
    return templates.TemplateResponse(
        request=request,
        name="finance.html",
        context={"request": request, "active_page": "finance"},
    )


@router.get("/chartbot", response_class=HTMLResponse)
async def chartbot_page(request: Request):
    """
    Chartbot - 종목 차트 정기 발송 관리 페이지
    """
    return templates.TemplateResponse(
        request=request,
        name="chartbot.html",
        context={"request": request, "active_page": "chartbot"},
    )


@router.get("/calendar", response_class=HTMLResponse)
async def calendar_page(request: Request):
    """
    캘린더 알림 관리 페이지
    """
    return templates.TemplateResponse(
        request=request,
        name="calendar.html",
        context={"request": request, "active_page": "calendar"},
    )


@router.get("/reminders", response_class=HTMLResponse)
async def reminders_page(request: Request):
    """
    예약 메모 관리 페이지
    """
    return templates.TemplateResponse(
        request=request,
        name="reminders.html",
        context={"request": request, "active_page": "reminders"},
    )


@router.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request):
    """
    전체 로그 조회 페이지
    """
    return templates.TemplateResponse(
        request=request,
        name="logs.html",
        context={"request": request, "active_page": "logs"},
    )


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """
    전역 설정 및 인증 관리 페이지
    """
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={"request": request, "active_page": "settings"},
    )


_YOUTUBE_SPA = Path(__file__).resolve().parents[2] / "app" / "static" / "youtube" / "index.html"


@router.get("/youtube", include_in_schema=False)
@router.get("/youtube/{full_path:path}", include_in_schema=False)
async def youtube_spa(full_path: str = ""):
    """
    YouTube Monitor SPA 셸 서빙.
    React Router가 클라이언트 사이드 라우팅을 처리하므로
    /youtube/ 로 시작하는 모든 경로에서 같은 index.html 반환.
    """
    if _YOUTUBE_SPA.exists():
        return FileResponse(str(_YOUTUBE_SPA), media_type="text/html")
    return HTMLResponse("<h1>YouTube Monitor UI를 빌드해 주세요.</h1><p>frontend/youtube/ 에서 <code>npm run build</code> 실행</p>", status_code=503)


@router.get("/api/dashboard/auth-status")
async def get_auth_status(db: Session = Depends(get_db)):
    """
    인증 상태 조회 API
    구글 연동 상태 반환
    """
    try:
        user = get_or_create_user(db)

        return JSONResponse(
            content={
                "google_connected": bool(user.google_access_token),
                "telegram_connected": bool(user.telegram_chat_id),
            }
        )
    except Exception as e:
        return JSONResponse(
            content={
                "google_connected": False,
                "telegram_connected": False,
                "error": str(e)
            }
        )
