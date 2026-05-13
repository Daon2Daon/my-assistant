# YouTube 자동 모니터링 모듈 구현 계획서 (v1.1)

> **참조 명세서**: `docs/youtube_monitor_spec.md`
> **대상 앱**: `my-assistant` (FastAPI)
> **작성일**: 2026-05-11
> **총 예상 기간**: 약 26 영업일 (5.5주, 1인 풀타임 기준)

---

## 구현 원칙

- 각 Phase 완료 후 사용자 확인을 받고 다음 Phase 진행
- P1~P5 완료 시 백엔드 단독 동작 가능 (중간 데모 가능)
- P6~P8 완료 시 자동화 파이프라인 완성
- P9~P11 완료 시 웹 UI 완성
- 기존 `my-assistant` 앱의 기능을 해치지 않는 무중단 추가 원칙

---

## Phase 1. 설정 인프라 (SQLite + Fernet 암호화)

> **목표**: UI 없이도 SQLite에 설정 입력 시 PG 엔진 정상 생성되는 설정 기반 구축
> **예상 기간**: 3일

### 1.1 환경 변수 및 의존성

- [ ] `requirements.txt`에 신규 패키지 추가
  - `psycopg[binary]>=3.1.18`
  - `asyncpg>=0.29.0`
  - `openai>=1.40.0`
  - `cryptography>=42.0.0`
  - `youtube-transcript-api>=0.6.2`
  - `isodate>=0.6.1`
- [ ] `app/config.py`에 신규 환경변수 추가
  - `YOUTUBE_SETTINGS_FERNET_KEY`
  - `YOUTUBE_BOOTSTRAP_*` 시드 변수 (DB, litellm, API 키)
- [ ] `.env.example`에 신규 항목 추가 및 FERNET_KEY 생성 안내 주석 작성

### 1.2 SQLite 설정 모델 및 마이그레이션

- [ ] `app/models/youtube_setting.py` 생성 (SQLite `youtube_settings` 테이블 SQLAlchemy 모델)
- [ ] `migrations/youtube/000_sqlite_settings.sql` 작성 (`youtube_settings` DDL)
- [ ] `migrations/youtube/000_seed_settings.sql` 작성 (기본값 INSERT 시드 데이터)
- [ ] `app/database.py`의 `run_migrations()`에 `_migrate_youtube_settings()` 블록 추가
  - 테이블 미존재 시 DDL + 시드 적용
  - `YOUTUBE_BOOTSTRAP_*` 환경변수 값이 있으면 설정에 반영 (1회만)

### 1.3 SettingsManager 구현

- [ ] `app/services/youtube/__init__.py` 생성 (패키지 초기화)
- [ ] `app/services/youtube/settings_manager.py` 구현
  - Fernet 암호화/복호화 (`YOUTUBE_SETTINGS_FERNET_KEY` 사용)
  - 카테고리별 설정 조회 (`get_database()`, `get_ai_gateway()`, `get_polling()`, `get_notification()`)
  - 메모리 캐시 (60초 TTL) + `invalidate(category)` 메서드
  - `is_secret=1` 항목 자동 Fernet 처리
  - `AIGatewaySettings`, `DatabaseSettings`, `PollingSettings`, `NotificationSettings` 데이터 클래스

### 1.4 테스트

- [ ] `tests/youtube/test_settings_manager.py` 작성
  - Fernet 암호화/복호화 왕복 테스트
  - 캐시 TTL 및 무효화 동작 테스트
  - 설정 카테고리별 CRUD 테스트

---

## Phase 2. PostgreSQL 스키마 및 SQLAlchemy 모델

> **목표**: `apply_schema` 호출 시 PG에 7개 테이블 멱등 생성
> **예상 기간**: 2일

### 2.1 마이그레이션 스크립트

