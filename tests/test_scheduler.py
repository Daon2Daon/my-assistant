"""
스케줄러 동작 테스트
APScheduler 기반 스케줄러 서비스 테스트
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from app.services.scheduler import SchedulerService


class TestSchedulerService:
    """SchedulerService 테스트"""

    @pytest.fixture
    def scheduler(self):
        """테스트용 스케줄러 픽스처"""
        # 메모리 기반 스케줄러 (JobStore 없음)
        from apscheduler.schedulers.background import BackgroundScheduler

        service = SchedulerService.__new__(SchedulerService)
        service.scheduler = BackgroundScheduler()
        service._running = False
        return service

    def test_start(self, scheduler):
        """스케줄러 시작 테스트"""
        scheduler.start()
        assert scheduler.is_running() is True

        # 정리
        scheduler.shutdown()

    def test_shutdown(self, scheduler):
        """스케줄러 종료 테스트"""
        scheduler.start()
        scheduler.shutdown()
        assert scheduler.is_running() is False

    def test_is_running_initial(self, scheduler):
        """초기 상태 테스트"""
        assert scheduler.is_running() is False

    def test_add_cron_job(self, scheduler):
        """Cron Job 등록 테스트"""
        scheduler.start()

        mock_func = MagicMock()
        scheduler.add_cron_job(
            func=mock_func,
            job_id="test_cron_job",
            hour=7,
            minute=0,
        )

        job = scheduler.get_job("test_cron_job")
        assert job is not None
        assert job.id == "test_cron_job"

        # 정리
        scheduler.shutdown()

    def test_add_cron_job_with_args(self, scheduler):
        """인자가 있는 Cron Job 등록 테스트"""
        scheduler.start()

        mock_func = MagicMock()
        scheduler.add_cron_job(
            func=mock_func,
            job_id="test_cron_job_args",
            hour=8,
            minute=30,
            args=("Seoul",),
        )

        job = scheduler.get_job("test_cron_job_args")
        assert job is not None
        assert job.args == ("Seoul",)

        # 정리
        scheduler.shutdown()

    def test_add_date_job(self, scheduler):
        """Date Job 등록 테스트"""
        scheduler.start()

        mock_func = MagicMock()
        run_date = datetime.now() + timedelta(hours=1)

        scheduler.add_date_job(
            func=mock_func,
            job_id="test_date_job",
            run_date=run_date,
        )

        job = scheduler.get_job("test_date_job")
        assert job is not None
        assert job.id == "test_date_job"

        # 정리
        scheduler.shutdown()

    def test_remove_job(self, scheduler):
        """Job 삭제 테스트"""
        scheduler.start()

        mock_func = MagicMock()
        scheduler.add_cron_job(
            func=mock_func,
            job_id="test_remove_job",
            hour=9,
            minute=0,
        )

        # 삭제
        result = scheduler.remove_job("test_remove_job")
        assert result is True

        # 삭제 확인
        job = scheduler.get_job("test_remove_job")
        assert job is None

        # 정리
        scheduler.shutdown()

    def test_remove_nonexistent_job(self, scheduler):
        """존재하지 않는 Job 삭제 테스트"""
        scheduler.start()

        result = scheduler.remove_job("nonexistent_job")
        assert result is False

        # 정리
        scheduler.shutdown()

    def test_get_job(self, scheduler):
        """Job 조회 테스트"""
        scheduler.start()

        mock_func = MagicMock()
        scheduler.add_cron_job(
            func=mock_func,
            job_id="test_get_job",
            hour=10,
            minute=0,
        )

        job = scheduler.get_job("test_get_job")
        assert job is not None
        assert job.id == "test_get_job"

        # 정리
        scheduler.shutdown()

    def test_get_job_not_found(self, scheduler):
        """존재하지 않는 Job 조회 테스트"""
        scheduler.start()

        job = scheduler.get_job("nonexistent_job")
        assert job is None

        # 정리
        scheduler.shutdown()

    def test_get_all_jobs_empty(self, scheduler):
        """빈 Job 목록 조회 테스트"""
        scheduler.start()

        jobs = scheduler.get_all_jobs()
        assert jobs == []

        # 정리
        scheduler.shutdown()

    def test_get_all_jobs(self, scheduler):
        """Job 목록 조회 테스트"""
        scheduler.start()

        mock_func = MagicMock()

        scheduler.add_cron_job(mock_func, "job1", 7, 0)
        scheduler.add_cron_job(mock_func, "job2", 8, 0)

        jobs = scheduler.get_all_jobs()
        assert len(jobs) == 2

        job_ids = [job["id"] for job in jobs]
        assert "job1" in job_ids
        assert "job2" in job_ids

        # 정리
        scheduler.shutdown()

    def test_pause_job(self, scheduler):
        """Job 일시 정지 테스트"""
        scheduler.start()

        mock_func = MagicMock()
        scheduler.add_cron_job(mock_func, "test_pause", 7, 0)

        result = scheduler.pause_job("test_pause")
        assert result is True

        # 일시 정지된 Job 확인
        job = scheduler.get_job("test_pause")
        assert job.next_run_time is None  # 일시 정지 시 next_run_time이 None

        # 정리
        scheduler.shutdown()

    def test_pause_nonexistent_job(self, scheduler):
        """존재하지 않는 Job 일시 정지 테스트"""
        scheduler.start()

        result = scheduler.pause_job("nonexistent")
        assert result is False

        # 정리
        scheduler.shutdown()

    def test_resume_job(self, scheduler):
        """Job 재개 테스트"""
        scheduler.start()

        mock_func = MagicMock()
        scheduler.add_cron_job(mock_func, "test_resume", 7, 0)

        # 일시 정지 후 재개
        scheduler.pause_job("test_resume")
        result = scheduler.resume_job("test_resume")
        assert result is True

        # 재개된 Job 확인
        job = scheduler.get_job("test_resume")
        assert job.next_run_time is not None

        # 정리
        scheduler.shutdown()

    def test_resume_nonexistent_job(self, scheduler):
        """존재하지 않는 Job 재개 테스트"""
        scheduler.start()

        result = scheduler.resume_job("nonexistent")
        assert result is False

        # 정리
        scheduler.shutdown()

    def test_replace_existing_job(self, scheduler):
        """기존 Job 교체 테스트"""
        scheduler.start()

        mock_func1 = MagicMock()
        mock_func2 = MagicMock()

        # 첫 번째 Job 등록
        scheduler.add_cron_job(mock_func1, "replace_job", 7, 0)

        # 같은 ID로 다른 Job 등록 (교체)
        scheduler.add_cron_job(mock_func2, "replace_job", 8, 0, replace_existing=True)

        jobs = scheduler.get_all_jobs()
        assert len(jobs) == 1

        job = scheduler.get_job("replace_job")
        # CronTrigger 문자열 형식: "cron[hour='8', minute='0']"
        trigger_str = str(job.trigger)
        assert "hour='8'" in trigger_str or "08:00" in trigger_str

        # 정리
        scheduler.shutdown()


class TestSchedulerServiceSingleton:
    """싱글톤 인스턴스 테스트"""

    def test_singleton_instance(self):
        """싱글톤 인스턴스 테스트"""
        from app.services.scheduler import scheduler_service

        assert scheduler_service is not None

    def test_singleton_is_scheduler_service(self):
        """싱글톤 타입 확인"""
        from app.services.scheduler import scheduler_service, SchedulerService

        assert isinstance(scheduler_service, SchedulerService)
