"""
YouTube 예약발송 서비스.

APScheduler CronTrigger 잡(`youtube_notify_HHMM`)에서 호출되며,
PostgreSQL에서 분석 완료·미발송 영상을 조회해 순차적으로 Telegram 발송한다.

- 즉시발송(immediate) 모드에서는 아무것도 하지 않고 종료.
- 예약발송(scheduled) 모드에서만 실제 발송을 수행.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker


async def _youtube_scheduled_notify_async() -> None:
    from app.services.youtube.db_engine import db_engine_manager
    from app.services.youtube.settings_manager import get_youtube_settings_manager
    from app.services.bots.youtube_bot import youtube_bot
    from app.models.youtube_video import YoutubeVideo

    mgr = get_youtube_settings_manager()
    notif_cfg = mgr.get_notification()

    if not notif_cfg.telegram_enabled:
        print("ℹ️  youtube_scheduled_notify: Telegram 알림 비활성 — skip")
        return

    if notif_cfg.send_mode != "scheduled":
        print("ℹ️  youtube_scheduled_notify: 즉시발송 모드 — 예약잡은 실행하지 않음")
        return

    try:
        engine = await db_engine_manager.get_engine()
    except Exception as exc:
        print(f"⚠️  youtube_scheduled_notify: DB 연결 실패 — {exc}")
        return

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # 미발송 · 분석완료 영상 video_pk 목록 조회 (오래된 영상부터)
    async with session_factory() as sess:
        stmt = (
            select(YoutubeVideo.video_pk)
            .where(YoutubeVideo.analysis_status == "done")
            .where(YoutubeVideo.notified_at.is_(None))
            .order_by(YoutubeVideo.published_at.asc())
        )
        result = await sess.execute(stmt)
        all_pending_pks = list(result.scalars().all())

    if not all_pending_pks:
        print("ℹ️  youtube_scheduled_notify: 미발송 영상 없음")
        return

    max_per = int(notif_cfg.scheduled_max_per_run or 5)
    if max_per < 1:
        max_per = 1
    elif max_per > 50:
        max_per = 50

    video_pks = all_pending_pks[:max_per]
    remaining = len(all_pending_pks) - len(video_pks)

    wait_sec = int(notif_cfg.wait_between_messages_sec or 30)
    threshold = float(notif_cfg.low_confidence_threshold or 0.5)

    print(
        f"📤 youtube_scheduled_notify: 이번 회차 {len(video_pks)}건 발송 "
        f"(대기 {wait_sec}초/건, 회당 상한 {max_per}건"
        f"{f', 잔여 미발송 약 {remaining}건은 다음 회차' if remaining > 0 else ''})"
    )
    sent = 0

    for i, pk in enumerate(video_pks):
        try:
            async with session_factory() as sess:
                async with sess.begin():
                    ok = await youtube_bot.notify(
                        session=sess,
                        video_pk=pk,
                        low_confidence_threshold=threshold,
                    )
            if ok:
                sent += 1
        except Exception as exc:
            print(f"⚠️  youtube_scheduled_notify: video_pk={pk} 발송 실패 — {exc}")

        if i < len(video_pks) - 1 and wait_sec > 0:
            await asyncio.sleep(wait_sec)

    print(f"✅ youtube_scheduled_notify: {sent}/{len(video_pks)}건 발송 완료 (이번 회차)")


def youtube_scheduled_notify_sync() -> None:
    """APScheduler CronTrigger 잡에서 호출되는 동기 래퍼."""
    asyncio.run(_youtube_scheduled_notify_async())