- [ ] `migrations/youtube/001_init_schema.sql` 작성
  - `youtube` 스키마 생성
  - `set_updated_at()` 트리거 함수
  - `youtube.channels` 테이블 + 인덱스 + 트리거
  - `youtube.videos` 테이블 + 인덱스 + 트리거
  - `youtube.video_details` 테이블 + 인덱스
  - `youtube.video_summaries` 테이블
  - `youtube.tags` 테이블
  - `youtube.video_tags` 중간 테이블 + 인덱스
  - `youtube.job_logs` 테이블 + 인덱스
  - `youtube.schema_migrations` 버전 추적 테이블
- [ ] `migrations/youtube/002_indexes.sql` 작성 (추가 성능 인덱스, 선택)

### 2.2 DBEngineManager 구현

- [ ] `app/services/youtube/db_engine.py` 구현
  - `DBEngineManager` 싱글톤 클래스
  - `get_engine()`: 설정 변경 감지 시 엔진 재생성 (DSN 시그니처 비교)
  - `recreate_engine()`: 설정 변경 후 강제 재생성
  - `health_check()`: `SELECT 1` 연결 확인
  - `ensure_schema()`: `migrations/youtube/*.sql` 순차 적용 (schema_migrations 추적)
  - `DBNotConfiguredError` 예외 클래스
  - `pool_size=5, max_overflow=5, pool_pre_ping=True` 설정
  - `search_path` 를 `youtube` 스키마로 고정

### 2.3 SQLAlchemy ORM 모델 (PostgreSQL)

- [ ] `app/models/youtube_channel.py` (PG `youtube.channels` 매핑)
- [ ] `app/models/youtube_video.py` (PG `youtube.videos` 매핑, `analysis_status` Enum)
- [ ] `app/models/youtube_video_detail.py` (PG `youtube.video_details` 매핑, JSONB 필드)
- [ ] `app/models/youtube_video_summary.py` (PG `youtube.video_summaries` 매핑)
- [ ] `app/models/youtube_tag.py` (PG `youtube.tags` 매핑)
- [ ] `app/models/youtube_video_tag.py` (PG `youtube.video_tags` M:N 중간 테이블)
- [ ] `app/models/youtube_job_log.py` (PG `youtube.job_logs` 매핑)

### 2.4 테스트

- [ ] `tests/youtube/test_db_engine.py` 작성
  - DSN 시그니처 변경 시 엔진 재생성 테스트
  - `ensure_schema()` 멱등성 테스트 (2회 실행해도 오류 없음)
- [ ] `tests/youtube/test_models.py` 작성
  - 각 모델 INSERT/SELECT 기본 동작 테스트

---

## Phase 3. YouTube Data API 래퍼

> **목표**: 채널 resolver + playlist 폴러 동작, 30개 채널 수동 추가/조회 시나리오 통과
> **예상 기간**: 2일

### 3.1 YouTube API 클라이언트 구현

- [ ] `app/services/youtube/youtube_api.py` 구현
  - `resolve_channel(input_str)`: 다양한 입력 형태를 채널 ID로 정규화
    - `/channel/UC...` : 직접 사용
    - `@handle` / `/@handle` : `channels?forHandle=` API 호출
    - `/user/legacyName` : `channels?forUsername=` API 호출
    - `/c/customName` : `search.list` fallback (쿼터 100 unit 경고 UI 표시)
  - `get_channel_meta(channel_id)`: 채널 메타정보 조회 (이름, 썸네일, 업로드 플레이리스트 ID)
  - `get_latest_videos(playlist_id, max_results=5)`: `playlistItems.list` 호출
  - `get_video_details(video_ids: list)`: `videos.list` 일괄 호출
  - `ChannelMeta`, `VideoMeta` 데이터 클래스 정의
  - YouTube API 키는 `SettingsManager.get_polling()` 에서 런타임 로딩
  - 일일 쿼터 사용량 추적 및 한도 초과 시 `QuotaExceededError` 발생

### 3.2 테스트

- [ ] `tests/youtube/test_youtube_api.py` 작성
  - `resolve_channel()` 각 URL 패턴 단위 테스트 (실제 API 호출 없이 httpx mock 사용)
  - `get_latest_videos()` 응답 파싱 테스트

