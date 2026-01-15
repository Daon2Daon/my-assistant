"""
스케줄러 서비스
APScheduler를 사용한 정기 작업 관리
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional, List, Dict
from app.config import settings


class SchedulerService:
    """
    스케줄러 관리 서비스
    정기 작업 및 일회성 작업 스케줄링
    """

    def __init__(self):
        # Job Store 설정 (SQLite에 Job 정보 저장)
        jobstores = {
            "default": SQLAlchemyJobStore(url=settings.DATABASE_URL)
        }

        # Scheduler 설정
        self.scheduler = BackgroundScheduler(
            jobstores=jobstores,
            job_defaults={
                "coalesce": False,  # 누락된 작업을 하나로 합치지 않음
                "max_instances": 3,  # 동시 실행 최대 인스턴스 수
            },
            timezone=ZoneInfo("Asia/Seoul"),  # 한국 시간대 설정
        )

        self._running = False

    def start(self):
        """
        스케줄러 시작
        """
        if not self._running:
            self.scheduler.start()
            self._running = True
            print("✅ 스케줄러 시작")

    def shutdown(self):
        """
        스케줄러 종료
        """
        if self._running:
            self.scheduler.shutdown()
            self._running = False
            print("👋 스케줄러 종료")

    def is_running(self) -> bool:
        """
        스케줄러 실행 상태 확인
        """
        return self._running

    def add_cron_job(
        self,
        func,
        job_id: str,
        hour: int,
        minute: int,
        args: Optional[tuple] = None,
        replace_existing: bool = True,
    ):
        """
        정기 작업(Cron) 등록
        매일 지정된 시간에 실행

        Args:
            func: 실행할 함수
            job_id: Job ID (고유 식별자)
            hour: 시 (0-23)
            minute: 분 (0-59)
            args: 함수 인자
            replace_existing: 기존 Job 교체 여부
        """
        trigger = CronTrigger(hour=hour, minute=minute)

        self.scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            args=args or (),
            replace_existing=replace_existing,
        )

        print(f"📅 Cron Job 등록: {job_id} - 매일 {hour:02d}:{minute:02d}")

    def add_interval_job(
        self,
        func,
        job_id: str,
        minutes: int,
        args: Optional[tuple] = None,
        replace_existing: bool = True,
    ):
        """
        주기 작업(Interval) 등록
        지정된 시간 간격으로 반복 실행

        Args:
            func: 실행할 함수
            job_id: Job ID (고유 식별자)
            minutes: 실행 간격 (분)
            args: 함수 인자
            replace_existing: 기존 Job 교체 여부
        """
        trigger = IntervalTrigger(minutes=minutes)

        self.scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            args=args or (),
            replace_existing=replace_existing,
        )

        print(f"⏱️  Interval Job 등록: {job_id} - {minutes}분마다 실행")

    def add_date_job(
        self,
        func,
        job_id: str,
        run_date: datetime,
        args: Optional[tuple] = None,
        replace_existing: bool = True,
    ):
        """
        일회성 작업(Date) 등록
        지정된 시간에 한 번만 실행

        Args:
            func: 실행할 함수
            job_id: Job ID (고유 식별자)
            run_date: 실행 시간
            args: 함수 인자
            replace_existing: 기존 Job 교체 여부
        """
        trigger = DateTrigger(run_date=run_date)

        self.scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            args=args or (),
            replace_existing=replace_existing,
        )

        print(f"⏰ Date Job 등록: {job_id} - {run_date.strftime('%Y-%m-%d %H:%M:%S')}")

    def remove_job(self, job_id: str) -> bool:
        """
        Job 삭제

        Args:
            job_id: 삭제할 Job ID

        Returns:
            bool: 삭제 성공 여부
        """
        try:
            self.scheduler.remove_job(job_id)
            print(f"🗑️  Job 삭제: {job_id}")
            return True
        except Exception as e:
            print(f"❌ Job 삭제 실패: {job_id} - {e}")
            return False

    def get_job(self, job_id: str):
        """
        Job 조회

        Args:
            job_id: 조회할 Job ID

        Returns:
            Job 객체 또는 None
        """
        return self.scheduler.get_job(job_id)

    def get_all_jobs(self) -> List[Dict]:
        """
        모든 Job 목록 조회

        Returns:
            List[Dict]: Job 정보 리스트
        """
        jobs = self.scheduler.get_jobs()
        job_list = []

        for job in jobs:
            job_info = {
                "id": job.id,
                "name": job.name,
                "next_run_time": (
                    job.next_run_time.isoformat() if job.next_run_time else None
                ),
                "trigger": str(job.trigger),
            }
            job_list.append(job_info)

        return job_list

    def pause_job(self, job_id: str) -> bool:
        """
        Job 일시 정지

        Args:
            job_id: 정지할 Job ID

        Returns:
            bool: 성공 여부
        """
        try:
            self.scheduler.pause_job(job_id)
            print(f"⏸️  Job 일시 정지: {job_id}")
            return True
        except Exception as e:
            print(f"❌ Job 정지 실패: {job_id} - {e}")
            return False

    def resume_job(self, job_id: str) -> bool:
        """
        Job 재개

        Args:
            job_id: 재개할 Job ID

        Returns:
            bool: 성공 여부
        """
        try:
            self.scheduler.resume_job(job_id)
            print(f"▶️  Job 재개: {job_id}")
            return True
        except Exception as e:
            print(f"❌ Job 재개 실패: {job_id} - {e}")
            return False


# 싱글톤 인스턴스
scheduler_service = SchedulerService()
