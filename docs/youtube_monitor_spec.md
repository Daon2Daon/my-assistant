# [기능 명세서] My Assistant – YouTube 자동 모니터링 모듈 (v1.1)

> **문서 목적**: 기존 `my-assistant` (FastAPI 기반 개인 비서 앱)에 **YouTube 채널 자동 모니터링 + AI 영상 분석 + Telegram 발송** 기능을 신규 모듈(`youtube_monitor`)로 통합 추가하기 위한 구현 명세서.
>
> **작성 기준일**: 2026-05-11
> **개정 이력**:
> - v1.0 (2026-05-11): 최초 작성. SQLite + Gemini 직접 SDK 기준.
> - v1.1 (2026-05-11): **PostgreSQL(개인 서버)** 및 **litellm AI Gateway(개인 서버)** 채택. 두 항목 모두 Web UI에서 동적 설정 가능하도록 변경.
>
> **대상 코드베이스**: `/Users/mook/Library/CloudStorage/SynologyDrive-Mook_Cloud/04.Coding/my-assistant`
> **참고 자료**: 기존 n8n 워크플로우(`n8n.json`), Postgres 테이블(`youtube_channels`, `video_summaries`, `experts`, `economist_claims`)

---

## 1. 개요 및 배경

### 1.1 추진 배경

현재 운영 중인 자동화는 두 갈래로 분리되어 있음.

1. **n8n 워크플로우** — Postgres `workspace.youtube_channels` 테이블의 활성 채널을 1일 3회(08/14/20시) 폴링, YouTube Data API + Gemini 2.5 Flash로 영상 분석 후 Telegram 발송.
2. **`my-assistant` 앱** — FastAPI + SQLite로 구축된 개인 비서 앱. 날씨/금융/캘린더/메모/차트 봇 + Telegram 발송 인프라 보유.

n8n은 ‘노코드 자동화’의 장점이 있지만 다음 한계가 있음.

- **분석 깊이 부족**: 단일 `summary` 컬럼에 마크다운 텍스트를 통째로 넣음. 구조화된 인사이트(주장/근거/태그/타임코드)가 없어 후속 활용이 불가.
- **순서·메타 관리 부실**: 채널별 영상 시퀀스, 발행 순번, 카테고리/태그가 분리되어 있지 않음.
- **재처리 불가**: 분석 실패 시 수동 개입이 필요. 동일 영상에 대한 분석 버전 관리 안 됨.
- **알림 길이 제어 곤란**: Telegram에 ‘상세 요약’이 그대로 전송되어 채널 가독성 저하.

이번 모듈은 위 한계를 정규화된 RDB 스키마와 Python 비동기 파이프라인으로 흡수해, **상세 분석 테이블**과 **알림용 요약 테이블**을 분리하고 기존 `my-assistant` 인프라(Telegram, APScheduler, 인증, 대시보드)를 그대로 재사용함.

### 1.2 목표 (Goals)

| # | 목표 | 측정 기준 |
|---|------|-----------|
| G1 | 사용자가 웹 UI에서 모니터링 채널을 CRUD 할 수 있음 | 추가/삭제/활성화 토글 작동 |
| G2 | 활성 채널의 신규 업로드를 자동 감지해 분석·기록·발송 | 12시간 내 업로드 영상 95% 이상 자동 처리 |
| G3 | 영상 분석을 ‘상세’와 ‘요약’으로 이중 기록 | 두 테이블 모두 채워진 행 비율 ≥ 99% |
| G4 | 카테고리/태그 자동 분류로 후속 검색 가능 | 영상 1건당 평균 태그 수 ≥ 3 |
| G5 | 기존 `my-assistant` 운영을 해치지 않고 무중단 추가 | 기존 라우터·미들웨어·DB 영향 없음, 마이그레이션 1회로 적용 |

### 1.3 비목표 (Non-Goals)

- 다중 사용자 동시 운영(멀티 테넌트). 본 모듈은 단일 사용자(`user_id=1`) 기준.
- 영상 다운로드/저장(저작권·용량 이슈).
- YouTube 댓글·구독자 통계 분석.
- 라이브 스트림 실시간 모니터링(다음 단계).

---

## 2. 시스템 아키텍처

### 2.1 컴포넌트 다이어그램 (텍스트, v1.1)

```
┌─────────────────────────────────────────────────────────────────────┐
│                        my-assistant (FastAPI)                       │
│                                                                     │
│  ┌──────────────────┐      ┌───────────────────────────────────┐    │
│  │  Web UI (React)  │ ───▶ │  /api/youtube/* (신규 라우터)     │    │
│  │  /youtube        │ ◀─── │  channels, videos, settings,      │    │
│  │                  │      │  jobs, tags                       │    │
│  └──────────────────┘      └───────────────────────────────────┘    │
│                                       │                             │
│                                       ▼                             │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  YouTubeMonitorService                                      │    │
│  │  ┌──────────────┐ ┌──────────────┐ ┌────────────────────┐   │    │
│  │  │ Channel CRUD │ │ Polling Job  │ │ Analysis Pipeline  │   │    │
│  │  │              │ │ (동적 주기)  │ │ (LLM via Gateway)  │   │    │
│  │  └──────────────┘ └──────────────┘ └────────────────────┘   │    │
│  └─────────────────────────────────────────────────────────────┘    │
│           │           │             │                  │            │
│           ▼           ▼             ▼                  ▼            │
│  ┌─────────────┐ ┌──────────┐ ┌─────────────┐ ┌────────────────┐   │
│  │ Notification│ │APScheduler│ │ Settings    │ │ DB Engine      │   │
│  │ Service     │ │ (기존)   │ │ Manager     │ │ Manager        │   │
│  │ → Telegram  │ │+youtube_*│ │ (런타임설정)│ │ (PG 동적 연결) │   │
│  └─────────────┘ └──────────┘ └─────────────┘ └────────────────┘   │
└──────┬───────────────┬────────────────┬────────────────┬───────────┘
       │               │                │                │
       ▼               ▼                ▼                ▼
   Telegram      YouTube Data    SQLite                PostgreSQL
   Bot API       API v3          (assistant.db)        (개인 서버)
                                  - youtube_settings    - youtube.*
                                  - 기존 my-assistant     7개 테이블
                                    데이터
                                ▲
                                │
                                ▼
                          litellm Gateway
                          (개인 서버, http://litellm:4000)
                          ├─ /gemini/v1beta/...  (멀티모달 영상)
                          └─ /v1/chat/completions (OpenAI 호환, fallback)
```

**핵심 변경점 (v1.1)**:
- 영상 데이터는 **PostgreSQL**(개인 서버)에 `youtube` 스키마로 저장. SQLite에는 **설정값(`youtube_settings`)만** 저장.
- LLM 호출은 모두 **litellm Gateway**를 경유. Gemini 멀티모달은 native 패스스루 경로, 일반 텍스트는 OpenAI 호환 경로.
- DB 접속/모델 선택/API 키 등은 **`Settings Manager`** 가 SQLite의 `youtube_settings`에서 읽어 런타임에 적용. UI에서 변경 시 즉시 반영(엔진 재생성).

### 2.2 기술 스택 (v1.1)