---

## Phase 4. LLM 클라이언트 (litellm Gateway)

> **목표**: `/v1/models` 호출 + 표본 video 분석 성공
> **예상 기간**: 2일

### 4.1 LiteLLMClient 구현

- [ ] `app/services/youtube/llm_client.py` 구현
  - `LiteLLMClient` 클래스 (httpx.AsyncClient, timeout=300)
  - **경로 A**: `analyze_video_native(model, video_url, prompt, schema)`
    - `POST {base_url}/gemini/v1beta/models/{model}:generateContent?key={api_key}`
    - `fileData` 멀티모달 입력 구성
    - `responseMimeType: application/json` + `responseSchema` 사용
  - **경로 B**: `chat(model, messages, response_format=None)`
    - `POST {base_url}/v1/chat/completions` (OpenAI 호환)
    - `Authorization: Bearer {api_key}`
  - `get_available_models()`: `/v1/models` 호출, `gemini/`, `claude`, `gpt` 카테고리화
  - `AnalyzerResult`, `ChatResult` 응답 파싱 데이터 클래스
  - 비용 추적: `token_input`, `token_output`, `cost_usd` 계산
  - 일일 예산 한도(`daily_budget_usd`) 초과 시 `BudgetExceededError` 발생

### 4.2 테스트

- [ ] `tests/youtube/test_llm_client.py` 작성
  - 경로 A/B 응답 파싱 단위 테스트 (httpx mock)
  - 비용 계산 로직 테스트
  - 예산 초과 예외 발생 테스트

---

## Phase 5. 영상 분석 파이프라인

> **목표**: 표본 10개 영상 분석 성공률 >= 90%
> **예상 기간**: 3일

### 5.1 분석 엔진 구현

- [ ] `app/services/youtube/analyzer.py` 구현
  - `analyze(video_pk, video_url, channel_name, published_at, settings_snapshot)` 메인 함수
  - **[1] 설정 로딩**: `SettingsManager.get_ai_gateway()`
  - **[2] 경로 A 시도**: `LiteLLMClient.analyze_video_native(primary_model, ...)`
  - **[3a] Fallback**: `youtube-transcript-api`로 자막 추출 (경로 A 실패 시)
  - **[3b] 경로 B**: `LiteLLMClient.chat(fallback_model, ...)` (자막 기반 텍스트 분석)
  - **[4] 응답 검증**: 필수 필드 7종 확인, 토큰/길이 가드
  - **[5] DB 트랜잭션**: `video_details`, `video_summaries`, `tags`, `video_tags` 동시 커밋
  - **[6] 알림 큐잉** 호출
  - 프롬프트 v1.0 (명세서 4.3.3 기준): `PROMPT_V1_0` 상수로 관리
  - `analysis_status` 관리: `pending` → `processing` → `done` / `failed`
  - 실패 시 `retry_count++`, `analysis_error` 기록
  - 60분 초과 영상: 챕터 분할 후 텍스트 분석 처리

### 5.2 태그 추출기 구현

- [ ] `app/services/youtube/tag_extractor.py` 구현
  - `extract_and_normalize(raw_tags: list, existing_tags: list)` 함수
  - 신규 태그 5개 이상일 때 LLM 경로 B로 동의어 통합 (`tagging_model` 사용)
  - 한국어 정규화 규칙: `'미 연준' → '연준'`, `'TSM' → 'TSMC'` 등
  - `youtube.tags` upsert + `youtube.video_tags` INSERT

### 5.3 테스트

- [ ] `tests/youtube/test_analyzer.py` 작성
  - 경로 A 성공 시나리오 (mock LLM 응답 사용)
  - 경로 A 실패 → 경로 B fallback 시나리오
  - 필수 필드 누락 시 검증 실패 처리 테스트
  - `retry_count` 증가 동작 테스트

---

## Phase 6. 모니터링 서비스 및 스케줄러 통합

