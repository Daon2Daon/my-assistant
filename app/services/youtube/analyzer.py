"""
YouTube 영상 분석 파이프라인.

명세 docs/youtube_monitor_spec.md 4.3 기준:
  [1] AI Gateway 설정 로딩
  [2] 경로 A: Gemini native passthrough (primary_model, fileData)
  [3a] 실패 시 youtube-transcript-api로 자막 추출
  [3b] 경로 B: OpenAI 호환 chat completions (fallback_model)
  [4] 응답 검증 (필수 필드 7종)
  [5] PG 트랜잭션 저장 (video_details, video_summaries, tags, videos.status)
  [6] notify 콜백 호출 (YoutubeBot 연결 시 외부에서 주입)
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.youtube_video import YoutubeVideo
from app.models.youtube_video_detail import YoutubeVideoDetail
from app.models.youtube_video_summary import YoutubeVideoSummary
from app.services.youtube.llm_client import LiteLLMClient, LiteLLMError
from app.services.youtube.settings_manager import AIGatewaySettings, get_youtube_settings_manager
from app.services.youtube.tag_extractor import extract_and_save_tags

# ---------- 프롬프트 v1.0 ----------

ANALYSIS_PROMPT_V1: str = """# 역할
당신은 한국어 콘텐츠를 분석하는 미디어 분석가입니다.

# 입력
- 채널: {channel_name}
- 업로드: {published_at_kst}
- 영상 URL: {video_url}

# 작업
이 영상을 시청자가 직접 보지 않아도 핵심을 파악할 수 있도록 분석하세요.
출력은 다음 JSON Schema를 준수하세요. 모든 텍스트는 한국어, '~함', '~임' 개조식으로 작성.

# JSON Schema
{{
  "one_line": "string (≤100자)",
  "headline": "string (이모지 1~2개 + 핵심 키워드, ≤40자)",
  "short_summary_md": "string (≤800자, Telegram HTML 허용)",
  "bullet_points": ["string 3~5개"],
  "full_analysis_md": "string (마크다운, 섹션: 한 줄 요약/주요 내용/결론 및 인사이트)",
  "key_points": [{{"timestamp":"hh:mm:ss","point":"string"}}],
  "insights": ["string"],
  "entities": [{{"type":"person|company|ticker|metric","name":"string"}}],
  "sentiment": "bullish|bearish|neutral|mixed",
  "tags": [{{"name":"string","type":"topic|ticker|person|sector","weight":0.0}}],
  "confidence_score": 0.0
}}

# 제약
- bullet_points는 각 항목 80자 이내.
- tags는 5~10개, 한국어 정규화 (예: '미 연준' → '연준').
- 영상 길이가 60분 초과면 핵심 챕터별로 key_points 분할.
- 정치적·민감 주제는 사실 위주로 중립 표현."""

FALLBACK_PROMPT_V1: str = """# 역할
당신은 한국어 콘텐츠를 분석하는 미디어 분석가입니다.

# 입력
- 채널: {channel_name}
- 업로드: {published_at_kst}
- 영상 자막(일부):
{transcript}

# 작업
위 자막을 기반으로 영상을 분석해 JSON을 반환하세요.

# JSON Schema
{{
  "one_line": "string (≤100자)",
  "headline": "string (이모지 1~2개 + 핵심 키워드, ≤40자)",
  "short_summary_md": "string (≤800자, Telegram HTML 허용)",
  "bullet_points": ["string 3~5개"],
  "full_analysis_md": "string",
  "key_points": [],
  "insights": ["string"],
  "entities": [],
  "sentiment": "bullish|bearish|neutral|mixed",
  "tags": [{{"name":"string","type":"topic|ticker|person|sector","weight":0.0}}],
  "confidence_score": 0.0
}}"""

REQUIRED_FIELDS = {
    "one_line",
    "headline",
    "short_summary_md",
    "bullet_points",
    "full_analysis_md",
    "sentiment",
    "confidence_score",
}

PROMPT_VERSION = "v1.0"


# ---------- 데이터 클래스 ----------

@dataclass
class AnalysisPipelineResult:
    data: Dict[str, Any]
    route: str          # 'A' or 'B'
    model_name: str
    gateway_url: str
    prompt_version: str = PROMPT_VERSION
    raw_text: str = ""
    token_input: Optional[int] = None
    token_output: Optional[int] = None
    cost_usd: Optional[float] = None


class AnalysisFailedError(RuntimeError):
    """경로 A·B 모두 실패했을 때."""


class AnalysisValidationError(ValueError):
    """응답 검증 실패."""


# ---------- 검증 ----------

def _validate(data: Dict[str, Any]) -> None:
    missing = REQUIRED_FIELDS - set(data.keys())
    if missing:
        raise AnalysisValidationError(f"필수 필드 누락: {missing}")
    sentiment_valid = {"bullish", "bearish", "neutral", "mixed"}
    if data.get("sentiment") not in sentiment_valid:
        raise AnalysisValidationError(
            f"sentiment 값이 잘못됨: {data.get('sentiment')!r}"
        )
    score = data.get("confidence_score")
    if not isinstance(score, (int, float)) or not (0.0 <= float(score) <= 1.0):
        raise AnalysisValidationError(
            f"confidence_score 범위 오류: {score!r}"
        )


# ---------- 자막 추출 (동기 → executor) ----------

def _get_transcript_sync(video_id: str, languages: tuple[str, ...] = ("ko", "en")) -> str:
    """youtube-transcript-api (동기) 호출."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore

        transcripts = YouTubeTranscriptApi.get_transcript(video_id, languages=list(languages))
        return " ".join(t.get("text", "") for t in transcripts)[:20000]
    except Exception as e:
        raise RuntimeError(f"자막 추출 실패: {e}") from e


