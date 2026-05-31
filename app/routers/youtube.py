"""
YouTube 모니터 REST API 라우터.

엔드포인트 구조:
  /api/youtube/channels         채널 CRUD + 즉시 모니터링
  /api/youtube/videos           영상 목록/상세/재분석
  /api/youtube/tags             태그 클라우드
  /api/youtube/jobs/logs        잡 로그
  /api/youtube/stats            운영 통계
  /api/youtube/settings/*       설정 조회/수정/테스트
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

logger = logging.getLogger(__name__)
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.schemas.youtube import (
    ChannelCreate,
    ChannelUpdate,
    ChannelResponse,
    DigestDetailResponse,
    DigestGenerateRequest,
    DigestGenerateResponse,
    DigestListItem,
    InstantAnalyzeRequest,
    InstantAnalyzeResponse,
    JobLogResponse,
    PaginatedDigests,
    PaginatedJobLogs,
    PaginatedVideos,
    PollTriggerResponse,
    StatsResponse,
    TagResponse,
    VideoDetailResponse,
    VideoNotifyRequest,
    VideoNotifyResponse,
    VideoResponse,
    VideoSummaryEmbed,
)
from app.schemas.youtube_settings import (
    AIGatewaySettingsResponse,
    AIGatewaySettingsUpdate,
    AIGatewayTestRequest,
    ConnectionTestResponse,
    DatabaseSettingsResponse,
    DatabaseSettingsUpdate,
    DBHealthResponse,
    DigestSettingsResponse,
    DigestSettingsUpdate,
    GatewayTestAnalyzeResponse,
    ModelInfo,
    ModelsResponse,
    NotificationSettingsResponse,
    NotificationSettingsUpdate,
    PromptSettingsResponse,
    PromptSettingsUpdate,
    RuntimeSettingsResponse,
    RuntimeSettingsUpdate,
    SchemaApplyResponse,
)
from app.models.youtube_channel import YoutubeChannel
from app.models.youtube_deleted_video import YoutubeDeletedVideo
from app.models.youtube_digest import YoutubeDigest
from app.models.youtube_job_log import YoutubeJobLog
from app.models.youtube_tag import YoutubeTag
from app.models.youtube_video import YoutubeVideo
from app.models.youtube_video_analysis import YoutubeVideoAnalysis
from app.models.youtube_video_tag import YoutubeVideoTag
from app.services.youtube.settings_manager import get_youtube_settings_manager, mask_secret
from app.models.youtube_setting import YoutubeSetting

router = APIRouter(prefix="/api/youtube", tags=["YouTube"])

# ── 가상 채널 (즉시/추가 영상 분석 전용) ─────────────────────────────────────────
INSTANT_CHANNEL_ID = "__instant__"
INSTANT_CHANNEL_NAME = "추가 영상"


def _extract_video_id(url: str) -> str | None:
    """YouTube URL에서 video_id 추출. 지원 형식: watch?v=, youtu.be/, /shorts/"""
    from urllib.parse import urlparse, parse_qs

    url = url.strip()
    try:
        p = urlparse(url)
        host = p.netloc.lower().lstrip("www.")
        if host in ("youtube.com",):
            if p.path == "/watch":
                return parse_qs(p.query).get("v", [None])[0]
            if p.path.startswith("/shorts/"):
                return p.path.split("/shorts/")[1].split("?")[0] or None
            if p.path.startswith("/embed/"):
                return p.path.split("/embed/")[1].split("?")[0] or None
        if host == "youtu.be":
            return p.path.lstrip("/").split("?")[0] or None
    except Exception:
        pass
    return None


def _parse_iso_duration(iso: str | None) -> int | None:
    """ISO 8601 duration → 초."""
    if not iso:
        return None
    try:
        import isodate
        return int(isodate.parse_duration(iso).total_seconds())
    except Exception:
        return None


async def ensure_instant_channel(session: AsyncSession) -> YoutubeChannel:
    """가상 채널 레코드가 없으면 생성, 있으면 반환."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    stmt = select(YoutubeChannel).where(YoutubeChannel.channel_id == INSTANT_CHANNEL_ID)
    result = await session.execute(stmt)
    channel = result.scalar_one_or_none()
    if channel:
        return channel

    upsert = (
        pg_insert(YoutubeChannel)
        .values(
            channel_id=INSTANT_CHANNEL_ID,
            channel_name=INSTANT_CHANNEL_NAME,
            upload_playlist_id=INSTANT_CHANNEL_ID,
            is_active=False,
            notify_enabled=False,
            poll_interval_min=99999,
        )
        .on_conflict_do_nothing(index_elements=["channel_id"])
        .returning(YoutubeChannel)
    )
    row = (await session.execute(upsert)).fetchone()
    await session.flush()
    if row:
        return row[0]
    # 동시 요청으로 이미 삽입된 경우 재조회
    result = await session.execute(stmt)
    return result.scalar_one()


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
    """전체 채널 목록 조회 (가상 채널 제외)."""
    stmt = (
        select(YoutubeChannel)
        .where(YoutubeChannel.channel_id != INSTANT_CHANNEL_ID)
        .order_by(YoutubeChannel.channel_name)
    )
    if is_active is not None:
        stmt = stmt.where(YoutubeChannel.is_active == is_active)
    result = await session.execute(stmt)
    return result.scalars().all()