> **목표**: `youtube_master_poll` 잡이 설정값 따라 동작
> **예상 기간**: 2일

### 6.1 MonitorService 구현

- [ ] `app/services/youtube/monitor_service.py` 구현
  - `process_channel(channel)`: 채널 단위 폴링 + 분석 큐잉 오케스트레이터
    1. `playlistItems.list` (최근 5개)
    2. `video_exists()` 중복 확인
    3. `published_at >= now - window_hours` 필터 (백필 모드 ON 시 우회)
    4. `videos.list` 일괄 메타 조회
    5. `youtube.videos` INSERT (`sequence_in_channel` 계산)
    6. `last_checked_at`, `last_video_id` 갱신
    7. 신규 영상마다 `analyze_video` 비동기 태스크 큐잉
  - `list_due_channels()`: `(now - last_checked_at) >= poll_interval_min` 인 활성 채널 조회
  - 백필 모드: 신규 채널 등록 시 1회 ON (최근 5개 전부 처리)
  - `DBNotConfiguredError` 및 `QuotaExceededError` 우아한 처리

### 6.2 스케줄러 통합

- [ ] `app/services/scheduler.py`에 `setup_youtube_jobs()` 추가
  - `youtube_master_poll` 잡: `IntervalTrigger(minutes=master_interval_min)`
    - `asyncio.Semaphore(max_concurrent_channels)` 동시성 제어
    - `asyncio.gather(*[_process(c) for c in due_channels], return_exceptions=True)`
  - `youtube_gateway_health` 잡: 5분 주기, `/v1/models` 헬스체크
    - 실패 시 `db_health=False` 플래그 → 분석 잡 자동 SKIP
  - `youtube` jobstore 분리 키 사용
  - 주기 변경 시 기존 잡 reschedule (settings 변경 API 호출 시)
- [ ] `app/main.py`에 `startup_event`에서 `setup_youtube_jobs()` 호출 추가
  - `youtube_settings_seed()` 호출 (첫 실행 시 시드)

### 6.3 테스트

- [ ] `tests/youtube/test_monitor_service.py` 작성
  - `list_due_channels()` 주기 필터 동작 테스트
  - 중복 비디오 skip 동작 테스트
  - `sequence_in_channel` 순번 계산 테스트

---

## Phase 7. Telegram 알림 봇

> **목표**: 표본 영상 알림 메시지 수신 확인
> **예상 기간**: 1일

### 7.1 YouTubeBot 구현

- [x] `app/services/bots/youtube_bot.py` 구현
  - `YoutubeBot` 클래스 (기존 봇 패턴 계승)
  - `notify(video_pk)`: 발송 포맷 조합 + Telegram 발송
    - 발송 포맷 (명세서 4.4.1 HTML 형식 준수)
    - `notified_at IS NOT NULL` 이면 재발송 차단
    - 4096자 초과 시 `short_summary_md` 절단 + "... (전체 보기)" 링크
    - `confidence_score < low_confidence_threshold` 이면 '저신뢰도' 배지 추가
  - `notify_batch(video_pks: list)`: 채널 간 30초 wait 배치 발송
  - `format_duration(seconds)`: `"15:03"` 형태 변환
  - `format_published_at_kst(dt)`: KST 변환 + `"2026-05-07 18:00 KST"` 포맷

---

## Phase 8. REST API 라우터

> **목표**: OpenAPI `/docs`에 `/api/youtube/*` 전체 엔드포인트 노출
> **예상 기간**: 2일

### 8.1 Pydantic 스키마 정의

- [x] `app/schemas/youtube.py` 작성 (영상/채널/잡 스키마)
  - `ChannelCreate`, `ChannelUpdate`, `ChannelResponse`
  - `VideoResponse`, `VideoDetailResponse` (페이지네이션 포함)
  - `TagResponse`, `JobLogResponse`, `StatsResponse`
