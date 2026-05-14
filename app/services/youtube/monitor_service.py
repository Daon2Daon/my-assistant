"""
YouTube 모니터 서비스: 채널 폴링(수집)과 미분석 영상 배치 분석을 분리한다.

- `youtube_master_poll_sync`: 채널 폴링 → 신규 영상 DB 적재만 수행. 한 번의 마스터 실행에서 YouTube API 클라이언트는 채널 간 공유한다.
- `youtube_pending_analysis_sync`: DB의 `pending` 영상을 선점(claim) 후 분석 파이프라인 실행(스케줄 **실행당 1건**).

APScheduler(BackgroundScheduler)는 별도 스레드에서 동기 함수를 실행하므로,
각 sync 엔트리포인트가 asyncio.run()으로 비동기 로직을 감싼다.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Sequence

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.models.youtube_channel import YoutubeChannel
from app.models.youtube_video import YoutubeVideo
from app.services.youtube.db_engine import DBNotConfiguredError, db_engine_manager
from app.services.youtube.job_logger import (
    JobTimer,
    _JOB_TYPE_CHANNEL_POLL,
    _JOB_TYPE_GATEWAY_HEALTH,
    _JOB_TYPE_VIDEO_ANALYZE,
    _STATUS_FAIL,
    _STATUS_SKIP,
    _STATUS_SUCCESS,
    write_job_log,
)
from app.services.youtube.settings_manager import PollingSettings, get_youtube_settings_manager
from app.services.youtube.youtube_api import (
    PlaylistItemMeta,
    YouTubeAPIClient,
    YouTubeQuotaExceededError,
    get_youtube_api_client,
)


def _videos_table_sql_ident() -> str:
    """PostgreSQL quoted identifier for youtube.videos (스키마는 모델과 동일)."""
    t = YoutubeVideo.__table__
    schema = t.schema or "youtube"
    return f'"{schema}"."{t.name}"'


async def claim_pending_video_pks(session: AsyncSession, limit: int) -> List[int]:
    """
    analysis_status='pending' 행을 FOR UPDATE SKIP LOCKED으로 선점하고
    'processing'으로 바꾼 뒤 video_pk 목록을 반환한다.
    """
    if limit < 1:
        return []
    fq = _videos_table_sql_ident()
    stmt = text(
        f"""
        WITH picked AS (
            SELECT video_pk FROM {fq}
            WHERE analysis_status = :pending
            ORDER BY published_at ASC NULLS LAST, video_pk ASC
            LIMIT :lim
            FOR UPDATE SKIP LOCKED
        )
        UPDATE {fq} AS v
        SET analysis_status = :processing, updated_at = NOW()
        FROM picked
        WHERE v.video_pk = picked.video_pk
        RETURNING v.video_pk
        """
    )
    result = await session.execute(
        stmt,
        {"pending": "pending", "processing": "processing", "lim": limit},
    )
    rows = result.fetchall()
    return [int(r[0]) for r in rows]


# 프로세스 크래시·잡 중단 등으로 claim 직후 DB에만 남은 오래된 processing 행을 pending으로 되돌림.
STALE_PROCESSING_RESET_MINUTES = 180


async def reset_stale_processing_videos(session: AsyncSession, stale_minutes: int) -> int:
    """updated_at이 stale_minutes보다 오래된 processing 행을 pending으로 복구. 복구 건수 반환."""
    if stale_minutes < 1:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)
    stmt = (
        update(YoutubeVideo)
        .where(YoutubeVideo.analysis_status == "processing")
        .where(YoutubeVideo.updated_at < cutoff)
        .values(
            analysis_status="pending",
            analysis_error="[자동복구] 분석 중 상태가 비정상적으로 길어져 대기열로 되돌림",
            updated_at=datetime.now(timezone.utc),
        )
    )
    result = await session.execute(stmt)
    return int(result.rowcount or 0)


class MonitorService:
    def __init__(self, polling: PollingSettings):
        self.polling = polling

    # ── 채널 조회 ────────────────────────────────────────────────────────────

    async def list_due_channels(self, session: AsyncSession) -> List[YoutubeChannel]:
        """
        폴링이 필요한 활성 채널 목록 반환.
        (now - last_checked_at) >= poll_interval_min OR last_checked_at IS NULL
        """
        now = datetime.now(timezone.utc)
        stmt = select(YoutubeChannel).where(YoutubeChannel.is_active.is_(True))
        result = await session.execute(stmt)
        channels = result.scalars().all()

        due: List[YoutubeChannel] = []
        for ch in channels:
            if ch.last_checked_at is None:
                due.append(ch)
                continue
            lc = ch.last_checked_at
            if lc.tzinfo is None:
                lc = lc.replace(tzinfo=timezone.utc)
            interval = timedelta(minutes=int(ch.poll_interval_min or self.polling.default_channel_interval_min))
            if now - lc >= interval:
                due.append(ch)
        return due

    # ── 채널 단위 폴링 ───────────────────────────────────────────────────────

    async def process_channel(
        self,
        channel: YoutubeChannel,
        session: AsyncSession,
        api_client: YouTubeAPIClient,
        backfill: bool = False,
    ) -> List[int]:
        """
        채널 폴링 → 신규 영상 INSERT → 새 video_pk 목록 반환.
        backfill=True 이면 window_hours 필터 우회(신규 채널 등록 시 1회).
        """
        now = datetime.now(timezone.utc)
        window = timedelta(hours=int(self.polling.window_hours or 24))

        # playlistItems 조회
        items: Sequence[PlaylistItemMeta] = await api_client.get_latest_playlist_items(
            channel.upload_playlist_id, max_results=5
        )
        if not items:
            await self._update_last_checked(session, channel, now)
            return []

        # 신규 후보 필터
        candidate_ids = [it.video_id for it in items]
        new_ids = await self._filter_new_videos(session, candidate_ids)
        if not new_ids:
            await self._update_last_checked(session, channel, now, items[0].video_id)
            return []

        # videos.list 상세 조회
        video_metas = await api_client.get_video_details(new_ids)
        if not video_metas:
            await self._update_last_checked(session, channel, now)
            return []

        # window_hours 필터 (backfill 모드 OFF 시)
        cutoff = now - window
        if not backfill:
            video_metas = [
                v for v in video_metas
                if _parse_iso(v.published_at) >= cutoff
            ]

        if not video_metas:
            await self._update_last_checked(session, channel, now, items[0].video_id)
            return []

        # 다음 sequence 번호 계산
        seq_start = await self._next_sequence(session, channel.channel_pk)

        inserted_pks: List[int] = []
        for idx, vm in enumerate(video_metas):
            seq = seq_start + idx
            stmt = (
                pg_insert(YoutubeVideo)
                .values(
                    channel_pk=channel.channel_pk,
                    video_id=vm.video_id,
                    video_url=vm.video_url,
                    title=vm.title,
                    description=vm.description,
                    thumbnail_url=vm.thumbnail_url,
                    published_at=_parse_iso(vm.published_at),
                    duration_seconds=_parse_duration(vm.duration),
                    view_count=vm.view_count,
                    like_count=vm.like_count,
                    sequence_in_channel=seq,
                    analysis_status="pending",
                    retry_count=0,
                )
                .on_conflict_do_nothing(index_elements=["video_id"])
                .returning(YoutubeVideo.video_pk)
            )
            row = await session.execute(stmt)
            pk = row.scalar()
            if pk:
                inserted_pks.append(pk)

        await session.flush()
        await self._update_last_checked(session, channel, now, items[0].video_id)
        return inserted_pks

    # ── 헬퍼 ────────────────────────────────────────────────────────────────

    async def _filter_new_videos(
        self, session: AsyncSession, video_ids: List[str]
    ) -> List[str]:
        """DB에 이미 존재하는 video_id를 제외하고 신규 목록만 반환.

        ON CONFLICT DO NOTHING INSERT 전에 사전 필터링하여 불필요한
        API 호출(get_video_details)을 줄이는 역할도 합니다.
        """
        if not video_ids:
            return []
        stmt = select(YoutubeVideo.video_id).where(YoutubeVideo.video_id.in_(video_ids))
        result = await session.execute(stmt)
        existing = {row for row in result.scalars()}
        return [v for v in video_ids if v not in existing]

    async def _next_sequence(self, session: AsyncSession, channel_pk: int) -> int:
        stmt = select(func.max(YoutubeVideo.sequence_in_channel)).where(
            YoutubeVideo.channel_pk == channel_pk
        )
        result = await session.execute(stmt)
        max_seq = result.scalar()
        return 1 if max_seq is None else int(max_seq) + 1

    async def _update_last_checked(
        self,
        session: AsyncSession,
        channel: YoutubeChannel,
        now: datetime,
        last_video_id: Optional[str] = None,
    ) -> None:
        update_vals: dict = {"last_checked_at": now}
        if last_video_id:
            update_vals["last_video_id"] = last_video_id
        await session.execute(
            text(
                "UPDATE youtube.channels SET last_checked_at = :ts"
                + (", last_video_id = :vid" if last_video_id else "")
                + " WHERE channel_pk = :pk"
            ),
            {"ts": now, "vid": last_video_id, "pk": channel.channel_pk}
            if last_video_id
            else {"ts": now, "pk": channel.channel_pk},
        )


# ── ISO 파싱 / duration 파싱 헬퍼 ────────────────────────────────────────────

def _parse_iso(dt_str: str) -> datetime:
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


def _parse_duration(iso_duration: Optional[str]) -> Optional[int]:
    """ISO 8601 duration → 초. 예: PT15M33S → 933."""
    if not iso_duration:
        return None
    try:
        import isodate  # type: ignore

        return int(isodate.parse_duration(iso_duration).total_seconds())
    except Exception:
        return None


# ── 마스터 폴링 비동기 로직 ──────────────────────────────────────────────────

async def _youtube_master_poll_async() -> None:
    """마스터 폴링 잡의 비동기 구현체."""
    mgr = get_youtube_settings_manager()
    polling_cfg = mgr.get_polling()

    try:
        engine = await db_engine_manager.get_engine()
    except DBNotConfiguredError:
        print("⚠️  YouTube DB 미설정 - 마스터 폴링 SKIP")
        return
    except Exception as e:
        print(f"❌ YouTube DB 연결 실패 - 마스터 폴링 SKIP: {e}")
        return

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    service = MonitorService(polling=polling_cfg)

    async with session_factory() as session:
        try:
            due_channels = await service.list_due_channels(session)
        except Exception as e:
            print(f"❌ due_channels 조회 실패: {e}")
            return

    if not due_channels:
        return

    print(f"📡 YouTube 마스터 폴링: {len(due_channels)}개 채널 처리 시작")

    poll_sem = asyncio.Semaphore(int(polling_cfg.max_concurrent_channels or 5))
    api_client = get_youtube_api_client(polling=polling_cfg)

    async def _process_one(channel: YoutubeChannel) -> None:
        async with poll_sem:
            timer = JobTimer()
            with timer:
                try:
                    async with session_factory() as sess:
                        async with sess.begin():
                            new_pks = await service.process_channel(
                                channel=channel,
                                session=sess,
                                api_client=api_client,
                            )

                    await write_job_log(
                        session_factory,
                        job_type=_JOB_TYPE_CHANNEL_POLL,
                        status=_STATUS_SUCCESS,
                        message=f"신규 영상 {len(new_pks)}건 수집" if new_pks else "신규 영상 없음",
                        duration_ms=timer.elapsed_ms,
                        channel_pk=channel.channel_pk,
                    )

                except YouTubeQuotaExceededError as e:
                    print(f"⚠️  YouTube 쿼터 초과: {e}")
                    await write_job_log(
                        session_factory,
                        job_type=_JOB_TYPE_CHANNEL_POLL,
                        status=_STATUS_SKIP,
                        message=f"쿼터 초과: {e}",
                        duration_ms=timer.elapsed_ms,
                        channel_pk=channel.channel_pk,
                    )
                except Exception as e:
                    print(f"❌ 채널 처리 실패 (channel_pk={channel.channel_pk}): {e}")
                    await write_job_log(
                        session_factory,
                        job_type=_JOB_TYPE_CHANNEL_POLL,
                        status=_STATUS_FAIL,
                        message=str(e)[:500],
                        duration_ms=timer.elapsed_ms,
                        channel_pk=channel.channel_pk,
                    )

    try:
        await asyncio.gather(*[_process_one(ch) for ch in due_channels], return_exceptions=True)
    finally:
        await api_client.aclose()

    print("✅ YouTube 마스터 폴링 완료")


async def _youtube_pending_analysis_async() -> None:
    """스케줄 잡: DB에서 pending 영상 1건만 선점한 뒤 AI 분석·DB 저장.

    사용자 설정 `pending_analysis_interval_min` 주기로 호출되며,
    한 번의 실행에서는 **한 건씩**만 처리한다(동시 다발 분석 없음).
    """
    mgr = get_youtube_settings_manager()
    polling_cfg = mgr.get_polling()

    try:
        engine = await db_engine_manager.get_engine()
    except DBNotConfiguredError:
        print("⚠️  YouTube DB 미설정 - 미분석 영상 분석 잡 SKIP")
        return
    except Exception as e:
        print(f"❌ YouTube DB 연결 실패 - 미분석 영상 분석 잡 SKIP: {e}")
        return

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    batch_limit = 1

    n_reset = 0
    claimed: List[int] = []
    async with session_factory() as sess:
        async with sess.begin():
            n_reset = await reset_stale_processing_videos(sess, STALE_PROCESSING_RESET_MINUTES)
            claimed = await claim_pending_video_pks(sess, batch_limit)

    if n_reset:
        print(f"♻️  YouTube: 오래된 분석중(processing) 영상 {n_reset}건을 pending으로 복구")

    if not claimed:
        return

    print("🧠 YouTube 미분석 배치: 1건 분석 시작")
    analysis_sem = asyncio.Semaphore(1)
    await _analyze_batch(claimed, analysis_sem, polling_cfg, engine=engine)
    print("✅ YouTube 미분석 배치 완료")


def youtube_pending_analysis_sync() -> None:
    """APScheduler에 등록할 동기 wrapper (미분석 영상 배치 분석)."""
    asyncio.run(_youtube_pending_analysis_async())


async def _analyze_batch(
    video_pks: List[int],
    sem: asyncio.Semaphore,
    polling_cfg: PollingSettings,
    *,
    engine: AsyncEngine | None = None,
) -> None:
    """영상 분석 배치 (스케줄러 미분석 잡 또는 기타 호출부에서 video_pk 목록 전달).

    analysis_interval_sec > 0 이면 영상 간 순차 처리하며 대기 시간 삽입.
    Gemini 무료 티어처럼 분당 호출 제한이 있는 경우 throttling 역할을 합니다.
    analysis_interval_sec == 0 이면 기존처럼 세마포어 기반 병렬 처리합니다.

    engine이 주어지면 db_engine_manager.get_engine()를 다시 호출하지 않는다.
    """
    from app.services.youtube.analyzer import build_analysis_pipeline

    eng = engine if engine is not None else await db_engine_manager.get_engine()
    session_factory = async_sessionmaker(eng, expire_on_commit=False)

    from app.services.bots.youtube_bot import notify_video_callback

    pipeline = build_analysis_pipeline(notify_callback=notify_video_callback)
    interval_sec = int(polling_cfg.analysis_interval_sec or 0)

    async def _analyze_one(video_pk: int) -> None:
        async with sem:
            timer = JobTimer()
            channel_pk: Optional[int] = None
            with timer:
                try:
                    async with session_factory() as sess:
                        async with sess.begin():
                            stmt = select(YoutubeVideo).where(YoutubeVideo.video_pk == video_pk)
                            result = await sess.execute(stmt)
                            video = result.scalar_one_or_none()
                            if not video:
                                return

                            ch_stmt = select(YoutubeChannel).where(
                                YoutubeChannel.channel_pk == video.channel_pk
                            )
                            ch_result = await sess.execute(ch_stmt)
                            channel = ch_result.scalar_one_or_none()
                            channel_pk = video.channel_pk

                            await pipeline.run_and_save(
                                session=sess,
                                video_pk=video_pk,
                                video_url=video.video_url,
                                channel_name=channel.channel_name if channel else "",
                                published_at_str=video.published_at.isoformat(),
                            )
                except Exception as e:
                    print(f"❌ 분석 실패 (video_pk={video_pk}): {e}")
                    try:
                        async with session_factory() as fail_sess:
                            async with fail_sess.begin():
                                await fail_sess.execute(
                                    update(YoutubeVideo)
                                    .where(YoutubeVideo.video_pk == video_pk)
                                    .values(
                                        analysis_status="failed",
                                        analysis_error=str(e)[:500],
                                        updated_at=datetime.now(timezone.utc),
                                    )
                                )
                    except Exception as upd_exc:
                        print(
                            f"⚠️  분석 실패 상태 DB 기록 오류 (video_pk={video_pk}): {upd_exc}"
                        )
                    await write_job_log(
                        session_factory,
                        job_type=_JOB_TYPE_VIDEO_ANALYZE,
                        status=_STATUS_FAIL,
                        message=str(e)[:500],
                        duration_ms=timer.elapsed_ms,
                        channel_pk=channel_pk,
                        video_pk=video_pk,
                    )
                else:
                    await write_job_log(
                        session_factory,
                        job_type=_JOB_TYPE_VIDEO_ANALYZE,
                        status=_STATUS_SUCCESS,
                        message="분석 완료",
                        duration_ms=timer.elapsed_ms,
                        channel_pk=channel_pk,
                        video_pk=video_pk,
                    )

    if interval_sec > 0:
        # 순차 처리: 영상 사이마다 대기하여 API 호출 제한 회피
        for idx, pk in enumerate(video_pks):
            if idx > 0:
                print(f"⏳ 분석 간격 대기 {interval_sec}초 (video_pk={pk})")
                await asyncio.sleep(interval_sec)
            await _analyze_one(pk)
    else:
        # 병렬 처리: 세마포어로 동시 실행 수 제한
        await asyncio.gather(*[_analyze_one(pk) for pk in video_pks], return_exceptions=True)


def youtube_master_poll_sync() -> None:
    """APScheduler에 등록할 동기 wrapper."""
    asyncio.run(_youtube_master_poll_async())


async def _youtube_gateway_health_async() -> None:
    """litellm Gateway 헬스체크 (5분 주기)."""
    try:
        engine = await db_engine_manager.get_engine()
    except Exception:
        engine = None

    session_factory = async_sessionmaker(engine, expire_on_commit=False) if engine else None
    timer = JobTimer()

    with timer:
        client = None
        try:
            from app.services.youtube.llm_client import get_litellm_client

            mgr = get_youtube_settings_manager()
            ai_cfg = mgr.get_ai_gateway()
            if not ai_cfg.base_url or not ai_cfg.api_key:
                return
            client = get_litellm_client(settings=ai_cfg)
            await client.get_models(force_refresh=True)

            if session_factory:
                await write_job_log(
                    session_factory,
                    job_type=_JOB_TYPE_GATEWAY_HEALTH,
                    status=_STATUS_SUCCESS,
                    message="Gateway 응답 정상",
                    duration_ms=timer.elapsed_ms,
                )
        except Exception as e:
            print(f"⚠️  YouTube Gateway 헬스체크 실패: {e}")
            if session_factory:
                await write_job_log(
                    session_factory,
                    job_type=_JOB_TYPE_GATEWAY_HEALTH,
                    status=_STATUS_FAIL,
                    message=str(e)[:500],
                    duration_ms=timer.elapsed_ms,
                )
        finally:
            if client is not None:
                await client.aclose()


def youtube_gateway_health_sync() -> None:
    """APScheduler에 등록할 동기 wrapper."""
    asyncio.run(_youtube_gateway_health_async())
