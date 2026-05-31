"""
YouTube 주간 리뷰(Weekly Review) 집계 서비스.

지정한 기간(period_weeks 주) 동안 분석 완료(analysis_status='done')된 영상을
카테고리(channels.category)별로 묶어 다음을 집계한다.

- 영상 수
- 감성 분포 (bullish / bearish / neutral / mixed / unknown)
- 상위 태그 (weight 합 기준)
- 상위 채널 (영상 수 기준)
- 영상별 요약 자료 (headline / one_line / bullet_points 등) — W-3 LLM 합성 입력용

이 모듈은 LLM을 호출하지 않는다. 순수 집계만 담당하며, 결과는
W-3(LLM 합성)과 W-4(API 응답)에서 재사용할 수 있도록 직렬화 헬퍼를 제공한다.
"""

from __future__ import annotations

import asyncio
import html
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.youtube_channel import YoutubeChannel
from app.models.youtube_tag import YoutubeTag
from app.models.youtube_video import YoutubeVideo
from app.models.youtube_video_analysis import YoutubeVideoAnalysis
from app.models.youtube_video_tag import YoutubeVideoTag

# 카테고리 미지정(NULL/빈값) 영상을 묶는 기본 그룹명
UNCATEGORIZED = "미분류"

# 집계 상한
TOP_TAGS_LIMIT = 15
TOP_CHANNELS_LIMIT = 10

# 감성 값 정규화 대상 (그 외/누락은 'unknown')
_VALID_SENTIMENTS = ("bullish", "bearish", "neutral", "mixed")


def _normalize_category(raw: Optional[str]) -> str:
    """채널 카테고리를 정규화. NULL/공백은 '미분류'로 묶는다."""
    s = (raw or "").strip()
    return s if s else UNCATEGORIZED


def split_category_tokens(raw: Optional[str]) -> List[str]:
    """채널 category 문자열을 콤마 기준 다중 태그로 분리.

    예: '경제, 투자, 재테크' → ['경제', '투자', '재테크']
    NULL/공백은 빈 리스트. 중복은 입력 순서를 유지하며 제거한다.
    """
    s = (raw or "").strip()
    if not s:
        return []
    seen: set[str] = set()
    out: List[str] = []
    for part in s.split(","):
        t = part.strip()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _normalize_sentiment(raw: Optional[str]) -> str:
    s = (raw or "").strip().lower()
    return s if s in _VALID_SENTIMENTS else "unknown"


def compute_period_range(
    period_weeks: int, end_dt: Optional[datetime] = None
) -> Tuple[datetime, datetime]:
    """집계 기간(UTC) 계산.

    end_dt(기본: 현재 UTC)를 종료 시각으로, 그로부터 period_weeks 주 전을 시작으로 한다.
    period_weeks 는 1~8 범위로 보정한다.
    """
    weeks = int(period_weeks or 1)
    if weeks < 1:
        weeks = 1
    elif weeks > 8:
        weeks = 8

    end = end_dt or datetime.now(timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    start = end - timedelta(weeks=weeks)
    return start, end


@dataclass
class VideoBrief:
    """영상 1건의 요약 자료 (LLM 합성 입력 및 상세 표시용)."""

    video_pk: int
    channel_name: str
    title: str
    headline: Optional[str]
    one_line: Optional[str]
    bullet_points: Optional[Any]
    sentiment: str
    video_url: str
    published_at: Optional[datetime]
    view_count: Optional[int]
    insights: Optional[Any] = None
    entities: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "video_pk": self.video_pk,
            "channel_name": self.channel_name,
            "title": self.title,
            "headline": self.headline,
            "one_line": self.one_line,
            "bullet_points": self.bullet_points,
            "sentiment": self.sentiment,
            "video_url": self.video_url,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "view_count": self.view_count,
            "insights": self.insights,
            "entities": self.entities,
        }


@dataclass
class CategoryAggregate:
    """대상 범위(전체 또는 선택 필터) 1개의 집계 결과.

    그룹핑은 더 이상 카테고리별로 분리하지 않고 단일 통합으로 묶는다.
    `category` 는 이 통합 리뷰의 라벨(예: '전체', 또는 선택 카테고리 요약)이다.
    `top_categories` 는 포함된 영상들의 카테고리 토큰 분포(콤마 분리)다.
    """

    category: str
    video_count: int = 0
    sentiment_breakdown: Dict[str, int] = field(default_factory=dict)
    top_tags: List[Dict[str, Any]] = field(default_factory=list)
    top_channels: List[Dict[str, Any]] = field(default_factory=list)
    top_categories: List[Dict[str, Any]] = field(default_factory=list)
    videos: List[VideoBrief] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "video_count": self.video_count,
            "sentiment_breakdown": self.sentiment_breakdown,
            "top_tags": self.top_tags,
            "top_channels": self.top_channels,
            "top_categories": self.top_categories,
            "videos": [v.to_dict() for v in self.videos],
        }