| 레이어 | 기술 | 선정 이유 |
|--------|------|-----------|
| Web Framework | FastAPI 0.109+ (기존) | 동일 앱에 라우터만 추가, 비동기 I/O로 외부 API 호출 효율 |
| Frontend | React 18 + Vite + Tailwind | 사용자 선택 사항. `app/static/youtube/` 빌드 산출물 서빙. 기존 Jinja2 페이지와 공존 |
| ORM | SQLAlchemy 2.0 (기존) | 기존 패턴 일치. 단일 코드로 SQLite/PostgreSQL 양쪽 지원 |
| **DB (앱 설정)** | **SQLite** (기존 `data/assistant.db`) | 기존 `my-assistant` 데이터 + `youtube_settings`(연결 정보, 모델 설정). 부트스트랩 단계의 신뢰원(信賴源) |
| **DB (YouTube 데이터)** | **PostgreSQL 14+ (개인 서버)** | 사용자 보유 PG 서버 활용. 누적 영상/태그/JSONB 활용에 유리. 연결 정보는 UI에서 동적 설정 |
| Scheduler | APScheduler `BackgroundScheduler` (기존) | jobstore는 기존대로 SQLite에 보관(부트 시점 의존성 최소화) |
| **AI Gateway** | **litellm (개인 서버)** | 단일 API로 Gemini/Claude/OpenAI 통합. 모델·키·엔드포인트를 UI에서 변경 가능. n8n 워크플로우와 동일한 경로 재사용 |
| Video Analysis (Primary) | **Gemini 2.5 Pro/Flash** (litellm `gemini/` 패스스루) | YouTube URL 직접 fileData 입력 → 자막+영상 동시 처리, 자막 없는 영상도 분석 |
| Video Analysis (Fallback) | OpenAI 호환 chat completions via litellm | transcript-api로 자막 추출 후 모델 무관 텍스트 분석 |
| YouTube API | YouTube Data API v3 (`playlistItems`, `videos`) | 채널의 업로드 플레이리스트(`UC→UU`) 활용 |
| Notification | 기존 `NotificationService` + `TelegramSender` | 신규 봇 클래스 `youtube_bot.py`만 추가 |
| HTTP Client | `httpx` (기존) | 비동기 호출 |
| **DB Driver** | **`psycopg[binary]` 3.1+** | 비동기 지원, SQLAlchemy 2.0과 호환 |
| 패키징 | Docker Compose (기존 `docker-compose.yml` 확장) | 별도 서비스 아님. PostgreSQL/litellm은 사용자 개인 서버에 이미 운영 중이므로 추가 컨테이너 불필요 |

### 2.3 신규 디렉터리 구조 (v1.1, 기존 패턴 준수)

```
my-assistant/
├── app/
│   ├── models/
│   │   ├── youtube_setting.py            ← (SQLite) 설정 저장 - DB 연결, AI Gateway, 폴링
│   │   ├── youtube_channel.py            ← (PostgreSQL) 신규
│   │   ├── youtube_video.py              ← (PostgreSQL) 신규
│   │   ├── youtube_video_detail.py       ← (PostgreSQL) 신규
│   │   ├── youtube_video_summary.py      ← (PostgreSQL) 신규
│   │   ├── youtube_tag.py                ← (PostgreSQL) 신규
│   │   ├── youtube_video_tag.py          ← (PostgreSQL) 신규 (M:N)
│   │   └── youtube_job_log.py            ← (PostgreSQL) 신규
│   ├── schemas/
│   │   └── youtube.py                    ← 신규 (Pydantic)
│   ├── routers/
│   │   └── youtube.py                    ← 신규 (/api/youtube/*, /api/youtube/settings/*)
│   ├── services/
│   │   ├── youtube/                      ← 신규 디렉터리
│   │   │   ├── __init__.py
│   │   │   ├── settings_manager.py       ← v1.1: 런타임 설정 로더/캐시/암호화
│   │   │   ├── db_engine.py              ← v1.1: PG 동적 엔진 매니저(연결 검증, 재생성)
│   │   │   ├── llm_client.py             ← v1.1: litellm 통합 클라이언트(Gemini 패스스루 + OpenAI 호환)
│   │   │   ├── youtube_api.py            ← YouTube Data API 래퍼
│   │   │   ├── analyzer.py               ← (구 gemini_analyzer.py) LLM-agnostic 분석기
│   │   │   ├── monitor_service.py        ← 폴링 + 파이프라인 오케스트레이터
│   │   │   └── tag_extractor.py          ← LLM 기반 태그 추출
│   │   └── bots/
│   │       └── youtube_bot.py            ← 기존 봇 패턴 따름, 알림 포맷터
│   ├── static/
│   │   └── youtube/                      ← React 빌드 산출물 (assets/, index.html)
│   └── templates/
│       └── youtube.html                  ← React SPA 호스팅용 단일 Jinja 셸
├── frontend/
│   └── youtube/                          ← React 소스 (Vite, npm)
│       ├── src/
│       ├── package.json
│       └── vite.config.ts
├── migrations/
│   └── youtube/                          ← v1.1: PostgreSQL DDL 스크립트
│       ├── 001_init_schema.sql
│       └── 002_indexes.sql
├── docs/
│   └── youtube_monitor_spec.md           ← 본 문서 사본
└── requirements.txt                      ← v1.1: psycopg[binary], openai, cryptography 등 추가
```

---

## 3. 데이터베이스 설계 (v1.1, 2-DB 분리)

### 3.0 DB 분리 전략

| DB | 위치 | 역할 | 부트 시 필요 |
|----|------|------|--------------|
| **SQLite** (`data/assistant.db`) | 앱 컨테이너 | 기존 my-assistant 데이터 + `youtube_settings` (PG 접속/AI Gateway/폴링 설정) | ✅ 항상 |
| **PostgreSQL** (개인 서버) | 별도 서버 | 영상 데이터 7개 테이블 (`youtube` 스키마) | ❌ 첫 설정 후. 미설정 시 UI에서 ‘설정 필요’ 안내 |

> **부트스트랩 원칙**: PostgreSQL 접속 정보는 PostgreSQL이 아닌 **SQLite**에 보관해야 “설정 못 읽어서 설정 못 함” 순환을 피함. AES-256-GCM(`cryptography.Fernet`)로 암호화 저장, 키는 `.env`의 `YOUTUBE_SETTINGS_FERNET_KEY` 사용.

### 3.1 ERD 개요

```
[SQLite: assistant.db]
   youtube_settings          ← PG 접속, AI Gateway, 폴링 정책

[PostgreSQL: <user_dsn>, schema=youtube]
   youtube_channels ──┐
      1               │ 1:N
                      ▼
                 youtube_videos ────┬──── 1:1 ────► youtube_video_details
                      │             │
                      │             └──── 1:1 ────► youtube_video_summaries
                      │
                      │ M:N (via youtube_video_tags)
                      ▼
                 youtube_tags
                      
   youtube_job_logs (독립)
```

### 3.2 테이블별 DDL

#### 3.2.0 `youtube_settings` — **(SQLite, 부트스트랩 설정)**

```sql
-- SQLite (data/assistant.db)
CREATE TABLE IF NOT EXISTS youtube_settings (
    setting_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    category     TEXT    NOT NULL,                -- 'database' / 'ai_gateway' / 'polling' / 'notification'
    key          TEXT    NOT NULL,                -- 카테고리 내 키 (예: 'host', 'api_key', 'model_name')
    value        TEXT,                            -- 평문 값
    value_enc    BLOB,                            -- 암호화 값 (api_key, password 등 민감정보)
    value_type   TEXT    DEFAULT 'string',        -- 'string'/'int'/'float'/'bool'/'json'
    is_secret    INTEGER DEFAULT 0,               -- 1이면 value_enc 사용
    description  TEXT,                            -- UI 표시용 설명
    updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (category, key)
);
```

**시드 데이터(앱 첫 실행 시 INSERT)**

| category | key | 기본값 | 설명 |
|----------|-----|--------|------|
| database | host | (빈 값) | PG 호스트 (예: `192.168.1.10`) |
| database | port | 5432 | PG 포트 |
| database | dbname | youtube_monitor | 데이터베이스명 |
| database | username | (빈 값) | PG 사용자 |
| database | password | (빈 값, secret) | PG 비밀번호 (Fernet 암호화) |
| database | schema | youtube | PG 스키마명 |
| database | sslmode | prefer | `disable`/`prefer`/`require` |
| ai_gateway | base_url | `http://litellm:4000` | litellm 엔드포인트 |
| ai_gateway | api_key | (빈 값, secret) | litellm Master Key (Fernet) |
| ai_gateway | primary_model | `gemini/gemini-2.5-flash` | 멀티모달 분석 (네이티브 패스스루 경로) |
| ai_gateway | fallback_model | `gemini/gemini-2.5-flash` | 텍스트 fallback 분석용 (OpenAI 호환 경로) |
| ai_gateway | tagging_model | `gemini/gemini-2.5-flash` | 태그 정제용 (저비용 모델 권장) |
| ai_gateway | temperature | 0.3 | 모델 공통 |
| ai_gateway | max_tokens | 8192 | |
| ai_gateway | daily_budget_usd | 2.0 | 일일 한도 |
| polling | master_interval_min | 12 | 마스터 잡 주기 |
| polling | default_channel_interval_min | 720 | 채널 기본 주기 |
| polling | youtube_api_key | (빈 값, secret) | YouTube Data API 키 |
| polling | youtube_daily_quota | 10000 | API 쿼터 한도 |
| polling | window_hours | 24 | 신규 영상 인정 윈도우 |
| polling | max_concurrent_channels | 5 | 폴링 동시성 |
| polling | max_concurrent_analyses | 3 | 분석 동시성 |
| notification | telegram_enabled | true | 알림 ON/OFF |
| notification | wait_between_messages_sec | 30 | 채널 간 대기 |
| notification | low_confidence_threshold | 0.5 | 이하면 ‘저신뢰도’ 배지 |

