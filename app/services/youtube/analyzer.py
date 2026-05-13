"""
YouTube 영상 분석 파이프라인.

명세 docs/youtube_monitor_spec.md 4.3 기준:
  [1] AI Gateway 설정 로딩
  [2] 경로 A: Gemini native passthrough (primary_model, fileData)
  [3] 경로 B: fallback_model로 OpenAI 호환 엔드포인트 재시도
  [4] 응답 검증 (필수 필드 7종)
  [5] PG 트랜잭션 저장 (video_analysis, tags, videos.status)
  [6] notify 콜백 호출 (YoutubeBot 연결 시 외부에서 주입)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.youtube_video import YoutubeVideo
from app.models.youtube_video_analysis import YoutubeVideoAnalysis
from app.services.youtube.llm_client import LiteLLMClient, LiteLLMError
from app.services.youtube.settings_manager import AIGatewaySettings, get_youtube_settings_manager
from app.services.youtube.tag_extractor import extract_and_save_tags

# ---------- 프롬프트 v2.0 ----------

ANALYSIS_PROMPT_V1: str = """다음 url의 유튜브 영상의 내용을 직접 보지 않아도 이해할 수 있도록 한국어로 상세히 정리해줘.

## 영상 정보
- 채널명: {channel_name}
- 업로드 일시: {published_at_kst}

## 분석 요청 항목
- 한 줄 요약: 이 영상이 전달하려는 핵심 메시지를 한 문장으로 정리할 것.
- 헤드라인: 이모지 1~2개와 핵심 키워드를 포함해 40자 이내로 작성할 것.
- 짧은 요약: 텔레그램 알림용 요약문을 800자 이내로 작성할 것.
- 주요 내용 (Bullet points): 전체 내용을 5~10개의 핵심 포인트로 나누어 자세히 설명할 것. 각 항목은 80자 이내.
- 전체 분석: 마크다운 형식으로 '한 줄 요약 / 주요 내용 / 결론 및 인사이트' 섹션을 포함해 상세히 작성할 것.
- 타임스탬프 포인트: 영상의 핵심 장면을 hh:mm:ss 형식의 타임스탬프와 함께 정리할 것. 60분 초과 영상은 챕터별로 분할.
- 인사이트: 시청자가 얻을 수 있는 유익한 정보나 결론을 3~5개로 정리할 것.
- 등장 인물/기업/지표: 영상에 등장하는 주요 인물, 기업, 티커, 수치를 추출할 것.
- 감성: 영상의 전체 논조를 bullish/bearish/neutral/mixed 중 하나로 판단할 것.
- 태그: 영상 내용을 대표하는 태그를 5~10개 추출할 것. 한국어로 정규화 (예: '미 연준' → '연준').
- 신뢰도: 분석의 완성도를 0.0~1.0 사이의 숫자로 자기 평가할 것.

## 출력 형식
반드시 아래 JSON 형식으로만 출력할 것. 모든 텍스트는 한국어, '~함', '~임' 형태의 개조식으로 작성.
정치적·민감 주제는 사실 위주로 중립 표현.

{{
  "one_line": "string",
  "headline": "string",
  "short_summary_md": "string",
  "bullet_points": ["string"],
  "full_analysis_md": "string",
  "key_points": [{{"timestamp":"hh:mm:ss","point":"string"}}],
  "insights": ["string"],
  "entities": [{{"type":"person|company|ticker|metric","name":"string"}}],
  "sentiment": "bullish|bearish|neutral|mixed",
  "tags": [{{"name":"string","type":"topic|ticker|person|sector","weight":0.0}}],
  "confidence_score": 0.0
}}"""

FALLBACK_PROMPT_V1: str = """다음 유튜브 영상의 내용을 직접 보지 않아도 이해할 수 있도록 한국어로 상세히 정리해줘.

## 영상 정보
- 채널명: {channel_name}
- 업로드 일시: {published_at_kst}
- 영상 URL: {video_url}

## 분석 요청 항목
- 한 줄 요약: 이 영상이 전달하려는 핵심 메시지를 한 문장으로 정리할 것.
- 헤드라인: 이모지 1~2개와 핵심 키워드를 포함해 40자 이내로 작성할 것.
- 짧은 요약: 텔레그램 알림용 요약문을 800자 이내로 작성할 것.
- 주요 내용 (Bullet points): 전체 내용을 5~10개의 핵심 포인트로 나누어 자세히 설명할 것. 각 항목은 80자 이내.
- 전체 분석: 마크다운 형식으로 '한 줄 요약 / 주요 내용 / 결론 및 인사이트' 섹션을 포함해 상세히 작성할 것.
- 타임스탬프 포인트: 영상의 핵심 장면을 hh:mm:ss 형식의 타임스탬프와 함께 정리할 것. 60분 초과 영상은 챕터별로 분할.
- 인사이트: 시청자가 얻을 수 있는 유익한 정보나 결론을 3~5개로 정리할 것.
- 등장 인물/기업/지표: 영상에 등장하는 주요 인물, 기업, 티커, 수치를 추출할 것.
- 감성: 영상의 전체 논조를 bullish/bearish/neutral/mixed 중 하나로 판단할 것.
- 태그: 영상 내용을 대표하는 태그를 5~10개 추출할 것. 한국어로 정규화 (예: '미 연준' → '연준').
- 신뢰도: 분석의 완성도를 0.0~1.0 사이의 숫자로 자기 평가할 것.

