-- ============================================================
-- Migration 004: videos.source_channel_name 추가
-- 추가 영상(즉시 분석): 등록된 채널이 아닌 임의 URL의 실제 채널명 보존
-- ============================================================

BEGIN;

ALTER TABLE youtube.videos
    ADD COLUMN IF NOT EXISTS source_channel_name TEXT;

INSERT INTO youtube.schema_migrations (version, applied_at, description)
VALUES (4, NOW(), 'add videos.source_channel_name for instant analysis')
ON CONFLICT (version) DO NOTHING;

COMMIT;
