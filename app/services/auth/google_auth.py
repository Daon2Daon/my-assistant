"""
구글 OAuth 인증 서비스
구글 로그인 및 Calendar API 연동
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from app.config import settings


class GoogleAuthService:
    """구글 인증 및 캘린더 서비스"""

    def __init__(self):
        self.client_id = settings.GOOGLE_CLIENT_ID
        self.client_secret = settings.GOOGLE_CLIENT_SECRET
        self.redirect_uri = settings.GOOGLE_REDIRECT_URI

        # OAuth 스코프 (Calendar 읽기 권한)
        self.scopes = [
            "https://www.googleapis.com/auth/calendar.readonly",
            "openid",
            "https://www.googleapis.com/auth/userinfo.email",
        ]

    def create_flow(self) -> Flow:
        """
        OAuth Flow 생성
        """
        client_config = {
            "web": {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [self.redirect_uri],
            }
        }

        flow = Flow.from_client_config(
            client_config=client_config,
            scopes=self.scopes,
            redirect_uri=self.redirect_uri,
        )

        return flow

    def get_authorization_url(self) -> str:
        """
        구글 로그인 인증 URL 생성

        Returns:
            str: 인증 URL
        """
        flow = self.create_flow()

        # offline access를 통해 refresh token 획득
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            prompt="consent",  # 매번 동의 화면 표시 (refresh token 확보)
            include_granted_scopes="true",
        )

        return auth_url

    def get_credentials_from_code(self, code: str) -> Credentials:
        """
        인증 코드로 Credentials 발급

        Args:
            code: 구글 인증 서버에서 받은 인증 코드

        Returns:
            Credentials: 구글 인증 정보 객체

        Raises:
            Exception: 인증 실패 시
        """
        flow = self.create_flow()

        try:
            flow.fetch_token(code=code)
            credentials = flow.credentials
            return credentials
        except Exception as e:
            raise Exception(f"구글 토큰 발급 실패: {str(e)}")

    def create_credentials(
        self,
        access_token: str,
        refresh_token: str,
        token_expiry: Optional[datetime] = None,
    ) -> Credentials:
        """
        저장된 토큰으로 Credentials 객체 생성

        Args:
            access_token: 액세스 토큰
            refresh_token: 리프레시 토큰
            token_expiry: 토큰 만료 시간

        Returns:
            Credentials: 구글 인증 정보 객체
        """
        credentials = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=self.scopes,
            expiry=token_expiry,
        )

        return credentials

    def refresh_credentials(self, credentials: Credentials) -> Credentials:
        """
        Credentials 갱신

        Args:
            credentials: 만료된 Credentials 객체

        Returns:
            Credentials: 갱신된 Credentials 객체

        Raises:
            Exception: 갱신 실패 시
        """
        try:
            from google.auth.transport.requests import Request

            credentials.refresh(Request())
            return credentials
        except Exception as e:
            raise Exception(f"구글 토큰 갱신 실패: {str(e)}")

    def get_calendar_events(
        self,
        credentials: Credentials,
        time_min: Optional[datetime] = None,
        time_max: Optional[datetime] = None,
        max_results: int = 10,
    ) -> List[Dict]:
        """
        구글 캘린더 일정 조회

        Args:
            credentials: 구글 인증 정보
            time_min: 조회 시작 시간 (기본: 오늘 00:00)
            time_max: 조회 종료 시간 (기본: 오늘 23:59)
            max_results: 최대 조회 개수

        Returns:
            List[Dict]: 일정 리스트

        Raises:
            Exception: 일정 조회 실패 시
        """
        try:
            # Calendar API 서비스 생성
            service = build("calendar", "v3", credentials=credentials)

            # 시간 범위 설정 (기본: 오늘)
            if not time_min:
                time_min = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            if not time_max:
                time_max = datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)

            # ISO 8601 형식으로 변환
            time_min_str = time_min.isoformat() + "Z"
            time_max_str = time_max.isoformat() + "Z"

            # 일정 조회
            events_result = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=time_min_str,
                    timeMax=time_max_str,
                    maxResults=max_results,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )

            events = events_result.get("items", [])
            return events

        except Exception as e:
            raise Exception(f"캘린더 일정 조회 실패: {str(e)}")

    def get_user_info(self, credentials: Credentials) -> Dict:
        """
        구글 사용자 정보 조회

        Args:
            credentials: 구글 인증 정보

        Returns:
            Dict: 사용자 정보

        Raises:
            Exception: 사용자 정보 조회 실패 시
        """
        try:
            from googleapiclient.discovery import build

            service = build("oauth2", "v2", credentials=credentials)
            user_info = service.userinfo().get().execute()
            return user_info
        except Exception as e:
            raise Exception(f"구글 사용자 정보 조회 실패: {str(e)}")


# 싱글톤 인스턴스
google_auth_service = GoogleAuthService()
