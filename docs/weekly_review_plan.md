# YouTube 주간 리뷰(Weekly Review) 기능 계획서

## 1. 개요

기존 YouTube 모니터는 영상을 한 건씩 분석하여 텔레그램으로 개별 발송한다.
본 기능은 일정 기간(기본 1주) 동안 분석 완료된 영상을 카테고리별로 묶어
하나의 리뷰 문서로 합성하고, 웹에서 열람 + 텔레그램 요약으로 전달한다.

### 1.1 목표

1. 카테고리별 주간 리뷰 자동 생성 (감성 분포, 핵심 주장, 주요 태그/채널 집계)
2. 리뷰 기간을 사용자가 주 단위로 조정 (기본 1주)
3. 발송 일정을 사용자가 예약 설정 (요일 + 시각, 복수 가능)
4. 웹 열람(전체 본문) + 텔레그램 요약(요약 + 웹 링크)

### 1.2 설계 원칙

- 신규 데이터 수집 없이 기존 `youtube.video_analysis` 데이터를 집계한다.
- 카테고리는 처음부터 분리 생성되도록 `channels.category` 기준으로 그룹핑한다.
  향후 정식 모니터링 그룹 테이블이 도입되면 `group_pk`로 승격한다.
- 기존 알림(`notification`) 설정/스케줄러 패턴을 그대로 재사용하여 일관성을 유지한다.

## 2. 현재 구조에서 활용하는 자산

| 자산 | 활용 |
|------|------|
| youtube.videos | published_at, analysis_status, channel_pk |
| youtube.video_analysis | one_line, headline, bullet_points, insights, entities, sentiment, cost_usd |
| youtube.channels.category | 카테고리 그룹핑 기준 (이미 존재) |
| youtube.tags / video_tags | top 태그 집계 (weight 합) |
| settings_manager (SQLite) | digest 설정 카테고리 추가 |
| scheduler setup_youtube_notify_jobs 패턴 | 예약 발송 잡 등록/재등록 |
| telegram_sender | 요약 발송 |

## 3. 데이터베이스 스키마

신규 테이블 `youtube.digests` (카테고리별 1행).

| 컬럼 | 타입 | 설명 |
|------|------|------|
| digest_pk | BIGSERIAL PK | |
| period_type | TEXT | 기본 'weekly' |
| period_weeks | INTEGER | 리뷰 기간(주), 기본 1 |
| period_start | TIMESTAMPTZ | 집계 시작 |
| period_end | TIMESTAMPTZ | 집계 종료 |
| category | TEXT | NULL/빈값은 '미분류'. 향후 group_pk로 승격 |
| video_count | INTEGER | 대상 영상 수 |
| headline | TEXT | 리뷰 제목 |
| summary_md | TEXT | 웹 표시용 본문(마크다운) |
| telegram_summary | TEXT | 텔레그램 요약 |
| sentiment_breakdown | JSONB | bullish/bearish/neutral/mixed 카운트 |
| top_tags | JSONB | 상위 태그 목록 |
| top_channels | JSONB | 상위 채널 목록 |
| model_name | TEXT | 합성 모델 |
| token_input / token_output | INTEGER | 토큰 사용량 |
| cost_usd | DOUBLE PRECISION | 비용 |
| status | TEXT | pending / done / failed |
| error | TEXT | 실패 사유 |
| created_at / updated_at | TIMESTAMPTZ | |

마이그레이션: `migrations/youtube/007_add_digests.sql` (schema_migrations version 7).

## 4. 설정 (SQLite youtube_settings, category='digest')

| 키 | 타입 | 기본값 | 설명 |
|----|------|--------|------|
| enabled | bool | false | 주간 리뷰 on/off |
| period_weeks | int | 1 | 리뷰 기간(주), 1~8 |
| schedule_times | json | [] | [{"day_of_week":"sun","time":"20:00"}] 복수 가능 |
| telegram_enabled | bool | true | 텔레그램 요약 발송 여부 |
| categories | json | null | 대상 카테고리 범위(null=전체) |

