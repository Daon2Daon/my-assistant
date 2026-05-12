"""
YouTube 모니터 모듈: 태그 추출·정규화·저장.

- LLM 응답의 raw tags 리스트를 정규화하고 PG youtube.tags / youtube.video_tags에 upsert
- 신규 태그가 5개 이상이면 LiteLLMClient 경로 B로 동의어 통합 요청
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.youtube_tag import YoutubeTag
from app.models.youtube_video_tag import YoutubeVideoTag

# 자주 쓰이는 동의어 정규화 규칙 (소문자 매핑)
_ALIAS_MAP: Dict[str, str] = {
    "미 연준": "연준",
    "us fed": "연준",
    "federal reserve": "연준",
    "tsm": "tsmc",
    "s&p": "s&p500",
    "s&p 500": "s&p500",
    "나스닥 100": "나스닥",
    "nasdaq 100": "나스닥",
}

_VALID_TAG_TYPES = {"topic", "ticker", "person", "sector"}


def _normalize_tag_name(name: str) -> str:
    """공백 정리 + 소문자 + alias 치환."""
    normalized = re.sub(r"\s+", " ", (name or "").strip()).lower()
    return _ALIAS_MAP.get(normalized, normalized)


def _normalize_tag_type(t: str | None) -> str:
    return t if t in _VALID_TAG_TYPES else "topic"


async def _fetch_existing_tags(
    session: AsyncSession, names: Sequence[str]
) -> Dict[str, int]:
    """이름 목록에 대응하는 {name: tag_pk} 조회."""
    if not names:
        return {}
    stmt = select(YoutubeTag).where(YoutubeTag.name.in_(names))
    result = await session.execute(stmt)
    return {row.name: row.tag_pk for row in result.scalars().all()}


async def _upsert_tags(
    session: AsyncSession, tags: Sequence[Dict[str, Any]]
) -> Dict[str, int]:
    """
    tags 목록을 youtube.tags에 upsert(ON CONFLICT DO NOTHING) 후 {name: tag_pk} 반환.
    tags 항목 형식: {"name": str, "type": str, "weight": float}
    """
    name_to_pk: Dict[str, int] = {}
    for t in tags:
        raw_name = t.get("name") or ""
        name = _normalize_tag_name(raw_name)
        if not name:
            continue
        tag_type = _normalize_tag_type(t.get("type"))

        await session.execute(
            text(
                """
                INSERT INTO youtube.tags (name, tag_type)
                VALUES (:name, :tag_type)
                ON CONFLICT (name) DO NOTHING
                """
            ),
            {"name": name, "tag_type": tag_type},
        )

    await session.flush()

    all_names = [
        _normalize_tag_name(t.get("name") or "") for t in tags if t.get("name")
    ]
    if all_names:
        name_to_pk = await _fetch_existing_tags(session, all_names)
    return name_to_pk


async def _upsert_video_tags(
    session: AsyncSession,
    video_pk: int,
    name_to_pk: Dict[str, int],
    tags: Sequence[Dict[str, Any]],
) -> None:
    for t in tags:
        name = _normalize_tag_name(t.get("name") or "")
        tag_pk = name_to_pk.get(name)
        if not tag_pk:
            continue
        weight = float(t.get("weight") or 1.0)
        await session.execute(
            text(
                """
                INSERT INTO youtube.video_tags (video_pk, tag_pk, weight)
                VALUES (:video_pk, :tag_pk, :weight)
                ON CONFLICT (video_pk, tag_pk) DO UPDATE SET weight = EXCLUDED.weight
                """
            ),
            {"video_pk": video_pk, "tag_pk": tag_pk, "weight": weight},
        )

    # video_count 재계산: 이 영상의 태그들만 갱신
    updated_tag_pks = [pk for pk in name_to_pk.values() if pk]
    if updated_tag_pks:
        await session.execute(
            text(
                """
                UPDATE youtube.tags t
                SET video_count = (
                    SELECT COUNT(*) FROM youtube.video_tags vt WHERE vt.tag_pk = t.tag_pk
                )
                WHERE t.tag_pk = ANY(:tag_pks)
                """
            ),
            {"tag_pks": updated_tag_pks},
        )


async def _merge_synonyms_with_llm(
    tags: List[Dict[str, Any]],
    llm_client: Any,
    tagging_model: str,
) -> List[Dict[str, Any]]:
    """LLM 경로 B로 동의어 통합. 실패 시 원본 반환."""
    names_str = ", ".join(t.get("name", "") for t in tags)
    prompt = (
        "아래 태그 목록에서 동의어·유사어를 한국어 표준형으로 통합해주세요.\n"
        "반드시 JSON 배열만 반환: "
        '[{"name":"태그명","type":"topic|ticker|person|sector","weight":0.0~1.0}]\n'
        f"태그 목록: {names_str}"
    )
    try:
        result = await llm_client.chat(
            model=tagging_model,
            messages=[{"role": "user", "content": prompt}],
        )
        merged = json.loads(result.content)
        if isinstance(merged, list) and merged:
            return merged
    except Exception as e:
        print(f"⚠️  태그 동의어 통합 LLM 실패 (원본 사용): {e}")
    return tags


async def extract_and_save_tags(
    session: AsyncSession,
    video_pk: int,
    raw_tags: List[Dict[str, Any]],
    llm_client: Optional[Any] = None,
    tagging_model: Optional[str] = None,
    llm_merge_threshold: int = 5,
) -> int:
    """
    raw_tags를 정규화하고 youtube.tags/youtube.video_tags에 저장.

    Returns:
        저장된 video_tags 행 수
    """
    if not raw_tags:
        return 0

    tags = list(raw_tags)

    # 신규 태그 5개 이상이고 LLM 클라이언트가 있을 때 동의어 통합
    if llm_client and tagging_model and len(tags) >= llm_merge_threshold:
        tags = await _merge_synonyms_with_llm(tags, llm_client, tagging_model)

    name_to_pk = await _upsert_tags(session, tags)
    await _upsert_video_tags(session, video_pk, name_to_pk, tags)
    return len(name_to_pk)