- [x] `app/schemas/youtube_settings.py` 작성 (설정 스키마)
  - `DatabaseSettingsResponse` (password 마스킹)
  - `AIGatewaySettingsResponse` (api_key 마스킹, 마지막 4자만 노출)
  - `DatabaseSettingsUpdate`, `AIGatewaySettingsUpdate`
  - `ConnectionTestResponse`, `SchemaApplyResponse`

### 8.2 채널/영상/태그/잡 API

- [x] `app/routers/youtube.py` 구현 (`/api/youtube/*`)
  - `GET /api/youtube/channels` - 전체 채널 목록
  - `POST /api/youtube/channels` - 채널 추가 (resolve_channel + auto_poll_now 지원)
  - `PATCH /api/youtube/channels/{pk}` - 활성/주기/카테고리 수정
  - `DELETE /api/youtube/channels/{pk}` - 채널 삭제 (CASCADE)
  - `POST /api/youtube/channels/{pk}/poll` - 즉시 폴링 트리거 (`202 {job_id}`)
  - `GET /api/youtube/videos` - 영상 목록 (channel_pk, tag, status, since 필터 + 페이지네이션)
  - `GET /api/youtube/videos/{video_pk}` - 영상 상세 (detail + summary + tags)
  - `POST /api/youtube/videos/{video_pk}/reanalyze` - 재분석 트리거
  - `GET /api/youtube/tags` - 태그 클라우드 (count 포함)
  - `GET /api/youtube/jobs/logs` - 잡 로그 조회 (페이지네이션)
  - `GET /api/youtube/stats` - 운영 통계

### 8.3 설정 API

- [x] 설정 엔드포인트를 `app/routers/youtube.py`에 통합 (`/api/youtube/settings/*`)
  - `GET/PUT /api/youtube/settings/database`
  - `POST /api/youtube/settings/database/test_connection`
  - `POST /api/youtube/settings/database/apply_schema`
  - `GET /api/youtube/settings/database/health`
  - `GET/PUT /api/youtube/settings/ai_gateway`
  - `POST /api/youtube/settings/ai_gateway/test_connection`
  - `POST /api/youtube/settings/ai_gateway/test_analyze`
  - `GET /api/youtube/settings/ai_gateway/models`
  - `GET/PUT /api/youtube/settings/runtime` (polling + notification 통합)
  - 민감 설정 변경 시 admin 재인증 토큰 검증 (기존 `ADMIN_PASSWORD` 활용)

### 8.4 앱 등록

- [x] `app/main.py`에 YouTube 라우터 등록
  - `from app.routers import youtube`
  - `app.include_router(youtube.router)`
  - SPA 셸 라우트: `GET /youtube/{full_path:path}` → `templates/youtube.html` 반환

### 8.5 테스트

- [x] `tests/youtube/test_router.py` 작성
  - 채널 CRUD API 테스트 (mock DB 사용)
  - 영상 목록 페이지네이션 테스트
- [x] `tests/youtube/test_settings_router.py` 작성
  - 설정 조회/수정 API 테스트
  - 민감 정보 마스킹 검증

---

## Phase 9. React UI - 채널/영상 화면

> **목표**: 채널 관리, 영상 목록, 영상 상세 E2E 시나리오 통과
> **예상 기간**: 3일

### 9.1 React 프로젝트 초기화

- [x] `frontend/youtube/` Vite + React 18 + Tailwind CSS 프로젝트 생성
  - `frontend/youtube/package.json`
  - `frontend/youtube/vite.config.ts` (빌드 출력: `../../app/static/youtube/`)
  - Tailwind CSS 설정
  - `fetch` 기반 API 클라이언트 (`credentials: 'include'` 포함)

### 9.2 공통 컴포넌트

- [x] 레이아웃 컴포넌트 (사이드바 네비게이션)
- [x] 로딩 스피너, 에러 배너 컴포넌트
- [x] 배지 컴포넌트 (분석 상태: pending/processing/done/failed)
- [x] 페이지네이션 컴포넌트

