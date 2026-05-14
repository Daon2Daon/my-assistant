"""
구글 OAuth 인증 서비스
구글 로그인 및 Calendar API 연동
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo
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

    def _web_client_config(self) -> dict:
        return {
            "web": {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [self.redirect_uri],
            }
        }

    def create_flow(self) -> Flow:
        """
        OAuth Flow 생성 (토큰 갱신·API 호출용, PKCE 없음)
        """
        return Flow.from_client_config(
            client_config=self._web_client_config(),
            scopes=self.scopes,
            redirect_uri=self.redirect_uri,
        )

    def get_authorization_url(self) -> Tuple[str, str, Optional[str]]:
        """
        구글 로그인 인증 URL 생성

        PKCE(code_verifier)는 authorization 단계와 token 단계에서 동일한 값이어야 합니다.
        반환된 code_verifier는 서버 세션에 저장한 뒤 콜백의 get_credentials_from_code에 넘겨야 합니다.

        Returns:
            (auth_url, state, code_verifier)
        """
        flow = Flow.from_client_config(
            client_config=self._web_client_config(),
            scopes=self.scopes,
            redirect_uri=self.redirect_uri,
            autogenerate_code_verifier=True,
        )

        # offline access를 통해 refresh token 획득
        auth_url, state = flow.authorization_url(
            access_type="offline",
            prompt="consent",  # 매번 동의 화면 표시 (refresh token 확보)
            include_granted_scopes="true",
        )

        return auth_url, state, flow.code_verifier

    def get_credentials_from_code(
        self, code: str, code_verifier: Optional[str] = None
    ) -> Credentials:
        """
        인증 코드로 Credentials 발급

        Args:
            code: 구글 인증 서버에서 받은 인증 코드
            code_verifier: 로그인 단계(get_authorization_url)에서 발급·세션에 보관한 PKCE 검증값

        Returns:
            Credentials: 구글 인증 정보 객체

        Raises:
            Exception: 인증 실패 시
        """
        flow = Flow.from_client_config(
            client_config=self._web_client_config(),
            scopes=self.scopes,
            redirect_uri=self.redirect_uri,
            code_verifier=code_verifier,
            autogenerate_code_verifier=False,
        )

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

    def _kst_today_utc_bounds(self) -> Tuple[datetime, datetime]:
        """
        KST 기준 '오늘' 달력일의 [00:00, 다음날 00:00) 구간을 UTC aware datetime으로 반환.
        Google Calendar events.list의 timeMax는 exclusive이므로 상한은 다음날 00:00 KST.
        """
        kst = ZoneInfo("Asia/Seoul")
        now_kst = datetime.now(kst)
        start_kst = now_kst.replace(hour=0, minute=0, second=0, microsecond=0)
        end_kst_exclusive = start_kst + timedelta(days=1)
        return (
            start_kst.astimezone(timezone.utc),
            end_kst_exclusive.astimezone(timezone.utc),
        )

    @staticmethod
    def _to_rfc3339_z(dt: datetime) -> str:
        """timezone-aware datetime을 Calendar API용 RFC3339 UTC(Z) 문자열로 변환."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

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
            time_min: 조회 시작 시간 (기본: KST 달력 오늘 00:00에 해당하는 UTC 시각)
            time_max: 조회 종료 상한 (기본: KST 다음날 00:00, API 규격상 exclusive)
            max_results: 최대 조회 개수

        Returns:
            List[Dict]: 일정 리스트

        Raises:
            Exception: 일정 조회 실패 시
        """
        try:
            # Calendar API 서비스 생성
            service = build("calendar", "v3", credentials=credentials)

            # 시간 범위: 기본은 KST 달력 '오늘'
            if not time_min or not time_max:
                utc_min, utc_max = self._kst_today_utc_bounds()
                if not time_min:
                    time_min = utc_min
                if not time_max:
                    time_max = utc_max

            if time_min.tzinfo is None:
                time_min_str = time_min.isoformat() + "Z"
            else:
                time_min_str = self._to_rfc3339_z(time_min)
            if time_max.tzinfo is None:
                time_max_str = time_max.isoformat() + "Z"
            else:
                time_max_str = self._to_rfc3339_z(time_max)

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

    def get_calendar_list(self, credentials: Credentials) -> List[Dict]:
        """
        사용자의 캘린더 목록 조회

        Args:
            credentials: 구글 인증 정보

        Returns:
            List[Dict]: 캘린더 목록
                - id: 캘린더 ID
                - summary: 캘린더 이름
                - description: 캘린더 설명
                - backgroundColor: 배경 색상
                - foregroundColor: 전경 색상
                - primary: Primary 캘린더 여부
                - accessRole: 접근 권한 (owner, writer, reader 등)

        Raises:
            Exception: 캘린더 목록 조회 실패 시
        """
        try:
            # Calendar API 서비스 생성
            service = build("calendar", "v3", credentials=credentials)

            # 캘린더 목록 조회
            calendar_list_result = service.calendarList().list().execute()

            calendars = calendar_list_result.get("items", [])

            # 필요한 정보만 추출
            result = []
            for calendar in calendars:
                result.append({
                    "id": calendar.get("id"),
                    "summary": calendar.get("summary"),
                    "description": calendar.get("description", ""),
                    "backgroundColor": calendar.get("backgroundColor", "#9E69AF"),
                    "foregroundColor": calendar.get("foregroundColor", "#FFFFFF"),
                    "primary": calendar.get("primary", False),
                    "accessRole": calendar.get("accessRole", "reader"),
                })

            return result

        except Exception as e:
            raise Exception(f"캘린더 목록 조회 실패: {str(e)}")

    def get_multiple_calendars_events(
        self,
        credentials: Credentials,
        calendar_ids: List[str],
        time_min: Optional[datetime] = None,
        time_max: Optional[datetime] = None,
        max_results: int = 10,
    ) -> Dict[str, List[Dict]]:
        """
        여러 캘린더의 일정 조회

        Args:
            credentials: 구글 인증 정보
            calendar_ids: 조회할 캘린더 ID 리스트
            time_min: 조회 시작 시간 (기본: KST 달력 오늘 00:00에 해당하는 UTC 시각)
            time_max: 조회 종료 상한 (기본: KST 다음날 00:00, API 규격상 exclusive)
            max_results: 캘린더당 최대 조회 개수

        Returns:
            Dict[str, List[Dict]]: 캘린더 ID별 일정 리스트
                {
                    "calendar_id": [일정1, 일정2, ...],
                    ...
                }

        Raises:
            Exception: 일정 조회 실패 시
        """
        try:
            # Calendar API 서비스 생성
            service = build("calendar", "v3", credentials=credentials)

            # 시간 범위: 기본은 KST 달력 '오늘'
            if not time_min or not time_max:
                utc_min, utc_max = self._kst_today_utc_bounds()
                if not time_min:
                    time_min = utc_min
                if not time_max:
                    time_max = utc_max

            if time_min.tzinfo is None:
                time_min_str = time_min.isoformat() + "Z"
            else:
                time_min_str = self._to_rfc3339_z(time_min)
            if time_max.tzinfo is None:
                time_max_str = time_max.isoformat() + "Z"
            else:
                time_max_str = self._to_rfc3339_z(time_max)

            # 각 캘린더별로 일정 조회
            results = {}
            for calendar_id in calendar_ids:
                try:
                    events_result = (
                        service.events()
                        .list(
                            calendarId=calendar_id,
                            timeMin=time_min_str,
                            timeMax=time_max_str,
                            maxResults=max_results,
                            singleEvents=True,
                            orderBy="startTime",
                        )
                        .execute()
                    )
                    results[calendar_id] = events_result.get("items", [])
                except Exception as e:
                    # 개별 캘린더 조회 실패 시 빈 리스트 (다른 캘린더는 계속 조회)
                    print(f"캘린더 {calendar_id} 조회 실패: {e}")
                    results[calendar_id] = []

            return results

        except Exception as e:
            raise Exception(f"다중 캘린더 일정 조회 실패: {str(e)}")


# 싱글톤 인스턴스
google_auth_service = GoogleAuthService()
