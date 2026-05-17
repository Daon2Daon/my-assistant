-- ============================================================
-- 006_add_deleted_videos.sql
-- 사용자가 삭제한 영상의 video_id를 보관하여 채널 재폴링 시 재추가를 방지한다.
-- ============================================================

SET search_path TO youtube;

CREATE TABLE IF NOT EXISTS youtube.deleted_videos (
    id          BIGSERIAL    PRIMARY KEY,
    video_id    TEXT         NOT NULL UNIQUE,
    deleted_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS deleted_videos_video_id_idx ON youtube.deleted_videos (video_id);

-- ── schema_migrations 기록 ──────────────────────────────────────────────────
INSERT INTO youtube.schema_migrations (version, applied_at, description)
VALUES (6, NOW(), 'add deleted_videos table: block re-ingestion of user-deleted videos')
ON CONFLICT (version) DO NOTHING;