> 변경은 모두 UI에서. `SettingsManager`는 메모리 캐시(60초 TTL) + 즉시 무효화 API 제공.

---

#### 3.2.1 ~ 3.2.7 — **PostgreSQL `youtube` 스키마**

전체를 단일 `migrations/youtube/001_init_schema.sql`로 적용. 멱등성을 위해 `IF NOT EXISTS` 사용.

```sql
-- ============================================================
-- 001_init_schema.sql — PostgreSQL 14+ , schema = youtube
-- ============================================================
CREATE SCHEMA IF NOT EXISTS youtube;
SET search_path TO youtube;

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
    key_points        JSONB,                                       -- [{"timestamp":"hh:mm:ss","point":"…"}, …]
    insights          JSONB,
    entities          JSONB,
    sentiment         TEXT        CHECK (sentiment IN ('bullish','bearish','neutral','mixed')),
    confidence_score  DOUBLE PRECISION,
    model_name        TEXT,                                        -- 분석에 사용된 모델 (litellm key 그대로)
    gateway_url       TEXT,                                        -- 분석 시점 litellm base_url 스냅샷
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
```

> **순번(`sequence_in_channel`) 산출 규칙**: 동일 `channel_pk` 내에서 `published_at` 오름차순 RANK. 신규 INSERT 시 서비스 레이어에서 `MAX(sequence)+1` 부여. `uq_videos_channel_seq` UNIQUE INDEX로 중복 방지.

> **JSONB 활용**: `key_points`, `insights`, `entities`, `tags(weight)`는 SQLite의 TEXT 대신 JSONB로 저장 → GIN 인덱스, JSON path 쿼리, 후속 검색 기능에 유리.

### 3.3 마이그레이션 절차

#### 3.3.1 SQLite (`youtube_settings`)

기존 `app/database.py::run_migrations()`에 신규 블록 추가:

```python
def _migrate_youtube_settings():
    if not _table_exists(cursor, "youtube_settings"):
        cursor.executescript(open("migrations/youtube/000_sqlite_settings.sql").read())
        cursor.executescript(open("migrations/youtube/000_seed_settings.sql").read())
        print("✅ youtube_settings 테이블 생성 + 시드 적용")
```

#### 3.3.2 PostgreSQL (`youtube` 스키마)

`db_engine.py::ensure_schema()` 가 PG 연결 성공 시 1회 실행:

```python
async def ensure_schema(engine: AsyncEngine):
    async with engine.begin() as conn:
        await conn.execute(text(open("migrations/youtube/001_init_schema.sql").read()))
        # 002_indexes.sql, 003_*, … 추가 마이그레이션도 순차 적용 (schema_migrations 테이블로 추적)
```

별도 스키마 버전 추적 테이블:
```sql
CREATE TABLE IF NOT EXISTS youtube.schema_migrations (
    version       INTEGER PRIMARY KEY,
    applied_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    description   TEXT
);
```

#### 3.3.3 기존 데이터 이관 (선택)

기존 n8n Postgres의 `workspace.video_summaries` / `workspace.youtube_channels` → 신규 `youtube.*` 매핑 스크립트 (`scripts/import_legacy.py`). 본 명세 범위 외, 부록 10.5 참조.

---

## 4. 기능 명세

### 4.1 채널 관리 (CRUD)

#### 4.1.1 사용자 시나리오

1. 사용자가 `/youtube` 페이지에 진입.
2. ‘채널 추가’ 입력란에 **다음 중 한 가지** 입력:
   - YouTube 채널 URL (`https://www.youtube.com/@johndoe`, `/channel/UC...`, `/c/...`, `/user/...`)
   - 채널 핸들 (`@johndoe`)
   - 채널 ID (`UCxxxxxxxxxxxxxxxxxxxxxx`)
3. 백엔드는 입력값을 정규화해 채널 ID를 추출, 메타정보(이름·썸네일·업로드 플레이리스트 ID)를 가져와 DB에 저장.
4. 저장 직후 ‘즉시 1회 폴링’ 옵션 체크 시, 비동기 task로 첫 폴링 실행해 최근 영상 1건 즉시 분석.

#### 4.1.2 API 사양 (REST, JSON)

| Method | Path | 설명 | 요청 본문 | 응답 |
|--------|------|------|-----------|------|
| GET    | `/api/youtube/channels` | 전체 채널 목록 | – | `[{channel_pk, channel_id, channel_name, is_active, …}]` |
| POST   | `/api/youtube/channels` | 신규 채널 추가 | `{ "input": "@johndoe", "category": "투자", "poll_interval_min": 720, "auto_poll_now": true }` | `201 {channel_pk, …}` |
| PATCH  | `/api/youtube/channels/{pk}` | 활성/주기/카테고리 수정 | `{ "is_active": false }` | `200 {…}` |
| DELETE | `/api/youtube/channels/{pk}` | 채널 삭제 (CASCADE로 관련 영상도 제거) | – | `204` |
| POST   | `/api/youtube/channels/{pk}/poll` | 즉시 폴링 트리거 | – | `202 {job_id}` |
| GET    | `/api/youtube/videos` | 영상 목록 (필터: channel_pk, tag, status, since) | – | 페이지네이션 응답 |
| GET    | `/api/youtube/videos/{video_pk}` | 영상 상세 (detail+summary+tags) | – | `{video, detail, summary, tags[]}` |
| POST   | `/api/youtube/videos/{video_pk}/reanalyze` | 재분석 트리거 | – | `202 {job_id}` |
| GET    | `/api/youtube/tags` | 태그 클라우드 (count) | – | `[{name, count, type}]` |
| GET    | `/api/youtube/jobs/logs` | 잡 로그 조회 | – | 페이지네이션 응답 |
| GET    | `/api/youtube/stats` | 운영 통계 | – | `{total, active, today, pending, failed, cost}` |

#### 4.1.3 채널 ID 추출 로직 (`youtube_api.py::resolve_channel`)

```python
async def resolve_channel(input_str: str) -> ChannelMeta:
    """
    1) 입력 문자열 정규화 (URL 파싱)
    2) 패턴 분기:
       - /channel/UC...  → UC ID 직접 사용
       - @handle 또는 /@handle  → channels?part=id&forHandle=@handle
       - /user/legacyName → channels?part=id&forUsername=legacyName
       - /c/customName   → search.list?q=customName&type=channel (fallback, quota↑)
    3) channels?part=snippet,contentDetails,statistics&id={UC_ID}
       에서 메타 + uploads playlist ID 추출
    4) ChannelMeta 반환
    """
```

> ⚠️ `/c/...` 커스텀 URL은 공식 API로 즉시 변환이 안 되어 `search.list`를 1회 호출(쿼터 100 unit). 가급적 `@handle` 입력을 권장하는 가이드 문구를 UI에 표시.

### 4.2 정기 폴링 (Polling Job)

#### 4.2.1 스케줄러 등록

`app/services/scheduler.py::setup_youtube_jobs()` 신규 메서드를 만들어 `main.py::startup_event`에서 호출.

- **단일 ‘마스터 폴링 잡’**을 12분마다 실행 (`IntervalTrigger(minutes=12)`).
- 마스터 잡은 DB의 활성 채널 중 `(now - last_checked_at) >= poll_interval_min` 인 채널만 골라 처리(채널별 `poll_interval_min` 존중).
- 채널 처리 단위는 `asyncio.gather`로 동시 실행하되, **최대 동시 실행 5개**(세마포어)로 YouTube API 쿼터 보호.

```python
# pseudo
@scheduler.scheduled_job(IntervalTrigger(minutes=12), id="youtube_master_poll")
async def youtube_master_poll():
    channels = await crud.list_due_channels(now=utcnow())
    sem = asyncio.Semaphore(5)
    async def _process(ch):
        async with sem:
            await monitor_service.process_channel(ch)
    await asyncio.gather(*[_process(c) for c in channels], return_exceptions=True)
```

> 채널별 ‘즉시 폴링’ 트리거(POST `/poll`)는 `DateTrigger(run_date=now)`로 별도 잡 등록 — 동일 코드 경로 재사용.

