"""
카카오 OAuth 인증 서비스
카카오 로그인 및 "나에게 보내기" API 구현
"""

import httpx
from typing import Dict, Optional
from app.config import settings


class KakaoAuthService:
    """카카오 인증 및 메시지 발송 서비스"""

    def __init__(self):
        self.rest_api_key = settings.KAKAO_REST_API_KEY
        self.redirect_uri = settings.KAKAO_REDIRECT_URI
        self.auth_url = settings.KAKAO_AUTH_URL
        self.token_url = settings.KAKAO_TOKEN_URL
        self.api_url = settings.KAKAO_API_URL

    def get_authorization_url(self) -> str:
        """
        카카오 로그인 인증 URL 생성
        사용자를 카카오 로그인 페이지로 리다이렉트하기 위한 URL
        """
        params = {
            "client_id": self.rest_api_key,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
        }
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{self.auth_url}?{query_string}"

    async def get_token_from_code(self, code: str) -> Dict:
        """
        인증 코드로 액세스 토큰 발급

        Args:
            code: 카카오 인증 서버에서 받은 인증 코드

        Returns:
            Dict: 토큰 정보 (access_token, refresh_token, expires_in 등)

        Raises:
            Exception: 토큰 발급 실패 시
        """
        data = {
            "grant_type": "authorization_code",
            "client_id": self.rest_api_key,
            "redirect_uri": self.redirect_uri,
            "code": code,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code != 200:
                raise Exception(
                    f"카카오 토큰 발급 실패: {response.status_code} - {response.text}"
                )

            return response.json()

    async def refresh_access_token(self, refresh_token: str) -> Dict:
        """
        Refresh Token으로 Access Token 갱신

        Args:
            refresh_token: 리프레시 토큰

        Returns:
            Dict: 새로운 토큰 정보

        Raises:
            Exception: 토큰 갱신 실패 시
        """
        data = {
            "grant_type": "refresh_token",
            "client_id": self.rest_api_key,
            "refresh_token": refresh_token,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code != 200:
                raise Exception(
                    f"카카오 토큰 갱신 실패: {response.status_code} - {response.text}"
                )

            return response.json()

    async def send_message_to_me(
        self, access_token: str, message: str, link: Optional[Dict] = None
    ) -> Dict:
        """
        카카오톡 "나에게 보내기" API

        Args:
            access_token: 카카오 액세스 토큰
            message: 보낼 메시지 내용
            link: 선택적 링크 정보 (웹 URL, 모바일 URL 등)

        Returns:
            Dict: API 응답

        Raises:
            Exception: 메시지 발송 실패 시
        """
        url = f"{self.api_url}/v2/api/talk/memo/default/send"

        # 기본 템플릿 구성
        template = {
            "object_type": "text",
            "text": message,
            "link": link or {"web_url": "https://developers.kakao.com"},
        }

        data = {"template_object": str(template)}

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, data=data, headers=headers)

            if response.status_code != 200:
                raise Exception(
                    f"카카오 메시지 발송 실패: {response.status_code} - {response.text}"
                )

            return response.json()

    async def get_user_info(self, access_token: str) -> Dict:
        """
        카카오 사용자 정보 조회

        Args:
            access_token: 카카오 액세스 토큰

        Returns:
            Dict: 사용자 정보

        Raises:
            Exception: 사용자 정보 조회 실패 시
        """
        url = f"{self.api_url}/v2/user/me"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)

            if response.status_code != 200:
                raise Exception(
                    f"카카오 사용자 정보 조회 실패: {response.status_code} - {response.text}"
                )

            return response.json()


# 싱글톤 인스턴스
kakao_auth_service = KakaoAuthService()