@router.post("/channels", response_model=ChannelResponse, status_code=status.HTTP_201_CREATED)
async def add_channel(
    body: ChannelCreate,
    session: AsyncSession = Depends(get_pg_session),
):
    """채널 추가 (resolve_channel → DB 저장 → 선택적 즉시 모니터링)."""
    from app.services.youtube.youtube_api import YouTubeAPIClient, YouTubeAPIError

    mgr = get_youtube_settings_manager()
    poll_cfg = mgr.get_polling()

    if not poll_cfg.youtube_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="YouTube API 키가 설정되지 않았습니다.",
        )

    client = YouTubeAPIClient(polling=poll_cfg)
    try:
        meta = await client.resolve_channel(body.channel_input)
    except YouTubeAPIError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    existing = await session.execute(
        select(YoutubeChannel).where(YoutubeChannel.channel_id == meta.channel_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"이미 등록된 채널입니다: {meta.channel_id}",
        )

    channel = YoutubeChannel(
        channel_id=meta.channel_id,
        channel_name=meta.channel_name,
        channel_handle=meta.channel_handle,
        upload_playlist_id=meta.upload_playlist_id,
        thumbnail_url=meta.thumbnail_url,
        description=meta.description,
        category=body.category,
        poll_interval_min=body.poll_interval_min,
        notify_enabled=body.notify_enabled,
        is_active=body.is_active,
    )
    session.add(channel)
    await session.flush()  # channel_pk 할당

    if body.auto_poll_now and body.is_active:
        asyncio.create_task(_trigger_channel_poll(channel.channel_pk))

    return channel


@router.patch("/channels/{channel_pk}", response_model=ChannelResponse)
async def update_channel(
    channel_pk: int,
    body: ChannelUpdate,
    session: AsyncSession = Depends(get_pg_session),
):
    """채널 부분 수정 (활성 여부, 모니터링 주기, 카테고리 등)."""
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
    """채널 즉시 모니터링 트리거 (비동기 백그라운드)."""
    channel = await session.get(YoutubeChannel, channel_pk)
    if not channel:
        raise HTTPException(status_code=404, detail="채널을 찾을 수 없습니다.")

    job_id = str(uuid.uuid4())
    asyncio.create_task(_trigger_channel_poll(channel_pk))
    return PollTriggerResponse(
        job_id=job_id,
        message=f"채널 '{channel.channel_name}' 모니터링 요청이 접수되었습니다.",
    )


async def _trigger_channel_poll(channel_pk: int) -> None:
    """백그라운드에서 단일 채널 모니터링 실행 (첫 실행 시 24시간 window 적용)."""
    from app.services.youtube.db_engine import db_engine_manager, DBNotConfiguredError
    from app.services.youtube.monitor_service import MonitorService
    from app.services.youtube.settings_manager import get_youtube_settings_manager
    from app.services.youtube.youtube_api import get_youtube_api_client
    from sqlalchemy.ext.asyncio import async_sessionmaker

    try:
        mgr = get_youtube_settings_manager()
        polling_cfg = mgr.get_polling()
        engine = await db_engine_manager.get_engine()
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        service = MonitorService(polling=polling_cfg)
        api_client = get_youtube_api_client(polling=polling_cfg)

        async with session_factory() as sess:
            async with sess.begin():
                channel = await sess.get(YoutubeChannel, channel_pk)
                if not channel:
                    return
                new_pks = await service.process_channel(
                    channel=channel,
                    session=sess,
                    api_client=api_client,
                )

        await api_client.aclose()

    except DBNotConfiguredError:
        print(f"⚠️  즉시 모니터링 SKIP — PostgreSQL 미설정 (channel_pk={channel_pk})")
    except Exception as exc:
        print(f"⚠️  즉시 모니터링 실패 (channel_pk={channel_pk}): {exc}")


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

    # analysis 인라인 조인 (one_line + headline)
    video_pks = [v.video_pk for v in rows]
    analyses: dict[int, YoutubeVideoAnalysis] = {}
    if video_pks:
        a_result = await session.execute(
            select(YoutubeVideoAnalysis).where(YoutubeVideoAnalysis.video_pk.in_(video_pks))
        )
        analyses = {a.video_pk: a for a in a_result.scalars().all()}

    items = []
    for v in rows:
        a = analyses.get(v.video_pk)
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
                    one_line=a.one_line, headline=a.headline
                ) if a else None,
            )
        )

    return PaginatedVideos(total=total, page=page, page_size=page_size, items=items)