#### 4.2.2 폴링 알고리즘 (`monitor_service.process_channel`)

1. `playlistItems.list?playlistId={UU...}&maxResults=5&part=snippet,contentDetails` 호출. (최근 5개로 확대해 누락 방지)
2. 각 항목 `videoId`에 대해:
   - `youtube_videos`에 이미 존재하면 **skip**.
   - `published_at`가 `now - 24h` 이전이면 skip (백필 모드 OFF 시).
3. 신규 후보에 대해 `videos.list?id={ids}&part=snippet,contentDetails,statistics` 일괄 호출 (1회).
4. `youtube_videos` INSERT (`analysis_status='pending'`, `sequence_in_channel` 계산).
5. 채널 `last_checked_at`/`last_video_id` 갱신.
6. 신규 영상 각각에 대해 `analyze_video` 잡을 즉시 큐잉(아래 4.3).

> **백필 모드**: 신규 채널 등록 시 자동으로 1회만 ON. `published_at` 24시간 필터 우회, 최근 5개 영상 전부 분석.

### 4.3 영상 분석 파이프라인 (litellm Gateway 경유, v1.1)

#### 4.3.1 LLM 호출 경로

litellm은 **두 가지 인터페이스**를 동시에 노출함. 본 모듈은 둘 다 사용.

| 경로 | 용도 | URL 패턴 |
|------|------|----------|
| **A. Native Gemini 패스스루** | 영상 fileData 멀티모달 분석 (1순위) | `POST {base_url}/gemini/v1beta/models/{model}:generateContent?key={api_key}` |
| **B. OpenAI 호환 chat completions** | 텍스트 fallback, 태그 정제, 모델 교체 (Claude/GPT 등) | `POST {base_url}/v1/chat/completions` (`Authorization: Bearer {api_key}`) |

**선정 이유**:
- 경로 A는 기존 n8n에서 동일하게 사용 중이라 검증됨. fileData URL을 그대로 인식.
- 경로 B는 모델 교체 자유도 확보. 사용자가 Settings UI에서 `gemini/gemini-2.5-pro` → `claude-3-5-sonnet`으로 바꾸면 fallback/태깅 경로가 즉시 다른 모델로 라우팅.

```python
# llm_client.py 핵심 인터페이스
class LiteLLMClient:
    def __init__(self, settings: AIGatewaySettings):
        self.base_url = settings.base_url           # e.g. http://litellm:4000
        self.api_key = settings.api_key             # litellm Master Key (Fernet 복호화 후)
        self.client = httpx.AsyncClient(timeout=300.0)

    async def analyze_video_native(self, model: str, video_url: str, prompt: str,
                                   schema: dict) -> AnalyzerResult:
        """경로 A: Gemini fileData multimodal."""
        # model = 'gemini-2.5-flash' (litellm passthrough에서는 prefix 'gemini/' 없이)
        url = f"{self.base_url}/gemini/v1beta/models/{model}:generateContent"
        body = {
            "contents": [{"role": "user", "parts": [
                {"fileData": {"fileUri": video_url}},
                {"text": prompt}
            ]}],
            "generationConfig": {"responseMimeType": "application/json", "responseSchema": schema}
        }
        resp = await self.client.post(url, params={"key": self.api_key}, json=body)
        resp.raise_for_status()
        return _parse_gemini_response(resp.json())

    async def chat(self, model: str, messages: list[dict],
                   response_format: Optional[dict] = None) -> ChatResult:
        """경로 B: OpenAI 호환. fallback 분석 + 태그 정제용."""
        # model = 'gemini/gemini-2.5-flash' 혹은 'claude-3-5-sonnet' 등 litellm 라우팅 키
        body = {"model": model, "messages": messages}
        if response_format:
            body["response_format"] = response_format
        resp = await self.client.post(
            f"{self.base_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=body
        )
        resp.raise_for_status()
        return ChatResult.parse(resp.json())
```

#### 4.3.2 분석 엔진 선택 매트릭스

| 시나리오 | 경로 | 사용 모델 (예) | 비고 |
|----------|------|----------------|------|
| 일반 영상 분석 | A (native) | `primary_model` (예: `gemini-2.5-flash`) | 1순위 |
| fileData 거부 (private/지역제한) | B (openai) | `fallback_model` | transcript-api로 자막 추출 → 본문만 분석 |
| 60분 초과 영상 | A → 토큰 초과 시 B | primary → fallback | 챕터 분할 후 텍스트 분석 |
| 태그 정제 (동의어 통합) | B | `tagging_model` (저비용) | 신규 태그가 5개 이상일 때만 호출 |

> **운영 정책**: A 실패 시 자동 B로 폴백 → 둘 다 실패 시 `analysis_status='failed'`, `retry_count < 3` 동안 1시간 간격 재시도. 실패 사유는 `analysis_error`에 짧게, 전체 스택은 `youtube.job_logs`에 기록.

#### 4.3.3 분석 워크플로우 (`analyzer.analyze`)

```
[input]  video_pk, video_url, channel_name, published_at, settings_snapshot
   │
   ▼
[1] settings_manager.get_ai_gateway() → base_url, api_key, primary_model, …
   │
   ▼
[2] 경로 A 시도: llm_client.analyze_video_native(primary_model, video_url, prompt_v1.0)
   │
   ├── 성공 → [4]
   ├── 실패 (fileData rejected, INVALID_ARGUMENT, timeout 등)
   │     │
   │     ▼
   │   [3a] youtube-transcript-api로 자막 추출
   │     │
   │     ▼
   │   [3b] 경로 B: llm_client.chat(fallback_model, messages, response_format=json_schema)
   │     │
   │     ├── 성공 → [4]
   │     └── 실패 → analysis_status='failed', retry_count++, return
   │
   ▼
[4] 응답 검증 (필수 필드 7종, 토큰/길이 가드)
   │
   ▼
[5] PostgreSQL 트랜잭션:
    - youtube.video_details (full_*, model_name, gateway_url)
    - youtube.video_summaries (one_line, short_summary_md, …)
    - youtube.tags / youtube.video_tags (upsert)
    - youtube.videos.analysis_status='done'
   │
   ▼
[6] notify 잡 큐잉 (Telegram)
```

#### 4.3.4 모델 변경 시나리오

사용자가 Settings UI에서 `primary_model`을 `gemini-2.5-flash` → `gemini-2.5-pro`로 변경하면:

1. PATCH `/api/youtube/settings/ai_gateway/primary_model` 호출
2. `SettingsManager.invalidate_cache()` 실행 → 다음 분석부터 즉시 새 모델 적용
3. **이미 진행 중**인 분석은 기존 모델로 완료 (트랜잭션 보호)
4. UI에서 ‘테스트 호출’ 버튼으로 새 모델 즉시 검증 가능

> 모든 분석 결과의 `youtube.video_details.model_name`에 호출 시점 모델명을 저장. 같은 영상을 재분석하면 row가 **UPSERT** 되어 모델 비교 추적 가능 (선택: `analysis_history` 테이블로 분리하면 버전 비교 가능, 본 명세 범위 외).

#### 4.3.3 프롬프트 (v1.0)

````text
# 역할
당신은 한국어 콘텐츠를 분석하는 미디어 분석가입니다.

# 입력
- 채널: {channel_name}
- 업로드: {published_at_kst}
- 영상 URL: {video_url}

# 작업
이 영상을 시청자가 직접 보지 않아도 핵심을 파악할 수 있도록 분석하세요.
출력은 다음 JSON Schema를 준수하세요. 모든 텍스트는 한국어, '~함', '~임' 개조식으로 작성.

# JSON Schema (Gemini structured output)
{
  "one_line": "string (≤100자)",
  "headline": "string (이모지 1~2개 + 핵심 키워드, ≤40자)",
  "short_summary_md": "string (≤800자, Telegram HTML 허용)",
  "bullet_points": ["string 3~5개"],
  "full_analysis_md": "string (마크다운, 섹션: 한 줄 요약/주요 내용/결론 및 인사이트)",
  "key_points": [{"timestamp":"hh:mm:ss","point":"string"}],
  "insights": ["string"],
  "entities": [{"type":"person|company|ticker|metric","name":"string"}],
  "sentiment": "bullish|bearish|neutral|mixed",
  "tags": [{"name":"string","type":"topic|ticker|person|sector","weight":0.0~1.0}],
  "confidence_score": 0.0~1.0
}

