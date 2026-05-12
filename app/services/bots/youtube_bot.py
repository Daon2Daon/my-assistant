"""
YouTube 모니터 알림 봇.

기존 TelegramSender / NotificationService 인프라를 그대로 사용.
분석 완료된 영상의 요약을 Telegram HTML 포맷으로 포매팅해 발송한다.

발송 포맷 (명세 4.4.1):
    <b>🎬 [{channel_name}] 신규 영상</b>

    <b>{headline}</b>

    <i>{one_line}</i>

    {short_summary_md}

    🏷 {tags_joined}
    📅 {published_at_kst}  ·  ⏱ {duration_human}

    🔗 <a href="{video_url}">영상 보러가기</a>
"""

from __future__ import annotations

import asyncio
import html
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import select, update

from app.models.youtube_channel import YoutubeChannel
from app.models.youtube_tag import YoutubeTag
from app.models.youtube_video import YoutubeVideo
from app.models.youtube_video_analysis import YoutubeVideoAnalysis
from app.models.youtube_video_tag import YoutubeVideoTag
from app.services.notification.telegram_sender import telegram_sender

# Telegram 메시지 최대 글자 수
_TELEGRAM_MAX_LEN = 4096
# 발송 대기 기본값 (초) — settings 없을 때 fallback
_DEFAULT_WAIT_SEC = 30


def _to_kst(dt: datetime) -> str:
    try:
        from zoneinfo import ZoneInfo

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        kst = dt.astimezone(ZoneInfo("Asia/Seoul"))
        return kst.strftime("%Y-%m-%d %H:%M KST")
    except Exception:
        return str(dt)


def _format_duration(seconds: Optional[int]) -> str:
    if not seconds:
        return ""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _truncate_html(text: str, max_len: int, suffix: str = "...") -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - len(suffix)] + suffix


def _escape(s: str) -> str:
    """HTML 특수문자 이스케이프 (plain text 영역용)."""
    return html.escape(s or "")


def build_notification_text(
    channel_name: str,
    headline: Optional[str],
    one_line: str,
    short_summary_md: str,
    tags: List[str],
    published_at: datetime,
    duration_seconds: Optional[int],
    video_url: str,
    confidence_score: Optional[float] = None,
    low_confidence_threshold: float = 0.5,
) -> str:
    """명세 4.4.1 포맷으로 Telegram HTML 메시지 생성."""
    lines: List[str] = []

    # 저신뢰도 배지
    if confidence_score is not None and confidence_score < low_confidence_threshold:
        lines.append("⚠️ <b>[저신뢰도 분석]</b>")
        lines.append("")

    lines.append(f"<b>🎬 [{_escape(channel_name)}] 신규 영상</b>")
    lines.append("")

    if headline:
        lines.append(f"<b>{_escape(headline)}</b>")
        lines.append("")

    lines.append(f"<i>{_escape(one_line)}</i>")
    lines.append("")

    lines.append(short_summary_md or "")
    lines.append("")

    if tags:
        lines.append(f"🏷 {', '.join(_escape(t) for t in tags)}")

    meta_parts: List[str] = [f"📅 {_to_kst(published_at)}"]
    dur = _format_duration(duration_seconds)
    if dur:
        meta_parts.append(f"⏱ {dur}")
    lines.append("  ·  ".join(meta_parts))
    lines.append("")

    lines.append(f'🔗 <a href="{video_url}">영상 보러가기</a>')

    text = "\n".join(lines)

    # 4096자 초과 시 short_summary_md 절단
    if len(text) > _TELEGRAM_MAX_LEN:
        overflow = len(text) - _TELEGRAM_MAX_LEN + 50
        truncated_summary = _truncate_html(
            short_summary_md,
            max(0, len(short_summary_md) - overflow),
            suffix=f'... <a href="{video_url}">(전체 보기)</a>',
        )
        return build_notification_text(
            channel_name=channel_name,
            headline=headline,
            one_line=one_line,
            short_summary_md=truncated_summary,
            tags=tags,
            published_at=published_at,
            duration_seconds=duration_seconds,
            video_url=video_url,
            confidence_score=confidence_score,
            low_confidence_threshold=low_confidence_threshold,
        )

    return text