async def aggregate_period(
    session: AsyncSession,
    period_start: datetime,
    period_end: datetime,
    categories: Optional[List[str]] = None,
    channel_pks: Optional[List[int]] = None,
    tags: Optional[List[str]] = None,
) -> Optional[CategoryAggregate]:
    """기간 내 분석 완료 영상을 **단일 통합**으로 집계한다.

    카테고리별로 분리하지 않고, 대상 범위에 해당하는 모든 영상을 하나의 리뷰로 묶는다.
    대상 필터(카테고리/채널/태그)는 **타입 간 AND, 타입 내 OR**로 결합한다.
    모든 필터가 비어 있으면 기간 내 전체 영상을 대상으로 한다('전체').

    카테고리 매칭은 채널 category 문자열을 콤마로 토큰화하여 비교한다.
    예: 채널 category='경제, 투자' 이고 categories=['투자'] 이면 매칭됨.

    Args:
        session: PostgreSQL AsyncSession
        period_start, period_end: 집계 기간(UTC). published_at 이 [start, end) 범위인 영상.
        categories: 대상 카테고리 토큰 목록. None/빈값이면 카테고리 제한 없음.
        channel_pks: 대상 채널 pk 목록. None/빈값이면 채널 제한 없음.
        tags: 대상 태그 이름 목록. None/빈값이면 태그 제한 없음.

    Returns:
        단일 CategoryAggregate. 영상이 0건이면 None.
    """
    # 대상 카테고리 필터 토큰 집합
    category_filter: Optional[set[str]] = None
    if categories:
        toks = {c.strip() for c in categories if c and c.strip()}
        category_filter = toks or None

    # 통합 리뷰 라벨 결정
    if category_filter:
        review_label = ", ".join(sorted(category_filter))
    else:
        review_label = "전체"

    # ── 1) 영상 + 분석 + 채널 조회 ───────────────────────────────────────────
    stmt = (
        select(
            YoutubeVideo.video_pk,
            YoutubeVideo.title,
            YoutubeVideo.video_url,
            YoutubeVideo.published_at,
            YoutubeVideo.view_count,
            YoutubeVideo.source_channel_name,
            YoutubeChannel.channel_name,
            YoutubeChannel.category,
            YoutubeVideoAnalysis.headline,
            YoutubeVideoAnalysis.one_line,
            YoutubeVideoAnalysis.bullet_points,
            YoutubeVideoAnalysis.sentiment,
            YoutubeVideoAnalysis.insights,
            YoutubeVideoAnalysis.entities,
        )
        .join(YoutubeChannel, YoutubeVideo.channel_pk == YoutubeChannel.channel_pk)
        .outerjoin(
            YoutubeVideoAnalysis,
            YoutubeVideoAnalysis.video_pk == YoutubeVideo.video_pk,
        )
        .where(YoutubeVideo.analysis_status == "done")
        .where(YoutubeVideo.published_at >= period_start)
        .where(YoutubeVideo.published_at < period_end)
    )

    # 채널 필터 (타입 내 OR)
    if channel_pks:
        stmt = stmt.where(YoutubeVideo.channel_pk.in_(list(channel_pks)))

    # 태그 필터 (선택 태그 중 하나라도 달린 영상; 타입 내 OR)
    if tags:
        tag_subq = (
            select(YoutubeVideoTag.video_pk)
            .join(YoutubeTag, YoutubeTag.tag_pk == YoutubeVideoTag.tag_pk)
            .where(YoutubeTag.name.in_(list(tags)))
            .scalar_subquery()
        )
        stmt = stmt.where(YoutubeVideo.video_pk.in_(tag_subq))

    stmt = stmt.order_by(YoutubeVideo.published_at.asc())
    rows = (await session.execute(stmt)).all()

    agg = CategoryAggregate(category=review_label)
    channel_counts: Dict[str, int] = {}
    category_counts: Dict[str, int] = {}
    video_pks: List[int] = []

    for r in rows:
        cat_tokens = split_category_tokens(r.category)
        # 카테고리 필터: 채널 토큰 중 하나라도 선택 집합에 들면 포함 (타입 내 OR)
        if category_filter is not None and not (set(cat_tokens) & category_filter):
            continue

        display_channel = (r.source_channel_name or r.channel_name or "YouTube").strip()
        sentiment = _normalize_sentiment(r.sentiment)

        agg.video_count += 1
        agg.sentiment_breakdown[sentiment] = agg.sentiment_breakdown.get(sentiment, 0) + 1
        channel_counts[display_channel] = channel_counts.get(display_channel, 0) + 1
        for tok in (cat_tokens or [UNCATEGORIZED]):
            category_counts[tok] = category_counts.get(tok, 0) + 1

        agg.videos.append(
            VideoBrief(
                video_pk=int(r.video_pk),
                channel_name=display_channel,
                title=r.title or "",
                headline=r.headline,
                one_line=r.one_line,
                bullet_points=r.bullet_points,
                sentiment=sentiment,
                video_url=r.video_url or "",
                published_at=r.published_at,
                view_count=r.view_count,
                insights=r.insights,
                entities=r.entities,
            )
        )
        video_pks.append(int(r.video_pk))

    if agg.video_count == 0:
        return None

    # ── 2) 상위 태그 집계 (weight 합) ────────────────────────────────────────
    tag_acc: Dict[str, List[float]] = {}
    if video_pks:
        tag_stmt = (
            select(
                YoutubeTag.name,
                YoutubeVideoTag.weight,
            )
            .join(YoutubeTag, YoutubeTag.tag_pk == YoutubeVideoTag.tag_pk)
            .where(YoutubeVideoTag.video_pk.in_(video_pks))
        )
        tag_rows = (await session.execute(tag_stmt)).all()
        for tr in tag_rows:
            name = (tr.name or "").strip()
            if not name:
                continue
            weight = float(tr.weight) if tr.weight is not None else 1.0
            if name in tag_acc:
                tag_acc[name][0] += weight
                tag_acc[name][1] += 1
            else:
                tag_acc[name] = [weight, 1]

    # ── 3) top_tags / top_channels / top_categories 확정 ────────────────────
    tags_sorted = sorted(tag_acc.items(), key=lambda kv: (kv[1][0], kv[1][1]), reverse=True)
    agg.top_tags = [
        {"name": name, "weight": round(w, 4), "count": int(cnt)}
        for name, (w, cnt) in tags_sorted[:TOP_TAGS_LIMIT]
    ]
    agg.top_channels = [
        {"name": name, "count": int(cnt)}
        for name, cnt in sorted(channel_counts.items(), key=lambda kv: kv[1], reverse=True)[:TOP_CHANNELS_LIMIT]
    ]
    agg.top_categories = [
        {"name": name, "count": int(cnt)}
        for name, cnt in sorted(category_counts.items(), key=lambda kv: kv[1], reverse=True)
    ]

    return agg