# 제약
- bullet_points는 각 항목 80자 이내.
- tags는 5~10개, 한국어 정규화 (예: '미 연준' → '연준', 'TSM' → 'TSMC').
- 영상 길이가 60분 초과면 핵심 챕터별로 key_points 분할.
- 정치적·민감 주제는 사실 위주로 중립 표현.
````

#### 4.3.4 비용·쿼터 가드

- YouTube Data API: 일일 10,000 unit (기본). `playlistItems.list`=1, `videos.list`=1, `channels.list`=1. 채널 30개 × 12분 폴링 = 일 3,600 호출 ≈ 3,600 unit. 안전 마진 충분.
- Gemini Flash: 영상 1건당 평균 30k input + 4k output 토큰 가정 → 약 $0.0035/건. 일 50건 처리 시 $0.18.
- 환경변수로 일일 한도(`YOUTUBE_DAILY_QUOTA`, `GEMINI_DAILY_BUDGET_USD`) 설정. 초과 시 폴링 잡이 자동 SKIP하고 `youtube_job_logs`에 기록.

### 4.4 Telegram 발송 (`youtube_bot.py`)

#### 4.4.1 발송 포맷

```html
<b>🎬 [{channel_name}] 신규 영상</b>

<b>{headline}</b>

<i>{one_line}</i>

{short_summary_md}

🏷 {tags_joined}
📅 {published_at_kst}  ·  ⏱ {duration_human}

🔗 <a href="{video_url}">영상 보러가기</a>
```

#### 4.4.2 발송 정책

- 채널별 **알림 ON/OFF**(`youtube_channels.is_active`와 별도, 향후 `notify_enabled` 컬럼 추가 가능).
- 동일 video_pk에 대해 `notified_at IS NOT NULL` 이면 재발송 안 함.
- 4096자 초과 시 `short_summary_md`를 절단 후 “… (전체 보기)” 링크 부착.
- 배치 발송 시 채널 간 30초 wait (n8n 워크플로우 패턴 유지). 텔레그램 30 msg/sec rate limit 보호.

### 4.5 웹 UI (React SPA)

#### 4.5.1 라우팅 구조

| Path (SPA) | 설명 |
|------------|------|
| `/youtube/` | 대시보드 — 최근 24h 신규 영상, 채널 상태 카드, 처리 통계 |
| `/youtube/channels` | 채널 관리 — 추가 폼, 목록 테이블, 활성/주기/카테고리 인라인 편집 |
| `/youtube/videos` | 영상 목록 — 채널/태그/기간 필터, 분석 상태 배지, 상세 모달 |
| `/youtube/videos/:videoPk` | 영상 상세 — 상세 분석 마크다운 렌더, 요약 / 태그 / 메타 / 재분석 버튼 |
| `/youtube/tags` | 태그 클라우드 — 빈도순 + 클릭 시 해당 영상 필터 |
| `/youtube/jobs` | 잡 로그 — 최근 100건 (성공/실패/스킵) |

#### 4.5.2 핵심 화면 와이어프레임 (요약)

**채널 관리 화면**
```
┌─────────────────────────────────────────────────────────────────┐
│ + 채널 추가  [ @handle 또는 URL 입력 ___________ ] [추가]       │
├─────────────────────────────────────────────────────────────────┤
│ [✓] 활성 │ 채널명     │ 카테고리 │ 주기   │ 마지막 폴링 │ ⋮  │
│ [✓]      │ 서재형     │ 투자     │ 12h    │ 3분 전     │ ⋮  │
│ [✓]      │ 김영익     │ 경제     │ 12h    │ 11분 전    │ ⋮  │
│ [ ]      │ 홍춘욱     │ 경제     │ 24h    │ 5h 전      │ ⋮  │
└─────────────────────────────────────────────────────────────────┘
```

**영상 상세 화면**
```
┌─────────────────────────────────────────────────────────────────┐
│ 🎬 삼성전자 하이닉스 못 오른 진짜 이유                          │
│ 채널: 서재형  ·  업로드: 2026-05-07 18:00 KST  ·  15:03         │
│ 분석상태: ✅ done  [재분석]                                      │
├──────────────────────────────────┬──────────────────────────────┤
│ ## 한 줄 요약                    │ 알림 미리보기 (Telegram)     │
│ …                                │ ┌──────────────────────────┐ │
│ ## 주요 내용                     │ │ 🎬 [서재형] 신규 영상   │ │
│ - …                              │ │ … short summary …        │ │
│ ## 결론 및 인사이트              │ └──────────────────────────┘ │
│ - …                              │                              │
├──────────────────────────────────┴──────────────────────────────┤
│ 🏷 태그: 반도체, HBM, 삼성전자, 메모리                          │
│ 📊 sentiment: neutral  ·  confidence: 0.82                      │
└─────────────────────────────────────────────────────────────────┘
```

#### 4.5.3 인증 통합

- 기존 `AuthMiddleware`(세션 기반) 적용. `/youtube/*`도 자동 보호됨.
- React 앱은 `fetch('/api/youtube/...', { credentials: 'include' })`로 세션 쿠키 전달.
- React 빌드 산출물은 `app/static/youtube/`에 배치, FastAPI 라우트 `GET /youtube/{full_path:path}`가 `templates/youtube.html`(단일 셸)을 반환하여 SPA 클라이언트 라우팅 위임.

### 4.6 운영 가시성

- `/api/youtube/jobs/logs?limit=100` — 잡 로그 조회.
- `/api/youtube/stats` — `{ total_channels, active_channels, videos_today, videos_pending, videos_failed, llm_cost_today_usd, db_health, gateway_health }`.
- 기존 `/logs` 페이지에 youtube 카테고리 필터 추가 (Logs 모델은 그대로).

---

### 4.7 AI Gateway 설정 UI (v1.1)

#### 4.7.1 화면 (`/youtube/settings/ai-gateway`)

```
┌─ AI Gateway (litellm) ──────────────────────────────────────────┐
│                                                                 │
│  Base URL  [ http://litellm:4000           ]                    │
│  API Key   [ ●●●●●●●●●●●●●●●●  ] [표시] [재생성]                │
│  Status    🟢 연결됨   ·   응답 ms: 87   ·   모델 14개          │
│                                                                 │
│  ┌── 모델 선택 ──────────────────────────────────────────┐     │
│  │ Primary (멀티모달 영상)                                │     │
│  │   [ gemini-2.5-flash          ▼ ]                      │     │
│  │ Fallback (텍스트, fileData 거부 시)                    │     │
│  │   [ gemini/gemini-2.5-flash   ▼ ]                      │     │
│  │ Tagging (저비용)                                       │     │
│  │   [ gemini/gemini-2.5-flash   ▼ ]                      │     │
│  └────────────────────────────────────────────────────────┘     │
│                                                                 │
│  Temperature      [ 0.3 ]   Max tokens [ 8192 ]                 │
│  Daily budget USD [ 2.0 ]   오늘 사용  $0.18                    │
│                                                                 │
│  [연결 테스트]  [샘플 영상 분석 1회]  [저장]                    │
└─────────────────────────────────────────────────────────────────┘
```

#### 4.7.2 동작 사양

| 동작 | 설명 |
|------|------|
| **연결 테스트** | `GET {base_url}/v1/models` → 사용 가능 모델 목록을 가져와 드롭다운에 채움. 실패 시 빨간 배지와 응답 본문 표시 |
| **모델 드롭다운** | `/v1/models` 응답에서 `gemini/*`, `claude*`, `gpt*` 패턴을 카테고리화. 사용자가 리스트에 없는 모델명을 직접 입력 가능 (자유 입력 옵션) |
| **API Key 저장** | Fernet 암호화 후 `youtube_settings.value_enc`에 저장. UI는 마지막 4자만 마스킹 표시 |
| **샘플 영상 분석** | 미리 정의한 표본 video_url로 즉시 1회 분석 수행. 결과 미리보기를 모달로 표시(저장은 안 함) |
| **저장** | `PUT /api/youtube/settings/ai_gateway` → SQLite 업데이트 + `SettingsManager.invalidate_cache()` |
| **권한 가드** | 기존 `AuthMiddleware` 적용. 추가로 ‘민감설정 변경’은 admin 비밀번호 재입력 필요 (기존 `ADMIN_PASSWORD` 활용) |

