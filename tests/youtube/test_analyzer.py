"""
AnalysisPipeline 단위 테스트.

DB(AsyncSession)와 LiteLLMClient는 모두 mock 처리.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.youtube.analyzer import (
    AnalysisFailedError,
    AnalysisPipeline,
    AnalysisValidationError,
    _validate,
    _published_at_kst,
    _extract_video_id,
)
from app.services.youtube.llm_client import AnalyzerResult, ChatResult, LiteLLMError
from app.services.youtube.settings_manager import AIGatewaySettings


# ── 공통 픽스처 ────────────────────────────────────────────────────────────────

GOOD_DATA = {
    "one_line": "한 줄 요약",
    "headline": "🎬 헤드라인",
    "short_summary_md": "짧은 요약",
    "bullet_points": ["포인트 1", "포인트 2"],
    "full_analysis_md": "전체 분석",
    "key_points": [],
    "insights": [],
    "entities": [],
    "sentiment": "neutral",
    "tags": [{"name": "반도체", "type": "topic", "weight": 0.9}],
    "confidence_score": 0.85,
}


def _make_ai_settings() -> AIGatewaySettings:
    return AIGatewaySettings(
        base_url="http://litellm:4000",
        api_key="key",
        primary_model="gemini-2.5-flash",
        fallback_model="gemini/gemini-2.5-flash",
        tagging_model="gemini/gemini-2.5-flash",
        temperature=0.3,
        max_tokens=8192,
        daily_budget_usd=2.0,
    )


def _make_pipeline(llm_mock, notify=None) -> AnalysisPipeline:
    return AnalysisPipeline(
        llm_client=llm_mock,
        ai_settings=_make_ai_settings(),
        notify_callback=notify,
    )


# ── _validate ──────────────────────────────────────────────────────────────────

def test_validate_passes_on_good_data():
    _validate(GOOD_DATA)


def test_validate_raises_on_missing_field():
    bad = {k: v for k, v in GOOD_DATA.items() if k != "sentiment"}
    with pytest.raises(AnalysisValidationError, match="sentiment"):
        _validate(bad)


def test_validate_raises_on_bad_sentiment():
    bad = {**GOOD_DATA, "sentiment": "unknown"}
    with pytest.raises(AnalysisValidationError, match="sentiment"):
        _validate(bad)


def test_validate_raises_on_out_of_range_confidence():
    bad = {**GOOD_DATA, "confidence_score": 1.5}
    with pytest.raises(AnalysisValidationError, match="confidence_score"):
        _validate(bad)


# ── 유틸 함수 ─────────────────────────────────────────────────────────────────

def test_extract_video_id_from_watch_url():
    assert _extract_video_id("https://www.youtube.com/watch?v=abc123") == "abc123"


def test_extract_video_id_from_short_url():
    assert _extract_video_id("https://youtu.be/abc123") == "abc123"


def test_published_at_kst_converts_utc():
    result = _published_at_kst("2026-05-11T06:00:00Z")
    assert "KST" in result
    assert "2026-05-11" in result


# ── run(): 경로 A 성공 ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_route_a_success():
    llm = MagicMock()
    llm.analyze_video_native = AsyncMock(
        return_value=AnalyzerResult(data=GOOD_DATA, raw_text=json.dumps(GOOD_DATA))
    )
    pipeline = _make_pipeline(llm)
    result = await pipeline.run(
        video_pk=1,
        video_url="https://www.youtube.com/watch?v=abc",
        channel_name="테스트 채널",
        published_at_str="2026-05-11T06:00:00Z",
    )
    assert result.route == "A"
    assert result.data["sentiment"] == "neutral"
    llm.analyze_video_native.assert_awaited_once()


# ── run(): 경로 A 실패 → 경로 B 성공 ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_route_a_fails_fallback_to_b():
    llm = MagicMock()
    llm.analyze_video_native = AsyncMock(side_effect=LiteLLMError("fileData error"))
    llm.chat = AsyncMock(
        return_value=ChatResult(content=json.dumps(GOOD_DATA), raw={})
    )

    with patch(
        "app.services.youtube.analyzer._get_transcript_async",
        new=AsyncMock(return_value="자막 텍스트"),
    ):
        pipeline = _make_pipeline(llm)
        result = await pipeline.run(
            video_pk=2,
            video_url="https://www.youtube.com/watch?v=xyz",
            channel_name="채널",
            published_at_str="2026-05-11T06:00:00Z",
        )

    assert result.route == "B"
    llm.chat.assert_awaited_once()


# ── run(): 경로 A·B 모두 실패 ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_both_routes_fail_raises_analysis_failed_error():
    llm = MagicMock()
    llm.analyze_video_native = AsyncMock(side_effect=LiteLLMError("A fail"))
    llm.chat = AsyncMock(side_effect=LiteLLMError("B fail"))

    with patch(
        "app.services.youtube.analyzer._get_transcript_async",
        new=AsyncMock(return_value=""),
    ):
        pipeline = _make_pipeline(llm)
        with pytest.raises(AnalysisFailedError):
            await pipeline.run(
                video_pk=3,
                video_url="https://www.youtube.com/watch?v=fail",
                channel_name="채널",
                published_at_str="2026-05-11T06:00:00Z",
            )


# ── run(): 경로 A 결과가 검증 실패 → 경로 B fallback ─────────────────────────

@pytest.mark.asyncio
async def test_run_route_a_validation_failure_falls_back_to_b():
    bad_data = {**GOOD_DATA, "sentiment": "INVALID"}
    llm = MagicMock()
    llm.analyze_video_native = AsyncMock(
        return_value=AnalyzerResult(data=bad_data, raw_text=json.dumps(bad_data))
    )
    llm.chat = AsyncMock(
        return_value=ChatResult(content=json.dumps(GOOD_DATA), raw={})
    )

    with patch(
        "app.services.youtube.analyzer._get_transcript_async",
        new=AsyncMock(return_value=""),
    ):
        pipeline = _make_pipeline(llm)
        result = await pipeline.run(
            video_pk=4,
            video_url="https://www.youtube.com/watch?v=val",
            channel_name="채널",
            published_at_str="2026-05-11T06:00:00Z",
        )
    assert result.route == "B"


# ── notify_callback 호출 확인 ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_save_to_db_calls_notify_callback():
    llm = MagicMock()
    notify = AsyncMock()
    pipeline = _make_pipeline(llm, notify=notify)

    session = AsyncMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()

    from app.services.youtube.analyzer import AnalysisPipelineResult

    result = AnalysisPipelineResult(
        data=GOOD_DATA,
        route="A",
        model_name="gemini-2.5-flash",
        gateway_url="http://litellm:4000",
    )

    with patch(
        "app.services.youtube.analyzer.extract_and_save_tags",
        new=AsyncMock(return_value=1),
    ):
        await pipeline.save_to_db(session=session, video_pk=5, result=result)

    notify.assert_awaited_once_with(5)
