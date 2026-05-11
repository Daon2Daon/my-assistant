-- ============================================================
-- 001_init_schema.sql — PostgreSQL 14+ , schema = youtube
-- 멱등 적용을 위해 IF NOT EXISTS 사용
-- ============================================================

CREATE SCHEMA IF NOT EXISTS youtube;
SET search_path TO youtube;

-- 스키마 마이그레이션 버전 추적
CREATE TABLE IF NOT EXISTS youtube.schema_migrations (
    version       INTEGER PRIMARY KEY,
    applied_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    description   TEXT
);

-- 공용 함수: updated_at 자동 갱신
CREATE OR REPLACE FUNCTION youtube.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 3.2.1 channels --------------------------------------------------
CREATE TABLE IF NOT EXISTS youtube.channels (
    channel_pk          BIGSERIAL    PRIMARY KEY,
    channel_id          TEXT         NOT NULL UNIQUE,
    channel_name        TEXT         NOT NULL,
    channel_handle      TEXT,
    upload_playlist_id  TEXT         NOT NULL,
    thumbnail_url       TEXT,
    description         TEXT,
    category            TEXT,
    poll_interval_min   INTEGER      NOT NULL DEFAULT 720,
    is_active           BOOLEAN      NOT NULL DEFAULT TRUE,
    notify_enabled      BOOLEAN      NOT NULL DEFAULT TRUE,
    last_checked_at     TIMESTAMPTZ,
    last_video_id       TEXT,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_channels_active ON youtube.channels(is_active);
DROP TRIGGER IF EXISTS trg_channels_updated ON youtube.channels;
CREATE TRIGGER trg_channels_updated BEFORE UPDATE ON youtube.channels
    FOR EACH ROW EXECUTE FUNCTION youtube.set_updated_at();

-- 3.2.2 videos ----------------------------------------------------
CREATE TABLE IF NOT EXISTS youtube.videos (
    video_pk             BIGSERIAL   PRIMARY KEY,
    channel_pk           BIGINT      NOT NULL REFERENCES youtube.channels(channel_pk) ON DELETE CASCADE,
    video_id             TEXT        NOT NULL UNIQUE,
    video_url            TEXT        NOT NULL,
    title                TEXT        NOT NULL,
    description          TEXT,
    thumbnail_url        TEXT,
    published_at         TIMESTAMPTZ NOT NULL,
    duration_seconds     INTEGER,
    view_count           BIGINT,
    like_count           BIGINT,
    sequence_in_channel  INTEGER,
    analysis_status      TEXT        NOT NULL DEFAULT 'pending'
                      CHECK (analysis_status IN ('pending','processing','done','failed','skipped')),
    analysis_error       TEXT,
    retry_count          INTEGER     NOT NULL DEFAULT 0,
    notified_at          TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_videos_channel ON youtube.videos(channel_pk);
CREATE INDEX IF NOT EXISTS idx_videos_status  ON youtube.videos(analysis_status);
CREATE INDEX IF NOT EXISTS idx_videos_pubdate ON youtube.videos(published_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_videos_channel_seq
    ON youtube.videos(channel_pk, sequence_in_channel)
    WHERE sequence_in_channel IS NOT NULL;
DROP TRIGGER IF EXISTS trg_videos_updated ON youtube.videos;
CREATE TRIGGER trg_videos_updated BEFORE UPDATE ON youtube.videos
    FOR EACH ROW EXECUTE FUNCTION youtube.set_updated_at();

-- 3.2.3 video_details (상세 분석) ---------------------------------
CREATE TABLE IF NOT EXISTS youtube.video_details (
    detail_pk         BIGSERIAL   PRIMARY KEY,
    video_pk          BIGINT      NOT NULL UNIQUE REFERENCES youtube.videos(video_pk) ON DELETE CASCADE,
    full_transcript   TEXT,
    full_analysis_md  TEXT        NOT NULL,
    key_points        JSONB,
    insights          JSONB,
    entities          JSONB,
    sentiment         TEXT        CHECK (sentiment IN ('bullish','bearish','neutral','mixed')),
    confidence_score  DOUBLE PRECISION,
    model_name        TEXT,
    gateway_url       TEXT,
    prompt_version    TEXT,
    token_input       INTEGER,
    token_output      INTEGER,
    cost_usd          DOUBLE PRECISION,
    analyzed_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_details_video ON youtube.video_details(video_pk);

-- 3.2.4 video_summaries (알림용 요약) -----------------------------
CREATE TABLE IF NOT EXISTS youtube.video_summaries (
    summary_pk         BIGSERIAL   PRIMARY KEY,
    video_pk           BIGINT      NOT NULL UNIQUE REFERENCES youtube.videos(video_pk) ON DELETE CASCADE,
    one_line           TEXT        NOT NULL,
    short_summary_md   TEXT        NOT NULL,
    headline           TEXT,
    bullet_points      JSONB,
    cta_text           TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3.2.5 tags / video_tags (M:N) -----------------------------------
CREATE TABLE IF NOT EXISTS youtube.tags (
    tag_pk     BIGSERIAL   PRIMARY KEY,
    name       TEXT        NOT NULL UNIQUE,
    tag_type   TEXT        NOT NULL DEFAULT 'topic'
               CHECK (tag_type IN ('topic','ticker','person','sector')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS youtube.video_tags (
    video_pk  BIGINT NOT NULL REFERENCES youtube.videos(video_pk) ON DELETE CASCADE,
    tag_pk    BIGINT NOT NULL REFERENCES youtube.tags(tag_pk)     ON DELETE CASCADE,
    weight    DOUBLE PRECISION DEFAULT 1.0,
    PRIMARY KEY (video_pk, tag_pk)
);
CREATE INDEX IF NOT EXISTS idx_video_tags_tag ON youtube.video_tags(tag_pk);

-- 3.2.6 job_logs --------------------------------------------------
CREATE TABLE IF NOT EXISTS youtube.job_logs (
    log_pk       BIGSERIAL   PRIMARY KEY,
    job_type     TEXT        NOT NULL CHECK (job_type IN ('poll','analyze','notify','reanalyze','health')),
    channel_pk   BIGINT,
    video_pk     BIGINT,
    status       TEXT        NOT NULL CHECK (status IN ('success','fail','skip')),
    message      TEXT,
    duration_ms  INTEGER,
    started_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_joblogs_started ON youtube.job_logs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_joblogs_status  ON youtube.job_logs(status);

