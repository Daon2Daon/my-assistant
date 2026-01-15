"""
예약 메모 봇
지정된 시간에 메모를 카카오톡으로 발송
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Optional
from app.database import SessionLocal
from app.crud import (
    get_or_create_user,
    create_log,
    get_reminder,
    update_reminder_sent_status,
    get_reminders,
)
from app.services.notification import notification_service
from app.services.scheduler import scheduler_service


class MemoBot:
    """예약 메모 봇"""

    def __init__(self):
        pass

    def format_memo_message(self, content: str, target_datetime: datetime = None) -> str:
        """
        메모 내용을 메시지 형식으로 포맷팅

        Args:
            content: 메모 내용
            target_datetime: 예약된 시간 (옵션)

        Returns:
            str: 포맷팅된 메시지
        """
        # 한국 시간대로 변환
        kst = ZoneInfo("Asia/Seoul")

        if target_datetime:
            # target_datetime이 있으면 사용 (예약된 정확한 시간)
            if target_datetime.tzinfo is None:
                # timezone 정보가 없으면 UTC로 간주하고 KST로 변환 (DB에 UTC로 저장되어 있음)
                dt_kst = target_datetime.replace(tzinfo=timezone.utc).astimezone(kst)
            else:
                # timezone 정보가 있으면 KST로 변환
                dt_kst = target_datetime.astimezone(kst)
        else:
            # 없으면 현재 시간 사용
            dt_kst = datetime.now(timezone.utc).astimezone(kst)

        message = f"""[예약 메모 알림]

{dt_kst.strftime('%Y년 %m월 %d일 %H:%M')}

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

            # 연동된 채널 확인
            available_channels = notification_service.get_available_channels(user)
            if not available_channels:
                create_log(db, "memo", "FAIL", f"연동된 알림 채널이 없습니다 (reminder_id: {reminder_id})")
                print("⚠️  알림 채널 연동이 필요합니다 (카카오톡 또는 텔레그램)")
                return

            # 메시지 포맷팅 (예약된 시간을 포함)
            message = self.format_memo_message(reminder.message_content, reminder.target_datetime)

            # 알림 발송 (연동된 모든 채널로 자동 발송)
            try:
                result = await notification_service.send(user, message)

                if result.success:
                    # 발송 상태 업데이트
                    update_reminder_sent_status(db, reminder_id, is_sent=True)

                    # 성공 로그
                    create_log(
                        db,
                        "memo",
                        "SUCCESS",
                        f"메모 알림 발송 성공 (reminder_id: {reminder_id}, {result.message})",
                    )
                    print(f"✅ 메모 알림 발송 완료 - reminder_id: {reminder_id}")
                else:
                    # 실패 로그
                    create_log(db, "memo", "FAIL", f"알림 발송 실패: {result.message} (reminder_id: {reminder_id})")
                    print(f"❌ 알림 발송 실패: {result.message}")

            except Exception as e:
                create_log(db, "memo", "FAIL", f"알림 발송 오류: {str(e)} (reminder_id: {reminder_id})")
                print(f"❌ 알림 발송 오류: {e}")

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
            target_datetime: 발송 예정 시간 (KST)
        """
        job_id = f"reminder_{reminder_id}"

        # target_datetime이 timezone 정보가 있는지 확인
        if target_datetime.tzinfo is None:
            # timezone 정보가 없으면 UTC로 간주하고 KST로 변환 (DB에 UTC로 저장되어 있음)
            kst_dt = target_datetime.replace(tzinfo=timezone.utc).astimezone(ZoneInfo("Asia/Seoul"))
        else:
            # timezone 정보가 있으면 이미 KST이므로 그대로 사용
            kst_dt = target_datetime

        scheduler_service.add_date_job(
            func=send_memo_notification_sync,
            job_id=job_id,
            run_date=kst_dt,
            args=(reminder_id,),
        )

        print(f"메모 Job 등록 완료: {job_id} - {kst_dt} (KST)")

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
                now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
                target_dt = reminder.target_datetime

                # target_datetime이 timezone 정보가 있는지 확인
                if target_dt.tzinfo is None:
                    # timezone 정보가 없으면 UTC로 간주하고 KST로 변환 (DB에 UTC로 저장되어 있음)
                    target_dt = target_dt.replace(tzinfo=timezone.utc).astimezone(ZoneInfo("Asia/Seoul"))

                if target_dt <= now_kst:
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