#### 4.7.3 Settings API

| Method | Path | 설명 |
|--------|------|------|
| GET    | `/api/youtube/settings/ai_gateway` | 전체 설정 (api_key는 마스킹) |
| PUT    | `/api/youtube/settings/ai_gateway` | 일괄 업데이트 |
| POST   | `/api/youtube/settings/ai_gateway/test_connection` | `/v1/models` 호출 결과 |
| POST   | `/api/youtube/settings/ai_gateway/test_analyze` | 표본 영상 1회 분석 (저장 X) |
| GET    | `/api/youtube/settings/ai_gateway/models` | 게이트웨이가 라우팅 가능한 모델 목록 캐시 |

#### 4.7.4 캐시 / 무효화

`SettingsManager`는 60초 TTL 메모리 캐시. 변경 API 호출 시 즉시 무효화:

```python
class SettingsManager:
    _cache: dict[str, Any] = {}
    _cache_expiry: float = 0

    async def get_ai_gateway(self) -> AIGatewaySettings:
        if time.time() < self._cache_expiry and 'ai_gateway' in self._cache:
            return self._cache['ai_gateway']
        rows = await self.repo.fetch_category('ai_gateway')
        s = AIGatewaySettings.from_rows(rows, fernet=self.fernet)
        self._cache['ai_gateway'] = s
        self._cache_expiry = time.time() + 60
        return s

    def invalidate(self, category: str | None = None):
        if category is None:
            self._cache.clear()
        else:
            self._cache.pop(category, None)
        self._cache_expiry = 0
```

---

### 4.8 PostgreSQL 연결 설정 UI (v1.1)

#### 4.8.1 화면 (`/youtube/settings/database`)

```
┌─ Database (PostgreSQL) ─────────────────────────────────────────┐
│                                                                 │
│  Host       [ 192.168.1.10        ]   Port [ 5432 ]             │
│  Database   [ youtube_monitor     ]   Schema [ youtube ]        │
│  Username   [ ytmonitor           ]                             │
│  Password   [ ●●●●●●●●●●  ] [표시]                              │
│  SSL Mode   [ prefer ▼ ]   (disable / prefer / require)         │
│                                                                 │
│  Status     🟢 연결됨  ·  PG 14.10  ·  스키마 OK  ·  테이블 7   │
│             지연 ms: 4.2  ·  Pool: 3/10                         │
│                                                                 │
│  [연결 테스트]  [스키마 적용]  [백업 다운로드]  [저장]           │
│                                                                 │
│  ⚠️ DB 변경 시 신규 영상 데이터는 새 DB로 저장됩니다.            │
│     기존 데이터는 ‘스키마 적용 → 데이터 이관’ 마법사 사용.        │
└─────────────────────────────────────────────────────────────────┘
```

#### 4.8.2 동작 사양

| 동작 | 설명 |
|------|------|
| **연결 테스트** | DSN 조립 → `psycopg.AsyncConnection.connect()` → `SELECT version()` → 결과/지연 표시. 실제 엔진은 만들지 않음 |
| **스키마 적용** | 연결 성공 후 `migrations/youtube/001_init_schema.sql` + 후속 마이그레이션 순차 실행. `youtube.schema_migrations` 기준으로 멱등 |
| **저장** | SQLite `youtube_settings`에 평문/암호화 저장 → `DBEngineManager.recreate_engine()` 호출 → 다음 요청부터 새 엔진 사용 |
| **백업 다운로드** | `pg_dump --schema-only youtube`를 컨테이너에서 실행해 SQL 다운로드 (선택 기능, 후순위) |
| **연결 실패 모드** | 잡 스케줄러가 `db_health=False`로 인식하면 youtube 잡들을 자동 SKIP, UI 헤더에 빨간 경고 띠 표시 |

#### 4.8.3 동적 엔진 매니저 (`db_engine.py`)

```python
class DBEngineManager:
    _engine: Optional[AsyncEngine] = None
    _dsn_signature: Optional[str] = None  # DSN 변경 감지용 해시

    async def get_engine(self) -> AsyncEngine:
        cfg = await settings_manager.get_database()
        if not cfg.is_configured:
            raise DBNotConfiguredError("DB 설정이 없습니다. /youtube/settings/database 에서 설정하세요.")
        sig = cfg.signature()  # host:port:db:user:schema:sslmode
        if self._engine is None or sig != self._dsn_signature:
            await self._dispose_existing()
            self._engine = create_async_engine(
                cfg.dsn,
                pool_size=5, max_overflow=5, pool_pre_ping=True,
                connect_args={"server_settings": {"search_path": cfg.schema}}
            )
            self._dsn_signature = sig
            await self.health_check(self._engine)
        return self._engine

    async def recreate_engine(self):
        """설정 변경 시 호출. 다음 get_engine()이 새 엔진을 만들도록 시그니처 무효화."""
        await self._dispose_existing()
        self._dsn_signature = None
        settings_manager.invalidate('database')

    async def health_check(self, engine: AsyncEngine) -> bool:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
```

#### 4.8.4 Settings API

| Method | Path | 설명 |
|--------|------|------|
| GET    | `/api/youtube/settings/database` | 현재 설정 (password 마스킹) |
| PUT    | `/api/youtube/settings/database` | 일괄 업데이트 (자동으로 엔진 재생성) |
| POST   | `/api/youtube/settings/database/test_connection` | 연결 테스트 (DB 변경 없이 검증) |
| POST   | `/api/youtube/settings/database/apply_schema` | `migrations/youtube/*.sql` 순차 적용 + 결과 리턴 |
| GET    | `/api/youtube/settings/database/health` | 현재 엔진 상태, 지연 ms, pool 사용률 |

#### 4.8.5 보안 고려사항

- 비밀번호/API 키는 SQLite의 `value_enc` 컬럼에 Fernet 암호화로 저장. 키는 `.env`의 `YOUTUBE_SETTINGS_FERNET_KEY` (32바이트 base64 url-safe).
- 응답 직렬화 단계에서 `is_secret=1`인 항목은 마지막 4자만 노출 (`****abcd`).
- ‘민감설정 변경’ API는 admin 재인증 토큰(15분 유효) 요구.
- TLS는 `sslmode=require` 권장. 자체 CA 사용 시 `sslrootcert` 파일 경로를 `value`에 저장 가능.

---

### 4.9 폴링·알림 정책도 UI에서 (v1.1 보너스)

`youtube_settings.category='polling'/'notification'` 항목은 **`/youtube/settings/runtime`** 화면에서 일괄 편집 가능. 변경 즉시 마스터 잡의 다음 사이클부터 적용.

| Key | UI 컴포넌트 |
|-----|-------------|
| master_interval_min | Number Input (1~60) |
| default_channel_interval_min | Number Input (60~10080) |
| youtube_api_key | Secret Input |
| youtube_daily_quota | Number Input |
| max_concurrent_channels / max_concurrent_analyses | Slider (1~10) |
| telegram_enabled | Toggle |
| wait_between_messages_sec | Number Input (0~120) |
| low_confidence_threshold | Slider (0.0~1.0, 0.05 step) |

---

## 5. 비기능 요구사항 (NFR)

| 항목 | 요구 수준 |
|------|-----------|
| 가용성 | 기존 앱과 동일 (Watchtower 자동 재배포, restart=always) |
| 성능 | 마스터 폴링 1회 평균 < 30초 (채널 30개 기준) |
| 분석 SLA | 신규 영상 감지 후 평균 5분 이내 Telegram 발송 |
| 동시성 | 채널 폴링 동시 5개, 영상 분석 동시 3개 (세마포어) |
| 오류 복구 | 분석 실패 시 1h 간격 최대 3회 재시도, 그 이후 수동 재시도 버튼 |
| 보안 | API 키는 `.env` 사용, DB 평문 저장 금지. React 빌드 산출물에 키 노출 X |
| 로깅 | 모든 외부 호출은 `youtube_job_logs`에 status/duration_ms 기록 |
| 백업 | `data/assistant.db` Synology 자동 백업 대상에 포함 (기존 정책 준수) |
| 호환성 | Python 3.10+, Node 20+ |

---

## 6. 환경변수 (v1.1, `.env` 추가 항목)

> v1.1 원칙: **운영 중 자주 바뀌는 값은 UI(`youtube_settings`)**, **부트스트랩 단계에서 필요한 비밀(secret)만 `.env`**.