### 9.3 대시보드 (`/youtube/`)

- [x] 최근 24시간 신규 영상 카드 목록
- [x] 채널 상태 요약 카드 (활성/비활성 채널 수)
- [x] 처리 통계 (오늘 처리 수, 대기 중, 실패, LLM 비용)
- [x] DB/Gateway 연결 상태 헬스 배너

### 9.4 채널 관리 (`/youtube/channels`)

- [x] 채널 추가 폼 (URL/핸들/ID 입력, 카테고리, 폴링 주기, 즉시 폴링 옵션)
- [x] 채널 목록 테이블 (활성 토글, 주기 인라인 편집, 마지막 폴링 시간, 즉시 폴링 버튼)
- [x] 채널 삭제 확인 모달

### 9.5 영상 목록 (`/youtube/videos`)

- [x] 필터 바 (채널 선택, 태그 선택, 기간, 분석 상태)
- [x] 영상 카드 목록 (썸네일, 제목, 채널명, 업로드 시간, 분석 상태 배지, 태그)
- [x] 페이지네이션

### 9.6 영상 상세 (`/youtube/videos/:videoPk`)

- [x] 상세 분석 마크다운 렌더링 (react-markdown)
- [x] Telegram 알림 미리보기 패널
- [x] 태그 목록, sentiment/confidence 표시
- [x] 재분석 버튼 + 진행 상태 표시

### 9.7 태그 클라우드 (`/youtube/tags`)

- [x] 빈도순 태그 클라우드 렌더링
- [x] 태그 클릭 시 해당 태그 영상 목록으로 이동

### 9.8 SPA 셸 및 서빙 설정

- [x] `app/routers/pages.py`에 `/youtube/{full_path}` → `app/static/youtube/index.html` FileResponse 라우트 추가
- [x] `app/templates/base.html` 네비게이션에 "YouTube 모니터" 메뉴 추가

---

## Phase 10. React UI - 설정 화면

> **목표**: 모든 설정 항목 UI에서 변경/저장/적용 PASS
> **예상 기간**: 3일

### 10.1 PostgreSQL 연결 설정 (`/youtube/settings/database`)

- [x] 연결 정보 입력 폼 (Host, Port, Database, Schema, Username, Password, SSL Mode)
- [x] '연결 테스트' 버튼 + 결과 표시 (버전, 지연 ms, Pool 상태)
- [x] '스키마 적용' 버튼 + 진행 로그 스트리밍 표시
- [x] 저장 버튼 + 변경 경고 메시지 ("신규 데이터는 새 DB로 저장됩니다")
- [x] 연결 실패 시 빨간 헤더 배너 표시

### 10.2 AI Gateway 설정 (`/youtube/settings/ai-gateway`)

- [x] litellm Base URL, API Key 입력 (마스킹 + 표시 토글)
- [x] '연결 테스트' 버튼 → 모델 목록 자동 드롭다운 채우기
- [x] Primary / Fallback / Tagging 모델 드롭다운 (+ 자유 입력 옵션)
- [x] Temperature, Max Tokens, Daily Budget 입력
- [x] '샘플 영상 분석' 버튼 → 결과 미리보기 모달 (저장 없이)
- [x] 저장 버튼

### 10.3 폴링/알림 설정 (`/youtube/settings/runtime`)

- [x] YouTube API Key 입력 (Secret Input)
- [x] Master Interval (Number Input, 1~60분)
- [x] Default Channel Interval (Number Input, 60~10080분)
- [x] 일일 쿼터 한도 (Number Input)
- [x] 채널 동시성 / 분석 동시성 (Slider, 1~10)
- [x] Telegram 알림 ON/OFF Toggle
- [x] 채널 간 대기 시간 (Number Input, 0~120초)
- [x] 저신뢰도 임계값 (Slider, 0.0~1.0)
- [x] 저장 즉시 마스터 잡 주기 적용 확인

---

## Phase 11. 운영 로그 및 통계