@router.get("/videos/{video_pk}", response_model=VideoDetailResponse)
async def get_video_detail(
    video_pk: int,
    session: AsyncSession = Depends(get_pg_session),
):
    """영상 상세 (analysis + tags 포함)."""
    video = await session.get(YoutubeVideo, video_pk)
    if not video:
        raise HTTPException(status_code=404, detail="영상을 찾을 수 없습니다.")

    analysis_r = await session.execute(
        select(YoutubeVideoAnalysis).where(YoutubeVideoAnalysis.video_pk == video_pk)
    )
    analysis = analysis_r.scalar_one_or_none()

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
        one_line=analysis.one_line if analysis else None,
        headline=analysis.headline if analysis else None,
        short_summary_md=analysis.short_summary_md if analysis else None,
        full_analysis_md=analysis.full_analysis_md if analysis else None,
        bullet_points=analysis.bullet_points if analysis else None,
        key_points=analysis.key_points if analysis else None,
        insights=analysis.insights if analysis else None,
        entities=analysis.entities if analysis else None,
        sentiment=analysis.sentiment if analysis else None,
        confidence_score=analysis.confidence_score if analysis else None,
        model_name=analysis.model_name if analysis else None,
        analyzed_at=analysis.analyzed_at if analysis else None,
        tags=tags,
    )