리뷰 합성 프롬프트는 기존 prompts 카테고리에 `digest_prompt`로 추가한다.

## 5. API 설계

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | /api/youtube/digests | 다이제스트 목록(페이지네이션) |
| GET | /api/youtube/digests/{digest_pk} | 다이제스트 상세 |
| POST | /api/youtube/digests/generate | 수동 생성/미리보기 |
| GET | /api/youtube/settings/digest | digest 설정 조회 |
| PUT | /api/youtube/settings/digest | digest 설정 저장 (잡 재등록) |

## 6. 구현 단계

### Phase W-1: 테이블 + 마이그레이션
- [x] migrations/youtube/007_add_digests.sql 작성
- [x] app/models/youtube_digest.py 모델 추가

### Phase W-2: 집계 로직 (LLM 없이)
- [x] app/services/youtube/digest_service.py 신규
- [x] period_weeks 기간 done 영상 조회 및 카테고리 그룹핑
- [x] 감성 분포 / top 태그 / top 채널 / 영상 수 집계

### Phase W-3: LLM 합성 리뷰
- [x] prompts.digest_prompt 추가 및 기본 프롬프트
- [x] 집계 결과 LLM 합성 (핵심 주장 / 합의 / 엇갈림)
- [x] LLM 실패 시 집계 템플릿 폴백

### Phase W-4: API 엔드포인트
- [x] GET /digests, GET /digests/{id}, POST /digests/generate
- [x] 응답 스키마 정의
- [x] generate_digests 공통 오케스트레이터 (W-5 스케줄러와 공용)

### Phase W-5: 스케줄러 잡 + 설정
- [x] digest 설정 카테고리 추가 (settings_manager DigestSettings + get_digest)
- [x] add_cron_job에 day_of_week 인자 추가 (하위 호환)
- [x] setup_youtube_digest_jobs / update_youtube_digest_jobs
- [x] GET/PUT /settings/digest (저장 시 잡 재등록)
- [x] 다이제스트 잡 러너 (youtube_weekly_digest_sync) + 설정 시드

### Phase W-6: 텔레그램 요약 발송
- [x] config base URL 키 확인 (기존 BASE_URL 재사용)
- [x] 텔레그램 요약 + 웹 전체보기 링크 발송 (4096자 회피)
- [x] 잡 러너에 발송 연결 (telegram_enabled 분기)

### Phase W-7: React 프론트
- [x] Digests 목록 페이지 (필터 / 지금 생성 / 페이지네이션)
- [x] DigestDetail 상세 (본문 마크다운 / 감성 / top 태그·채널 / 메타)
- [x] Settings 다이제스트 패널 (기간 / 예약(요일+시각) / 카테고리 / on-off)
- [x] Layout 사이드바 메뉴 추가 (주간 리뷰 / 설정)
- [x] api/digest.ts 클라이언트 + 라우팅
- [x] npm run build 검증 통과 (tsc + vite)

### Phase W-8: 테스트 + 문서화
- [x] 집계 로직 테스트 (aggregate_period: 그룹핑/필터/빈 결과)
- [x] 합성/폴백 테스트 (synthesize_with_llm, generate_category_review)
- [x] 헬퍼/텔레그램 메시지 테스트 (tests/youtube/test_digest_service.py, 18건 통과)
- [x] 본 문서 갱신

## 7. 기술적 고려사항

### 7.1 기간 계산
period_start = period_end - (period_weeks x 7일). period_end는 발송 시각 기준 KST.

### 7.2 메시지 길이
텔레그램 4096자 제한. 다이제스트는 요약 + 웹 링크로 전달하여 길이 문제를 회피한다.

### 7.3 엣지 케이스
- 대상 영상 0건 카테고리: 다이제스트 생성을 건너뛴다.
- LLM 합성 실패: 집계 결과만으로 템플릿 본문을 생성한다.
- 카테고리 미지정 영상: '미분류' 그룹으로 묶는다.

