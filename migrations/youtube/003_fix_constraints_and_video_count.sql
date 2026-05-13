-- ============================================================
-- Migration 003:
--   1. job_logs.job_type CHECK 제약 앱 실제 값으로 수정
--   2. tags.video_count 컬럼 추가 + 기존 데이터 백필
--   3. videos.description GIN(pg_trgm) 인덱스 추가
-- ============================================================
-- 트랜잭션: 앱(ensure_schema)이 engine.begin()으로 감싸므로 BEGIN/COMMIT 없음
-- ============================================================

-- ── 1. job_logs.job_type CHECK 제약 수정 ──────────────────────────────────

-- 기존 CHECK 제약 제거 (이름을 모를 수 있으므로 직접 조회 후 제거)
DO $$
DECLARE
    _con TEXT;
BEGIN
    SELECT con.conname INTO _con
    FROM pg_constraint con
    JOIN pg_class rel ON rel.oid = con.conrelid
    JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
    WHERE nsp.nspname = 'youtube'
      AND rel.relname = 'job_logs'
      AND con.contype = 'c'
      AND con.conname LIKE '%job_type%';
    IF _con IS NOT NULL THEN
        EXECUTE 'ALTER TABLE youtube.job_logs DROP CONSTRAINT ' || quote_ident(_con);
    END IF;
END;
$$;

-- 앱이 실제로 사용하는 값으로 CHECK 재추가
ALTER TABLE youtube.job_logs
    ADD CONSTRAINT job_logs_job_type_check
    CHECK (job_type IN (
        'channel_poll',
        'video_analyze',
        'video_reanalyze',
        'gateway_health',
        'notify'
    ));

-- ── 2. tags.video_count 컬럼 추가 + 기존 데이터 백필 ──────────────────────

ALTER TABLE youtube.tags
    ADD COLUMN IF NOT EXISTS video_count INTEGER NOT NULL DEFAULT 0;

-- 현재 video_tags 기준으로 백필
UPDATE youtube.tags t
SET video_count = (
    SELECT COUNT(*) FROM youtube.video_tags vt WHERE vt.tag_pk = t.tag_pk
);

-- ── 3. videos.description GIN 인덱스 (pg_trgm 기반 LIKE 검색용) ───────────
-- pg_trgm 확장은 ensure_schema()에서 앱 스키마(youtube 등)에 AUTOCOMMIT으로 미리 설치됨

CREATE INDEX IF NOT EXISTS idx_videos_description_trgm
    ON youtube.videos
    USING GIN (description gin_trgm_ops)
    WHERE description IS NOT NULL;

-- ── 4. schema_migrations 기록 ──────────────────────────────────────────────
INSERT INTO youtube.schema_migrations (version, applied_at, description)
VALUES (3, NOW(), 'fix job_type check, add tags.video_count, description GIN index')
ON CONFLICT (version) DO NOTHING;
