"""
캘린더 브리핑 봇
Google Calendar API를 사용한 일정 조회 및 알림
"""

from datetime import datetime
from typing import Dict, List, Optional
from app.database import SessionLocal
from app.crud import get_or_create_user, create_log, is_setting_active
from app.services.auth.google_auth import google_auth_service
from app.services.notification import notification_service


class CalendarBot:
    """캘린더 브리핑 봇"""

    def __init__(self):
        pass

    def get_today_events(self, credentials) -> Optional[List[Dict]]:
        """
        오늘의 일정 조회

        Args:
            credentials: 구글 인증 정보

        Returns:
            List[Dict]: 일정 리스트 또는 None
        """
        try:
            events = google_auth_service.get_calendar_events(credentials)
            return events
        except Exception as e:
            print(f"일정 조회 실패: {e}")
            return None

    def format_calendar_message(self, events: List[Dict]) -> str:
        """
        일정 데이터를 메시지 형식으로 포맷팅

        Args:
            events: 구글 캘린더 일정 리스트

        Returns:
            str: 포맷팅된 메시지
        """
        try:
            today = datetime.now()
            weekday_names = ["월", "화", "수", "목", "금", "토", "일"]
            weekday = weekday_names[today.weekday()]

            message = f"""[오늘의 일정] {today.strftime('%Y년 %m월 %d일')} ({weekday})

"""

            if not events:
                message += "오늘 예정된 일정이 없습니다."
                return message

            # 종일 일정과 시간 지정 일정 분리
            all_day_events = []
            timed_events = []

            for event in events:
                start = event.get("start", {})
                summary = event.get("summary", "제목 없음")

                # 종일 일정 (date 필드 사용)
                if "date" in start:
                    all_day_events.append(summary)
                # 시간 지정 일정 (dateTime 필드 사용)
                elif "dateTime" in start:
                    start_time = datetime.fromisoformat(
                        start["dateTime"].replace("Z", "+00:00")
                    )
                    end = event.get("end", {})
                    end_time = None
                    if "dateTime" in end:
                        end_time = datetime.fromisoformat(
                            end["dateTime"].replace("Z", "+00:00")
                        )

                    time_str = start_time.strftime("%H:%M")
                    if end_time:
                        time_str += f"~{end_time.strftime('%H:%M')}"

                    timed_events.append({"time": time_str, "summary": summary})

            # 종일 일정 출력
            if all_day_events:
                message += "[ 종일 일정 ]\n"
                for event_name in all_day_events:
                    message += f"- {event_name}\n"
                message += "\n"

            # 시간 지정 일정 출력
            if timed_events:
                message += "[ 시간 일정 ]\n"
                for event in timed_events:
                    message += f"- {event['time']} {event['summary']}\n"

            return message.strip()

        except Exception as e:
            print(f"메시지 포맷팅 실패: {e}")
            return "일정 정보를 가져올 수 없습니다."

    async def send_calendar_notification(self):
        """
        캘린더 브리핑 알림 발송
        DB에서 사용자 정보를 조회하고 카카오톡 메시지 발송
        """
        db = SessionLocal()

        try:
            # 사용자 조회
            user = get_or_create_user(db)

            # Settings에서 캘린더 알림 활성화 여부 확인
            if not is_setting_active(db, user.user_id, "calendar"):
                print("캘린더 알림이 비활성화되어 있습니다")
                create_log(db, "calendar", "SKIP", "캘린더 알림 비활성화 상태")
                return

            # 구글 토큰 확인
            if not user.google_access_token or not user.google_refresh_token:
                create_log(db, "calendar", "FAIL", "구글 토큰이 없습니다")
                print("구글 로그인이 필요합니다")
                return

            # 카카오 토큰 확인
            if not user.kakao_access_token:
                create_log(db, "calendar", "FAIL", "카카오 토큰이 없습니다")
                print("카카오 로그인이 필요합니다")
                return

            # 구글 Credentials 생성
            try:
                credentials = google_auth_service.create_credentials(
                    access_token=user.google_access_token,
                    refresh_token=user.google_refresh_token,
                    token_expiry=user.google_token_expiry,
                )

                # 토큰 만료 시 갱신
                if credentials.expired and credentials.refresh_token:
                    credentials = google_auth_service.refresh_credentials(credentials)
                    # 갱신된 토큰 DB 저장
                    from app.crud import update_user_google_tokens

                    update_user_google_tokens(
                        db,
                        user.user_id,
                        credentials.token,
                        credentials.refresh_token,
                        credentials.expiry,
                    )

            except Exception as e:
                create_log(db, "calendar", "FAIL", f"구글 인증 실패: {str(e)}")
                print(f"구글 인증 실패: {e}")
                return

            # 일정 조회
            events = self.get_today_events(credentials)

            if events is None:
                create_log(db, "calendar", "FAIL", "일정 조회 실패")
                return

            # 메시지 포맷팅
            message = self.format_calendar_message(events)

            # 연동된 채널 확인
            available_channels = notification_service.get_available_channels(user)
            if not available_channels:
                create_log(db, "calendar", "FAIL", "연동된 알림 채널이 없습니다")
                print("⚠️  알림 채널 연동이 필요합니다 (카카오톡 또는 텔레그램)")
                return

            # 알림 발송 (연동된 모든 채널로 자동 발송)
            try:
                result = await notification_service.send(user, message)

                if result.success:
                    # 성공 로그
                    create_log(
                        db,
                        "calendar",
                        "SUCCESS",
                        f"캘린더 알림 발송 성공 - {len(events)}개 일정 ({result.message})",
                    )
                    print(f"✅ 캘린더 알림 발송 완료 - {len(events)}개 일정")
                else:
                    # 실패 로그
                    create_log(db, "calendar", "FAIL", f"알림 발송 실패: {result.message}")
                    print(f"❌ 알림 발송 실패: {result.message}")

            except Exception as e:
                create_log(db, "calendar", "FAIL", f"알림 발송 오류: {str(e)}")
                print(f"❌ 알림 발송 오류: {e}")

        except Exception as e:
            create_log(db, "calendar", "FAIL", f"캘린더 알림 오류: {str(e)}")
            print(f"캘린더 알림 오류: {e}")

        finally:
            db.close()


# 싱글톤 인스턴스
calendar_bot = CalendarBot()


# 스케줄러에서 호출할 함수
def send_calendar_notification_sync():
    """
    동기 방식으로 캘린더 알림 발송
    스케줄러에서 비동기 함수를 호출하기 위한 래퍼
    """
    import asyncio

    try:
        asyncio.run(calendar_bot.send_calendar_notification())
    except Exception as e:
        print(f"캘린더 알림 실행 오류: {e}")
