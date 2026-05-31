"""
주간 리뷰(digest_service) 단위 테스트.

DB(AsyncSession)와 LLM 클라이언트는 mock 처리하고, 집계·합성·폴백·
텔레그램 메시지 구성 로직을 검증한다.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services.youtube import digest_service as ds


# ── 순수 헬퍼 ──────────────────────────────────────────────────────────────────

def test_normalize_category():
    assert ds._normalize_category(None) == ds.UNCATEGORIZED
    assert ds._normalize_category("   ") == ds.UNCATEGORIZED
    assert ds._normalize_category("  경제  ") == "경제"


def test_normalize_sentiment():
    assert ds._normalize_sentiment("BULLISH") == "bullish"
    assert ds._normalize_sentiment("foo") == "unknown"
    assert ds._normalize_sentiment(None) == "unknown"


def test_compute_period_range_clamp():
    end = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
    s, e = ds.compute_period_range(1, end)
    assert (e - s).days == 7
    s, _ = ds.compute_period_range(3, end)
    assert (e - s).days == 21
    s, _ = ds.compute_period_range(99, end)  # clamp -> 8
    assert (e - s).days == 56
    s, _ = ds.compute_period_range(0, end)  # clamp -> 1
    assert (e - s).days == 7


def test_sentiment_summary_and_dominant():
    bd = {"bullish": 3, "neutral": 1, "unknown": 2}
    assert ds._sentiment_summary_text(bd) == "긍정 3, 중립 1, 미상 2"
    # unknown은 우세 감성에서 제외
    assert ds._dominant_sentiment(bd) == "긍정"
    assert ds._dominant_sentiment({"unknown": 5}) is None
    assert ds._sentiment_summary_text({}) == "없음"


def test_parse_json_loose():
    assert ds._parse_json_loose('```json\n{"a": 1}\n```') == {"a": 1}
    assert ds._parse_json_loose('앞 텍스트 {"a": 2} 뒤 텍스트') == {"a": 2}
    assert ds._parse_json_loose("그냥 텍스트") is None
    assert ds._parse_json_loose("") is None


def test_usage_from_raw():
    ti, to, cost = ds._usage_from_raw(
        {"usage": {"prompt_tokens": 100, "completion_tokens": 50, "cost": 0.001}}
    )
    assert (ti, to, cost) == (100, 50, 0.001)
    ti, to, cost = ds._usage_from_raw({})
    assert ti is None and to is None and cost is None


# ── 집계용 가짜 세션 ────────────────────────────────────────────────────────────

class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    """execute() 호출 순서대로 큐에 쌓인 결과를 반환하는 async 세션 mock."""

    def __init__(self, results):
        self._results = list(results)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, *_a, **_k):
        return self._results.pop(0)


def _video_row(pk, category, sentiment, channel="채널A", source=None):
    return SimpleNamespace(
        video_pk=pk,
        title=f"제목{pk}",
        video_url=f"https://youtu.be/{pk}",
        published_at=datetime(2026, 5, 25, tzinfo=timezone.utc),
        view_count=100,
        source_channel_name=source,
        channel_name=channel,
        category=category,
        headline=f"헤드{pk}",
        one_line=f"한줄{pk}",
        bullet_points=[f"불릿{pk}"],
        sentiment=sentiment,
        insights=[f"인사이트{pk}"],
        entities=[{"type": "ticker", "name": f"종목{pk}"}],
    )


def _tag_row(pk, name, weight):
    return SimpleNamespace(video_pk=pk, name=name, weight=weight)


@pytest.fixture
def patched_aggregate_session():
    """aggregate_period 의 두 쿼리(영상, 태그)에 대한 결과를 주입."""
    def _make(video_rows, tag_rows):
        return _FakeSession([_FakeResult(video_rows), _FakeResult(tag_rows)])
    return _make


async def test_aggregate_period_single_unified(patched_aggregate_session):
    """카테고리 미지정 시 모든 영상을 단일 통합('전체')으로 묶는다."""
    video_rows = [
        _video_row(1, "경제, 투자", "bullish", channel="이코노미"),
        _video_row(2, "경제", "bearish", channel="이코노미"),
        _video_row(3, None, "neutral", channel="기타"),  # 미분류
    ]
    tag_rows = [
        _tag_row(1, "연준", 0.9),
        _tag_row(2, "연준", 0.5),
        _tag_row(2, "금리", 0.8),
        _tag_row(3, "잡담", 0.3),
    ]
    sess = patched_aggregate_session(video_rows, tag_rows)
    start = datetime(2026, 5, 23, tzinfo=timezone.utc)
    end = datetime(2026, 5, 30, tzinfo=timezone.utc)

    agg = await ds.aggregate_period(sess, start, end)

    assert agg is not None
    assert agg.category == "전체"
    assert agg.video_count == 3  # 카테고리 구분 없이 전부
    assert agg.sentiment_breakdown == {"bullish": 1, "bearish": 1, "neutral": 1}
    # 연준(0.9+0.5=1.4)이 금리(0.8)보다 상위
    assert agg.top_tags[0]["name"] == "연준"
    assert agg.top_tags[0]["count"] == 2
    assert agg.top_channels[0] == {"name": "이코노미", "count": 2}
    # 카테고리 토큰 분포: '경제'가 2건(콤마 분리)
    cat_counts = {c["name"]: c["count"] for c in agg.top_categories}
    assert cat_counts["경제"] == 2
    assert cat_counts["투자"] == 1
    assert cat_counts[ds.UNCATEGORIZED] == 1


async def test_aggregate_period_category_filter_comma_token(patched_aggregate_session):
    """카테고리 필터는 콤마 토큰 단위로 매칭한다. '경제,투자' 채널은 '투자' 필터에 포함."""
    video_rows = [
        _video_row(1, "경제, 투자", "bullish"),
        _video_row(2, "마케팅", "neutral"),
    ]
    tag_rows = [_tag_row(1, "연준", 1.0)]
    sess = patched_aggregate_session(video_rows, tag_rows)
    start = datetime(2026, 5, 23, tzinfo=timezone.utc)
    end = datetime(2026, 5, 30, tzinfo=timezone.utc)

    agg = await ds.aggregate_period(sess, start, end, categories=["투자"])
    assert agg is not None
    assert agg.video_count == 1  # video 1만 매칭
    assert agg.category == "투자"


async def test_aggregate_period_empty(patched_aggregate_session):
    sess = patched_aggregate_session([], [])
    start = datetime(2026, 5, 23, tzinfo=timezone.utc)
    end = datetime(2026, 5, 30, tzinfo=timezone.utc)
    agg = await ds.aggregate_period(sess, start, end)
    assert agg is None


async def test_aggregate_period_accepts_channel_and_tag_filters(patched_aggregate_session):
    """channel_pks/tags 필터 인자를 받아 쿼리가 정상 구성·실행되는지(예외 없음) 검증."""
    video_rows = [_video_row(1, "경제", "bullish")]
    tag_rows = [_tag_row(1, "연준", 1.0)]
    sess = patched_aggregate_session(video_rows, tag_rows)
    start = datetime(2026, 5, 23, tzinfo=timezone.utc)
    end = datetime(2026, 5, 30, tzinfo=timezone.utc)
    agg = await ds.aggregate_period(
        sess, start, end, categories=None, channel_pks=[1, 2], tags=["연준", "금리"]
    )
    assert agg is not None and agg.video_count == 1


def test_split_category_tokens():
    assert ds.split_category_tokens("경제, 투자, 재테크") == ["경제", "투자", "재테크"]
    assert ds.split_category_tokens("경제,경제, 투자") == ["경제", "투자"]  # 중복 제거
    assert ds.split_category_tokens(None) == []
    assert ds.split_category_tokens("  ") == []


def test_digest_settings_parses_channel_and_tag_filters():
    from app.services.youtube.settings_manager import DigestSettings
    from app.models.youtube_setting import YoutubeSetting as YS

    def row(k, v, vt="json"):
        r = YS(category="digest", key=k, value=v, value_type=vt)
        r.is_secret = 0
        return r

    rows = [
        row("channel_pks", "[1, 2, 3]"),
        row("tags", '["연준", "금리"]'),
    ]
    d = DigestSettings.from_rows(rows, None)
    assert d.channel_pks == [1, 2, 3]
    assert d.tags == ["연준", "금리"]

    # 빈 배열 → None (전체)
    d2 = DigestSettings.from_rows([row("channel_pks", "[]"), row("tags", "[]")], None)
    assert d2.channel_pks is None and d2.tags is None


# ── 합성 (LLM mock) + 폴백 ─────────────────────────────────────────────────────

def _make_agg(category="경제", n=2):
    videos = [
        ds.VideoBrief(
            video_pk=i,
            channel_name="채널A",
            title=f"제목{i}",
            headline=f"헤드{i}",
            one_line=f"한줄{i}",
            bullet_points=[f"불릿{i}a", f"불릿{i}b", f"불릿{i}c", f"불릿{i}d"],
            sentiment="bullish",
            video_url=f"https://youtu.be/{i}",
            published_at=datetime(2026, 5, 25, tzinfo=timezone.utc),
            view_count=10,
            insights=[f"인사이트{i}-1", f"인사이트{i}-2"],
            entities=[{"type": "ticker", "name": f"종목{i}"}],
        )
        for i in range(n)
    ]
    return ds.CategoryAggregate(
        category=category,
        video_count=n,
        sentiment_breakdown={"bullish": n},
        top_tags=[{"name": "연준", "weight": 1.0, "count": 1}],
        top_channels=[{"name": "채널A", "count": n}],
        videos=videos,
    )


def test_render_template_fallback():
    agg = _make_agg()
    r = ds.render_template_fallback(agg, "2026-05-23 ~ 05-30")
    assert r.used_llm is False
    assert "경제" in r.headline
    assert "AI 합성 미실행" in r.headline  # 폴백임을 명시
    # 4섹션 골격을 갖춰야 함 (한 줄 요약 나열이 아님)
    assert "## 주요 내용" in r.summary_md
    assert "## 관점과 의견" in r.summary_md
    assert "## 핵심 인사이트" in r.summary_md
    assert "## 주목할 종목·이슈" in r.summary_md
    assert "영상 2건" in r.summary_md
    assert r.telegram_summary.startswith("[AI 합성 미실행]")


def test_build_videos_block_bullet_limit():
    agg = _make_agg(n=1)
    block = ds._build_videos_block(agg)
    # 불릿 상한 3 → 4번째(불릿0d)는 제외
    assert "• 불릿0c" in block
    assert "불릿0d" not in block


def test_build_videos_block_includes_insights_and_entities():
    agg = _make_agg(n=1)
    block = ds._build_videos_block(agg)
    assert "인사이트0-1" in block
    assert "종목0" in block
    assert "논조: 긍정" in block  # sentiment 한글 표기


def test_format_entities():
    assert ds._format_entities([{"type": "ticker", "name": "삼성전자"}]) == "삼성전자"
    assert ds._format_entities(["연준", "코스피"]) == "연준, 코스피"
    assert ds._format_entities(None) == ""
    # 상한 6개
    many = [{"name": f"e{i}"} for i in range(10)]
    assert len(ds._format_entities(many).split(", ")) == 6


class _FakeChatResult:
    def __init__(self, content, raw):
        self.content = content
        self.raw = raw


class _FakeLLM:
    def __init__(self, content, raw=None):
        self._content = content
        self._raw = raw or {}

    async def chat(self, model, messages, temperature=None, max_tokens=None):
        return _FakeChatResult(self._content, self._raw)


class _FailLLM:
    async def chat(self, *a, **k):
        raise RuntimeError("boom")


async def test_synthesize_with_llm_success():
    agg = _make_agg()
    llm = _FakeLLM(
        '{"headline":"📈 핵심","summary_md":"## 본문","telegram_summary":"요약"}',
        {"usage": {"prompt_tokens": 120, "completion_tokens": 80, "cost": 0.0012}},
    )
    r = await ds.synthesize_with_llm(
        agg, "P", llm_client=llm, model="m", prompt_template=""
    )
    assert r is not None and r.used_llm is True
    assert r.headline == "📈 핵심"
    assert r.token_input == 120 and r.cost_usd == 0.0012


async def test_synthesize_with_llm_empty_body_returns_none():
    agg = _make_agg()
    llm = _FakeLLM('{"headline":"h","summary_md":"","telegram_summary":"t"}')
    r = await ds.synthesize_with_llm(agg, "P", llm_client=llm, model="m", prompt_template="")
    assert r is None


async def test_generate_category_review_falls_back_on_llm_error():
    agg = _make_agg()
    r = await ds.generate_category_review(agg, "P", llm_client=_FailLLM(), model="m")
    assert r.used_llm is False and r.summary_md


async def test_generate_category_review_no_llm_uses_template():
    agg = _make_agg()
    r = await ds.generate_category_review(agg, "P")  # llm_client 없음
    assert r.used_llm is False and r.summary_md


# ── 텔레그램 메시지 ─────────────────────────────────────────────────────────────

def _record(pk=42, summary="요약 내용", category="경제 & 투자"):
    return {
        "category": category,
        "headline": "📈 금리 <인하> 기대",
        "telegram_summary": summary,
        "period_start": datetime(2026, 5, 23, tzinfo=timezone.utc),
        "period_end": datetime(2026, 5, 30, tzinfo=timezone.utc),
        "video_count": 7,
        "digest_pk": pk,
    }


def test_build_digest_telegram_html_escape_and_link():
    msg = ds._build_digest_telegram_html(_record(), "https://app.example.com/")
    assert "경제 &amp; 투자" in msg
    assert "금리 &lt;인하&gt; 기대" in msg
    assert 'href="https://app.example.com/youtube/digests/42"' in msg
    assert "웹에서 전체 보기" in msg


def test_build_digest_telegram_html_no_link_without_pk_or_baseurl():
    rec = _record()
    rec.pop("digest_pk")
    assert "웹에서 전체 보기" not in ds._build_digest_telegram_html(rec, "https://x")
    assert "웹에서 전체 보기" not in ds._build_digest_telegram_html(_record(), "")


def test_build_digest_telegram_html_truncates():
    rec = _record(summary="가" * 5000)
    msg = ds._build_digest_telegram_html(rec, "https://x")
    assert len(msg) <= ds._DIGEST_TELEGRAM_MAX_LEN
    assert msg.endswith("...")
