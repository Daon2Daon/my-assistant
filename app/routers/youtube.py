"""
YouTube 모니터 REST API 라우터.

엔드포인트 구조:
  /api/youtube/channels         채널 CRUD + 즉시 폴링
  /api/youtube/videos           영상 목록/상세/재분석
  /api/youtube/tags             태그 클라우드
  /api/youtube/jobs/logs        잡 로그
  /api/youtube/stats            운영 통계
  /api/youtube/settings/*       설정 조회/수정/테스트
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.schemas.youtube import (
    ChannelCreate,
    ChannelUpdate,
    ChannelResponse,
    JobLogResponse,
    PaginatedJobLogs,
    PaginatedVideos,
    PollTriggerResponse,
    StatsResponse,
    TagResponse,
    VideoDetailResponse,
    VideoResponse,
    VideoSummaryEmbed,
)
from app.schemas.youtube_settings import (
    AIGatewaySettingsResponse,
    AIGatewaySettingsUpdate,
    ConnectionTestResponse,
    DatabaseSettingsResponse,
    DatabaseSettingsUpdate,
    DBHealthResponse,
    GatewayTestAnalyzeResponse,
    ModelInfo,
    ModelsResponse,
    RuntimeSettingsResponse,
    RuntimeSettingsUpdate,
    SchemaApplyResponse,
)
from app.models.youtube_channel import YoutubeChannel
from app.models.youtube_job_log import YoutubeJobLog
from app.models.youtube_tag import YoutubeTag
from app.models.youtube_video import YoutubeVideo
from app.models.youtube_video_detail import YoutubeVideoDetail
from app.models.youtube_video_summary import YoutubeVideoSummary
from app.models.youtube_video_tag import YoutubeVideoTag
from app.services.youtube.settings_manager import get_youtube_settings_manager, mask_secret
from app.models.youtube_setting import YoutubeSetting

router = APIRouter(prefix="/api/youtube", tags=["YouTube"])


# ── PG AsyncSession 의존성 ────────────────────────────────────────────────────

async def get_pg_session() -> AsyncSession:
    """PostgreSQL AsyncSession 주입 — DB 미설정 시 503 반환."""
    from app.services.youtube.db_engine import db_engine_manager, DBNotConfiguredError

    try:
        engine = await db_engine_manager.get_engine()
    except DBNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"PostgreSQL 미설정: {exc}",
        ) from exc
    factory = async_sessionmaker(engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


# ── 내부 유틸 ─────────────────────────────────────────────────────────────────

def _settings_db():
    """SQLite 설정 session."""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _upsert_setting(db, category: str, key: str, value: str, is_secret: bool = False) -> None:
    """settings 테이블에 단일 키-값 upsert."""
    from cryptography.fernet import Fernet
    from app.config import settings as app_settings

    row = (
        db.query(YoutubeSetting)
        .filter(YoutubeSetting.category == category, YoutubeSetting.key == key)
        .first()
    )
    if row is None:
        row = YoutubeSetting(category=category, key=key)
        db.add(row)

    if is_secret:
        fernet_key = app_settings.YOUTUBE_SETTINGS_FERNET_KEY
        if not fernet_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="YOUTUBE_SETTINGS_FERNET_KEY 미설정 — 비밀 값을 저장할 수 없습니다.",
            )
        f = Fernet(fernet_key.strip().encode())
        row.value_enc = f.encrypt(value.encode())
        row.value = None
    else:
        row.value = value

    row.is_secret = 1 if is_secret else 0
    row.updated_at = datetime.now(timezone.utc)
    db.commit()


# ──────────────────────────────────────────────────────────────────────────────
# 채널
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/channels", response_model=List[ChannelResponse])
async def list_channels(
    is_active: Optional[bool] = None,
    session: AsyncSession = Depends(get_pg_session),
):
    """전체 채널 목록 조회."""
    stmt = select(YoutubeChannel).order_by(YoutubeChannel.channel_name)
    if is_active is not None:
        stmt = stmt.where(YoutubeChannel.is_active == is_active)
    result = await session.execute(stmt)
    return result.scalars().all()


@router.post("/channels", response_model=ChannelResponse, status_code=status.HTTP_201_CREATED)
async def add_channel(
    body: ChannelCreate,
    session: AsyncSession = Depends(get_pg_session),
):
    """채널 추가 (resolve_channel → DB 저장 → 선택적 즉시 폴링)."""
    from app.services.youtube.youtube_api import YouTubeAPIClient, YouTubeAPIError

    mgr = get_youtube_settings_manager()
    poll_cfg = mgr.get_polling()

    if not poll_cfg.youtube_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="YouTube API 키가 설정되지 않았습니다.",
        )

    client = YouTubeAPIClient(api_key=poll_cfg.youtube_api_key)
    try:
        channel_id = await client.resolve_channel(body.channel_input)
        meta = await client.get_channel_meta(channel_id)
    except YouTubeAPIError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    existing = await session.execute(
        select(YoutubeChannel).where(YoutubeChannel.channel_id == channel_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"이미 등록된 채널입니다: {channel_id}",
        )

    channel = YoutubeChannel(
        channel_id=channel_id,
        channel_name=meta.get("title", channel_id),
        channel_handle=meta.get("handle"),
        upload_playlist_id=meta.get("upload_playlist_id", ""),
        thumbnail_url=meta.get("thumbnail_url"),
        description=meta.get("description"),
        category=body.category,
        poll_interval_min=body.poll_interval_min,
        notify_enabled=body.notify_enabled,
        is_active=True,
    )
    session.add(channel)
    await session.flush()  # channel_pk 할당

    if body.auto_poll_now:
        asyncio.create_task(_trigger_channel_poll(channel.channel_pk))

    return channel


@router.patch("/channels/{channel_pk}", response_model=ChannelResponse)
async def update_channel(
    channel_pk: int,
    body: ChannelUpdate,
    session: AsyncSession = Depends(get_pg_session),
):
    """채널 부분 수정 (활성 여부, 폴링 주기, 카테고리 등)."""
    channel = await session.get(YoutubeChannel, channel_pk)
    if not channel:
        raise HTTPException(status_code=404, detail="채널을 찾을 수 없습니다.")

    updates = body.model_dump(exclude_none=True)
    if updates:
        updates["updated_at"] = datetime.now(timezone.utc)
        await session.execute(
            update(YoutubeChannel)
            .where(YoutubeChannel.channel_pk == channel_pk)
            .values(**updates)
        )
        await session.refresh(channel)
    return channel


@router.delete("/channels/{channel_pk}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_pk: int,
    session: AsyncSession = Depends(get_pg_session),
):
    """채널 삭제 (CASCADE — videos / details / summaries / tags 연관 데이터 삭제)."""
    channel = await session.get(YoutubeChannel, channel_pk)
    if not channel:
        raise HTTPException(status_code=404, detail="채널을 찾을 수 없습니다.")
    await session.delete(channel)


@router.post(
    "/channels/{channel_pk}/poll",
    response_model=PollTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_channel_poll(
    channel_pk: int,
    session: AsyncSession = Depends(get_pg_session),
):
    """채널 즉시 폴링 트리거 (비동기 백그라운드)."""
    channel = await session.get(YoutubeChannel, channel_pk)
    if not channel:
        raise HTTPException(status_code=404, detail="채널을 찾을 수 없습니다.")

    job_id = str(uuid.uuid4())
    asyncio.create_task(_trigger_channel_poll(channel_pk))
    return PollTriggerResponse(
        job_id=job_id,
        message=f"채널 '{channel.channel_name}' 폴링 요청이 접수되었습니다.",
    )


async def _trigger_channel_poll(channel_pk: int) -> None:
    """백그라운드에서 단일 채널 폴링 실행."""
    from app.services.youtube.monitor_service import MonitorService

    monitor = MonitorService()
    try:
        await monitor.process_channel(channel_pk)
    except Exception as exc:
        print(f"⚠️  즉시 폴링 실패 (channel_pk={channel_pk}): {exc}")


# ──────────────────────────────────────────────────────────────────────────────
# 영상
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/videos", response_model=PaginatedVideos)
async def list_videos(
    channel_pk: Optional[int] = None,
    tag: Optional[str] = None,
    analysis_status: Optional[str] = None,
    since: Optional[datetime] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_pg_session),
):
    """영상 목록 (필터 + 페이지네이션)."""
    stmt = select(YoutubeVideo).order_by(YoutubeVideo.published_at.desc())

    if channel_pk is not None:
        stmt = stmt.where(YoutubeVideo.channel_pk == channel_pk)
    if analysis_status is not None:
        stmt = stmt.where(YoutubeVideo.analysis_status == analysis_status)
    if since is not None:
        stmt = stmt.where(YoutubeVideo.published_at >= since)
    if tag is not None:
        tag_subq = (
            select(YoutubeVideoTag.video_pk)
            .join(YoutubeTag, YoutubeTag.tag_pk == YoutubeVideoTag.tag_pk)
            .where(YoutubeTag.name == tag)
            .scalar_subquery()
        )
        stmt = stmt.where(YoutubeVideo.video_pk.in_(tag_subq))

    total_result = await session.execute(select(func.count()).select_from(stmt.subquery()))
    total = total_result.scalar_one()

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    rows = (await session.execute(stmt)).scalars().all()

    # summary 인라인 조인
    video_pks = [v.video_pk for v in rows]
    summaries: dict[int, YoutubeVideoSummary] = {}
    if video_pks:
        s_result = await session.execute(
            select(YoutubeVideoSummary).where(YoutubeVideoSummary.video_pk.in_(video_pks))
        )
        summaries = {s.video_pk: s for s in s_result.scalars().all()}

    items = []
    for v in rows:
        s = summaries.get(v.video_pk)
        items.append(
            VideoResponse(
                video_pk=v.video_pk,
                channel_pk=v.channel_pk,
                video_id=v.video_id,
                video_url=v.video_url,
                title=v.title,
                thumbnail_url=v.thumbnail_url,
                published_at=v.published_at,
                duration_seconds=v.duration_seconds,
                view_count=v.view_count,
                like_count=v.like_count,
                analysis_status=v.analysis_status,
                notified_at=v.notified_at,
                created_at=v.created_at,
                summary=VideoSummaryEmbed(
                    one_line=s.one_line, headline=s.headline
                ) if s else None,
            )
        )

    return PaginatedVideos(total=total, page=page, page_size=page_size, items=items)


@router.get("/videos/{video_pk}", response_model=VideoDetailResponse)
async def get_video_detail(
    video_pk: int,
    session: AsyncSession = Depends(get_pg_session),
):
    """영상 상세 (detail + summary + tags 포함)."""
    video = await session.get(YoutubeVideo, video_pk)
    if not video:
        raise HTTPException(status_code=404, detail="영상을 찾을 수 없습니다.")

    detail_r = await session.execute(
        select(YoutubeVideoDetail).where(YoutubeVideoDetail.video_pk == video_pk)
    )
    detail = detail_r.scalar_one_or_none()

    summary_r = await session.execute(
        select(YoutubeVideoSummary).where(YoutubeVideoSummary.video_pk == video_pk)
    )
    summary = summary_r.scalar_one_or_none()

    tag_r = await session.execute(
        select(YoutubeTag.name)
        .join(YoutubeVideoTag, YoutubeTag.tag_pk == YoutubeVideoTag.tag_pk)
        .where(YoutubeVideoTag.video_pk == video_pk)
        .order_by(YoutubeVideoTag.weight.desc())
    )
    tags = list(tag_r.scalars().all())

    return VideoDetailResponse(
        video_pk=video.video_pk,
        channel_pk=video.channel_pk,
        video_id=video.video_id,
        video_url=video.video_url,
        title=video.title,
        description=video.description,
        thumbnail_url=video.thumbnail_url,
        published_at=video.published_at,
        duration_seconds=video.duration_seconds,
        view_count=video.view_count,
        like_count=video.like_count,
        sequence_in_channel=video.sequence_in_channel,
        analysis_status=video.analysis_status,
        analysis_error=video.analysis_error,
        retry_count=video.retry_count,
        notified_at=video.notified_at,
        created_at=video.created_at,
        updated_at=video.updated_at,
        one_line=summary.one_line if summary else None,
        headline=summary.headline if summary else None,
        short_summary_md=summary.short_summary_md if summary else None,
        full_analysis_md=detail.full_analysis_md if detail else None,
        bullet_points=summary.bullet_points if summary else None,
        key_points=detail.key_points if detail else None,
        insights=detail.insights if detail else None,
        entities=detail.entities if detail else None,
        sentiment=detail.sentiment if detail else None,
        confidence_score=detail.confidence_score if detail else None,
        model_name=detail.model_name if detail else None,
        analyzed_at=detail.analyzed_at if detail else None,
        tags=tags,
    )


@router.post(
    "/videos/{video_pk}/reanalyze",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=PollTriggerResponse,
)
async def reanalyze_video(
    video_pk: int,
    session: AsyncSession = Depends(get_pg_session),
):
    """영상 재분석 트리거 (status → pending, retry_count 초기화)."""
    video = await session.get(YoutubeVideo, video_pk)
    if not video:
        raise HTTPException(status_code=404, detail="영상을 찾을 수 없습니다.")

    await session.execute(
        update(YoutubeVideo)
        .where(YoutubeVideo.video_pk == video_pk)
        .values(
            analysis_status="pending",
            retry_count=0,
            analysis_error=None,
            updated_at=datetime.now(timezone.utc),
        )
    )

    job_id = str(uuid.uuid4())
    asyncio.create_task(_trigger_reanalyze(video_pk))
    return PollTriggerResponse(
        job_id=job_id,
        message=f"영상 (video_pk={video_pk}) 재분석 요청이 접수되었습니다.",
    )


async def _trigger_reanalyze(video_pk: int) -> None:
    from app.services.youtube.analyzer import build_analysis_pipeline
    from app.services.bots.youtube_bot import notify_video_callback
    from app.services.youtube.db_engine import db_engine_manager

    try:
        engine = await db_engine_manager.get_engine()
        factory = async_sessionmaker(engine, expire_on_commit=False)
        pipeline = build_analysis_pipeline(notify_callback=notify_video_callback)
        async with factory() as sess:
            async with sess.begin():
                await pipeline.run_and_save(session=sess, video_pk=video_pk)
    except Exception as exc:
        print(f"⚠️  재분석 실패 (video_pk={video_pk}): {exc}")


# ──────────────────────────────────────────────────────────────────────────────
# 태그
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/tags", response_model=List[TagResponse])
async def list_tags(
    min_count: int = Query(1, ge=1, description="최소 영상 수"),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_pg_session),
):
    """태그 클라우드 (영상 count 내림차순)."""
    count_col = func.count(YoutubeVideoTag.video_pk).label("video_count")
    stmt = (
        select(YoutubeTag, count_col)
        .join(YoutubeVideoTag, YoutubeTag.tag_pk == YoutubeVideoTag.tag_pk, isouter=True)
        .group_by(YoutubeTag.tag_pk)
        .having(count_col >= min_count)
        .order_by(count_col.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [
        TagResponse(
            tag_pk=tag.tag_pk,
            name=tag.name,
            tag_type=tag.tag_type,
            video_count=cnt or 0,
        )
        for tag, cnt in rows
    ]


# ──────────────────────────────────────────────────────────────────────────────
# 잡 로그
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/jobs/logs", response_model=PaginatedJobLogs)
async def list_job_logs(
    job_type: Optional[str] = None,
    log_status: Optional[str] = Query(None, alias="status"),
    channel_pk: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_pg_session),
):
    """잡 로그 조회 (페이지네이션)."""
    stmt = select(YoutubeJobLog).order_by(YoutubeJobLog.started_at.desc())

    if job_type:
        stmt = stmt.where(YoutubeJobLog.job_type == job_type)
    if log_status:
        stmt = stmt.where(YoutubeJobLog.status == log_status)
    if channel_pk is not None:
        stmt = stmt.where(YoutubeJobLog.channel_pk == channel_pk)

    total_r = await session.execute(select(func.count()).select_from(stmt.subquery()))
    total = total_r.scalar_one()

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    items = (await session.execute(stmt)).scalars().all()

    return PaginatedJobLogs(total=total, page=page, page_size=page_size, items=items)


# ──────────────────────────────────────────────────────────────────────────────
# 통계
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/stats", response_model=StatsResponse)
async def get_stats(session: AsyncSession = Depends(get_pg_session)):
    """운영 통계 집계."""
    ch_total = (await session.execute(select(func.count(YoutubeChannel.channel_pk)))).scalar_one()
    ch_active = (
        await session.execute(
            select(func.count(YoutubeChannel.channel_pk)).where(YoutubeChannel.is_active.is_(True))
        )
    ).scalar_one()

    vid_total = (await session.execute(select(func.count(YoutubeVideo.video_pk)))).scalar_one()
    vid_analyzed = (
        await session.execute(
            select(func.count(YoutubeVideo.video_pk)).where(
                YoutubeVideo.analysis_status == "done"
            )
        )
    ).scalar_one()
    vid_pending = (
        await session.execute(
            select(func.count(YoutubeVideo.video_pk)).where(
                YoutubeVideo.analysis_status == "pending"
            )
        )
    ).scalar_one()
    vid_failed = (
        await session.execute(
            select(func.count(YoutubeVideo.video_pk)).where(
                YoutubeVideo.analysis_status == "failed"
            )
        )
    ).scalar_one()
    vid_notified = (
        await session.execute(
            select(func.count(YoutubeVideo.video_pk)).where(
                YoutubeVideo.notified_at.isnot(None)
            )
        )
    ).scalar_one()

    tag_total = (await session.execute(select(func.count(YoutubeTag.tag_pk)))).scalar_one()

    last_poll_r = await session.execute(
        select(func.max(YoutubeChannel.last_checked_at))
    )
    last_poll = last_poll_r.scalar_one()

    return StatsResponse(
        total_channels=ch_total,
        active_channels=ch_active,
        total_videos=vid_total,
        analyzed_videos=vid_analyzed,
        pending_videos=vid_pending,
        failed_videos=vid_failed,
        notified_videos=vid_notified,
        total_tags=tag_total,
        last_poll_at=last_poll,
    )


# ──────────────────────────────────────────────────────────────────────────────
# 설정 — 데이터베이스
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/settings/database", response_model=DatabaseSettingsResponse)
def get_database_settings():
    """데이터베이스 설정 조회 (password 마스킹)."""
    mgr = get_youtube_settings_manager()
    d = mgr.get_database()
    return DatabaseSettingsResponse(
        host=d.host,
        port=d.port,
        dbname=d.dbname,
        username=d.username,
        password_masked=mask_secret(d.password),
        schema_name=d.schema,
        sslmode=d.sslmode,
        is_configured=d.is_configured,
    )


@router.put("/settings/database", response_model=DatabaseSettingsResponse)
def update_database_settings(body: DatabaseSettingsUpdate, db=Depends(_settings_db)):
    """데이터베이스 설정 수정."""
    field_map = {
        "host": ("host", False),
        "port": ("port", False),
        "dbname": ("dbname", False),
        "username": ("username", False),
        "schema_name": ("schema", False),
        "sslmode": ("sslmode", False),
    }
    data = body.model_dump(exclude_none=True)
    for attr, (key, is_secret) in field_map.items():
        if attr in data:
            _upsert_setting(db, "database", key, str(data[attr]), is_secret)

    if data.get("password"):
        _upsert_setting(db, "database", "password", data["password"], is_secret=True)

    mgr = get_youtube_settings_manager()
    mgr.invalidate("database")
    return get_database_settings()


@router.post("/settings/database/test_connection", response_model=ConnectionTestResponse)
async def test_database_connection():
    """PostgreSQL 연결 테스트."""
    from app.services.youtube.db_engine import db_engine_manager, DBNotConfiguredError

    try:
        t0 = time.monotonic()
        engine = await db_engine_manager.get_engine()
        async with engine.connect() as conn:
            from sqlalchemy import text
            await conn.execute(text("SELECT 1"))
        latency_ms = int((time.monotonic() - t0) * 1000)
        return ConnectionTestResponse(success=True, message="연결 성공", latency_ms=latency_ms)
    except DBNotConfiguredError as exc:
        return ConnectionTestResponse(success=False, message=f"미설정: {exc}")
    except Exception as exc:
        return ConnectionTestResponse(success=False, message=f"연결 실패: {exc}")


@router.post("/settings/database/apply_schema", response_model=SchemaApplyResponse)
async def apply_database_schema():
    """PostgreSQL 스키마 마이그레이션 강제 실행."""
    from app.services.youtube.db_engine import db_engine_manager, DBNotConfiguredError, ensure_schema

    try:
        engine = await db_engine_manager.get_engine()
        await ensure_schema(engine)
        return SchemaApplyResponse(
            success=True,
            message="스키마 마이그레이션 완료",
            migration_version="1",
        )
    except DBNotConfiguredError as exc:
        return SchemaApplyResponse(success=False, message=f"미설정: {exc}")
    except Exception as exc:
        return SchemaApplyResponse(success=False, message=f"마이그레이션 실패: {exc}")


@router.get("/settings/database/health", response_model=DBHealthResponse)
async def database_health():
    """PostgreSQL 연결 상태 확인."""
    from app.services.youtube.db_engine import db_engine_manager, DBNotConfiguredError, EngineHealth

    try:
        health: EngineHealth = await db_engine_manager.health_check()
        return DBHealthResponse(
            healthy=health.ok,
            message=health.message or "정상",
            latency_ms=int(health.latency_ms) if health.latency_ms else None,
        )
    except DBNotConfiguredError as exc:
        return DBHealthResponse(healthy=False, message=f"미설정: {exc}")
    except Exception as exc:
        return DBHealthResponse(healthy=False, message=str(exc))


# ──────────────────────────────────────────────────────────────────────────────
# 설정 — AI Gateway
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/settings/ai_gateway", response_model=AIGatewaySettingsResponse)
def get_ai_gateway_settings():
    """AI Gateway 설정 조회 (api_key 마스킹)."""
    mgr = get_youtube_settings_manager()
    g = mgr.get_ai_gateway()
    return AIGatewaySettingsResponse(
        base_url=g.base_url,
        api_key_masked=mask_secret(g.api_key),
        primary_model=g.primary_model,
        fallback_model=g.fallback_model,
        tagging_model=g.tagging_model,
        temperature=g.temperature,
        max_tokens=g.max_tokens,
        daily_budget_usd=g.daily_budget_usd,
    )


@router.put("/settings/ai_gateway", response_model=AIGatewaySettingsResponse)
def update_ai_gateway_settings(body: AIGatewaySettingsUpdate, db=Depends(_settings_db)):
    """AI Gateway 설정 수정."""
    plain_fields = {
        "base_url": "base_url",
        "primary_model": "primary_model",
        "fallback_model": "fallback_model",
        "tagging_model": "tagging_model",
        "temperature": "temperature",
        "max_tokens": "max_tokens",
        "daily_budget_usd": "daily_budget_usd",
    }
    data = body.model_dump(exclude_none=True)
    for attr, key in plain_fields.items():
        if attr in data:
            _upsert_setting(db, "ai_gateway", key, str(data[attr]), is_secret=False)

    if data.get("api_key"):
        _upsert_setting(db, "ai_gateway", "api_key", data["api_key"], is_secret=True)

    mgr = get_youtube_settings_manager()
    mgr.invalidate("ai_gateway")
    return get_ai_gateway_settings()


@router.post("/settings/ai_gateway/test_connection", response_model=ConnectionTestResponse)
async def test_ai_gateway_connection():
    """AI Gateway 연결 테스트 (모델 목록 조회)."""
    from app.services.youtube.llm_client import LiteLLMClient

    mgr = get_youtube_settings_manager()
    g = mgr.get_ai_gateway()
    client = LiteLLMClient(base_url=g.base_url, api_key=g.api_key)
    try:
        t0 = time.monotonic()
        models = await client.get_models(force_refresh=True)
        latency_ms = int((time.monotonic() - t0) * 1000)
        return ConnectionTestResponse(
            success=True,
            message=f"연결 성공 — 모델 {len(models)}개 확인",
            latency_ms=latency_ms,
        )
    except Exception as exc:
        return ConnectionTestResponse(success=False, message=f"연결 실패: {exc}")


@router.post("/settings/ai_gateway/test_analyze", response_model=GatewayTestAnalyzeResponse)
async def test_ai_gateway_analyze():
    """AI Gateway 텍스트 분석 테스트 (Route B — 샘플 프롬프트)."""
    from app.services.youtube.llm_client import LiteLLMClient

    mgr = get_youtube_settings_manager()
    g = mgr.get_ai_gateway()
    client = LiteLLMClient(base_url=g.base_url, api_key=g.api_key)
    try:
        t0 = time.monotonic()
        result = await client.chat(
            model=g.primary_model,
            messages=[{"role": "user", "content": "Say 'ok' in one word."}],
            max_tokens=10,
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        return GatewayTestAnalyzeResponse(
            success=True,
            message=f"분석 테스트 성공: {result.content[:80]}",
            model_used=g.primary_model,
            latency_ms=latency_ms,
        )
    except Exception as exc:
        return GatewayTestAnalyzeResponse(success=False, message=f"실패: {exc}")


@router.get("/settings/ai_gateway/models", response_model=ModelsResponse)
async def list_ai_gateway_models():
    """AI Gateway에서 사용 가능한 모델 목록 조회."""
    from app.services.youtube.llm_client import LiteLLMClient

    mgr = get_youtube_settings_manager()
    g = mgr.get_ai_gateway()
    client = LiteLLMClient(base_url=g.base_url, api_key=g.api_key)
    try:
        models = await client.get_models()
        return ModelsResponse(
            models=[ModelInfo(model_id=m.get("id", m) if isinstance(m, dict) else str(m))
                    for m in models]
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"모델 목록 조회 실패: {exc}") from exc


# ──────────────────────────────────────────────────────────────────────────────
# 설정 — 런타임 (polling + notification)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/settings/runtime", response_model=RuntimeSettingsResponse)
def get_runtime_settings():
    """런타임 설정 조회 (polling + notification 통합)."""
    mgr = get_youtube_settings_manager()
    p = mgr.get_polling()
    n = mgr.get_notification()
    return RuntimeSettingsResponse(
        master_interval_min=p.master_interval_min,
        default_channel_interval_min=p.default_channel_interval_min,
        youtube_api_key_masked=mask_secret(p.youtube_api_key),
        youtube_daily_quota=p.youtube_daily_quota,
        window_hours=p.window_hours,
        max_concurrent_channels=p.max_concurrent_channels,
        max_concurrent_analyses=p.max_concurrent_analyses,
        telegram_enabled=n.telegram_enabled,
        wait_between_messages_sec=n.wait_between_messages_sec,
        low_confidence_threshold=n.low_confidence_threshold,
    )


@router.put("/settings/runtime", response_model=RuntimeSettingsResponse)
def update_runtime_settings(body: RuntimeSettingsUpdate, db=Depends(_settings_db)):
    """런타임 설정 수정 (polling / notification)."""
    poll_fields = {
        "master_interval_min": ("polling", "master_interval_min", False),
        "default_channel_interval_min": ("polling", "default_channel_interval_min", False),
        "youtube_daily_quota": ("polling", "youtube_daily_quota", False),
        "window_hours": ("polling", "window_hours", False),
        "max_concurrent_channels": ("polling", "max_concurrent_channels", False),
        "max_concurrent_analyses": ("polling", "max_concurrent_analyses", False),
    }
    notif_fields = {
        "telegram_enabled": ("notification", "telegram_enabled", False),
        "wait_between_messages_sec": ("notification", "wait_between_messages_sec", False),
        "low_confidence_threshold": ("notification", "low_confidence_threshold", False),
    }

    data = body.model_dump(exclude_none=True)
    for attr, (cat, key, is_secret) in {**poll_fields, **notif_fields}.items():
        if attr in data:
            _upsert_setting(db, cat, key, str(data[attr]), is_secret)

    if data.get("youtube_api_key"):
        _upsert_setting(db, "polling", "youtube_api_key", data["youtube_api_key"], is_secret=True)

    mgr = get_youtube_settings_manager()
    mgr.invalidate("polling")
    mgr.invalidate("notification")

    # master poll job 주기 갱신
    try:
        from app.services.scheduler import scheduler_service

        scheduler_service.update_youtube_master_poll_job()
    except Exception:
        pass

    return get_runtime_settings()