class YoutubeBot:
    """YouTube 영상 알림 발송 봇."""

    async def notify(
        self,
        session: AsyncSession,
        video_pk: int,
        low_confidence_threshold: float = 0.5,
    ) -> bool:
        """
        단건 영상 알림 발송.
        - notified_at이 이미 있으면 재발송 없이 True 반환
        - 발송 성공 시 videos.notified_at 갱신
        """
        # video + detail + summary + tags 조회
        video = await self._fetch_video(session, video_pk)
        if not video:
            print(f"⚠️  YoutubeBot: video_pk={video_pk} 를 찾을 수 없습니다.")
            return False

        if video.notified_at is not None:
            return True  # 이미 발송됨

        channel = await self._fetch_channel(session, video.channel_pk)
        if channel and not channel.notify_enabled:
            return False  # 채널 알림 비활성화 (가상 채널 포함)

        analysis = await self._fetch_analysis(session, video_pk)
        tags = await self._fetch_tag_names(session, video_pk)

        if not analysis:
            print(f"⚠️  YoutubeBot: video_pk={video_pk} 분석 결과 없음 — 발송 skip")
            return False

        # source_channel_name이 있으면 실제 채널명 사용 (추가 영상)
        display_channel = (
            video.source_channel_name
            or (channel.channel_name if channel else "YouTube")
        )
        text = build_notification_text(
            channel_name=display_channel,
            headline=analysis.headline,
            one_line=analysis.one_line,
            short_summary_md=analysis.short_summary_md,
            tags=tags,
            published_at=video.published_at,
            duration_seconds=video.duration_seconds,
            video_url=video.video_url,
            confidence_score=analysis.confidence_score,
            low_confidence_threshold=low_confidence_threshold,
        )

        user = await self._get_user(session)
        if not user or not telegram_sender.is_available(user):
            print("⚠️  YoutubeBot: Telegram chat_id 없음 — 발송 skip")
            return False

        ok = await telegram_sender.send_message(user, text)
        if ok:
            await session.execute(
                update(YoutubeVideo)
                .where(YoutubeVideo.video_pk == video_pk)
                .values(notified_at=datetime.now(timezone.utc))
            )
        return ok

    async def notify_batch(
        self,
        session: AsyncSession,
        video_pks: List[int],
        wait_between_sec: int = _DEFAULT_WAIT_SEC,
        low_confidence_threshold: float = 0.5,
    ) -> int:
        """
        복수 영상 순차 발송. 채널 간 wait_between_sec 초 대기.
        반환값: 성공 건수
        """
        sent = 0
        for i, pk in enumerate(video_pks):
            ok = await self.notify(
                session=session,
                video_pk=pk,
                low_confidence_threshold=low_confidence_threshold,
            )
            if ok:
                sent += 1
            if i < len(video_pks) - 1:
                await asyncio.sleep(wait_between_sec)
        return sent

    # ── 내부 조회 헬퍼 ──────────────────────────────────────────────────────

    async def _fetch_video(
        self, session: AsyncSession, video_pk: int
    ) -> Optional[YoutubeVideo]:
        stmt = select(YoutubeVideo).where(YoutubeVideo.video_pk == video_pk)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _fetch_analysis(
        self, session: AsyncSession, video_pk: int
    ) -> Optional[YoutubeVideoAnalysis]:
        stmt = select(YoutubeVideoAnalysis).where(
            YoutubeVideoAnalysis.video_pk == video_pk
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _fetch_channel(
        self, session: AsyncSession, channel_pk: int
    ) -> Optional[YoutubeChannel]:
        stmt = select(YoutubeChannel).where(YoutubeChannel.channel_pk == channel_pk)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _fetch_tag_names(
        self, session: AsyncSession, video_pk: int
    ) -> List[str]:
        stmt = (
            select(YoutubeTag.name)
            .join(YoutubeVideoTag, YoutubeTag.tag_pk == YoutubeVideoTag.tag_pk)
            .where(YoutubeVideoTag.video_pk == video_pk)
            .order_by(YoutubeVideoTag.weight.desc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def _get_user(self, session):
        from app.database import SessionLocal
        from app.crud import get_or_create_user

        db = SessionLocal()
        try:
            return get_or_create_user(db)
        finally:
            db.close()


youtube_bot = YoutubeBot()


async def notify_video_callback(video_pk: int) -> None:
    """
    AnalysisPipeline의 notify_callback으로 주입할 함수.
    PG AsyncSession은 db_engine_manager에서 직접 얻는다.
    """
    from app.services.youtube.db_engine import db_engine_manager
    from app.services.youtube.settings_manager import get_youtube_settings_manager

    try:
        engine = await db_engine_manager.get_engine()
    except Exception as e:
        print(f"⚠️  notify_video_callback: DB 연결 실패 — skip (video_pk={video_pk}): {e}")
        return

    mgr = get_youtube_settings_manager()
    notif_cfg = mgr.get_notification()

    if not notif_cfg.telegram_enabled:
        return

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as sess:
        async with sess.begin():
            await youtube_bot.notify(
                session=sess,
                video_pk=video_pk,
                low_confidence_threshold=notif_cfg.low_confidence_threshold,
            )
