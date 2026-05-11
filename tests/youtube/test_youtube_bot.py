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
        one_line="한 줄 요약",
        short_summary_md="짧은 요약",
        tags=["반도체", "HBM"],
        published_at=_pub(),
        duration_seconds=333,
        video_url="https://www.youtube.com/watch?v=abc",
    )
    assert "테스트 채널" in text
    assert "헤드라인" in text
    assert "한 줄 요약" in text
    assert "반도체" in text
    assert "5:33" in text
    assert "영상 보러가기" in text
    assert "https://www.youtube.com/watch?v=abc" in text


def test_build_notification_text_low_confidence_badge():
    text = build_notification_text(
        channel_name="채널",
        headline=None,
        one_line="요약",
        short_summary_md="s",
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
        one_line="요약",
        short_summary_md="s",
        tags=[],
        published_at=_pub(),
        duration_seconds=None,
        video_url="https://www.youtube.com/watch?v=x",
        confidence_score=0.9,
        low_confidence_threshold=0.5,
    )
    assert "저신뢰도" not in text


def test_build_notification_text_truncates_long_summary():
    long_summary = "A" * 4000
    text = build_notification_text(
        channel_name="채널",
        headline=None,
        one_line="요약",
        short_summary_md=long_summary,
        tags=[],
        published_at=_pub(),
        duration_seconds=None,
        video_url="https://www.youtube.com/watch?v=x",
    )
    assert len(text) <= 4096
    assert "전체 보기" in text
