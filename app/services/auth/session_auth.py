"""
세션 기반 인증 서비스
관리자 로그인 및 세션 관리를 담당합니다.
"""

import logging
from fastapi import Request, HTTPException
from app.config import settings

# 로거 설정
logger = logging.getLogger(__name__)


def verify_admin_credentials(username: str, password: str) -> bool:
    """
    관리자 인증 정보 확인

    Args:
        username: 입력된 아이디
        password: 입력된 비밀번호

    Returns:
        bool: 인증 성공 여부
    """
    # 디버깅: 환경 변수 값 확인 (보안상 일부만 표시)
    logger.info(f"[AUTH DEBUG] 입력된 username: {username}")
    logger.info(f"[AUTH DEBUG] 설정된 ADMIN_USERNAME: {settings.ADMIN_USERNAME}")
    logger.info(f"[AUTH DEBUG] 입력된 password 길이: {len(password)}")
    logger.info(f"[AUTH DEBUG] 설정된 ADMIN_PASSWORD 길이: {len(settings.ADMIN_PASSWORD)}")
    logger.info(f"[AUTH DEBUG] 입력된 password 첫 3자: {password[:3] if len(password) >= 3 else password}")
    logger.info(f"[AUTH DEBUG] 설정된 ADMIN_PASSWORD 첫 3자: {settings.ADMIN_PASSWORD[:3] if len(settings.ADMIN_PASSWORD) >= 3 else settings.ADMIN_PASSWORD}")
    logger.info(f"[AUTH DEBUG] username 일치: {username == settings.ADMIN_USERNAME}")
    logger.info(f"[AUTH DEBUG] password 일치: {password == settings.ADMIN_PASSWORD}")
    
    # 따옴표가 포함되어 있는지 확인
    if settings.ADMIN_PASSWORD.startswith(("'", '"')) or settings.ADMIN_PASSWORD.endswith(("'", '"')):
        logger.warning(f"[AUTH WARNING] ADMIN_PASSWORD에 따옴표가 포함되어 있습니다!")
    
    # 특수문자 확인
    special_chars = ['@', '#', '$', '%', '&', '*', '!', '(', ')', '[', ']', '{', '}']
    password_special = [c for c in password if c in special_chars]
    env_password_special = [c for c in settings.ADMIN_PASSWORD if c in special_chars]
    logger.info(f"[AUTH DEBUG] 입력된 password의 특수문자: {password_special}")
    logger.info(f"[AUTH DEBUG] 설정된 ADMIN_PASSWORD의 특수문자: {env_password_special}")
    
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