### 7.4 비용
video_analysis.cost_usd 누적과 동일하게 digest.cost_usd에 합성 비용을 기록한다.

## 8. 우선순위

필수: W-1 ~ W-8 (MVP 전 범위)
권장 순서: W-1 → W-2 → W-3 → W-4 → W-5 → W-6 → W-7 → W-8

## 8-A. 업그레이드 (Phase U) — 브리핑 강화 + 대상 필터 확장

기존 주간 리뷰를 두 방향으로 보완.

### Phase U-1: AI 브리핑 강화
- [x] aggregate_period에 insights/entities 추가, VideoBrief 확장
- [x] _build_videos_block에 핵심 주장/인사이트/등장 종목·지표/논조 반영
- [x] DEFAULT_DIGEST_PROMPT 브리핑 구조화 (주요 내용 / 관점과 의견 / 핵심 인사이트 / 주목할 종목·이슈)
- [x] 합성 모델 fallback_model 전환

### Phase U-2: 대상 필터 확장 (채널/태그)
- [x] aggregate_period에 channel_pks/tags 필터 (타입 간 AND, 타입 내 OR)
- [x] generate_digests·잡 러너·수동 API 필터 전달 (요청값 > 설정값 폴백)
- [x] DigestSettings channel_pks/tags + 시드
- [x] 스키마(설정/생성요청) 확장

### Phase U-3: 프론트 + 문서
- [x] DigestSettings.tsx 채널/태그 멀티선택 + AND/OR 안내
- [x] api/digest.ts 타입 확장
- [x] npm run build 검증 통과
- [x] 본 문서 갱신

테스트: tests/youtube/test_digest_service.py 22건 통과.

## 8-B. 개선 (Phase F) — 단일 통합 / 폴백 / 카테고리 토큰화 / digest_model

운영 피드백 반영 개선.

### 문제 1: 브리핑 4섹션 미출력 (LLM 합성 실패)
- 원인: digest_model 미설정 → fallback_model(`gemini/gemini-2.5-flash`)이 chat completions에서 거부(400).
- AIGatewaySettings에 digest_model 추가 (digest_model > fallback_model > tagging_model 순).
- AI Gateway 설정 UI에 'Digest 모델' 선택기 + 미설정 경고 배너.
- 폴백 본문을 영상별 한 줄 요약 나열 → 4섹션 골격(주요 내용/관점과 의견/핵심 인사이트/주목할 종목·이슈)으로 재구성, status='fallback' 으로 구분.

### 문제 2: '전체'가 카테고리별 N개 생성
- aggregate_period 를 카테고리별 dict → 단일 CategoryAggregate(또는 None) 반환으로 재작성.
- 미선택 시 라벨 '전체'로 모든 영상 1개 통합. 선택 시 해당 범위 1개 통합.
- generate_digests 의 카테고리 루프 제거.

### 문제 3: 카테고리 중복 (콤마 혼용)
- split_category_tokens(): '경제, 투자, 재테크' → ['경제','투자','재테크'].
- 카테고리 필터를 콤마 토큰 단위 매칭으로 변경 (집합 교집합).
- 집계에 top_categories(토큰 분포) 추가.
- 프론트: collectCategoryTokens() 헬퍼로 설정/목록의 카테고리 칩을 토큰 단위로 표시.

### 부가
- 다이제스트 삭제 기능 (DELETE /digests/{pk} + 목록 삭제 버튼/모달).

테스트: tests/youtube/test_digest_service.py 23건 통과.

## 8-C. 프롬프트 통합 (Phase P)

### 분석 프롬프트 단일화
- primary_prompt/fallback_prompt(경로 A/B 구분) → 단일 analysis_prompt 통합.
- analyzer 경로 A·B 모두 동일 프롬프트 사용. FALLBACK_PROMPT_V1 상수 제거.
- 하위호환: DB에 analysis_prompt 없으면 기존 primary_prompt 승계.

