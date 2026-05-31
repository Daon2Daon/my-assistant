-- ============================================================
-- 007_add_digests.sql
-- 주간 리뷰(Weekly Review) 저장 테이블.
-- 일정 기간(기본 1주) 동안 분석 완료된 영상을 카테고리별로 묶어
-- 합성한 리뷰 결과를 보관한다. (카테고리별 1행)
-- ============================================================

SET search_path TO youtube;

CREATE TABLE IF NOT EXISTS youtube.digests (
    digest_pk           BIGSERIAL    PRIMARY KEY,
    period_type         TEXT         NOT NULL DEFAULT 'weekly',
    period_weeks        INTEGER      NOT NULL DEFAULT 1,
    period_start        TIMESTAMPTZ  NOT NULL,
    period_end          TIMESTAMPTZ  NOT NULL,
    category            TEXT,
    video_count         INTEGER      NOT NULL DEFAULT 0,
    headline            TEXT,
    summary_md          TEXT,
    telegram_summary    TEXT,
    sentiment_breakdown JSONB,
    top_tags            JSONB,
    top_channels        JSONB,
    model_name          TEXT,
    token_input         INTEGER,
    token_output        INTEGER,
    cost_usd            DOUBLE PRECISION,
    status              TEXT         NOT NULL DEFAULT 'pending',
    error               TEXT,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS digests_period_idx ON youtube.digests (period_end DESC, category);

CREATE INDEX IF NOT EXISTS digests_status_idx ON youtube.digests (status);

-- ── schema_migrations 기록 ──────────────────────────────────────────────────
INSERT INTO youtube.schema_migrations (version, applied_at, description)
VALUES (7, NOW(), 'add digests table: weekly review aggregation per category')
ON CONFLICT (version) DO NOTHING;