```bash
# --- 필수 ----------------------------------------------------------
# 설정 암호화 키 (32바이트 base64 url-safe)
# 생성: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
YOUTUBE_SETTINGS_FERNET_KEY=...

# 기존 my-assistant 항목 (그대로)
TELEGRAM_BOT_TOKEN=...
SECRET_KEY=...
SESSION_SECRET_KEY=...
ADMIN_USERNAME=admin
ADMIN_PASSWORD=...

# --- 선택 (UI 첫 실행 전 기본값 주입 용도) ---------------------------
# UI에서 비워두면 부트스트랩 시 이 값들이 youtube_settings에 시드됨
YOUTUBE_BOOTSTRAP_DB_HOST=
YOUTUBE_BOOTSTRAP_DB_PORT=5432
YOUTUBE_BOOTSTRAP_DB_NAME=youtube_monitor
YOUTUBE_BOOTSTRAP_DB_USER=
YOUTUBE_BOOTSTRAP_DB_PASSWORD=
YOUTUBE_BOOTSTRAP_DB_SCHEMA=youtube
YOUTUBE_BOOTSTRAP_DB_SSLMODE=prefer

YOUTUBE_BOOTSTRAP_LITELLM_BASE_URL=http://litellm:4000
YOUTUBE_BOOTSTRAP_LITELLM_API_KEY=
YOUTUBE_BOOTSTRAP_PRIMARY_MODEL=gemini-2.5-flash
YOUTUBE_BOOTSTRAP_FALLBACK_MODEL=gemini/gemini-2.5-flash
YOUTUBE_BOOTSTRAP_TAGGING_MODEL=gemini/gemini-2.5-flash

YOUTUBE_BOOTSTRAP_YOUTUBE_API_KEY=
```

> 위의 `BOOTSTRAP_*` 값은 **앱 첫 실행 시 1회만** `youtube_settings`에 시드되고, 이후에는 UI 변경이 우선됨. `.env`를 다시 바꿔도 `youtube_settings`에 이미 값이 있으면 덮어쓰지 않음. 명시적으로 `--reseed` 플래그로 실행해야 재시드.

`requirements.txt` 추가 (v1.1):

```
# AI Gateway / LLM
openai>=1.40.0                # litellm OpenAI 호환 경로용
httpx>=0.26.0                 # 기존, 명시
youtube-transcript-api>=0.6.2 # fallback용

# PostgreSQL
psycopg[binary]>=3.1.18
asyncpg>=0.29.0               # SQLAlchemy async 드라이버 호환

# Security
cryptography>=42.0.0          # Fernet 암호화

# 유틸
isodate>=0.6.1                # ISO 8601 duration 파싱
```

---

## 7. 개발 단계 / 마일스톤 (v1.1)

| Phase | 기간 | 산출물 | 완료 조건 |
|-------|------|--------|-----------|
| **P1. 설정·DB 인프라** | 3일 | `youtube_settings` 모델·시드, `SettingsManager`, `DBEngineManager`(PG 동적 엔진), Fernet 암호화, PG 마이그레이션 러너 | UI 없이도 SQLite에 설정 입력 → PG 엔진 정상 생성, `pytest tests/youtube/test_settings_manager.py` PASS |
| **P2. PG 스키마·모델** | 2일 | SQLAlchemy 모델 7종, `001_init_schema.sql`, schema_migrations 추적 | `apply_schema` 호출 시 7개 테이블 멱등 생성 |
| **P3. YouTube API 래퍼** | 2일 | `youtube_api.py`, 채널 resolver, playlist 폴러 | 30개 채널 수동 추가/조회 시나리오 동작 |
| **P4. LLM 클라이언트(litellm)** | 2일 | `llm_client.py` (경로 A/B), 모델 카탈로그 캐시, 비용 추적 | `/v1/models` 호출 + 표본 video 분석 성공 |
| **P5. 분석 파이프라인** | 3일 | `analyzer.py`, 프롬프트 v1.0, fallback 경로, 트랜잭션 저장 | 표본 10개 영상 분석 성공률 ≥ 90% |
| **P6. Monitor Service & Scheduler** | 2일 | `monitor_service.py`, APScheduler 통합, 동시성 가드 | `youtube_master_poll` 잡이 설정값 따라 동작 |
| **P7. Telegram 봇** | 1일 | `youtube_bot.py`, 포맷터, 실 발송 | 표본 영상 알림 메시지 수신 확인 |
| **P8. REST API** | 2일 | `routers/youtube.py`, Pydantic 스키마 (영상/채널/잡 + **settings**) | OpenAPI `/docs`에 `/api/youtube/*` 전부 노출 |
| **P9. React UI - 채널/영상** | 3일 | `/youtube`, `/channels`, `/videos`, `/videos/:pk` | 각 화면 E2E 시나리오 통과 |
| **P10. React UI - 설정 화면** | 3일 | `/settings/database`, `/settings/ai-gateway`, `/settings/runtime`, 연결 테스트 모달, 비밀 마스킹 | 모든 설정 항목 UI에서 변경/저장/적용 PASS |
| **P11. 운영 로그/통계** | 1일 | `/stats`, `/jobs` 페이지, 헬스 헤더 띠 | 대시보드 실시간 카운트 + 헬스 상태 표시 |
| **P12. 통합 테스트 & 문서** | 2일 | E2E 시나리오, 운영 가이드, README 업데이트 | 신규 설치 시나리오: ENV 0개 → UI에서 모두 설정 → 첫 영상 분석 PASS |

**총 예상**: 약 26 영업일 (≈ 5.5주, 1인 풀타임 기준). v1.0 대비 +7일은 설정 인프라 + 설정 UI에 투입.

> 권장: P1~P5까지 완료되면 ‘백엔드 단독 동작’ 가능. P6~P8로 자동화 완성. P9~P11로 UI 완성. 단계별 데모 가능.

---

## 8. 위험 요소 및 대응 (v1.1)

| 위험 | 영향 | 대응 |
|------|------|------|
| YouTube API 쿼터 초과 | 폴링 중단 | UI(`youtube_settings.polling.youtube_daily_quota`) 한도, 초과 시 자동 SKIP, 알림 1회 발송 |
| Gemini fileData 비공개/지역제한 영상 거부 | 분석 누락 | transcript-api → litellm OpenAI 호환 fallback, 그래도 실패 시 메타만 발송 |
| `published_at` 시간대 혼동 (UTC ↔ KST) | 중복/누락 | DB는 `TIMESTAMPTZ`(UTC) 저장, 표시·필터링 시 KST 변환 (`zoneinfo`) |
| LLM 환각/오정보 | 잘못된 알림 | `confidence_score` < `low_confidence_threshold`면 알림 본문에 ‘저신뢰도’ 배지, 수동 검토 큐 |
| **PostgreSQL 연결 끊김 (네트워크/서버 다운)** | 폴링·분석·UI 영상 페이지 모두 영향 | `pool_pre_ping=True`, 재시도(1초→3초→10초 백오프), `db_health=False`면 잡 자동 SKIP, UI 헤더에 빨간 띠 |
| **litellm Gateway 다운** | 분석 잡 실패 누적 | 헬스체크 별도 잡(5분 주기) `GET /v1/models`, 실패 시 분석 잡 일시 정지, 복구 시 자동 재개 |
| **잘못된 API 키/모델명을 UI에 저장** | 분석 전부 실패 | 저장 전 강제 ‘연결 테스트’ + ‘샘플 분석’ 통과 시에만 PUT 허용 (강한 검증 모드 옵션) |
| **Fernet 키 분실** | 모든 secret 복호화 불가 | `.env`에서 키 분리 + 1Password/Bitwarden 백업 권장. UI에서 ‘키 회전’ 시 모든 secret 재암호화 |
| 기존 APScheduler Job Store(SQLite)에 youtube job 폭증 | 성능 저하 | youtube 잡은 별도 jobstore key(`'youtube'`) 분리, 정기 housekeeping(7일 이상 완료된 DateTrigger 잡 정리) |
| **두 DB(SQLite/PG) 트랜잭션 불일치** | 알림은 갔는데 PG 저장 실패 | 발송은 PG 트랜잭션 커밋 후에만 수행. ‘이미 분석됐는데 알림 안 감’ 케이스는 `notified_at IS NULL`로 재발송 가능 |
| React 빌드 실수로 운영 페이지 깨짐 | UX 저하 | `app/static/youtube/` 빌드는 별도 Dockerfile stage로 격리, 실패 시 이미지 빌드 중단 |
| **마이그레이션 중 사용자 PG 권한 부족** | `CREATE SCHEMA` 실패 | UI에서 필요 권한 목록(`CREATE`, `CONNECT`, `USAGE`, `INSERT/UPDATE/DELETE`) 안내 + 사전 점검 쿼리 제공 |