> **목표**: 대시보드 실시간 카운트 + 헬스 상태 표시
> **예상 기간**: 1일

### 11.1 잡 로그 화면 (`/youtube/jobs`)

- [x] 최근 100건 잡 로그 목록 (job_type, status, 채널명, 영상 제목, duration_ms, 시간)
- [x] 성공/실패/스킵 카운트 요약 배지
- [x] 자동 새로고침 (30초 주기)

### 11.2 운영 통계 통합

- [x] `/api/youtube/stats` 응답 대시보드 위젯 연동
  - `total_channels`, `active_channels`
  - `videos_today`, `videos_pending`, `videos_failed`
  - `llm_cost_today_usd`
  - `db_health`, `gateway_health`
- [x] DB 연결 끊김 / Gateway 다운 시 전체 헤더에 빨간 경고 띠 표시
- [x] 기존 `/logs` 페이지에 youtube 카테고리 필터 추가

---

## Phase 12. 통합 테스트 및 문서화

> **목표**: 신규 설치 시나리오 - ENV 최소 설정 → UI로 모두 설정 → 첫 영상 분석 PASS
> **예상 기간**: 2일

### 12.1 통합 테스트

- [x] 전체 파이프라인 E2E 테스트 작성
  - 채널 추가 → 폴링 → 분석 → Telegram 발송 시나리오
  - 분석 실패 → 재시도 → 재분석 버튼 시나리오
  - DB 연결 끊김 → 잡 SKIP → 복구 시나리오
- [x] 기존 `my-assistant` 기능 회귀 테스트 확인 (기존 라우터, 스케줄러 영향 없음)

### 12.2 빌드 및 배포 설정

- [x] `Dockerfile` 업데이트
  - Node 20 multi-stage build 단계 추가 (React 빌드 → `app/static/youtube/` 복사)
  - 빌드 실패 시 이미지 빌드 중단
- [x] `.github/workflows/docker-publish.yml` 프론트엔드 빌드 단계 추가

### 12.3 문서화

- [x] `README.md` YouTube 모니터 모듈 섹션 추가
  - 첫 설치 시나리오 (명세서 10.4 기준 7단계)
  - 환경변수 설명
  - 트러블슈팅 가이드 (PG 권한, Fernet 키, 쿼터 초과)
- [x] `docs/youtube_monitor_spec.md` 최종 반영 사항 업데이트

---

## 구현 순서 요약

```
P1 (설정 인프라) → P2 (PG 스키마) → P3 (YouTube API) → P4 (LLM 클라이언트)
     → P5 (분석 파이프라인)
         [백엔드 단독 동작 가능 - 중간 데모]
     → P6 (스케줄러) → P7 (Telegram 봇) → P8 (REST API)
         [자동화 파이프라인 완성]
     → P9 (React UI - 채널/영상) → P10 (React UI - 설정) → P11 (로그/통계)
         [웹 UI 완성]
     → P12 (통합 테스트 & 문서)
         [최종 완성]
```

## 수정이 필요한 기존 파일 목록

| 파일 | 변경 내용 |
|------|-----------|
| `app/main.py` | youtube 라우터 등록, startup_event 시드/스케줄러 호출 추가 |
| `app/database.py` | `youtube_setting` 모델 임포트, `_migrate_youtube_settings()` 추가 |
| `app/config.py` | `YOUTUBE_SETTINGS_FERNET_KEY`, `YOUTUBE_BOOTSTRAP_*` 변수 추가 |
| `app/services/scheduler.py` | `setup_youtube_jobs()` 추가, youtube jobstore 분리 |
| `app/templates/base.html` | 네비게이션에 "YouTube 모니터" 메뉴 추가 |
| `requirements.txt` | psycopg, asyncpg, openai, cryptography, youtube-transcript-api, isodate 추가 |
| `Dockerfile` / `docker-compose.yml` | Node 20 multi-stage build 추가 (선택) |
| `.env.example` | FERNET_KEY 및 BOOTSTRAP_* 항목 추가 |