# ──────────────────────────────────────────────────────────────────────────────
# LLM 합성 리뷰 (W-3)
# ──────────────────────────────────────────────────────────────────────────────

# LLM 입력 크기 상한 (토큰 폭증 방지)
_MAX_VIDEOS_IN_PROMPT = 40
_MAX_BULLETS_PER_VIDEO = 3
_MAX_INSIGHTS_PER_VIDEO = 3
_MAX_ENTITIES_PER_VIDEO = 6

# 감성 라벨 한글 표기 (요약/표시용)
_SENTIMENT_KO = {
    "bullish": "긍정",
    "bearish": "부정",
    "neutral": "중립",
    "mixed": "혼조",
    "unknown": "미상",
}

# 기본 다이제스트 합성 프롬프트. prompts.digest_prompt 가 비어 있을 때 사용한다.
# 사용 가능한 placeholder: {category} {period_label} {video_count}
#                          {sentiment_summary} {top_tags} {videos_block}
DEFAULT_DIGEST_PROMPT: str = """너는 경제·투자 콘텐츠를 종합하는 애널리스트다. 아래는 '{category}' 카테고리에서 {period_label} 동안 분석 완료된 유튜브 영상 {video_count}건의 요약·인사이트 모음이다.

## 집계 정보
- 감성 분포: {sentiment_summary}
- 주요 태그: {top_tags}

## 영상별 자료 (헤드라인 · 한줄요약 · 핵심 주장 · 인사이트 · 등장 종목/지표)
{videos_block}

## 작성 지침
위 영상들을 가로질러 이번 기간의 핵심을 한국어로 '브리핑' 형태로 종합하라. 개별 영상 나열이 아니라, 여러 영상에 걸쳐 반복되는 주장·관점·흐름을 묶어 서술할 것.
- 행위 서술('~을 다뤘다', '~을 분석했다') 금지. 무엇을 주장·전망·결론 내렸는지를 직접 서술.
- 같은 방향의 견해가 여럿이면 '합의된 관점', 견해가 갈리면 '엇갈리는 관점'으로 구분해 대비할 것.
- 인사이트는 시청자가 실제 판단에 쓸 수 있도록 구체적 근거·수치와 함께 정리.
- '~함', '~임' 형태의 개조식. 정치·민감 주제는 사실 위주 중립 표현.

## 출력 형식
반드시 아래 JSON 형식으로만 출력:
{{
  "headline": "이모지 1~2개 포함, 이번 기간 핵심을 한 줄로 (40자 이내)",
  "summary_md": "마크다운 본문. 반드시 다음 4개 섹션(## 제목)을 순서대로 포함: '## 주요 내용'(이번 기간 핵심 주제·이슈), '## 관점과 의견'(합의된 관점 / 엇갈리는 관점 구분), '## 핵심 인사이트'(실행 가능한 판단 근거), '## 주목할 종목·이슈'(등장 종목/지표 중심)",
  "telegram_summary": "텔레그램용 짧은 브리핑 (400자 이내, 마크다운 없이 일반 텍스트). 주요 내용과 핵심 관점 위주."
}}"""


