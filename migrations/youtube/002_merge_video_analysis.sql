-- ============================================================
-- Migration 002: video_details + video_summaries → video_analysis
--
-- 멱등 설계:
--   - 신규 DB: 001에서 video_analysis가 이미 생성되어 있고
--     video_details/video_summaries는 존재하지 않음 → 데이터 이전 건너뜀
--   - 기존 DB: video_details/video_summaries 데이터를 video_analysis로 복사 후 삭제
-- ============================================================
-- 트랜잭션: 앱(ensure_schema)이 engine.begin()으로 감싸므로 BEGIN/COMMIT 없음
-- ============================================================

-- ── 1. video_analysis 통합 테이블 생성 (001에서 이미 생성된 경우 무시) ───────
CREATE TABLE IF NOT EXISTS youtube.video_analysis (
    video_pk          BIGINT           PRIMARY KEY
                                           REFERENCES youtube.videos(video_pk) ON DELETE CASCADE,

    -- 요약 (구 video_summaries)
    one_line          TEXT             NOT NULL DEFAULT '',
    headline          TEXT,
    short_summary_md  TEXT             NOT NULL DEFAULT '',
    bullet_points     JSONB,

    -- 상세 분석 (구 video_details)
    full_analysis_md  TEXT,
    full_transcript   TEXT,
    key_points        JSONB,
    insights          JSONB,
    entities          JSONB,
    sentiment         TEXT,
    confidence_score  DOUBLE PRECISION,

    -- 모델/비용 메타
    model_name        TEXT,
    gateway_url       TEXT,
    prompt_version    TEXT,
    token_input       INTEGER,
    token_output      INTEGER,
    cost_usd          DOUBLE PRECISION,

    analyzed_at       TIMESTAMPTZ      NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_video_analysis_video ON youtube.video_analysis(video_pk);

-- ── 2. 기존 데이터 이전 (구 테이블이 존재하는 경우에만) ──────────────────────
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'youtube'
          AND table_name   = 'video_details'
    ) THEN
        INSERT INTO youtube.video_analysis (
            video_pk,
            one_line, headline, short_summary_md, bullet_points,
            full_analysis_md, full_transcript,
            key_points, insights, entities,
            sentiment, confidence_score,
            model_name, gateway_url, prompt_version,
            token_input, token_output, cost_usd,
            analyzed_at
        )
        SELECT
            COALESCE(vd.video_pk, vs.video_pk),
            COALESCE(vs.one_line, ''),
            vs.headline,
            COALESCE(vs.short_summary_md, ''),
            vs.bullet_points,
            vd.full_analysis_md,
            vd.full_transcript,
            vd.key_points,
            vd.insights,
            vd.entities,
            vd.sentiment,
            vd.confidence_score,
            vd.model_name,
            vd.gateway_url,
            vd.prompt_version,
            vd.token_input,
            vd.token_output,
            vd.cost_usd,
            COALESCE(vd.analyzed_at, vs.created_at, NOW())
        FROM youtube.video_details vd
        FULL OUTER JOIN youtube.video_summaries vs
            ON vd.video_pk = vs.video_pk
        ON CONFLICT (video_pk) DO NOTHING;
    END IF;
END;
$$;

-- ── 3. 구 테이블 삭제 (없으면 무시) ──────────────────────────────────────────
DROP TABLE IF EXISTS youtube.video_details;
DROP TABLE IF EXISTS youtube.video_summaries;

-- ── 4. schema_migrations 기록 ──────────────────────────────────────────────
INSERT INTO youtube.schema_migrations (version, applied_at, description)
VALUES (2, NOW(), 'merge video_details + video_summaries into video_analysis')
ON CONFLICT (version) DO NOTHING;