### 주간 리뷰 프롬프트 편집 (위치: '프롬프트' 메뉴)
- 판단: 같은 '프롬프트 편집' 행위라 '프롬프트' 메뉴에 통합. '주간 리뷰' 메뉴는 일정·기간·대상 등 운영 설정 위주로 유지.
- 프롬프트 메뉴 = '영상 분석 프롬프트' + '주간 리뷰 프롬프트' 2개 섹션. 각 섹션별 변수 안내 제공.
- digest_prompt 미설정 시 DEFAULT_DIGEST_PROMPT 노출.

### 변경 파일
- settings_manager(PromptSettings: analysis_prompt+digest_prompt), analyzer(단일 프롬프트),
  schemas(PromptSettingsResponse/Update), router(get/put/reset),
  client.ts, PromptSettings.tsx(2섹션), InstantAnalyze.tsx·VideoDetail.tsx(primary_prompt→analysis_prompt).

테스트: 23건 통과 + 하위호환 검증.

## 9. 구현 완료 요약

전체 Phase(W-1 ~ W-8, U-1 ~ U-3, F, P) 구현 완료.

### 9.1 변경/신규 파일

| 파일 | 상태 | 내용 |
|------|------|------|
| migrations/youtube/007_add_digests.sql | 신규 | youtube.digests 테이블 (schema_migrations v7) |
| app/models/youtube_digest.py | 신규 | YoutubeDigest ORM 모델 |
| app/services/youtube/digest_service.py | 신규 | 집계 + LLM 합성 + 폴백 + 생성 오케스트레이터 + 잡 러너 + 텔레그램 |
| app/services/youtube/settings_manager.py | 수정 | DigestSettings + get_digest, PromptSettings.digest_prompt |
| app/services/scheduler.py | 수정 | add_cron_job day_of_week, setup/update_youtube_digest_jobs |
| app/routers/youtube.py | 수정 | /digests, /digests/{id}, /digests/generate, /settings/digest |
| app/schemas/youtube.py | 수정 | Digest 응답/요청 스키마 |
| app/schemas/youtube_settings.py | 수정 | DigestSettingsResponse/Update, DigestScheduleItem |
| migrations/youtube/000_seed_settings.sql | 수정 | digest 기본 설정 시드 |
| frontend/youtube/src/api/digest.ts | 신규 | 다이제스트/설정 API 클라이언트 |
| frontend/youtube/src/pages/Digests.tsx | 신규 | 목록 페이지 |
| frontend/youtube/src/pages/DigestDetail.tsx | 신규 | 상세 페이지 |
| frontend/youtube/src/pages/settings/DigestSettings.tsx | 신규 | 설정 패널 |
| frontend/youtube/src/App.tsx, components/Layout.tsx | 수정 | 라우팅 + 사이드바 메뉴 |
| tests/youtube/test_digest_service.py | 신규 | 단위 테스트 18건 |

### 9.2 API 엔드포인트

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | /api/youtube/digests | 목록(페이지네이션, 카테고리 필터) |
| GET | /api/youtube/digests/{digest_pk} | 상세 |
| POST | /api/youtube/digests/generate | 수동 생성/미리보기 |
| GET | /api/youtube/settings/digest | 설정 조회 |
| PUT | /api/youtube/settings/digest | 설정 저장 (잡 재등록) |

### 9.3 배포 메모

- PostgreSQL: 마이그레이션 007은 다음 연결 시 자동 적용(ensure_schema) 또는 설정 화면의 스키마 적용으로 즉시 반영.
- 프론트: Docker 멀티스테이지 빌드가 frontend/youtube 소스를 npm run build 하여 app/static/youtube 를 재생성.
- 설정: youtube_settings의 digest 카테고리 5개 키 시드(멱등). 기본 enabled=false.

---

작성일: 2026-05-30
상태: 구현 완료 (Phase W-1 ~ W-8)
버전: 1.0.0
