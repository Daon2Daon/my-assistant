"""
인증 API 라우터
구글 OAuth 로그인 엔드포인트 및 관리자 세션 로그인
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Form
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from urllib.parse import quote
from pydantic import BaseModel

from app.database import get_db
from app.services.auth.google_auth import google_auth_service
from app.services.auth.session_auth import (
    verify_admin_credentials,
    create_session,
    destroy_session,
    is_authenticated,
)
from app.crud import (
    get_or_create_user,
    update_user_google_tokens,
    update_user_telegram_chat_id,
    disconnect_user_telegram,
    create_log,
)
from app.services.notification import notification_service
from app.config import settings

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ============================================================
# Request Models
# ============================================================


class TelegramVerifyRequest(BaseModel):
    """텔레그램 연동 확인 요청"""

    chat_id: str


# ============================================================
# 구글 OAuth
# ============================================================


@router.get("/google/login")
async def google_login():
    """
    구글 로그인 시작
    사용자를 구글 인증 페이지로 리다이렉트
    """
    auth_url = google_auth_service.get_authorization_url()
    return RedirectResponse(url=auth_url)


@router.get("/google/callback")
async def google_callback(code: str = Query(...), db: Session = Depends(get_db)):
    """
    구글 인증 콜백
    인증 코드를 받아서 토큰을 발급하고 DB에 저장

    Args:
        code: 구글 인증 서버에서 받은 인증 코드
        db: 데이터베이스 세션
    """
    try:
        # 인증 코드로 Credentials 발급
        credentials = google_auth_service.get_credentials_from_code(code)

        access_token = credentials.token
        refresh_token = credentials.refresh_token
        token_expiry = credentials.expiry

        if not access_token or not refresh_token:
            raise HTTPException(status_code=400, detail="토큰 발급 실패")

        # 사용자 정보 조회 (선택사항)
        try:
            user_info = google_auth_service.get_user_info(credentials)
            print(f"✅ 구글 로그인 성공: {user_info.get('email')}")
        except Exception as e:
            print(f"⚠️  사용자 정보 조회 실패: {e}")

        # DB에 토큰 저장
        user = get_or_create_user(db)
        update_user_google_tokens(
            db, user.user_id, access_token, refresh_token, token_expiry
        )

        # 로그 기록
        create_log(db, "auth", "SUCCESS", f"구글 로그인 성공 (user_id: {user.user_id})")

        # Settings 페이지로 리다이렉트
        return RedirectResponse(url="/settings?google_login=success", status_code=303)

    except Exception as e:
        # 에러 로그 기록 (실패해도 계속 진행)
        try:
            create_log(db, "auth", "FAIL", f"구글 로그인 실패: {str(e)}")
        except:
            pass

        # 에러 발생 시에도 Settings 페이지로 리다이렉트
        error_message = quote(str(e))
        return RedirectResponse(url=f"/settings?google_login=error&message={error_message}", status_code=303)


@router.get("/google/status")
async def google_status(db: Session = Depends(get_db)):
    """
    구글 인증 상태 확인
    현재 사용자의 구글 토큰 보유 여부 확인
    """
    user = get_or_create_user(db)

    has_google_token = bool(user.google_access_token)

    return JSONResponse(
        content={
            "user_id": user.user_id,
            "google_authenticated": has_google_token,
            "google_token_exists": has_google_token,
            "google_token_expiry": (
                user.google_token_expiry.isoformat()
                if user.google_token_expiry
                else None
            ),
        }
    )


@router.post("/google/disconnect")
async def google_disconnect(db: Session = Depends(get_db)):
    """
    구글 캘린더 연동 해제
    DB에서 구글 토큰 제거
    """
    try:
        user = get_or_create_user(db)

        if not user.google_access_token:
            raise HTTPException(status_code=400, detail="연동된 구글 캘린더가 없습니다")

        # DB에서 구글 토큰 제거
        user.google_access_token = None
        user.google_refresh_token = None
        user.google_token_expiry = None
        db.commit()

        # 로그 기록
        create_log(
            db,
            "auth",
            "SUCCESS",
            f"구글 캘린더 연동 해제 (user_id: {user.user_id})",
        )

        return JSONResponse(
            content={
                "message": "구글 캘린더 연동 해제 성공",
                "user_id": user.user_id,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        create_log(db, "auth", "FAIL", f"구글 캘린더 연동 해제 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"연동 해제 실패: {str(e)}")


@router.post("/google/test-calendar")
async def google_test_calendar(db: Session = Depends(get_db)):
    """
    구글 캘린더 조회 테스트
    오늘 일정을 조회하여 반환
    """
    try:
        user = get_or_create_user(db)

        if not user.google_access_token or not user.google_refresh_token:
            raise HTTPException(status_code=400, detail="구글 로그인이 필요합니다")

        # Credentials 생성
        credentials = google_auth_service.create_credentials(
            user.google_access_token,
            user.google_refresh_token,
            user.google_token_expiry,
        )

        # 토큰 만료 확인 및 갱신
        if credentials.expired and credentials.refresh_token:
            try:
                credentials = google_auth_service.refresh_credentials(credentials)

                # 갱신된 토큰 저장
                update_user_google_tokens(
                    db,
                    user.user_id,
                    credentials.token,
                    credentials.refresh_token,
                    credentials.expiry,
                )
            except Exception as e:
                raise HTTPException(status_code=401, detail=f"토큰 갱신 실패: {str(e)}")

        # 오늘 일정 조회
        events = google_auth_service.get_calendar_events(credentials)

        # 로그 기록
        create_log(
            db,
            "calendar",
            "SUCCESS",
            f"캘린더 일정 조회 성공 (user_id: {user.user_id}, count: {len(events)})",
        )

        # 일정 포맷팅
        formatted_events = []
        for event in events:
            start = event.get("start", {})
            end = event.get("end", {})
            formatted_events.append(
                {
                    "summary": event.get("summary", "제목 없음"),
                    "start": start.get("dateTime") or start.get("date"),
                    "end": end.get("dateTime") or end.get("date"),
                    "description": event.get("description", ""),
                }
            )

        return JSONResponse(
            content={
                "message": f"오늘 일정 {len(events)}개 조회 완료",
                "count": len(events),
                "events": formatted_events,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        create_log(db, "calendar", "FAIL", f"캘린더 일정 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"일정 조회 실패: {str(e)}")


# ============================================================
# 텔레그램 연동
# ============================================================


@router.get("/telegram/start")
async def telegram_start():
    """
    텔레그램 연동 시작
    봇 정보 및 연동 방법 안내 반환

    Returns:
        봇 링크 및 연동 방법
    """
    try:
        # 봇 토큰에서 봇 username 추출 (간단히 구현)
        bot_token = settings.TELEGRAM_BOT_TOKEN
        print(f"🔍 TELEGRAM_BOT_TOKEN 확인: {bot_token[:20]}..." if bot_token and len(bot_token) > 20 else f"🔍 TELEGRAM_BOT_TOKEN: {bot_token}")

        if not bot_token or bot_token == "your_telegram_bot_token":
            raise HTTPException(
                status_code=500,
                detail="텔레그램 봇 토큰이 설정되지 않았습니다. TELEGRAM_BOT_TOKEN 환경변수를 설정해주세요.",
            )

        # 봇 정보 조회
        from app.services.notification import telegram_sender

        print("📞 텔레그램 봇 정보 조회 시작...")
        bot_info = await telegram_sender.get_bot_info()
        print(f"📞 텔레그램 봇 정보 조회 결과: {bot_info}")

        if not bot_info or not bot_info.get("ok"):
            raise HTTPException(status_code=500, detail="텔레그램 봇 정보 조회 실패")

        bot_data = bot_info.get("result", {})
        bot_username = bot_data.get("username", "")

        if not bot_username:
            raise HTTPException(status_code=500, detail="봇 username을 찾을 수 없습니다")

        bot_link = f"https://t.me/{bot_username}"

        return JSONResponse(
            content={
                "bot_username": bot_username,
                "bot_link": bot_link,
                "instructions": [
                    "1. 아래 링크를 클릭하여 텔레그램 봇을 엽니다",
                    "2. /start 명령을 전송합니다",
                    "3. 봇이 응답한 Chat ID를 복사합니다",
                    "4. 아래 입력란에 Chat ID를 입력하고 '연동하기'를 클릭합니다",
                ],
                "message": "텔레그램 연동을 시작합니다",
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ 텔레그램 연동 시작 에러: {type(e).__name__} - {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"봇 정보 조회 실패: {str(e)}")


@router.post("/telegram/verify")
async def telegram_verify(
    request: TelegramVerifyRequest, db: Session = Depends(get_db)
):
    """
    텔레그램 연동 확인
    사용자가 입력한 chat_id를 검증하고 DB에 저장

    Args:
        request: chat_id를 포함한 요청 body
        db: 데이터베이스 세션
    """
    try:
        # chat_id 검증
        chat_id = request.chat_id.strip() if request.chat_id else ""

        if not chat_id:
            raise HTTPException(status_code=400, detail="Chat ID를 입력해주세요")

        # 사용자 조회
        user = get_or_create_user(db)

        # DB에 chat_id 저장
        update_user_telegram_chat_id(db, user.user_id, chat_id)

        # 로그 기록
        create_log(
            db,
            "auth",
            "SUCCESS",
            f"텔레그램 연동 성공 (user_id: {user.user_id}, chat_id: {chat_id})",
        )

        return JSONResponse(
            content={
                "message": "텔레그램 연동 성공",
                "user_id": user.user_id,
                "chat_id": chat_id,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        create_log(db, "auth", "FAIL", f"텔레그램 연동 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"연동 실패: {str(e)}")


@router.post("/telegram/disconnect")
async def telegram_disconnect(db: Session = Depends(get_db)):
    """
    텔레그램 연동 해제
    DB에서 chat_id 제거
    """
    try:
        user = get_or_create_user(db)

        if not user.telegram_chat_id:
            raise HTTPException(status_code=400, detail="연동된 텔레그램이 없습니다")

        # DB에서 chat_id 제거
        disconnect_user_telegram(db, user.user_id)

        # 로그 기록
        create_log(
            db,
            "auth",
            "SUCCESS",
            f"텔레그램 연동 해제 (user_id: {user.user_id})",
        )

        return JSONResponse(
            content={
                "message": "텔레그램 연동 해제 성공",
                "user_id": user.user_id,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        create_log(db, "auth", "FAIL", f"텔레그램 연동 해제 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"연동 해제 실패: {str(e)}")


@router.get("/telegram/status")
async def telegram_status(db: Session = Depends(get_db)):
    """
    텔레그램 연동 상태 확인
    현재 사용자의 텔레그램 chat_id 보유 여부 확인
    """
    user = get_or_create_user(db)

    has_telegram = bool(user.telegram_chat_id)

    return JSONResponse(
        content={
            "user_id": user.user_id,
            "telegram_connected": has_telegram,
            "chat_id": user.telegram_chat_id if has_telegram else None,
        }
    )


@router.post("/telegram/test")
async def telegram_test_message(db: Session = Depends(get_db)):
    """
    텔레그램 메시지 발송 테스트
    현재 연동된 사용자에게 테스트 메시지 발송
    """
    try:
        user = get_or_create_user(db)

        if not user.telegram_chat_id:
            raise HTTPException(
                status_code=400, detail="텔레그램 연동이 필요합니다"
            )

        # 테스트 메시지 발송
        message = "🎉 My Assistant 텔레그램 연동 테스트 메시지입니다!\n텔레그램 연동이 정상적으로 완료되었습니다."

        result = await notification_service.send_to_telegram(user, message)

        if not result:
            raise HTTPException(status_code=500, detail="메시지 발송 실패")

        # 로그 기록
        create_log(
            db, "memo", "SUCCESS", f"텔레그램 테스트 메시지 발송 성공 (user_id: {user.user_id})"
        )

        return JSONResponse(
            content={
                "message": "테스트 메시지 발송 성공",
                "chat_id": user.telegram_chat_id,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        create_log(db, "memo", "FAIL", f"텔레그램 테스트 메시지 발송 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"메시지 발송 실패: {str(e)}")


# ============================================================
# 관리자 세션 로그인
# ============================================================


@router.post("/login")
async def admin_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    """
    관리자 로그인
    세션 기반 인증으로 관리자 로그인 처리

    Args:
        request: FastAPI Request 객체
        username: 관리자 아이디
        password: 관리자 비밀번호
        db: 데이터베이스 세션

    Returns:
        RedirectResponse: 로그인 성공 시 메인 페이지로, 실패 시 로그인 페이지로 리다이렉트
    """
    # 인증 확인
    if verify_admin_credentials(username, password):
        # 세션 생성
        create_session(request)

        # 로그 기록
        try:
            create_log(db, "auth", "SUCCESS", f"관리자 로그인 성공 (username: {username})")
        except Exception as e:
            print(f"⚠️  로그 기록 실패: {e}")

        # 메인 페이지로 리다이렉트
        return RedirectResponse(url="/", status_code=303)
    else:
        # 로그 기록
        try:
            create_log(db, "auth", "FAIL", f"관리자 로그인 실패 (username: {username})")
        except Exception as e:
            print(f"⚠️  로그 기록 실패: {e}")

        # 로그인 페이지로 리다이렉트 (에러 파라미터 포함)
        return RedirectResponse(url="/login?error=1", status_code=303)


@router.post("/logout")
async def admin_logout(request: Request, db: Session = Depends(get_db)):
    """
    관리자 로그아웃
    세션을 제거하고 로그인 페이지로 리다이렉트

    Args:
        request: FastAPI Request 객체
        db: 데이터베이스 세션

    Returns:
        RedirectResponse: 로그인 페이지로 리다이렉트
    """
    # 로그 기록 (세션 제거 전)
    username = request.session.get("username", "unknown")
    try:
        create_log(db, "auth", "SUCCESS", f"관리자 로그아웃 (username: {username})")
    except Exception as e:
        print(f"⚠️  로그 기록 실패: {e}")

    # 세션 제거
    destroy_session(request)

    # 로그인 페이지로 리다이렉트
    return RedirectResponse(url="/login", status_code=303)


@router.get("/session/status")
async def session_status(request: Request):
    """
    세션 상태 확인
    현재 세션의 인증 상태를 반환

    Args:
        request: FastAPI Request 객체

    Returns:
        JSONResponse: 인증 상태 정보
    """
    authenticated = is_authenticated(request)
    username = request.session.get("username") if authenticated else None

    return JSONResponse(
        content={
            "authenticated": authenticated,
            "username": username,
        }
    )