## 출력 형식
반드시 아래 JSON 형식으로만 출력할 것. 모든 텍스트는 한국어, '~함', '~임' 형태의 개조식으로 작성.
정치적·민감 주제는 사실 위주로 중립 표현.

{{
  "one_line": "string",
  "headline": "string",
  "short_summary_md": "string",
  "bullet_points": ["string"],
  "full_analysis_md": "string",
  "key_points": [{{"timestamp":"hh:mm:ss","point":"string"}}],
  "insights": ["string"],
  "entities": [{{"type":"person|company|ticker|metric","name":"string"}}],
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

PROMPT_VERSION = "v2.0"


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
        custom_prompt: Optional[str] = None,
    ) -> AnalysisPipelineResult:
        """
        LLM 호출 + 검증 (DB 저장 없음, save_to_db()로 분리).

        경로 A: primary_model로 Gemini native (fileData.fileUri)
        경로 B: fallback_model로 OpenAI 호환 엔드포인트 폴백
        custom_prompt가 주어지면 경로 A·B 모두 해당 프롬프트 사용.
        """
        from app.services.youtube.settings_manager import get_youtube_settings_manager
        pub_kst = _published_at_kst(published_at_str)

        # DB 저장 프롬프트 로딩 (없으면 코드 기본값 사용)
        mgr = get_youtube_settings_manager()
        prompt_cfg = mgr.get_prompts()

        def _render(template: str) -> str:
            return template.format(
                channel_name=channel_name,
                published_at_kst=pub_kst,
                video_url=video_url,
            )

        if custom_prompt:
            base_prompt_a = _render(custom_prompt)
            base_prompt_b = _render(custom_prompt)
        else:
            template_a = prompt_cfg.primary_prompt or ANALYSIS_PROMPT_V1
            template_b = prompt_cfg.fallback_prompt or FALLBACK_PROMPT_V1
            base_prompt_a = _render(template_a)
            base_prompt_b = _render(template_b)

        # --- 경로 A ---
        try:
            result = await self._llm.analyze_video_native(
                model=self._ai.primary_model,
                video_url=video_url,
                prompt=base_prompt_a,
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

        # --- 경로 B: fallback_model로 OpenAI 호환 엔드포인트 재시도 ---
        try:
            chat_result = await self._llm.chat(
                model=self._ai.fallback_model,
                messages=[{"role": "user", "content": base_prompt_b}],
                temperature=self._ai.temperature,
                max_tokens=self._ai.max_tokens,
            )
            raw_text = chat_result.content.strip()
            # JSON 블록이 마크다운 코드펜스로 감싸진 경우 제거
            if raw_text.startswith("```"):
                lines = raw_text.splitlines()
                raw_text = "\n".join(
                    line for line in lines if not line.startswith("```")
                )
            try:
                data = json.loads(raw_text)
            except Exception as parse_err:
                raise LiteLLMError(f"경로 B 응답 JSON 파싱 실패: {parse_err}") from parse_err
            _validate(data)
            return AnalysisPipelineResult(
                data=data,
                route="B",
                model_name=self._ai.fallback_model,
                gateway_url=self._ai.base_url,
                raw_text=raw_text,
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
        """PG 트랜잭션: video_analysis / tags / video_tags / videos.status."""
        data = result.data

        # video_analysis upsert (통합 테이블)
        analysis_stmt = pg_insert(YoutubeVideoAnalysis).values(
            video_pk=video_pk,
            one_line=data.get("one_line", ""),
            headline=data.get("headline"),
            short_summary_md=data.get("short_summary_md", ""),
            bullet_points=data.get("bullet_points"),
            full_analysis_md=data.get("full_analysis_md"),
            full_transcript=None,
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
        analysis_upsert = analysis_stmt.on_conflict_do_update(
            index_elements=["video_pk"],
            set_={
                "one_line": analysis_stmt.excluded.one_line,
                "headline": analysis_stmt.excluded.headline,
                "short_summary_md": analysis_stmt.excluded.short_summary_md,
                "bullet_points": analysis_stmt.excluded.bullet_points,
                "full_analysis_md": analysis_stmt.excluded.full_analysis_md,
                "key_points": analysis_stmt.excluded.key_points,
                "insights": analysis_stmt.excluded.insights,
                "entities": analysis_stmt.excluded.entities,
                "sentiment": analysis_stmt.excluded.sentiment,
                "confidence_score": analysis_stmt.excluded.confidence_score,
                "model_name": analysis_stmt.excluded.model_name,
                "gateway_url": analysis_stmt.excluded.gateway_url,
                "prompt_version": analysis_stmt.excluded.prompt_version,
                "token_input": analysis_stmt.excluded.token_input,
                "token_output": analysis_stmt.excluded.token_output,
                "cost_usd": analysis_stmt.excluded.cost_usd,
                "analyzed_at": analysis_stmt.excluded.analyzed_at,
            },
        )
        await session.execute(analysis_upsert)

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
        custom_prompt: Optional[str] = None,
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
                custom_prompt=custom_prompt,
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
