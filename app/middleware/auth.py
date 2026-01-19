"""
인증 미들웨어
세션 기반 인증을 통해 보호된 경로에 대한 접근을 제어합니다.
"""

from fastapi import Request
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


# 인증이 필요 없는 경로
EXCLUDE_PATHS = [
    "/login",
    "/auth/login",
    "/static",
    "/favicon.ico",
    "/health",
]


class AuthMiddleware(BaseHTTPMiddleware):
    """
    인증 미들웨어
    모든 요청에 대해 세션을 확인하고 인증되지 않은 접근을 차단합니다.
    """

    async def dispatch(self, request: Request, call_next):
        """
        요청 처리 전 인증 확인

        Args:
            request: FastAPI Request 객체
            call_next: 다음 미들웨어 또는 라우터 핸들러

        Returns:
            Response: 인증 실패 시 리다이렉트 또는 에러, 성공 시 정상 응답
        """
        path = request.url.path

        # 제외 경로 체크 (인증 불필요)
        if any(path.startswith(p) for p in EXCLUDE_PATHS):
            return await call_next(request)

        # 세션에서 인증 상태 확인
        is_authenticated = request.session.get("authenticated", False)

        if not is_authenticated:
            # API 요청인 경우 JSON 에러 반환
            if path.startswith("/api/"):
                return JSONResponse(
                    {"detail": "Not authenticated"},
                    status_code=401
                )

            # 페이지 요청인 경우 로그인 페이지로 리다이렉트
            return RedirectResponse(url="/login", status_code=303)

        # 인증 성공 - 다음 핸들러로 진행
        return await call_next(request)
