-- ============================================================
-- 005_fix_notify_enabled.sql
-- channels.notify_enabled 컬럼이 없거나 DEFAULT FALSE로 추가된 경우를 교정한다.
--
-- 문제 상황:
--   001_init_schema.sql 은 CREATE TABLE IF NOT EXISTS 를 사용하므로,
--   channels 테이블이 이미 존재하면 notify_enabled 컬럼이 추가되지 않는다.
--   이후 ALTER TABLE 로 컬럼이 추가될 때 DEFAULT FALSE 가 적용되거나,
--   UI 에서 알림 비활성화 상태로 저장된 경우 기존 채널이 모두 FALSE 가 된다.
--
-- 이 마이그레이션은:
--   1. notify_enabled 컬럼이 없으면 DEFAULT TRUE 로 추가한다.
--   2. __instant__ 가상 채널을 제외한 모든 채널의 notify_enabled 를 TRUE 로 복원한다.
--   3. 컬럼 기본값을 TRUE 로 명시한다.
-- ============================================================

SET search_path TO youtube;

-- 1. notify_enabled 컬럼이 없으면 안전하게 추가 (DEFAULT TRUE)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'youtube'
          AND table_name   = 'channels'
          AND column_name  = 'notify_enabled'
    ) THEN
        ALTER TABLE youtube.channels
            ADD COLUMN notify_enabled BOOLEAN NOT NULL DEFAULT TRUE;
        RAISE NOTICE 'notify_enabled 컬럼 추가 완료 (DEFAULT TRUE)';
    ELSE
        RAISE NOTICE 'notify_enabled 컬럼 이미 존재 — 추가 건너뜀';
    END IF;
END
$$;

-- 2. 컬럼 기본값을 TRUE 로 보장 (DEFAULT FALSE 로 생성된 경우 교정)
ALTER TABLE youtube.channels
    ALTER COLUMN notify_enabled SET DEFAULT TRUE;

-- 3. __instant__ 가상 채널을 제외한 모든 채널을 notify_enabled = TRUE 로 복원
--    (사용자가 의도적으로 비활성화한 채널은 UI에서 다시 조정 가능)
UPDATE youtube.channels
SET notify_enabled = TRUE
WHERE notify_enabled = FALSE
  AND channel_id != '__instant__';

-- 결과 확인용 로그
DO $$
DECLARE
    total_count  INTEGER;
    enabled_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO total_count FROM youtube.channels WHERE channel_id != '__instant__';
    SELECT COUNT(*) INTO enabled_count FROM youtube.channels WHERE notify_enabled = TRUE AND channel_id != '__instant__';
    RAISE NOTICE '채널 현황: 전체 %, 알림 활성 %', total_count, enabled_count;
END
$$;

-- ── schema_migrations 기록 ──────────────────────────────────────────────────
INSERT INTO youtube.schema_migrations (version, applied_at, description)
VALUES (5, NOW(), 'fix notify_enabled: add column if missing and reset to TRUE for real channels')
ON CONFLICT (version) DO NOTHING;
