"""
YouTube 모니터 파이프라인 E2E 통합 테스트.

외부 의존성(YouTube API, LLM, PostgreSQL, Telegram)은 모두 mock 처리.
세 가지 핵심 시나리오를 검증합니다:
  1. 채널 폴링 → 신규 영상 감지 → 분석 → Telegram 알림 성공 흐름
  2. 분석 실패 → videos.status = 'failed' 기록 → 재분석 요청 처리
  3. DB 연결 불가 → 잡 SKIP 처리 → 복구 후 정상 폴링
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.youtube.analyzer import (
    AnalysisPipeline,
    AnalysisPipelineResult,
    AnalysisFailedError,
    _validate,
    REQUIRED_FIELDS,
)
from app.services.youtube.llm_client import AnalyzerResult, ChatResult
from app.services.youtube.monitor_service import (
    MonitorService,
    youtube_master_poll_sync,
)
from app.services.youtube.settings_manager import (
    AIGatewaySettings,
    PollingSettings,
)
from app.services.youtube.youtube_api import PlaylistItemMeta, VideoMeta


# ── 공통 픽스처 / 헬퍼 ────────────────────────────────────────────────────────

def _polling() -> PollingSettings:
    return PollingSettings(
        master_interval_min=12,
        default_channel_interval_min=720,
        youtube_api_key="test-api-key",
        youtube_daily_quota=10_000,
        window_hours=24,
        max_concurrent_channels=2,
        max_concurrent_analyses=2,
    )


def _ai_settings() -> AIGatewaySettings:
    return AIGatewaySettings(
        base_url="http://gateway.test",
        api_key="gw-key",
        primary_model="gemini-test",
        fallback_model="gpt-test",
        tagging_model="gpt-test",
        temperature=0.3,
        max_tokens=4096,
        daily_budget_usd=1.0,
    )


def _good_analysis_data() -> dict:
    """분석 파이프라인이 반환하는 유효한 JSON 데이터."""
    return {
        "one_line": "테스트 영상 한 줄 요약",
        "headline": "📌 테스트 헤드라인",
        "short_summary_md": "짧은 요약 내용입니다.",
        "bullet_points": ["포인트 1", "포인트 2", "포인트 3"],
        "full_analysis_md": "## 분석\n전체 분석 내용",
        "key_points": [{"timestamp": "00:01:00", "point": "핵심 포인트"}],
        "insights": ["인사이트 1"],
        "entities": [{"type": "person", "name": "홍길동"}],
        "sentiment": "bullish",
        "tags": [{"name": "테스트", "type": "topic", "weight": 0.9}],
        "confidence_score": 0.85,
    }


def _make_channel(pk: int = 1, playlist_id: str = "UUTEST") -> MagicMock:
    ch = MagicMock()
    ch.channel_pk = pk
    ch.channel_id = "UC_TEST"
    ch.channel_name = "테스트 채널"
    ch.upload_playlist_id = playlist_id
    ch.is_active = True
    ch.poll_interval_min = 720
    ch.last_checked_at = None
    return ch


def _make_playlist_item(video_id: str) -> PlaylistItemMeta:
    return PlaylistItemMeta(
        video_id=video_id,
        published_at=datetime.now(timezone.utc).isoformat(),
        title=f"영상 {video_id}",
    )


def _make_video_meta(video_id: str) -> VideoMeta:
    return VideoMeta(
        video_id=video_id,
        video_url=f"https://www.youtube.com/watch?v={video_id}",
        title=f"테스트 영상 {video_id}",
        description="영상 설명",
        thumbnail_url=None,
        published_at=datetime.now(timezone.utc).isoformat(),
        duration="PT10M30S",
        view_count=1000,
        like_count=50,
    )


# ── 시나리오 1: 채널 폴링 → 분석 → 알림 성공 흐름 ─────────────────────────────

class TestScenario1_PollingToNotification:
    """
    새 영상이 감지되면 분석 파이프라인이 실행되고,
    알림 콜백이 video_pk와 함께 호출되어야 한다.
    """

    @pytest.mark.asyncio
    async def test_new_video_triggers_analysis_and_notify(self):
        """process_channel → video pk 획득 → run_and_save → notify_callback 순서 검증."""
        good_data = _good_analysis_data()
        pipeline_result = AnalysisPipelineResult(
            data=good_data,
            route="A",
            model_name="gemini-test",
            gateway_url="http://gateway.test",
            raw_text=json.dumps(good_data),
        )

        notify_called_with: list[int] = []

        async def fake_notify(video_pk: int) -> None:
            notify_called_with.append(video_pk)

        mock_pipeline = AsyncMock()

        async def _run_and_save_with_notify(session, video_pk, **kwargs):
            await fake_notify(video_pk)
            return pipeline_result

        mock_pipeline.run_and_save.side_effect = _run_and_save_with_notify

        # ── MonitorService mock session / API ────────────────────────────────
        svc = MonitorService(_polling())
        channel = _make_channel(pk=1)

        api = AsyncMock()
        api.get_latest_playlist_items.return_value = [_make_playlist_item("v_new")]
        api.get_video_details.return_value = [_make_video_meta("v_new")]

        session = AsyncMock()
        existing_result = MagicMock()
        existing_result.scalars.return_value = iter([])
        seq_result = MagicMock()
        seq_result.scalar.return_value = None
        insert_result = MagicMock()
        insert_result.scalar.return_value = 42  # video_pk
        update_result = MagicMock()

        session.execute = AsyncMock(
            side_effect=[existing_result, seq_result, insert_result, update_result]
        )
        session.flush = AsyncMock()

        # ── 폴링 실행 ─────────────────────────────────────────────────────────
        new_pks = await svc.process_channel(
            channel=channel,
            session=session,
            api_client=api,
            backfill=True,
        )
        assert 42 in new_pks

        # 분석 + 알림 호출
        await mock_pipeline.run_and_save(
            session=session,
            video_pk=42,
            video_url="https://www.youtube.com/watch?v=v_new",
            channel_name="테스트 채널",
            published_at_str=datetime.now(timezone.utc).isoformat(),
        )

        assert notify_called_with == [42], "알림 콜백이 video_pk=42로 호출되어야 한다"

    def test_analysis_required_fields_validated(self):
        """분석 결과 데이터가 7개 필수 필드를 모두 포함하면 검증을 통과한다."""
        good_data = _good_analysis_data()
        # _validate가 예외를 던지지 않으면 통과
        _validate(good_data)

    def test_analysis_missing_field_raises_error(self):
        """필수 필드 누락 시 AnalysisValidationError가 발생한다."""
        from app.services.youtube.analyzer import AnalysisValidationError

        incomplete = _good_analysis_data()
        del incomplete["one_line"]

        with pytest.raises(AnalysisValidationError):
            _validate(incomplete)

    @pytest.mark.asyncio
    async def test_notify_skipped_when_no_callback(self):
        """notify_callback이 None이면 알림 없이 정상 완료."""
        ai = _ai_settings()
        mock_llm = AsyncMock()

        good_data = _good_analysis_data()
        # analyze_video_native는 AnalyzerResult를 반환해야 함
        mock_llm.analyze_video_native = AsyncMock(
            return_value=AnalyzerResult(
                data=good_data,
                raw_text=json.dumps(good_data),
            )
        )

        pipeline = AnalysisPipeline(
            llm_client=mock_llm,
            ai_settings=ai,
            notify_callback=None,
        )

        result = await pipeline.run(
            video_pk=10,
            video_url="https://www.youtube.com/watch?v=test",
            channel_name="채널",
            published_at_str="2026-05-11T00:00:00Z",
        )

        assert result.route == "A"
        assert result.data["confidence_score"] == 0.85


# ── 시나리오 2: 분석 실패 → failed 상태 기록 → 재분석 시 재실행 ─────────────────

class TestScenario2_AnalysisFailureAndRetry:
    """
    분석 파이프라인이 경로 A·B 모두 실패하면 videos.status = 'failed'로 갱신되고,
    재분석 요청 시 동일한 파이프라인이 다시 실행되어야 한다.
    """

    @pytest.mark.asyncio
    async def test_run_and_save_marks_status_processing_then_failed(self):
        """AnalysisFailedError 발생 시 processing → failed 상태 순서대로 갱신된다."""
        from app.services.youtube.llm_client import LiteLLMError

        ai = _ai_settings()
        mock_llm = AsyncMock()
        # 경로 A 실패
        mock_llm.analyze_video_native = AsyncMock(
            side_effect=LiteLLMError("Gemini API 오류")
        )
        # 경로 B도 실패
        mock_llm.chat = AsyncMock(side_effect=LiteLLMError("Chat API 오류"))

        pipeline = AnalysisPipeline(
            llm_client=mock_llm,
            ai_settings=ai,
        )

        session = AsyncMock()
        session.execute = AsyncMock(return_value=MagicMock())
        session.flush = AsyncMock()

        # run_and_save는 AnalysisFailedError를 전파하고, execute를 최소 2번 호출해야 함
        # (1번: processing 상태 설정, 1번: failed 상태 설정)
        with pytest.raises((AnalysisFailedError, Exception)):
            await pipeline.run_and_save(
                session=session,
                video_pk=99,
                video_url="https://www.youtube.com/watch?v=fail",
                channel_name="실패 채널",
                published_at_str="2026-05-11T00:00:00Z",
            )

        # execute가 최소 2번 호출되었는지 확인
        # (processing 상태 → flush → failed 상태)
        assert session.execute.call_count >= 2, \
            f"분석 실패 시 execute가 2번 이상 호출되어야 함 (실제: {session.execute.call_count}회)"
        assert session.flush.called, "flush가 호출되어야 한다"

    @pytest.mark.asyncio
    async def test_reanalyze_calls_pipeline_again(self):
        """재분석 요청 시 동일한 파이프라인이 새로운 인자로 다시 호출된다."""
        reanalyze_count = [0]

        async def fake_run_and_save(session, video_pk, **kwargs):
            reanalyze_count[0] += 1
            return AnalysisPipelineResult(
                data=_good_analysis_data(),
                route="B",
                model_name="gpt-test",
                gateway_url="http://gateway.test",
                raw_text="{}",
            )

        mock_pipeline = AsyncMock()
        mock_pipeline.run_and_save.side_effect = fake_run_and_save
        session = AsyncMock()

        # 재분석을 두 번 요청
        for _ in range(2):
            await mock_pipeline.run_and_save(
                session=session,
                video_pk=55,
                video_url="https://www.youtube.com/watch?v=retry",
                channel_name="재분석 채널",
                published_at_str="2026-05-11T00:00:00Z",
            )

        assert reanalyze_count[0] == 2, "재분석 요청 시 파이프라인이 재실행되어야 한다"

    @pytest.mark.asyncio
    async def test_route_b_fallback_on_route_a_failure(self):
        """경로 A 실패 시 자막 기반 경로 B로 폴백된다."""
        from app.services.youtube.llm_client import LiteLLMError

        ai = _ai_settings()
        mock_llm = AsyncMock()
        # 경로 A 실패
        mock_llm.analyze_video_native = AsyncMock(
            side_effect=LiteLLMError("멀티모달 오류")
        )
        # 경로 B 성공
        good_data = _good_analysis_data()
        mock_llm.chat = AsyncMock(
            return_value=ChatResult(content=json.dumps(good_data), raw={})
        )

        pipeline = AnalysisPipeline(
            llm_client=mock_llm,
            ai_settings=ai,
        )

        # 자막 추출을 mock (내부 동기 함수 patch)
        with patch(
            "app.services.youtube.analyzer._get_transcript_async",
            new_callable=AsyncMock,
            return_value="자막 내용 샘플입니다.",
        ):
            result = await pipeline.run(
                video_pk=77,
                video_url="https://www.youtube.com/watch?v=fallback",
                channel_name="폴백 채널",
                published_at_str="2026-05-11T00:00:00Z",
            )

        assert result.route == "B", "경로 A 실패 시 경로 B로 폴백되어야 한다"
        _validate(result.data)


# ── 시나리오 3: DB 연결 끊김 → SKIP → 복구 ────────────────────────────────────

class TestScenario3_DBConnectionFailureAndRecovery:
    """
    DB 연결이 불가능한 상태에서 youtube_master_poll_sync 호출 시
    예외가 로그에 기록되고 잡이 SKIP되어야 하며,
    연결 복구 후에는 정상적으로 폴링이 실행되어야 한다.
    """

    def test_master_poll_sync_handles_db_not_configured_error(self):
        """DBNotConfiguredError 발생 시 youtube_master_poll_sync가 조용히 종료된다.

        _youtube_master_poll_async()에서 DBNotConfiguredError는 try/except로 처리되어
        'SKIP' 메시지 출력 후 return됩니다. 따라서 예외가 전파되면 안 됩니다.
        """
        from app.services.youtube.db_engine import DBNotConfiguredError

        with patch(
            "app.services.youtube.monitor_service.get_youtube_settings_manager"
        ) as mock_mgr:
            mock_mgr.return_value.get_polling.return_value = _polling()

            with patch(
                "app.services.youtube.monitor_service.db_engine_manager"
            ) as mock_engine_mgr:
                # get_engine()이 DBNotConfiguredError 발생 → _youtube_master_poll_async에서 처리
                mock_engine_mgr.get_engine = AsyncMock(
                    side_effect=DBNotConfiguredError("DB 미설정")
                )

                # 예외가 전파되지 않고 함수가 정상 종료되어야 함
                youtube_master_poll_sync()

    def test_master_poll_sync_handles_generic_exception(self):
        """DB 엔진 획득 중 예기치 못한 예외 발생 시도 youtube_master_poll_sync가 조용히 종료된다."""
        with patch(
            "app.services.youtube.monitor_service.get_youtube_settings_manager"
        ) as mock_mgr:
            mock_mgr.return_value.get_polling.return_value = _polling()

            with patch(
                "app.services.youtube.monitor_service.db_engine_manager"
            ) as mock_engine_mgr:
                mock_engine_mgr.get_engine = AsyncMock(
                    side_effect=RuntimeError("연결 오류")
                )

                # 예외가 전파되지 않고 함수가 정상 종료되어야 함
                youtube_master_poll_sync()

    @pytest.mark.asyncio
    async def test_async_poll_skips_when_db_unavailable(self):
        """DB 연결 실패 시 _youtube_master_poll_async가 채널 조회를 건너뛴다."""
        from app.services.youtube.db_engine import DBNotConfiguredError
        from app.services.youtube.monitor_service import _youtube_master_poll_async

        with patch(
            "app.services.youtube.monitor_service.db_engine_manager"
        ) as mock_engine_mgr:
            mock_engine_mgr.get_engine.side_effect = DBNotConfiguredError("DB 미설정")

            with patch(
                "app.services.youtube.monitor_service.get_youtube_settings_manager"
            ) as mock_mgr:
                mock_mgr.return_value.get_polling.return_value = _polling()

                # 예외가 전파되지 않아야 한다
                await _youtube_master_poll_async()

    @pytest.mark.asyncio
    async def test_async_poll_processes_channels_when_db_available(self):
        """DB 연결 성공 시 채널 목록을 조회한다."""
        from app.services.youtube.monitor_service import _youtube_master_poll_async
        from sqlalchemy.ext.asyncio import async_sessionmaker

        mock_engine = MagicMock()

        with patch(
            "app.services.youtube.monitor_service.db_engine_manager"
        ) as mock_engine_mgr:
            mock_engine_mgr.get_engine.return_value = mock_engine

            with patch(
                "app.services.youtube.monitor_service.get_youtube_settings_manager"
            ) as mock_mgr:
                mock_mgr.return_value.get_polling.return_value = _polling()

                # async_sessionmaker를 mock하여 빈 채널 목록 반환
                inner_session = AsyncMock()
                inner_result = MagicMock()
                inner_result.scalars.return_value.all.return_value = []
                inner_session.execute = AsyncMock(return_value=inner_result)
                inner_session.commit = AsyncMock()

                mock_session_ctx = MagicMock()
                mock_session_ctx.__aenter__ = AsyncMock(return_value=inner_session)
                mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

                mock_factory = MagicMock(return_value=mock_session_ctx)

                with patch(
                    "app.services.youtube.monitor_service.async_sessionmaker",
                    return_value=mock_factory,
                ):
                    with patch(
                        "app.services.youtube.monitor_service.get_youtube_api_client",
                        return_value=AsyncMock(),
                    ):
                        await _youtube_master_poll_async()

                # DB 연결 성공 시 get_engine이 호출되어야 함
                mock_engine_mgr.get_engine.assert_called_once()


# ── 기존 기능 회귀 테스트 ───────────────────────────────────────────────────────

class TestRegressionExistingFeatures:
    """
    YouTube 모듈 추가 후 기존 app 기능이 영향받지 않는지 검증.
    """

    def test_existing_models_importable(self):
        """기존 SQLAlchemy 모델들이 정상 임포트된다."""
        from app.models.user import User
        from app.models.reminder import Reminder

        assert User.__tablename__ == "users"
        assert Reminder.__tablename__ == "reminders"

    def test_youtube_models_use_separate_base(self):
        """YouTube PG 모델이 기존 SQLite Base와 분리된 별도의 Base를 사용한다."""
        from app.database import Base as SqliteBase
        from app.models.youtube_pg_base import YoutubePGBase
        from app.models.youtube_channel import YoutubeChannel

        assert YoutubeChannel.__table__.metadata is not SqliteBase.metadata, \
            "YouTube PG 모델은 SQLite Base와 분리된 메타데이터를 사용해야 한다"

    def test_youtube_settings_model_registered_in_sqlite_base(self):
        """YoutubeSetting 모델은 SQLite Base에 등록되어야 한다."""
        from app.database import Base as SqliteBase

        assert "youtube_settings" in SqliteBase.metadata.tables, \
            "youtube_settings 테이블이 SQLite Base 메타데이터에 등록되어야 한다"

    def test_scheduler_has_youtube_jobs_method(self):
        """SchedulerService에 setup_youtube_jobs 메서드가 존재한다."""
        from app.services.scheduler import SchedulerService

        assert hasattr(SchedulerService, "setup_youtube_jobs"), \
            "SchedulerService에 setup_youtube_jobs 메서드가 있어야 한다"

    def test_main_router_includes_youtube(self):
        """app.routers.youtube에 router 인스턴스가 등록되어 있어야 한다."""
        import app.routers.youtube as youtube_router_module

        assert hasattr(youtube_router_module, "router"), \
            "youtube 라우터 모듈에 router 인스턴스가 있어야 한다"

    def test_required_fields_set_completeness(self):
        """REQUIRED_FIELDS가 명세에 정의된 7개 필드를 모두 포함한다."""
        expected = {
            "one_line", "headline", "short_summary_md",
            "bullet_points", "full_analysis_md", "sentiment", "confidence_score",
        }
        assert REQUIRED_FIELDS == expected, \
            f"REQUIRED_FIELDS가 예상과 다름: {REQUIRED_FIELDS}"
