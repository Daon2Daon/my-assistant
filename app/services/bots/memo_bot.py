"""
예약 메모 봇
지정된 시간에 메모를 카카오톡으로 발송
"""

from datetime import datetime
from typing import Optional
from app.database import SessionLocal
from app.crud import (
    get_or_create_user,
    create_log,
    get_reminder,
    update_reminder_sent_status,
    get_reminders,
)
from app.services.auth.kakao_auth import kakao_auth_service
from app.services.scheduler import scheduler_service


class MemoBot:
    """예약 메모 봇"""

    def __init__(self):
        pass

    def format_memo_message(self, content: str) -> str:
        """
        메모 내용을 메시지 형식으로 포맷팅

        Args:
            content: 메모 내용

        Returns:
            str: 포맷팅된 메시지
        """
        now = datetime.now()
        message = f"""[예약 메모 알림]

{now.strftime('%Y년 %m월 %d일 %H:%M')}

{content}"""
        return message

    async def send_memo_notification(self, reminder_id: int):
        """
        예약 메모 알림 발송

        Args:
            reminder_id: 발송할 메모 ID
        """
        db = SessionLocal()

        try:
            # 메모 조회
            reminder = get_reminder(db, reminder_id)

            if not reminder:
                print(f"메모를 찾을 수 없습니다: {reminder_id}")
                return

            # 이미 발송된 메모인 경우
            if reminder.is_sent:
                print(f"이미 발송된 메모입니다: {reminder_id}")
                return

            # 사용자 조회
            user = get_or_create_user(db)

            if not user.kakao_access_token:
                create_log(db, "memo", "FAIL", f"카카오 토큰이 없습니다 (reminder_id: {reminder_id})")
                print("카카오 로그인이 필요합니다")
                return

            # 메시지 포맷팅
            message = self.format_memo_message(reminder.message_content)

            # 카카오톡 메시지 발송
            try:
                await kakao_auth_service.send_message_to_me(
                    user.kakao_access_token, message
                )

                # 발송 상태 업데이트
                update_reminder_sent_status(db, reminder_id, is_sent=True)

                # 성공 로그
                create_log(
                    db,
                    "memo",
                    "SUCCESS",
                    f"메모 알림 발송 성공 (reminder_id: {reminder_id}, user_id: {user.user_id})",
                )
                print(f"메모 알림 발송 완료 - reminder_id: {reminder_id}")

            except Exception as e:
                create_log(db, "memo", "FAIL", f"메시지 발송 실패: {str(e)} (reminder_id: {reminder_id})")
                print(f"메시지 발송 실패: {e}")

        except Exception as e:
            create_log(db, "memo", "FAIL", f"메모 알림 오류: {str(e)}")
            print(f"메모 알림 오류: {e}")

        finally:
            db.close()

    def schedule_reminder(self, reminder_id: int, target_datetime: datetime):
        """
        메모를 스케줄러에 등록

        Args:
            reminder_id: 메모 ID
            target_datetime: 발송 예정 시간
        """
        job_id = f"reminder_{reminder_id}"

        scheduler_service.add_date_job(
            func=send_memo_notification_sync,
            job_id=job_id,
            run_date=target_datetime,
            args=(reminder_id,),
        )

        print(f"메모 Job 등록 완료: {job_id} - {target_datetime}")

    def cancel_reminder(self, reminder_id: int) -> bool:
        """
        메모 스케줄 취소

        Args:
            reminder_id: 취소할 메모 ID

        Returns:
            bool: 취소 성공 여부
        """
        job_id = f"reminder_{reminder_id}"
        return scheduler_service.remove_job(job_id)

    def restore_pending_reminders(self):
        """
        서버 재시작 시 미발송 메모 Job 복원
        """
        db = SessionLocal()

        try:
            # 사용자 조회
            user = get_or_create_user(db)

            # 미발송 메모 조회
            pending_reminders = get_reminders(db, user.user_id, is_sent=False)

            restored_count = 0
            skipped_count = 0

            for reminder in pending_reminders:
                # 이미 지난 시간의 메모는 건너뜀
                if reminder.target_datetime <= datetime.now():
                    skipped_count += 1
                    continue

                # 이미 등록된 Job이 있는지 확인
                job_id = f"reminder_{reminder.reminder_id}"
                existing_job = scheduler_service.get_job(job_id)

                if not existing_job:
                    self.schedule_reminder(
                        reminder.reminder_id, reminder.target_datetime
                    )
                    restored_count += 1

            if restored_count > 0 or skipped_count > 0:
                print(f"메모 Job 복원: {restored_count}개 등록, {skipped_count}개 건너뜀 (시간 만료)")

            return restored_count

        except Exception as e:
            print(f"메모 Job 복원 실패: {e}")
            return 0

        finally:
            db.close()


# 싱글톤 인스턴스
memo_bot = MemoBot()


# 스케줄러에서 호출할 함수
def send_memo_notification_sync(reminder_id: int):
    """
    동기 방식으로 메모 알림 발송
    스케줄러에서 비동기 함수를 호출하기 위한 래퍼
    """
    import asyncio

    try:
        asyncio.run(memo_bot.send_memo_notification(reminder_id))
    except Exception as e:
        print(f"메모 알림 실행 오류: {e}")