@router.delete("/videos/{video_pk}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_video(
    video_pk: int,
    session: AsyncSession = Depends(get_pg_session),
):
    """영상 삭제 (CASCADE — analysis / video_tags 연관 데이터 삭제).

    삭제된 video_id는 deleted_videos 테이블에 보관되어 채널 재폴링 시 재추가를 방지합니다.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    video = await session.get(YoutubeVideo, video_pk)
    if not video:
        raise HTTPException(status_code=404, detail="영상을 찾을 수 없습니다.")

    # 블록리스트에 video_id 기록 (이미 존재하면 무시)
    await session.execute(
        pg_insert(YoutubeDeletedVideo)
        .values(video_id=video.video_id)
        .on_conflict_do_nothing(index_elements=["video_id"])
    )

    await session.delete(video)


@router.post(
    "/videos/{video_pk}/notify",
    status_code=status.HTTP_200_OK,
    response_model=VideoNotifyResponse,
)
async def notify_video_manual(
    video_pk: int,
    body: VideoNotifyRequest = VideoNotifyRequest(),
):
    """분석 완료 영상을 Telegram으로 수동 발송.

    - 미발송 영상: 발송 후 notified_at 기록
    - 기발송 영상: force=True 로 재발송 (notified_at 갱신)
    """
    from app.services.youtube.db_engine import db_engine_manager
    from app.services.bots.youtube_bot import youtube_bot
    from app.services.youtube.settings_manager import get_youtube_settings_manager

    mgr = get_youtube_settings_manager()
    notif_cfg = mgr.get_notification()

    if not notif_cfg.telegram_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telegram 알림이 비활성화되어 있습니다. 설정 → 알림에서 활성화해 주세요.",
        )

    try:
        engine = await db_engine_manager.get_engine()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"DB 연결 실패: {exc}",
        ) from exc

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # 영상 존재 및 분석 완료 여부 확인
    async with session_factory() as sess:
        video = await sess.get(YoutubeVideo, video_pk)
        if not video:
            raise HTTPException(status_code=404, detail="영상을 찾을 수 없습니다.")
        if video.analysis_status != "done":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"분석이 완료된 영상만 발송할 수 있습니다. (현재 상태: {video.analysis_status})",
            )
        already_notified = video.notified_at is not None

    ok = await youtube_bot.notify_standalone(
        session_factory=session_factory,
        video_pk=video_pk,
        low_confidence_threshold=float(notif_cfg.low_confidence_threshold or 0.5),
        force=True,  # 수동 발송은 채널 notify_enabled 및 notified_at 설정을 무시
    )

    if not ok:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Telegram 발송에 실패했습니다. Bot 토큰 또는 Chat ID를 확인해 주세요.",
        )

    # 발송 후 갱신된 notified_at 조회
    async with session_factory() as sess:
        video = await sess.get(YoutubeVideo, video_pk)
        notified_at = video.notified_at if video else None

    label = "재발송" if already_notified else "발송"
    return VideoNotifyResponse(
        success=True,
        message=f"Telegram {label} 완료",
        notified_at=notified_at,
    )


class ReanalyzeRequest(BaseModel):
    custom_prompt: Optional[str] = Field(
        None, description="해당 영상 전용 분석 프롬프트. 미입력 시 기본 프롬프트 사용."
    )


@router.post(
    "/videos/{video_pk}/reanalyze",
    status_code=status.HTTP_200_OK,
    response_model=PollTriggerResponse,
)
async def reanalyze_video(
    video_pk: int,
    body: ReanalyzeRequest = ReanalyzeRequest(),
    session: AsyncSession = Depends(get_pg_session),
):
    """영상 재분석 즉시 시작 (status → processing, retry_count 초기화)."""
    video = await session.get(YoutubeVideo, video_pk)
    if not video:
        raise HTTPException(status_code=404, detail="영상을 찾을 수 없습니다.")

    await session.execute(
        update(YoutubeVideo)
        .where(YoutubeVideo.video_pk == video_pk)
        .values(
            analysis_status="processing",
            retry_count=0,
            analysis_error=None,
            updated_at=datetime.now(timezone.utc),
        )
    )

    job_id = str(uuid.uuid4())
    asyncio.create_task(_trigger_reanalyze(video_pk, custom_prompt=body.custom_prompt))
    return PollTriggerResponse(
        job_id=job_id,
        message=f"영상 (video_pk={video_pk}) 재분석을 시작합니다.",
    )


async def _trigger_reanalyze(video_pk: int, custom_prompt: Optional[str] = None) -> None:
    import time
    from app.services.youtube.analyzer import build_analysis_pipeline
    from app.services.bots.youtube_bot import notify_video_callback
    from app.services.youtube.db_engine import db_engine_manager
    from app.services.youtube.job_logger import (
        _JOB_TYPE_VIDEO_REANALYZE,
        _STATUS_FAIL,
        _STATUS_SUCCESS,
        write_job_log,
    )

    start = time.monotonic()

    try:
        engine = await db_engine_manager.get_engine()
        factory = async_sessionmaker(engine, expire_on_commit=False)
        pipeline = build_analysis_pipeline(notify_callback=notify_video_callback)
        channel_pk: Optional[int] = None

        async with factory() as sess:
            async with sess.begin():
                video = await sess.get(YoutubeVideo, video_pk)
                if not video:
                    print(f"⚠️  재분석 대상 영상 없음 (video_pk={video_pk})")
                    return

                channel_pk = video.channel_pk
                ch_result = await sess.execute(
                    select(YoutubeChannel).where(YoutubeChannel.channel_pk == video.channel_pk)
                )
                channel = ch_result.scalar_one_or_none()

                await pipeline.run_and_save(
                    session=sess,
                    video_pk=video_pk,
                    video_url=video.video_url,
                    channel_name=channel.channel_name if channel else "",
                    published_at_str=video.published_at.isoformat(),
                    custom_prompt=custom_prompt,
                )

        elapsed_ms = int((time.monotonic() - start) * 1000)
        await write_job_log(
            factory,
            job_type=_JOB_TYPE_VIDEO_REANALYZE,
            status=_STATUS_SUCCESS,
            message="재분석 완료" + (" (커스텀 프롬프트)" if custom_prompt else ""),
            duration_ms=elapsed_ms,
            channel_pk=channel_pk,
            video_pk=video_pk,
        )

    except Exception as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        print(f"⚠️  재분석 실패 (video_pk={video_pk}): {exc}")
        try:
            engine = await db_engine_manager.get_engine()
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as sess:
                async with sess.begin():
                    await sess.execute(
                        update(YoutubeVideo)
                        .where(YoutubeVideo.video_pk == video_pk)
                        .values(
                            analysis_status="failed",
                            analysis_error=str(exc),
                            updated_at=datetime.now(timezone.utc),
                        )
                    )
            await write_job_log(
                factory,
                job_type=_JOB_TYPE_VIDEO_REANALYZE,
                status=_STATUS_FAIL,
                message=str(exc)[:500],
                duration_ms=elapsed_ms,
                video_pk=video_pk,
            )
        except Exception as update_exc:
            print(f"⚠️  재분석 실패 상태 업데이트 오류 (video_pk={video_pk}): {update_exc}")


@router.post(
    "/instant-analyze",
    status_code=status.HTTP_200_OK,
    response_model=InstantAnalyzeResponse,
)
async def instant_analyze(
    body: InstantAnalyzeRequest,
    session: AsyncSession = Depends(get_pg_session),
):
    """
    YouTube URL을 입력받아 즉시 분석 시작.
    - 이미 DB에 있는 영상이면 기존 video_pk 반환 (existing=True)
    - 없으면 YouTube API로 메타 조회 → 가상 채널 소속으로 INSERT → 분석 시작
    """
    from app.services.youtube.youtube_api import YouTubeAPIClient, YouTubeAPIError

    video_id = _extract_video_id(body.video_url)
    if not video_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="유효한 YouTube URL을 입력해주세요. (watch?v=, youtu.be/, /shorts/ 형식 지원)",
        )

    # 이미 DB에 있는 영상이면 기존 결과 페이지로 이동
    existing_row = (
        await session.execute(
            select(YoutubeVideo).where(YoutubeVideo.video_id == video_id)
        )
    ).scalar_one_or_none()
    if existing_row:
        return InstantAnalyzeResponse(
            video_pk=existing_row.video_pk,
            video_id=existing_row.video_id,
            title=existing_row.title,
            source_channel_name=existing_row.source_channel_name or INSTANT_CHANNEL_NAME,
            analysis_status=existing_row.analysis_status,
            existing=True,
            message="이미 분석된 영상입니다. 기존 결과 페이지로 이동합니다.",
        )

    # YouTube API로 영상 메타데이터 조회
    mgr = get_youtube_settings_manager()
    poll_cfg = mgr.get_polling()
    if not poll_cfg.youtube_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="YouTube API 키가 설정되지 않았습니다.",
        )

    api_client = YouTubeAPIClient(polling=poll_cfg)
    try:
        metas = await api_client.get_video_details([video_id])
    except YouTubeAPIError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    finally:
        await api_client.aclose()

    if not metas:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"YouTube에서 영상을 찾을 수 없습니다. (video_id={video_id})",
        )

    vm = metas[0]

    # 영상의 YouTube channel_id가 DB에 등록된 채널인지 확인
    registered_channel: YoutubeChannel | None = None
    if vm.channel_id:
        ch_result = await session.execute(
            select(YoutubeChannel).where(YoutubeChannel.channel_id == vm.channel_id)
        )
        registered_channel = ch_result.scalar_one_or_none()

    if registered_channel:
        # 등록된 채널 소속으로 저장
        target_channel_pk = registered_channel.channel_pk
        display_channel_name = registered_channel.channel_name
        source_channel_name_val = None  # 등록 채널은 source_channel_name 불필요
    else:
        # 가상 채널 소속으로 저장
        instant_ch = await ensure_instant_channel(session)
        target_channel_pk = instant_ch.channel_pk
        display_channel_name = vm.channel_title or INSTANT_CHANNEL_NAME
        source_channel_name_val = display_channel_name

    # 영상 INSERT
    from datetime import datetime as _dt
    from dateutil import parser as _dp

    try:
        published_at = _dp.parse(vm.published_at)
    except Exception:
        published_at = _dt.now(timezone.utc)

    new_video = YoutubeVideo(
        channel_pk=target_channel_pk,
        video_id=vm.video_id,
        video_url=vm.video_url,
        title=vm.title,
        description=vm.description,
        thumbnail_url=vm.thumbnail_url,
        published_at=published_at,
        duration_seconds=_parse_iso_duration(vm.duration),
        view_count=vm.view_count,
        like_count=vm.like_count,
        source_channel_name=source_channel_name_val,
        analysis_status="processing",
        retry_count=0,
    )
    session.add(new_video)
    await session.flush()  # video_pk 할당

    video_pk = new_video.video_pk

    # 분석 비동기 시작
    asyncio.create_task(
        _trigger_reanalyze(video_pk, custom_prompt=body.custom_prompt)
    )

    return InstantAnalyzeResponse(
        video_pk=video_pk,
        video_id=vm.video_id,
        title=vm.title,
        source_channel_name=display_channel_name,
        analysis_status="processing",
        existing=False,
        message=f"'{vm.title}' 분석을 시작합니다.",
    )


@router.post(
    "/videos/reanalyze-failed",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=PollTriggerResponse,
)
async def reanalyze_failed_videos(
    limit: int = Query(20, ge=1, le=100, description="한 번에 pending으로 되돌릴 최대 영상 수"),
    session: AsyncSession = Depends(get_pg_session),
):
    """failed 상태 영상을 pending으로 되돌린 뒤, 미분석 배치 스케줄 잡이 분석하도록 맡긴다."""
    result = await session.execute(
        select(YoutubeVideo)
        .where(YoutubeVideo.analysis_status == "failed")
        .order_by(YoutubeVideo.updated_at.asc())
        .limit(limit)
    )
    videos = result.scalars().all()

    if not videos:
        return PollTriggerResponse(
            job_id=str(uuid.uuid4()),
            message="재분석 대상 영상이 없습니다 (failed 상태 없음).",
        )

    video_pks = [v.video_pk for v in videos]
    await session.execute(
        update(YoutubeVideo)
        .where(YoutubeVideo.video_pk.in_(video_pks))
        .values(
            analysis_status="pending",
            retry_count=0,
            analysis_error=None,
            updated_at=datetime.now(timezone.utc),
        )
    )

    job_id = str(uuid.uuid4())
    return PollTriggerResponse(
        job_id=job_id,
        message=(
            f"{len(video_pks)}개 영상을 pending으로 되돌렸습니다. "
            "미분석 배치 스케줄 잡이 순차 분석합니다."
        ),
    )


# ──────────────────────────────────────────────────────────────────────────────
# 태그
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/tags", response_model=List[TagResponse])
async def list_tags(
    min_count: int = Query(1, ge=1, description="최소 영상 수"),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_pg_session),
):
    """태그 클라우드 (video_count 내림차순, 사전 집계 컬럼 사용)."""
    stmt = (
        select(YoutubeTag)
        .where(YoutubeTag.video_count >= min_count)
        .order_by(YoutubeTag.video_count.desc())
        .limit(limit)
    )
    tags = (await session.execute(stmt)).scalars().all()
    return [
        TagResponse(
            tag_pk=t.tag_pk,
            name=t.name,
            tag_type=t.tag_type,
            video_count=t.video_count,
        )
        for t in tags
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
# 주간 리뷰 (Weekly Digest)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/digests", response_model=PaginatedDigests)
async def list_digests(
    category: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_pg_session),
):
    """다이제스트 목록 (최신순, 페이지네이션)."""
    stmt = select(YoutubeDigest).order_by(
        YoutubeDigest.period_end.desc(), YoutubeDigest.digest_pk.desc()
    )
    if category is not None:
        stmt = stmt.where(YoutubeDigest.category == category)

    total = (
        await session.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    rows = (await session.execute(stmt)).scalars().all()

    items = [DigestListItem.model_validate(r) for r in rows]
    return PaginatedDigests(total=total, page=page, page_size=page_size, items=items)


@router.get("/digests/{digest_pk}", response_model=DigestDetailResponse)
async def get_digest(
    digest_pk: int,
    session: AsyncSession = Depends(get_pg_session),
):
    """다이제스트 상세."""
    row = await session.get(YoutubeDigest, digest_pk)
    if not row:
        raise HTTPException(status_code=404, detail="다이제스트를 찾을 수 없습니다.")
    return DigestDetailResponse.model_validate(row)


@router.delete("/digests/{digest_pk}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_digest(
    digest_pk: int,
    session: AsyncSession = Depends(get_pg_session),
):
    """다이제스트 삭제."""
    row = await session.get(YoutubeDigest, digest_pk)
    if not row:
        raise HTTPException(status_code=404, detail="다이제스트를 찾을 수 없습니다.")
    await session.delete(row)


@router.post("/digests/generate", response_model=DigestGenerateResponse)
async def generate_digest_manual(body: DigestGenerateRequest = DigestGenerateRequest()):
    """다이제스트 수동 생성/미리보기.

    - save=True: 기간 집계 후 카테고리별 리뷰를 생성하여 저장
    - save=False: 저장하지 않고 미리보기만 반환
    period_weeks·대상 필터(카테고리/채널/태그) 미입력 시 digest 설정값을 사용한다.
    """
    from app.services.youtube.db_engine import db_engine_manager, DBNotConfiguredError
    from app.services.youtube import digest_service

    # 요청값이 없으면 설정값으로 폴백
    digest_cfg = None
    try:
        digest_cfg = get_youtube_settings_manager().get_digest()
    except Exception:
        digest_cfg = None

    period_weeks = body.period_weeks
    if period_weeks is None:
        period_weeks = int(getattr(digest_cfg, "period_weeks", 1) or 1) if digest_cfg else 1

    categories = body.categories if body.categories is not None else getattr(digest_cfg, "categories", None)
    channel_pks = body.channel_pks if body.channel_pks is not None else getattr(digest_cfg, "channel_pks", None)
    tags = body.tags if body.tags is not None else getattr(digest_cfg, "tags", None)

    try:
        engine = await db_engine_manager.get_engine()
    except DBNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"PostgreSQL 미설정: {exc}",
        ) from exc

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        records = await digest_service.generate_digests(
            session_factory,
            period_weeks=int(period_weeks),
            categories=categories,
            channel_pks=channel_pks,
            tags=tags,
            save=body.save,
        )
    except Exception as exc:
        logger.exception("다이제스트 수동 생성 실패")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"다이제스트 생성 실패: {exc}",
        ) from exc

    if not records:
        return DigestGenerateResponse(
            success=True,
            message="대상 기간에 분석 완료된 영상이 없습니다.",
            created_digest_pks=[],
            items=[],
        )

    items = [DigestDetailResponse.model_validate(r) for r in records]
    created_pks = [r["digest_pk"] for r in records if r.get("digest_pk") is not None]
    action = "저장" if body.save else "미리보기"
    return DigestGenerateResponse(
        success=True,
        message=f"{len(items)}개 카테고리 다이제스트 {action} 완료",
        created_digest_pks=created_pks,
        items=items,
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
    """PostgreSQL 연결 테스트 (스키마 생성 없이 접속만 확인)."""
    from app.services.youtube.db_engine import db_engine_manager

    health = await db_engine_manager.test_connection_only()
    return ConnectionTestResponse(
        success=health.ok,
        message=health.message or ("연결 성공" if health.ok else "연결 실패"),
        latency_ms=int(health.latency_ms) if health.latency_ms else None,
    )


@router.post("/settings/database/apply_schema", response_model=SchemaApplyResponse)
async def apply_database_schema():
    """PostgreSQL 스키마 마이그레이션 강제 실행."""
    from app.services.youtube.db_engine import db_engine_manager, DBNotConfiguredError

    try:
        await db_engine_manager.apply_schema()
        return SchemaApplyResponse(
            success=True,
            message="스키마 마이그레이션 완료",
            migration_version="최신",
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
        digest_model=g.digest_model,
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
        "digest_model": "digest_model",
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


def _resolve_test_settings(req: AIGatewayTestRequest | None):
    """
    DB 저장 설정을 베이스로, 요청 바디에 폼값이 있으면 해당 필드만 덮어쓴다.
    저장 전 "연결 테스트"가 폼 현재 값으로 동작하도록 하기 위한 헬퍼.
    """
    from dataclasses import replace as _replace
    from app.services.youtube.settings_manager import AIGatewaySettings

    mgr = get_youtube_settings_manager()
    g: AIGatewaySettings = mgr.get_ai_gateway()

    if req is None:
        return g

    overrides: dict = {}
    if req.base_url and req.base_url.strip():
        overrides["base_url"] = req.base_url.strip()
    if req.api_key and req.api_key.strip():
        overrides["api_key"] = req.api_key.strip()
    if req.primary_model and req.primary_model.strip():
        overrides["primary_model"] = req.primary_model.strip()

    return _replace(g, **overrides) if overrides else g


@router.post("/settings/ai_gateway/test_connection", response_model=ConnectionTestResponse)
async def test_ai_gateway_connection(body: AIGatewayTestRequest | None = None):
    """
    AI Gateway 연결 테스트 (모델 목록 조회).
    요청 바디에 base_url / api_key 를 넘기면 저장 없이 폼값으로 테스트한다.
    """
    from app.services.youtube.llm_client import LiteLLMClient

    g = _resolve_test_settings(body)
    if not (g.api_key or "").strip():
        return ConnectionTestResponse(
            success=False,
            message=(
                "연결 실패: AI Gateway API 키가 비어 있습니다. "
                "API 키를 입력하거나, 저장 후 다시 시도하세요."
            ),
        )
    client = LiteLLMClient(settings=g)
    try:
        t0 = time.monotonic()
        models = await client.get_models(force_refresh=True)
        latency_ms = int((time.monotonic() - t0) * 1000)
        return ConnectionTestResponse(
            success=True,
            message=f"연결 성공 — 모델 {len(models.models)}개 확인",
            latency_ms=latency_ms,
        )
    except Exception as exc:
        logger.warning("AI Gateway 연결 테스트 실패: %s", exc)
        return ConnectionTestResponse(success=False, message=f"연결 실패: {exc}")


@router.post("/settings/ai_gateway/test_analyze", response_model=GatewayTestAnalyzeResponse)
async def test_ai_gateway_analyze(body: AIGatewayTestRequest | None = None):
    """
    AI Gateway 텍스트 분석 테스트 (Route B — 샘플 프롬프트).
    요청 바디에 base_url / api_key / primary_model 을 넘기면 폼값으로 테스트한다.
    """
    from app.services.youtube.llm_client import LiteLLMClient

    g = _resolve_test_settings(body)
    if not (g.api_key or "").strip():
        return GatewayTestAnalyzeResponse(
            success=False,
            message=(
                "실패: AI Gateway API 키가 비어 있습니다. "
                "API 키를 입력하거나, 저장 후 다시 시도하세요."
            ),
        )
    client = LiteLLMClient(settings=g)
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
    client = LiteLLMClient(settings=g)
    try:
        gateway_mr = await client.get_models()
        return ModelsResponse(
            models=[ModelInfo(model_id=mi.id) for mi in gateway_mr.models]
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
        pending_analysis_interval_min=p.pending_analysis_interval_min,
        default_channel_interval_min=p.default_channel_interval_min,
        youtube_api_key_masked=mask_secret(p.youtube_api_key),
        youtube_daily_quota=p.youtube_daily_quota,
        window_hours=p.window_hours,
        max_concurrent_channels=p.max_concurrent_channels,
        max_concurrent_analyses=p.max_concurrent_analyses,
        analysis_interval_sec=p.analysis_interval_sec,
        telegram_enabled=n.telegram_enabled,
        wait_between_messages_sec=n.wait_between_messages_sec,
        low_confidence_threshold=n.low_confidence_threshold,
    )


@router.put("/settings/runtime", response_model=RuntimeSettingsResponse)
def update_runtime_settings(body: RuntimeSettingsUpdate, db=Depends(_settings_db)):
    """런타임 설정 수정 (polling / notification)."""
    poll_fields = {
        "master_interval_min": ("polling", "master_interval_min", False),
        "pending_analysis_interval_min": ("polling", "pending_analysis_interval_min", False),
        "default_channel_interval_min": ("polling", "default_channel_interval_min", False),
        "youtube_daily_quota": ("polling", "youtube_daily_quota", False),
        "window_hours": ("polling", "window_hours", False),
        "max_concurrent_channels": ("polling", "max_concurrent_channels", False),
        "max_concurrent_analyses": ("polling", "max_concurrent_analyses", False),
        "analysis_interval_sec": ("polling", "analysis_interval_sec", False),
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


# ──────────────────────────────────────────────────────────────────────────────
# 설정 — 프롬프트
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/settings/prompts", response_model=PromptSettingsResponse)
def get_prompt_settings():
    """현재 적용 중인 프롬프트 조회. DB 미설정 시 코드 기본값 반환.

    - analysis_prompt: 영상 분석 (경로 A·B 공통, 단일)
    - digest_prompt: 주간 리뷰 합성
    """
    from app.services.youtube.analyzer import ANALYSIS_PROMPT_V1, PROMPT_VERSION
    from app.services.youtube.digest_service import DEFAULT_DIGEST_PROMPT

    mgr = get_youtube_settings_manager()
    p = mgr.get_prompts()
    return PromptSettingsResponse(
        analysis_prompt=p.analysis_prompt or ANALYSIS_PROMPT_V1,
        digest_prompt=p.digest_prompt or DEFAULT_DIGEST_PROMPT,
        prompt_version=PROMPT_VERSION,
    )


@router.put("/settings/prompts", response_model=PromptSettingsResponse)
def update_prompt_settings(body: PromptSettingsUpdate, db=Depends(_settings_db)):
    """프롬프트 수정. 빈 문자열이면 코드 기본값으로 초기화."""
    data = body.model_dump(exclude_none=True)
    if "analysis_prompt" in data:
        _upsert_setting(db, "prompts", "analysis_prompt", data["analysis_prompt"])
    if "digest_prompt" in data:
        _upsert_setting(db, "prompts", "digest_prompt", data["digest_prompt"])
    mgr = get_youtube_settings_manager()
    mgr.invalidate("prompts")
    return get_prompt_settings()


@router.delete("/settings/prompts/reset", response_model=PromptSettingsResponse)
def reset_prompt_settings(db=Depends(_settings_db)):
    """분석 프롬프트를 코드 기본값으로 초기화."""
    from sqlalchemy import text as sa_text

    db.execute(
        sa_text("DELETE FROM youtube_settings WHERE category = 'prompts'")
    )
    db.commit()
    mgr = get_youtube_settings_manager()
    mgr.invalidate("prompts")
    return get_prompt_settings()


# ──────────────────────────────────────────────────────────────────────────────
# 설정 — 알림 발송 (notification)
# ──────────────────────────────────────────────────────────────────────────────

import json as _json


def _notification_response() -> NotificationSettingsResponse:
    mgr = get_youtube_settings_manager()
    n = mgr.get_notification()
    return NotificationSettingsResponse(
        telegram_enabled=n.telegram_enabled,
        send_mode=n.send_mode,
        scheduled_times=n.scheduled_times,
        scheduled_max_per_run=n.scheduled_max_per_run,
        wait_between_messages_sec=n.wait_between_messages_sec,
        low_confidence_threshold=n.low_confidence_threshold,
        quiet_hours_enabled=n.quiet_hours_enabled,
        quiet_hours_start=n.quiet_hours_start,
        quiet_hours_end=n.quiet_hours_end,
    )


@router.get("/settings/notification", response_model=NotificationSettingsResponse)
def get_notification_settings():
    """알림 발송 설정 조회."""
    return _notification_response()


@router.put("/settings/notification", response_model=NotificationSettingsResponse)
def update_notification_settings(body: NotificationSettingsUpdate, db=Depends(_settings_db)):
    """알림 발송 설정 수정.

    - send_mode: 'immediate'(즉시발송) | 'scheduled'(예약발송)
    - scheduled_times: ['HH:MM', ...] 형식의 예약 시각 목록 (최대 10개)
    """
    data = body.model_dump(exclude_none=True)

    simple_fields = {
        "telegram_enabled": "telegram_enabled",
        "send_mode": "send_mode",
        "scheduled_max_per_run": "scheduled_max_per_run",
        "wait_between_messages_sec": "wait_between_messages_sec",
        "low_confidence_threshold": "low_confidence_threshold",
        "quiet_hours_enabled": "quiet_hours_enabled",
        "quiet_hours_start": "quiet_hours_start",
        "quiet_hours_end": "quiet_hours_end",
    }
    for attr, key in simple_fields.items():
        if attr in data:
            _upsert_setting(db, "notification", key, str(data[attr]))

    if "scheduled_times" in data:
        _upsert_setting(
            db, "notification", "scheduled_times",
            _json.dumps(data["scheduled_times"], ensure_ascii=False),
        )

    mgr = get_youtube_settings_manager()
    mgr.invalidate("notification")

    # 예약발송 잡 재구성
    try:
        from app.services.scheduler import scheduler_service

        scheduler_service.update_youtube_notify_jobs()
    except Exception:
        logger.exception("YouTube 예약발송 스케줄 잡 갱신 실패")

    return _notification_response()


# ──────────────────────────────────────────────────────────────────────────────
# 설정 — 주간 리뷰 (digest)
# ──────────────────────────────────────────────────────────────────────────────

def _digest_response() -> DigestSettingsResponse:
    mgr = get_youtube_settings_manager()
    d = mgr.get_digest()
    return DigestSettingsResponse(
        enabled=d.enabled,
        period_weeks=d.period_weeks,
        schedule_times=d.schedule_times,
        telegram_enabled=d.telegram_enabled,
        categories=d.categories,
        channel_pks=d.channel_pks,
        tags=d.tags,
    )


@router.get("/settings/digest", response_model=DigestSettingsResponse)
def get_digest_settings():
    """주간 리뷰(다이제스트) 설정 조회."""
    return _digest_response()


@router.put("/settings/digest", response_model=DigestSettingsResponse)
def update_digest_settings(body: DigestSettingsUpdate, db=Depends(_settings_db)):
    """주간 리뷰 설정 수정.

    - period_weeks: 리뷰 기간(주), 1~8
    - schedule_times: [{"day_of_week":"sun","time":"20:00"}, ...] (KST)
    - categories/channel_pks/tags: 대상 필터 (미입력/빈 목록 = 전체)
    저장 후 다이제스트 스케줄 잡을 재등록한다.
    """
    data = body.model_dump(exclude_none=True)

    simple_fields = {
        "enabled": "enabled",
        "period_weeks": "period_weeks",
        "telegram_enabled": "telegram_enabled",
    }
    for attr, key in simple_fields.items():
        if attr in data:
            _upsert_setting(db, "digest", key, str(data[attr]))

    if "schedule_times" in data:
        # DigestScheduleItem 리스트 → 순수 dict 리스트(JSON 저장)
        _upsert_setting(
            db, "digest", "schedule_times",
            _json.dumps(data["schedule_times"], ensure_ascii=False),
        )

    # 대상 필터 (JSON 리스트 저장)
    for filter_key in ("categories", "channel_pks", "tags"):
        if filter_key in data:
            _upsert_setting(
                db, "digest", filter_key,
                _json.dumps(data[filter_key], ensure_ascii=False),
            )

    mgr = get_youtube_settings_manager()
    mgr.invalidate("digest")

    # 다이제스트 스케줄 잡 재구성
    try:
        from app.services.scheduler import scheduler_service

        scheduler_service.update_youtube_digest_jobs()
    except Exception:
        logger.exception("YouTube 다이제스트 스케줄 잡 갱신 실패")

    return _digest_response()