@dataclass
class ReviewResult:
    """카테고리 1개의 합성 리뷰 결과."""

    headline: str
    summary_md: str
    telegram_summary: str
    used_llm: bool
    model_name: Optional[str] = None
    token_input: Optional[int] = None
    token_output: Optional[int] = None
    cost_usd: Optional[float] = None


def _sentiment_summary_text(breakdown: Dict[str, int]) -> str:
    """감성 분포를 '긍정 3, 중립 1' 형태의 한글 문자열로."""
    if not breakdown:
        return "없음"
    parts = []
    for key in ("bullish", "bearish", "neutral", "mixed", "unknown"):
        cnt = breakdown.get(key, 0)
        if cnt:
            parts.append(f"{_SENTIMENT_KO[key]} {cnt}")
    return ", ".join(parts) if parts else "없음"


def _dominant_sentiment(breakdown: Dict[str, int]) -> Optional[str]:
    """가장 많은 감성 라벨(한글). unknown 제외, 모두 unknown이면 None."""
    filtered = {k: v for k, v in breakdown.items() if k != "unknown" and v}
    if not filtered:
        return None
    top = max(filtered.items(), key=lambda kv: kv[1])[0]
    return _SENTIMENT_KO.get(top, top)


def _top_tag_names(agg: "CategoryAggregate", limit: int = 8) -> List[str]:
    return [t["name"] for t in agg.top_tags[:limit] if t.get("name")]


def _format_entities(entities: Optional[Any]) -> str:
    """entities(JSONB, [{"type","name"}] 또는 문자열 리스트)를 'name, name' 문자열로."""
    if not isinstance(entities, list):
        return ""
    names: List[str] = []
    for e in entities:
        if isinstance(e, dict):
            name = str(e.get("name") or "").strip()
        else:
            name = str(e or "").strip()
        if name:
            names.append(name)
        if len(names) >= _MAX_ENTITIES_PER_VIDEO:
            break
    return ", ".join(names)


def _build_videos_block(agg: "CategoryAggregate") -> str:
    """영상별 요약 자료를 LLM 입력용 텍스트 블록으로 구성.

    헤드라인·한줄요약 외에 핵심 주장(bullet), 인사이트, 등장 기업/지표(entities)를
    함께 제공하여 합성 모델이 '관점·의견·인사이트'를 추출할 재료를 확보한다.
    """
    lines: List[str] = []
    videos = agg.videos[:_MAX_VIDEOS_IN_PROMPT]
    for v in videos:
        head = (v.headline or v.one_line or v.title or "").strip()
        lines.append(f"- [{v.channel_name}] {head} (논조: {_SENTIMENT_KO.get(v.sentiment, v.sentiment)})")
        if v.one_line and v.one_line.strip() and v.one_line.strip() != head:
            lines.append(f"  {v.one_line.strip()}")

        bullets = v.bullet_points if isinstance(v.bullet_points, list) else []
        for b in bullets[:_MAX_BULLETS_PER_VIDEO]:
            s = str(b).strip()
            if s:
                lines.append(f"  • {s}")

        insights = v.insights if isinstance(v.insights, list) else []
        for ins in insights[:_MAX_INSIGHTS_PER_VIDEO]:
            s = str(ins).strip()
            if s:
                lines.append(f"  ▶ 인사이트: {s}")

        ent_str = _format_entities(v.entities)
        if ent_str:
            lines.append(f"  · 등장: {ent_str}")

    remaining = len(agg.videos) - len(videos)
    if remaining > 0:
        lines.append(f"... 외 {remaining}건")
    return "\n".join(lines)


