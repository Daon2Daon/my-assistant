"""YoutubeBot: 포맷 로직 단위 테스트."""

from datetime import datetime, timezone

import pytest

from app.services.bots.youtube_bot import (
    _format_duration,
    _to_kst,
    build_notification_text,
)


def _pub() -> datetime:
    return datetime(2026, 5, 11, 9, 0, 0, tzinfo=timezone.utc)


def test_format_duration_mmss():
    assert _format_duration(333) == "5:33"


def test_format_duration_hhmmss():
    assert _format_duration(3661) == "1:01:01"


def test_format_duration_none():
    assert _format_duration(None) == ""


def test_to_kst_converts_utc():
    result = _to_kst(datetime(2026, 5, 11, 0, 0, 0, tzinfo=timezone.utc))
    assert "KST" in result
    assert "2026-05-11 09:00" in result


def test_build_notification_text_contains_required_parts():
    text = build_notification_text(
        channel_name="테스트 채널",
        headline="🎬 헤드라인",
        full_analysis_md="## 전체 분석\n본문 일부",
        bullet_points=["첫 포인트", "둘째 포인트"],
        tags=["반도체", "HBM"],
        published_at=_pub(),
        duration_seconds=333,
        video_url="https://www.youtube.com/watch?v=abc",
    )
    assert "테스트 채널" in text
    assert "헤드라인" in text
    assert "전체 분석" in text
    assert "첫 포인트" in text
    assert "반도체" in text
    assert "5:33" in text
    assert "영상 보러가기" in text
    assert "https://www.youtube.com/watch?v=abc" in text


def test_build_notification_text_low_confidence_badge():
    text = build_notification_text(
        channel_name="채널",
        headline=None,
        full_analysis_md="분석 본문",
        bullet_points=["a"],
        tags=[],
        published_at=_pub(),
        duration_seconds=None,
        video_url="https://www.youtube.com/watch?v=x",
        confidence_score=0.3,
        low_confidence_threshold=0.5,
    )
    assert "저신뢰도" in text


def test_build_notification_text_no_badge_above_threshold():
    text = build_notification_text(
        channel_name="채널",
        headline=None,
        full_analysis_md="분석",
        bullet_points=None,
        tags=[],
        published_at=_pub(),
        duration_seconds=None,
        video_url="https://www.youtube.com/watch?v=x",
        confidence_score=0.9,
        low_confidence_threshold=0.5,
    )
    assert "저신뢰도" not in text


def test_build_notification_text_escapes_ampersand_in_video_url():
    """YouTube URL 쿼리의 & 가 href 속성을 깨뜨리지 않도록 이스케이프."""
    url = "https://www.youtube.com/watch?v=abc&list=PLtest&index=1"
    text = build_notification_text(
        channel_name="채널",
        headline=None,
        full_analysis_md="짧은 본문",
        bullet_points=None,
        tags=[],
        published_at=_pub(),
        duration_seconds=None,
        video_url=url,
    )
    assert 'href="https://www.youtube.com/watch?v=abc&amp;list=PLtest&amp;index=1"' in text
    assert "watch?v=abc" in text


def test_build_notification_text_truncates_long_body():
    long_body = "A" * 4000
    text = build_notification_text(
        channel_name="채널",
        headline=None,
        full_analysis_md=long_body,
        bullet_points=["b"],
        tags=[],
        published_at=_pub(),
        duration_seconds=None,
        video_url="https://www.youtube.com/watch?v=x",
    )
    assert len(text) <= 4096
    assert "…" in text or len(long_body) > len(text)