async def _get_transcript_async(video_id: str) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _get_transcript_sync, video_id)


def _extract_video_id(video_url: str) -> str:
    from urllib.parse import parse_qs, urlparse

    parsed = urlparse(video_url)
    qs = parse_qs(parsed.query)
    if "v" in qs:
        return qs["v"][0]
    # youtu.be/VIDEO_ID
    path = parsed.path.strip("/")
    if path:
        return path
    raise ValueError(f"video_id 추출 실패: {video_url}")


def _published_at_kst(published_at_str: str) -> str:
    try:
        dt = datetime.fromisoformat(published_at_str.replace("Z", "+00:00"))
        from zoneinfo import ZoneInfo

        dt_kst = dt.astimezone(ZoneInfo("Asia/Seoul"))
        return dt_kst.strftime("%Y-%m-%d %H:%M KST")
    except Exception:
        return published_at_str


# ---------- 파이프라인 ----------

class AnalysisPipeline:
    def __init__(
        self,
        llm_client: LiteLLMClient,
        ai_settings: AIGatewaySettings,
        notify_callback: Optional[Callable[[int], Any]] = None,
    ):
        self._llm = llm_client
        self._ai = ai_settings
        self._notify_callback = notify_callback

    async def run(
        self,
        video_pk: int,
        video_url: str,
        channel_name: str,
        published_at_str: str,
    ) -> AnalysisPipelineResult:
        """LLM 호출 + 검증 (DB 저장 없음, save_to_db()로 분리)."""
        pub_kst = _published_at_kst(published_at_str)
        prompt = ANALYSIS_PROMPT_V1.format(
            channel_name=channel_name,
            published_at_kst=pub_kst,
            video_url=video_url,
        )

        # --- 경로 A ---
        try:
            result = await self._llm.analyze_video_native(
                model=self._ai.primary_model,
                video_url=video_url,
                prompt=prompt,
                temperature=self._ai.temperature,
                max_output_tokens=self._ai.max_tokens,
            )
            _validate(result.data)
            return AnalysisPipelineResult(
                data=result.data,
                route="A",
                model_name=self._ai.primary_model,
                gateway_url=self._ai.base_url,
                raw_text=result.raw_text,
            )
        except (LiteLLMError, AnalysisValidationError) as e:
            print(f"⚠️  경로 A 실패 (video_pk={video_pk}): {e}")

        # --- 경로 B fallback ---
        try:
            video_id = _extract_video_id(video_url)
            transcript = await _get_transcript_async(video_id)
        except Exception as e:
            transcript = f"(자막 없음: {e})"

        fallback_prompt = FALLBACK_PROMPT_V1.format(
            channel_name=channel_name,
            published_at_kst=pub_kst,
            transcript=transcript[:15000],
        )
        try:
            chat_result = await self._llm.chat(
                model=self._ai.fallback_model,
                messages=[{"role": "user", "content": fallback_prompt}],
                response_format={"type": "json_object"},
                temperature=self._ai.temperature,
                max_tokens=self._ai.max_tokens,
            )
            data = json.loads(chat_result.content)
            _validate(data)
            return AnalysisPipelineResult(
                data=data,
                route="B",
                model_name=self._ai.fallback_model,
                gateway_url=self._ai.base_url,
                raw_text=chat_result.content,
            )
        except Exception as e:
            raise AnalysisFailedError(
                f"경로 A·B 모두 실패 (video_pk={video_pk}): {e}"
            ) from e

    async def save_to_db(
        self,
        session: AsyncSession,
        video_pk: int,
        result: AnalysisPipelineResult,
    ) -> None:
        """PG 트랜잭션: video_details / video_summaries / tags / video_tags / videos.status."""
        data = result.data

        # video_details upsert
        detail_stmt = pg_insert(YoutubeVideoDetail).values(
            video_pk=video_pk,
            full_transcript=None,
            full_analysis_md=data.get("full_analysis_md", ""),
            key_points=data.get("key_points"),
            insights=data.get("insights"),
            entities=data.get("entities"),
            sentiment=data.get("sentiment"),
            confidence_score=float(data.get("confidence_score") or 0.0),
            model_name=result.model_name,
            gateway_url=result.gateway_url,
            prompt_version=result.prompt_version,
            token_input=result.token_input,
            token_output=result.token_output,
            cost_usd=result.cost_usd,
            analyzed_at=datetime.now(timezone.utc),
        )
        detail_upsert = detail_stmt.on_conflict_do_update(
            index_elements=["video_pk"],
            set_={
                "full_analysis_md": detail_stmt.excluded.full_analysis_md,
                "key_points": detail_stmt.excluded.key_points,
                "insights": detail_stmt.excluded.insights,
                "entities": detail_stmt.excluded.entities,
                "sentiment": detail_stmt.excluded.sentiment,
                "confidence_score": detail_stmt.excluded.confidence_score,
                "model_name": detail_stmt.excluded.model_name,
                "gateway_url": detail_stmt.excluded.gateway_url,
                "prompt_version": detail_stmt.excluded.prompt_version,
                "analyzed_at": detail_stmt.excluded.analyzed_at,
            },
        )
        await session.execute(detail_upsert)

        # video_summaries upsert
        summary_stmt = pg_insert(YoutubeVideoSummary).values(
            video_pk=video_pk,
            one_line=data.get("one_line", ""),
            short_summary_md=data.get("short_summary_md", ""),
            headline=data.get("headline"),
            bullet_points=data.get("bullet_points"),
            cta_text=None,
        )
        summary_upsert = summary_stmt.on_conflict_do_update(
            index_elements=["video_pk"],
            set_={
                "one_line": summary_stmt.excluded.one_line,
                "short_summary_md": summary_stmt.excluded.short_summary_md,
                "headline": summary_stmt.excluded.headline,
                "bullet_points": summary_stmt.excluded.bullet_points,
            },
        )
        await session.execute(summary_upsert)

        # tags
        raw_tags: List[Dict[str, Any]] = data.get("tags") or []
        await extract_and_save_tags(
            session=session,
            video_pk=video_pk,
            raw_tags=raw_tags,
            llm_client=self._llm,
            tagging_model=self._ai.tagging_model,
        )

        # videos 상태 done
        await session.execute(
            update(YoutubeVideo)
            .where(YoutubeVideo.video_pk == video_pk)
            .values(analysis_status="done")
        )

        if self._notify_callback:
            await self._notify_callback(video_pk)

    async def run_and_save(
        self,
        session: AsyncSession,
        video_pk: int,
        video_url: str,
        channel_name: str,
        published_at_str: str,
    ) -> AnalysisPipelineResult:
        """분석 실행 + DB 저장을 하나의 흐름으로 처리. 실패 시 videos.status를 failed로 갱신."""
        # 처리 중 상태로 변경
        await session.execute(
            update(YoutubeVideo)
            .where(YoutubeVideo.video_pk == video_pk)
            .values(analysis_status="processing")
        )
        await session.flush()

        try:
            result = await self.run(
                video_pk=video_pk,
                video_url=video_url,
                channel_name=channel_name,
                published_at_str=published_at_str,
            )
            await self.save_to_db(session=session, video_pk=video_pk, result=result)
            return result
        except AnalysisFailedError:
            await session.execute(
                update(YoutubeVideo)
                .where(YoutubeVideo.video_pk == video_pk)
                .values(
                    analysis_status="failed",
                    analysis_error="경로 A·B 모두 실패",
                )
            )
            raise
        except Exception as e:
            await session.execute(
                update(YoutubeVideo)
                .where(YoutubeVideo.video_pk == video_pk)
                .values(
                    analysis_status="failed",
                    analysis_error=str(e)[:500],
                )
            )
            raise


def build_analysis_pipeline(
    notify_callback: Optional[Callable[[int], Any]] = None,
) -> AnalysisPipeline:
    """앱 기본 SettingsManager + LiteLLMClient로 파이프라인 생성."""
    from app.services.youtube.llm_client import get_litellm_client

    mgr = get_youtube_settings_manager()
    ai_cfg = mgr.get_ai_gateway()
    llm = get_litellm_client(settings=ai_cfg)
    return AnalysisPipeline(
        llm_client=llm,
        ai_settings=ai_cfg,
        notify_callback=notify_callback,
    )