def _parse_json_loose(text: str) -> Optional[Dict[str, Any]]:
    """LLM 응답에서 JSON 객체를 관대하게 파싱. 코드펜스/주변 텍스트 허용."""
    if not text:
        return None
    raw = text.strip()
    # ```json ... ``` 코드펜스 제거
    fence = re.search(r"```(?:json)?\s*(.+?)\s*```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    # 첫 '{' ~ 마지막 '}' 구간 재시도
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            obj = json.loads(raw[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None
    return None


def _usage_from_raw(raw: Dict[str, Any]) -> Tuple[Optional[int], Optional[int], Optional[float]]:
    """OpenAI 호환 응답에서 토큰/비용 추출 (best-effort)."""
    usage = (raw or {}).get("usage") or {}
    token_input = usage.get("prompt_tokens")
    token_output = usage.get("completion_tokens")
    cost = (
        usage.get("cost")
        or usage.get("total_cost")
        or ((raw or {}).get("_hidden_params") or {}).get("response_cost")
    )
    try:
        cost = float(cost) if cost is not None else None
    except (TypeError, ValueError):
        cost = None
    return token_input, token_output, cost


def render_template_fallback(agg: "CategoryAggregate", period_label: str) -> ReviewResult:
    """LLM 없이 집계 결과만으로 리뷰 본문을 구성한다 (폴백 경로).

    LLM 합성이 실패하거나 비활성일 때도 리뷰가 비지 않도록 보장한다.
    """
    sentiment_txt = _sentiment_summary_text(agg.sentiment_breakdown)
    tag_names = _top_tag_names(agg, limit=10)
    headline = f"⚠️ [{period_label}] {agg.category} 주간 리뷰 (AI 합성 미실행)"

    # LLM 합성이 안 됐음을 명시하고, 4섹션 골격에 집계 자료를 채운다.
    md_lines: List[str] = [
        "> ⚠️ AI 합성에 실패하여 집계 자료만 표시합니다. "
        "설정 → AI Gateway에서 'Digest 모델'을 게이트웨이가 지원하는 이름으로 지정한 뒤 다시 생성하세요.",
        "",
        "## 주요 내용",
        f"- 대상: {agg.category} · 분석 영상 {agg.video_count}건",
        f"- 감성 분포: {sentiment_txt}",
    ]
    if tag_names:
        md_lines.append(f"- 자주 등장한 주제(태그): {', '.join(tag_names)}")

    md_lines += ["", "## 관점과 의견"]
    dom = _dominant_sentiment(agg.sentiment_breakdown)
    md_lines.append(
        f"- 이번 기간 전반의 논조는 '{dom or '미상'}'이 우세함 (감성 분포: {sentiment_txt})."
    )

    md_lines += ["", "## 핵심 인사이트"]
    # 영상별 인사이트를 모아 상위 일부만 노출 (한 줄 요약 나열 대신)
    collected: List[str] = []
    for v in agg.videos:
        ins = v.insights if isinstance(v.insights, list) else []
        for item in ins:
            s = str(item).strip()
            if s:
                collected.append(s)
            if len(collected) >= 8:
                break
        if len(collected) >= 8:
            break
    if collected:
        md_lines += [f"- {s}" for s in collected]
    else:
        md_lines.append("- (영상 분석에 인사이트 데이터가 없습니다.)")

    md_lines += ["", "## 주목할 종목·이슈"]
    if tag_names:
        md_lines.append(f"- {', '.join(tag_names[:10])}")
    else:
        md_lines.append("- (추출된 종목/이슈 태그가 없습니다.)")

    summary_md = "\n".join(md_lines)

    # 텔레그램 요약 (짧게)
    tg_parts = [f"{agg.category} · 영상 {agg.video_count}건"]
    if dom:
        tg_parts.append(f"주된 논조 {dom}")
    if tag_names:
        tg_parts.append("태그 " + ", ".join(tag_names[:3]))
    telegram_summary = "[AI 합성 미실행] " + " | ".join(tg_parts)

    return ReviewResult(
        headline=headline,
        summary_md=summary_md,
        telegram_summary=telegram_summary,
        used_llm=False,
    )


async def synthesize_with_llm(
    agg: "CategoryAggregate",
    period_label: str,
    *,
    llm_client: Any,
    model: str,
    prompt_template: str,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> Optional[ReviewResult]:
    """LLM으로 카테고리 리뷰를 합성한다. 실패 시 None 반환(폴백 유도)."""
    template = (prompt_template or "").strip() or DEFAULT_DIGEST_PROMPT
    prompt = template.format(
        category=agg.category,
        period_label=period_label,
        video_count=agg.video_count,
        sentiment_summary=_sentiment_summary_text(agg.sentiment_breakdown),
        top_tags=", ".join(_top_tag_names(agg, limit=10)) or "없음",
        videos_block=_build_videos_block(agg),
    )

    try:
        result = await llm_client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as exc:
        print(f"⚠️  주간 리뷰 LLM 합성 실패 (category={agg.category}): {exc}")
        return None

    parsed = _parse_json_loose(result.content)
    if not parsed:
        print(f"⚠️  주간 리뷰 LLM 응답 JSON 파싱 실패 (category={agg.category})")
        return None

    headline = str(parsed.get("headline") or "").strip()
    summary_md = str(parsed.get("summary_md") or "").strip()
    telegram_summary = str(parsed.get("telegram_summary") or "").strip()
    if not summary_md:
        # 필수 본문이 비면 합성 실패로 간주
        return None
    if not headline:
        headline = f"[{period_label}] {agg.category} 주간 리뷰"
    if not telegram_summary:
        telegram_summary = headline

    token_input, token_output, cost = _usage_from_raw(result.raw)
    return ReviewResult(
        headline=headline,
        summary_md=summary_md,
        telegram_summary=telegram_summary,
        used_llm=True,
        model_name=model,
        token_input=token_input,
        token_output=token_output,
        cost_usd=cost,
    )


async def generate_category_review(
    agg: "CategoryAggregate",
    period_label: str,
    *,
    llm_client: Any = None,
    model: Optional[str] = None,
    prompt_template: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> ReviewResult:
    """카테고리 리뷰 생성 오케스트레이션.

    llm_client 와 model 이 주어지면 LLM 합성을 시도하고, 실패하면 집계 템플릿으로
    폴백한다. llm_client 가 없으면 곧바로 템플릿 폴백을 사용한다.
    어떤 경우에도 ReviewResult 를 반환한다(리뷰가 비지 않도록 보장).
    """
    if llm_client and model:
        result = await synthesize_with_llm(
            agg,
            period_label,
            llm_client=llm_client,
            model=model,
            prompt_template=prompt_template or "",
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if result is not None:
            return result
    return render_template_fallback(agg, period_label)


# ──────────────────────────────────────────────────────────────────────────────
# 생성 오케스트레이션 (W-4 API · W-5 스케줄러 공용)
# ──────────────────────────────────────────────────────────────────────────────

def _period_label(period_start: datetime, period_end: datetime) -> str:
    """KST 기준 'YYYY-MM-DD ~ MM-DD' 라벨."""
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("Asia/Seoul")
        s = period_start.astimezone(tz)
        e = period_end.astimezone(tz)
        return f"{s.strftime('%Y-%m-%d')} ~ {e.strftime('%m-%d')}"
    except Exception:
        return f"{period_start.date()} ~ {period_end.date()}"


def _review_to_record(
    agg: "CategoryAggregate",
    review: "ReviewResult",
    period_start: datetime,
    period_end: datetime,
    period_weeks: int,
) -> Dict[str, Any]:
    """집계 + 합성 결과를 digests 행/응답에 쓸 dict로 변환."""
    return {
        "period_type": "weekly",
        "period_weeks": int(period_weeks),
        "period_start": period_start,
        "period_end": period_end,
        "category": agg.category,
        "video_count": agg.video_count,
        "headline": review.headline,
        "summary_md": review.summary_md,
        "telegram_summary": review.telegram_summary,
        "sentiment_breakdown": agg.sentiment_breakdown,
        "top_tags": agg.top_tags,
        "top_channels": agg.top_channels,
        "model_name": review.model_name,
        "token_input": review.token_input,
        "token_output": review.token_output,
        "cost_usd": review.cost_usd,
        # LLM 합성 성공 시 'done', 폴백(집계만)이면 'fallback' 으로 구분 표시
        "status": "done" if review.used_llm else "fallback",
        "error": None if review.used_llm else "AI 합성 미실행 (집계 폴백)",
    }


async def generate_digests(
    session_factory: Any,
    *,
    period_weeks: int,
    categories: Optional[List[str]] = None,
    channel_pks: Optional[List[int]] = None,
    tags: Optional[List[str]] = None,
    save: bool = True,
    end_dt: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """기간 집계 → 카테고리별 리뷰 합성 → (옵션) DB 저장.

    W-4 수동 생성 API와 W-5 스케줄러 잡이 공통으로 사용한다.

    Args:
        session_factory: PostgreSQL async_sessionmaker
        period_weeks: 리뷰 기간(주)
        categories: 대상 카테고리(None=전체)
        channel_pks: 대상 채널 pk 목록(None=전체)
        tags: 대상 태그 이름 목록(None=전체)
        save: True 면 youtube.digests 에 저장, False 면 미리보기(저장 안 함)
        end_dt: 기간 종료 시각(기본 현재 UTC)

    Returns:
        DigestDetailResponse 형태의 dict 목록. 저장 시 digest_pk/created_at 포함.
        대상 영상이 없으면 빈 리스트.
    """
    from app.models.youtube_digest import YoutubeDigest
    from app.services.youtube.settings_manager import get_youtube_settings_manager

    mgr = get_youtube_settings_manager()
    ai_cfg = mgr.get_ai_gateway()
    prompts = mgr.get_prompts()

    period_start, period_end = compute_period_range(period_weeks, end_dt)
    label = _period_label(period_start, period_end)

    async with session_factory() as sess:
        agg = await aggregate_period(
            sess, period_start, period_end, categories, channel_pks, tags
        )

    if agg is None:
        return []

    # 합성용 LLM 클라이언트 — chat completions(/v1/chat/completions) 전용 경로.
    # 기존 영상 분석(Path A)은 Gemini 네이티브 API를 직접 호출하므로 모델명 형식이 달라도 무관하지만,
    # 주간 리뷰는 OpenAI 호환 엔드포인트를 사용하므로 게이트웨이에 등록된 이름을 써야 한다.
    # 우선순위: digest_model > fallback_model > tagging_model
    llm_client = None
    model = (
        ai_cfg.digest_model or ai_cfg.fallback_model or ai_cfg.tagging_model or ""
    ).strip() or None
    if (ai_cfg.api_key or "").strip() and model:
        try:
            from app.services.youtube.llm_client import get_litellm_client

            llm_client = get_litellm_client(settings=ai_cfg)
        except Exception as exc:
            print(f"⚠️  주간 리뷰: LLM 클라이언트 생성 실패 — 템플릿 폴백 사용: {exc}")
            llm_client = None

    records: List[Dict[str, Any]] = []
    try:
        review = await generate_category_review(
            agg,
            label,
            llm_client=llm_client,
            model=model,
            prompt_template=prompts.digest_prompt,
            temperature=ai_cfg.temperature,
            max_tokens=ai_cfg.max_tokens,
        )
        records.append(
            _review_to_record(agg, review, period_start, period_end, int(period_weeks))
        )
    finally:
        if llm_client is not None:
            try:
                await llm_client.aclose()
            except Exception:
                pass

    if not save:
        return records

    # ── DB 저장 ──────────────────────────────────────────────────────────────
    saved: List[Dict[str, Any]] = []
    async with session_factory() as sess:
        async with sess.begin():
            for rec in records:
                row = YoutubeDigest(**rec)
                sess.add(row)
                await sess.flush()
                out = dict(rec)
                out["digest_pk"] = int(row.digest_pk)
                out["created_at"] = row.created_at
                saved.append(out)
    return saved


# ──────────────────────────────────────────────────────────────────────────────
# 스케줄러 잡 (W-5): 주간 리뷰 자동 생성
# ──────────────────────────────────────────────────────────────────────────────

def _app_log_digest(status: str, message: str) -> None:
    """SQLite 앱 로그(`logs` 테이블)에 다이제스트 회차 결과 기록."""
    try:
        from app.database import SessionLocal
        from app.crud import create_log

        db = SessionLocal()
        try:
            create_log(db, "youtube_digest", status, message[:500])
        finally:
            db.close()
    except Exception as exc:
        print(f"⚠️  Youtube 다이제스트 앱 로그 기록 실패: {exc}")


_DIGEST_TELEGRAM_MAX_LEN = 4096
_DIGEST_SEND_WAIT_SEC = 2  # 카테고리 간 발송 대기 (rate limit 회피)


def _build_digest_telegram_html(record: Dict[str, Any], base_url: str) -> str:
    """다이제스트 1건을 Telegram HTML 메시지로 구성 (요약 + 웹 링크)."""
    cat = html.escape(record.get("category") or "전체")
    headline = html.escape(record.get("headline") or "")
    summary = html.escape(record.get("telegram_summary") or "")
    label = _period_label(record["period_start"], record["period_end"])
    video_count = int(record.get("video_count") or 0)

    lines: List[str] = [f"<b>📊 [{cat}] 주간 리뷰</b>", ""]
    if headline:
        lines += [f"<b>{headline}</b>", ""]
    if summary:
        lines += [summary, ""]
    lines.append(f"🗓 {label}  ·  영상 {video_count}건")

    pk = record.get("digest_pk")
    if pk and base_url:
        link = f"{base_url.rstrip('/')}/youtube/digests/{pk}"
        lines.append(f'🔗 <a href="{html.escape(link, quote=True)}">웹에서 전체 보기</a>')

    text = "\n".join(lines)
    if len(text) > _DIGEST_TELEGRAM_MAX_LEN:
        text = text[: _DIGEST_TELEGRAM_MAX_LEN - 3] + "..."
    return text


async def _send_digest_telegram(records: List[Dict[str, Any]]) -> int:
    """저장된 다이제스트 레코드들을 Telegram으로 요약 발송. 발송 건수 반환."""
    from app.database import SessionLocal
    from app.crud import get_or_create_user
    from app.services.notification.telegram_sender import telegram_sender
    from app.config import settings as app_settings

    db = SessionLocal()
    try:
        user = get_or_create_user(db)
    finally:
        db.close()

    if not user or not telegram_sender.is_available(user):
        print("⚠️  youtube_weekly_digest: Telegram chat_id 없음 — 발송 skip")
        return 0

    base_url = (app_settings.BASE_URL or "").strip()
    sent = 0
    for i, rec in enumerate(records):
        msg = _build_digest_telegram_html(rec, base_url)
        try:
            ok = await telegram_sender.send_message(user, msg)
            if ok:
                sent += 1
        except Exception as exc:
            print(f"⚠️  youtube_weekly_digest: 발송 실패 (category={rec.get('category')}): {exc}")
        if i < len(records) - 1 and _DIGEST_SEND_WAIT_SEC > 0:
            await asyncio.sleep(_DIGEST_SEND_WAIT_SEC)
    return sent


async def _youtube_weekly_digest_async() -> None:
    """APScheduler 다이제스트 잡의 비동기 구현체.

    digest 설정의 period_weeks/categories 로 기간 집계 후 카테고리별 리뷰를 생성·저장한다.
    텔레그램 발송은 W-6에서 이 함수에 연결한다.
    """
    from app.services.youtube.db_engine import db_engine_manager
    from app.services.youtube.settings_manager import get_youtube_settings_manager

    mgr = get_youtube_settings_manager()
    dcfg = mgr.get_digest()

    if not dcfg.enabled:
        print("ℹ️  youtube_weekly_digest: 다이제스트 비활성 — skip")
        return

    try:
        engine = await db_engine_manager.get_engine()
    except Exception as exc:
        msg = f"youtube_weekly_digest: DB 연결 실패 — {exc}"
        print(f"⚠️  {msg}")
        _app_log_digest("ERROR", msg)
        return

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        records = await generate_digests(
            session_factory,
            period_weeks=dcfg.period_weeks,
            categories=dcfg.categories,
            channel_pks=dcfg.channel_pks,
            tags=dcfg.tags,
            save=True,
        )
        if not records:
            msg = "youtube_weekly_digest: 대상 기간 분석 완료 영상 없음 — 생성 없음"
            print(f"ℹ️  {msg}")
            _app_log_digest("INFO", msg)
            return

        cats = ", ".join(r["category"] for r in records)
        msg = f"주간 리뷰 {len(records)}개 카테고리 생성 완료 ({cats})"
        print(f"✅ youtube_weekly_digest: {msg}")
        _app_log_digest("SUCCESS", msg)

        # 텔레그램 요약 발송 (요약 + 웹 링크)
        if dcfg.telegram_enabled:
            sent = await _send_digest_telegram(records)
            send_msg = f"주간 리뷰 텔레그램 {sent}/{len(records)}건 발송"
            print(f"📤 youtube_weekly_digest: {send_msg}")
            _app_log_digest("SUCCESS" if sent > 0 else "FAIL", send_msg)
        else:
            print("ℹ️  youtube_weekly_digest: 텔레그램 발송 비활성 — 생성만 완료")
    finally:
        await db_engine_manager.dispose_current_loop_engine()


def youtube_weekly_digest_sync() -> None:
    """APScheduler CronTrigger 잡에서 호출되는 동기 래퍼."""
    asyncio.run(_youtube_weekly_digest_async())