---

## 9. 향후 확장 (Out of Scope, 메모)

- **인사이트 검색**: 태그·엔티티·키포인트 기반 풀텍스트 검색 (SQLite FTS5).
- **Expert 매핑**: 기존 `economist_claims` 테이블 마이그레이션, 채널 ↔ expert 연결.
- **요약 다이제스트**: 일일/주간 모든 신규 영상 통합 요약을 별도 알림으로 발송.
- **다국어 지원**: 영문 채널 추가 시 한국어 번역 옵션.
- **PostgreSQL 이관**: 영상 데이터 누적 100k 건 초과 시 SQLite → PostgreSQL.
- **Web Push**: Telegram 외 브라우저 알림.

---

## 10. 부록

### 10.1 신규 파일 체크리스트 (v1.1)

```
[ ] app/models/youtube_setting.py            (SQLite — 설정)
[ ] app/models/youtube_channel.py            (PostgreSQL — youtube.channels)
[ ] app/models/youtube_video.py              (PostgreSQL — youtube.videos)
[ ] app/models/youtube_video_detail.py
[ ] app/models/youtube_video_summary.py
[ ] app/models/youtube_tag.py
[ ] app/models/youtube_video_tag.py
[ ] app/models/youtube_job_log.py
[ ] app/schemas/youtube.py                   (Pydantic, 영상/채널/잡)
[ ] app/schemas/youtube_settings.py          (Pydantic, 설정 + 검증 + 마스킹)
[ ] app/routers/youtube.py                   (/api/youtube/*)
[ ] app/services/youtube/__init__.py
[ ] app/services/youtube/settings_manager.py (Fernet 암호화, 캐시)
[ ] app/services/youtube/db_engine.py        (PG 동적 엔진)
[ ] app/services/youtube/llm_client.py       (litellm: native + openai 호환)
[ ] app/services/youtube/youtube_api.py
[ ] app/services/youtube/analyzer.py         (구 gemini_analyzer.py)
[ ] app/services/youtube/monitor_service.py
[ ] app/services/youtube/tag_extractor.py
[ ] app/services/bots/youtube_bot.py
[ ] app/templates/youtube.html               (React SPA 셸)
[ ] app/static/youtube/                       (Vite 빌드 산출물)
[ ] frontend/youtube/                         (React 소스)
[ ] migrations/youtube/000_sqlite_settings.sql
[ ] migrations/youtube/000_seed_settings.sql
[ ] migrations/youtube/001_init_schema.sql   (PostgreSQL 7개 테이블)
[ ] migrations/youtube/002_indexes.sql       (선택, 추가 인덱스)
[ ] tests/youtube/test_settings_manager.py
[ ] tests/youtube/test_db_engine.py
[ ] tests/youtube/test_llm_client.py
[ ] tests/youtube/test_models.py
[ ] tests/youtube/test_youtube_api.py
[ ] tests/youtube/test_analyzer.py
[ ] tests/youtube/test_monitor_service.py
[ ] tests/youtube/test_router.py
[ ] tests/youtube/test_settings_router.py
[ ] docs/youtube_monitor_spec.md             (본 문서)
[ ] .env.example                             (FERNET_KEY 등 추가)
[ ] requirements.txt                         (psycopg, openai, cryptography 등 추가)
[ ] docker-compose.yml                       (필요 시 frontend build stage)
```

### 10.2 기존 파일 수정 사항 (v1.1)

| 파일 | 변경 내용 |
|------|-----------|
| `app/main.py` | `from app.routers import youtube` 추가, `app.include_router(youtube.router)` 추가, `startup_event`에서 `youtube_settings_seed()` + `scheduler_service.setup_youtube_jobs()` 호출 |
| `app/database.py` | `init_db()`에 `youtube_setting` 모델 임포트, `run_migrations()`에 `_migrate_youtube_settings()` 추가 |
| `app/config.py` | `YOUTUBE_SETTINGS_FERNET_KEY` 추가, BOOTSTRAP_* 시드 변수 로딩 |
| `app/services/scheduler.py` | `setup_youtube_jobs()` 추가 (마스터 폴링 + 게이트웨이 헬스체크), `youtube` jobstore 분리 |
| `app/templates/base.html` | 좌측 네비게이션에 "YouTube 모니터" 메뉴 추가 |
| `requirements.txt` | psycopg[binary], asyncpg, openai, cryptography, youtube-transcript-api, isodate 추가 |
| `Dockerfile` / `docker-compose.yml` | (선택) Node 20 multi-stage build로 React 빌드 단계 추가 |
| `.env.example` | 6장의 BOOTSTRAP_* 항목 추가, FERNET_KEY 생성 안내 주석 추가 |

### 10.3 n8n 워크플로우 마이그레이션 노트

| n8n 노드 | 신규 모듈 대응 |
|----------|-----------------|
| Schedule Trigger (08/14/20) | APScheduler `IntervalTrigger(minutes=12)` (더 촘촘하게) |
| SQL Query (활성 채널 스크리닝) | `crud.list_due_channels()` |
| HTTP Request (영상정보 추출) | `youtube_api.get_latest_videos()` |
| Execute SQL (중복 체크) | `crud.video_exists(video_id)` |
| If (12h 이내 + 미존재) | `monitor_service.process_channel()` 내부 분기 |
| HTTP Request (Gemini 분석) | `gemini_analyzer.analyze()` (직접 SDK 사용으로 단순화) |
| If (Gemini 오류) | try/except + retry_count |
| Postgres Insert | `crud.save_analysis_result()` (트랜잭션 1건으로 4개 테이블 동시 커밋) |
| Telegram Send | `youtube_bot.notify()` |
| Wait 30s | `asyncio.sleep(30)` (배치 간) |

### 10.4 첫 설치 시나리오 (v1.1)

1. 운영자가 `.env`에 **`YOUTUBE_SETTINGS_FERNET_KEY`** 만 채우고 컨테이너 재시작.
2. 브라우저로 `/youtube` 접속. ‘초기 설정 필요’ 카드 표시.
3. **`/youtube/settings/database`**: PG 호스트/포트/계정 입력 → ‘연결 테스트’ → ‘스키마 적용’ → ‘저장’.
4. **`/youtube/settings/ai-gateway`**: litellm Base URL/Key 입력 → ‘연결 테스트’(모델 목록 자동 채움) → 모델 선택 → ‘샘플 분석’ → ‘저장’.
5. **`/youtube/settings/runtime`**: YouTube API Key 입력 → 폴링/알림 옵션 확인.
6. **`/youtube/channels`**: 첫 채널(`@김영익` 등) 추가 → ‘즉시 폴링’ 체크.
7. 수 분 내 첫 영상 분석 결과가 Telegram으로 도착하면 설치 완료.

### 10.5 샘플 통합 흐름 (Sequence)

```
User              FastAPI          Scheduler         YouTube API     Gemini       Telegram
 │  추가 @서재형 │                │                 │                │            │
 ├──────────────▶│ POST /channels │                │                │            │
 │               │ resolve_channel ──────────────▶ │                │            │
 │               │ ◀───────────────────────────────│                │            │
 │               │ INSERT channel │                │                │            │
 │               │ poll_now (async)                │                │            │
 │               │ ───────────────▶│ run_date=now  │                │            │
 │               │                 │ playlistItems─▶│                │            │
 │               │                 │ ◀──────────────│                │            │
 │               │                 │ INSERT video (status=pending) │            │
 │               │                 │ analyze_video ──────────────────▶ │          │
 │               │                 │ ◀────────────────────────────────│           │
 │               │                 │ INSERT details/summary/tags    │            │
 │               │                 │ youtube_bot.notify ──────────────────────────▶│
 │               │                 │                 │                │  ✉ 수신   │
 │               │                 │ UPDATE notified_at              │            │
```

---

**문서 끝.** 본 명세서는 P1~P9 단계로 분할 구현하며, 각 Phase 종료 시점에 사용자 승인 후 다음 Phase 진행을 권장함 (`CLAUDE.md` 규칙 준수).
