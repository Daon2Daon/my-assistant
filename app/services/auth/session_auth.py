"""
세션 기반 인증 서비스
관리자 로그인 및 세션 관리를 담당합니다.
"""

from fastapi import Request, HTTPException
from app.config import settings


def verify_admin_credentials(username: str, password: str) -> bool:
    """
    관리자 인증 정보 확인

    Args:
        username: 입력된 아이디
        password: 입력된 비밀번호

    Returns:
        bool: 인증 성공 여부
    """
    return (
        username == settings.ADMIN_USERNAME and
        password == settings.ADMIN_PASSWORD
    )


def create_session(request: Request) -> None:
    """
    세션 생성 및 인증 정보 저장

    Args:
        request: FastAPI Request 객체
    """
    request.session["authenticated"] = True
    request.session["username"] = settings.ADMIN_USERNAME


def destroy_session(request: Request) -> None:
    """
    세션 제거

    Args:
        request: FastAPI Request 객체
    """
    request.session.clear()


def is_authenticated(request: Request) -> bool:
    """
    인증 상태 확인

    Args:
        request: FastAPI Request 객체

    Returns:
        bool: 인증 여부
    """
    return request.session.get("authenticated", False)


async def require_auth(request: Request) -> None:
    """
    인증 필요 의존성
    라우터에서 Depends로 사용하여 인증 강제

    Args:
        request: FastAPI Request 객체

    Raises:
        HTTPException: 인증되지 않은 경우 401 에러
    """
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Not authenticated")
