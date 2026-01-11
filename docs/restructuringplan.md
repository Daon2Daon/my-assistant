# UI 구조 개편 계획서 (Restructuring Plan)

## 1. 현재 구조 분석

### 1.1 현재 페이지 구성

| 경로 | 페이지명 | 포함 기능 |
|------|----------|-----------|
| `/` | Dashboard | 서비스 상태, 모듈 토글, Job 목록, 로그, Quick Test |
| `/reminders` | Reminders | 메모 등록/조회/삭제 |
| `/settings` | Settings | 인증 상태, 알림 시간 설정, Job 관리 |

### 1.2 문제점

1. **Dashboard 과부하**: 모든 기능이 단일 페이지에 집중되어 있음
2. **기능 중복**: Dashboard와 Settings에서 Job 관리 기능이 중복됨
3. **확장성 제한**: 새로운 봇 추가 시 Dashboard가 더욱 복잡해짐
4. **유지보수 어려움**: 각 봇별 고도화 시 코드 충돌 가능성 높음

### 1.3 현재 파일 구조

```
app/
├── routers/
│   ├── auth.py           # 인증 API
│   ├── dashboard.py      # 페이지 렌더링
│   ├── logs.py           # 로그 API
│   ├── reminders.py      # 메모 API
│   ├── scheduler.py      # 스케줄러 API
│   └── settings.py       # 설정 API
├── templates/
│   ├── base.html
│   ├── dashboard.html
│   ├── reminders.html
│   └── settings.html
└── static/js/
    ├── app.js
    ├── dashboard.js
    ├── reminders.js
    └── settings.js
```

---

## 2. 개편 목표

1. **기능별 독립 페이지**: 각 봇(날씨, 금융, 캘린더)을 개별 페이지로 분리
2. **확장 용이성**: 새로운 봇 추가 시 기존 코드 수정 최소화
3. **유지보수성 향상**: 각 기능별 독립적인 개발/테스트 가능
4. **사용자 경험 개선**: 명확한 네비게이션과 기능별 전용 UI

---

## 3. 개편 후 페이지 구조

### 3.1 신규 네비게이션 메뉴

```
[Home] [Weather] [Finance] [Calendar] [Reminders] [Logs] [Settings]
```

### 3.2 페이지별 기능 정의

| 경로 | 페이지명 | 주요 기능 |
|------|----------|-----------|
| `/` | Home | 시스템 상태 개요, 인증 상태, 스케줄러 상태 |
| `/weather` | Weather | 날씨 알림 설정, 테스트, 관련 로그 |
| `/finance` | Finance | 금융 알림 설정 (US/KR), 테스트, 관련 로그 |
| `/calendar` | Calendar | 캘린더 알림 설정, 테스트, 관련 로그 |
| `/reminders` | Reminders | 메모 등록/조회/삭제 (기존 유지) |
| `/logs` | Logs | 전체 로그 조회, 필터링, 검색 |
| `/settings` | Settings | 전역 설정, 인증 관리 |

---

## 4. 상세 페이지 설계

### 4.1 Home 페이지 (`/`)

**역할**: 시스템 전체 상태를 한눈에 파악

**구성 요소**:
- 시스템 상태 카드
  - 스케줄러 상태 (Running/Stopped)
  - Kakao 연동 상태
  - Google 연동 상태
- 모듈 요약 카드 (각 모듈 페이지로 링크)
  - Weather: 활성화 상태, 다음 발송 시간
  - Finance: 활성화 상태, 다음 발송 시간
  - Calendar: 활성화 상태, 다음 발송 시간
  - Reminders: 대기 중인 메모 개수
- 최근 활동 요약 (최근 5개 로그)

### 4.2 Weather 페이지 (`/weather`)

**역할**: 날씨 알림 전용 관리 페이지

**구성 요소**:
- 상태 카드
  - 활성화 토글
  - 다음 발송 예정 시간
  - 마지막 발송 시간/결과
- 설정 섹션
  - 알림 시간 설정 (시:분 선택)
  - 도시 설정 (향후 확장)
  - 저장 버튼
- 테스트 섹션
  - 즉시 테스트 버튼
  - 미리보기 (메시지 형식 확인)
- 관련 로그
  - 최근 날씨 알림 로그 (카테고리 필터 적용)

### 4.3 Finance 페이지 (`/finance`)

**역할**: 금융 알림 전용 관리 페이지

**구성 요소**:
- 상태 카드
  - US Market 활성화 토글
  - KR Market 활성화 토글
  - 각 시장별 다음 발송 시간
- 설정 섹션
  - US Market 알림 시간 설정
  - KR Market 알림 시간 설정
  - 관심 종목 설정 (향후 확장)
  - 저장 버튼
- 테스트 섹션
  - US Market 테스트 버튼
  - KR Market 테스트 버튼
- 관련 로그
  - 최근 금융 알림 로그

### 4.4 Calendar 페이지 (`/calendar`)

**역할**: 캘린더 알림 전용 관리 페이지

**구성 요소**:
- 상태 카드
  - 활성화 토글
  - Google 연동 상태
  - 다음 발송 예정 시간
- 설정 섹션
  - 알림 시간 설정
  - 캘린더 선택 (향후 확장: 다중 캘린더)
  - 저장 버튼
- 테스트 섹션
  - 즉시 테스트 버튼
  - 오늘 일정 미리보기
- 관련 로그
  - 최근 캘린더 알림 로그

### 4.5 Reminders 페이지 (`/reminders`)

**역할**: 예약 메모 관리 (기존 유지)

**변경 사항**: 없음 (현재 구조 유지)

### 4.6 Logs 페이지 (`/logs`)

**역할**: 전체 시스템 로그 조회 (신규)

**구성 요소**:
- 필터 섹션
  - 카테고리 필터 (All, Weather, Finance, Calendar, Memo)
  - 상태 필터 (All, Success, Fail, Skip)
  - 날짜 범위 필터
- 로그 테이블
  - 페이지네이션
  - 정렬 기능 (시간, 카테고리, 상태)
- 로그 상세 모달
  - 전체 메시지 내용 표시
  - 관련 데이터 표시

### 4.7 Settings 페이지 (`/settings`)

**역할**: 전역 설정 및 인증 관리

**구성 요소**:
- 인증 관리 섹션
  - Kakao Talk 연동/해제
  - Google Calendar 연동/해제
  - 토큰 상태 표시
- 스케줄러 관리
  - 스케줄러 시작/중지
  - 등록된 전체 Job 목록
- 시스템 설정 (향후 확장)
  - 타임존 설정
  - 언어 설정

---

## 5. 파일 구조 변경

### 5.1 신규 파일 구조

```
app/
├── routers/
│   ├── auth.py           # (유지) 인증 API
│   ├── pages.py          # (신규) 모든 페이지 렌더링 통합
│   ├── logs.py           # (유지) 로그 API
│   ├── reminders.py      # (유지) 메모 API
│   ├── scheduler.py      # (유지) 스케줄러 API
│   ├── settings.py       # (유지) 설정 API
│   ├── weather.py        # (신규) 날씨 전용 API
│   ├── finance.py        # (신규) 금융 전용 API
│   └── calendar.py       # (신규) 캘린더 전용 API
├── templates/
│   ├── base.html         # (수정) 네비게이션 확장
│   ├── home.html         # (신규) 홈 페이지
│   ├── weather.html      # (신규) 날씨 페이지
│   ├── finance.html      # (신규) 금융 페이지
│   ├── calendar.html     # (신규) 캘린더 페이지
│   ├── reminders.html    # (유지) 메모 페이지
│   ├── logs.html         # (신규) 로그 페이지
│   └── settings.html     # (수정) 설정 페이지 간소화
└── static/js/
    ├── app.js            # (유지) 공통 유틸리티
    ├── home.js           # (신규) 홈 페이지 스크립트
    ├── weather.js        # (신규) 날씨 페이지 스크립트
    ├── finance.js        # (신규) 금융 페이지 스크립트
    ├── calendar.js       # (신규) 캘린더 페이지 스크립트
    ├── reminders.js      # (유지) 메모 페이지 스크립트
    ├── logs.js           # (신규) 로그 페이지 스크립트
    └── settings.js       # (수정) 설정 페이지 스크립트
```

### 5.2 삭제 예정 파일

```
app/templates/dashboard.html  -> home.html로 대체
app/static/js/dashboard.js    -> home.js로 대체
app/routers/dashboard.py      -> pages.py로 통합
```

---

## 6. API 엔드포인트 변경

### 6.1 신규 API 엔드포인트

```
# Weather API
GET  /api/weather/status        - 날씨 모듈 상태 조회
GET  /api/weather/preview       - 날씨 메시지 미리보기
POST /api/weather/test          - 날씨 알림 테스트
GET  /api/weather/logs          - 날씨 관련 로그 조회

# Finance API
GET  /api/finance/status        - 금융 모듈 상태 조회
GET  /api/finance/preview/us    - US 시장 메시지 미리보기
GET  /api/finance/preview/kr    - KR 시장 메시지 미리보기
POST /api/finance/test/us       - US 시장 알림 테스트
POST /api/finance/test/kr       - KR 시장 알림 테스트
GET  /api/finance/logs          - 금융 관련 로그 조회

# Calendar API
GET  /api/calendar/status       - 캘린더 모듈 상태 조회
GET  /api/calendar/preview      - 오늘 일정 미리보기
POST /api/calendar/test         - 캘린더 알림 테스트
GET  /api/calendar/logs         - 캘린더 관련 로그 조회

# Logs API (확장)
GET  /api/logs                  - 전체 로그 조회 (페이지네이션 추가)
GET  /api/logs/stats            - 로그 통계 조회
```

### 6.2 기존 API 유지

```
# Settings API (유지)
GET    /api/settings
GET    /api/settings/{category}
PUT    /api/settings/{category}

# Reminders API (유지)
GET    /api/reminders
POST   /api/reminders
DELETE /api/reminders/{id}

# Scheduler API (유지)
GET    /api/scheduler/status
GET    /api/scheduler/jobs
POST   /api/scheduler/jobs/{type}
DELETE /api/scheduler/jobs/{job_id}
```

---

## 7. 구현 단계

### Phase R-1: 기반 작업

**예상 작업량**: 기본 구조 변경

**작업 항목**:
- [ ] `base.html` 네비게이션 확장 (7개 메뉴)
- [ ] `pages.py` 라우터 생성 (페이지 렌더링 통합)
- [ ] `home.html` 템플릿 생성
- [ ] `home.js` 스크립트 생성
- [ ] 기존 `dashboard.py`, `dashboard.html`, `dashboard.js` 제거

### Phase R-2: Weather 페이지 분리

**예상 작업량**: 중간

**작업 항목**:
- [ ] `weather.html` 템플릿 생성
- [ ] `weather.js` 스크립트 생성
- [ ] `weather.py` 라우터 생성 (API 확장)
- [ ] 미리보기 기능 구현
- [ ] 관련 로그 필터링 구현

### Phase R-3: Finance 페이지 분리

**예상 작업량**: 중간

**작업 항목**:
- [ ] `finance.html` 템플릿 생성
- [ ] `finance.js` 스크립트 생성
- [ ] `finance.py` 라우터 생성 (API 확장)
- [ ] US/KR 시장 개별 설정 UI
- [ ] 미리보기 기능 구현

### Phase R-4: Calendar 페이지 분리

**예상 작업량**: 중간

**작업 항목**:
- [ ] `calendar.html` 템플릿 생성
- [ ] `calendar.js` 스크립트 생성
- [ ] `calendar.py` 라우터 생성 (API 확장)
- [ ] 일정 미리보기 기능 구현
- [ ] Google 연동 상태 통합

### Phase R-5: Logs 페이지 신설

**예상 작업량**: 중간

**작업 항목**:
- [ ] `logs.html` 템플릿 생성
- [ ] `logs.js` 스크립트 생성
- [ ] `logs.py` API 확장 (페이지네이션, 통계)
- [ ] 필터링 UI 구현
- [ ] 로그 상세 모달 구현

### Phase R-6: Settings 페이지 정리

**예상 작업량**: 작음

**작업 항목**:
- [ ] `settings.html` 간소화 (전역 설정만 유지)
- [ ] `settings.js` 수정
- [ ] 각 봇 관련 설정을 개별 페이지로 이동 완료 확인

### Phase R-7: 통합 테스트 및 정리

**예상 작업량**: 작음

**작업 항목**:
- [ ] 모든 페이지 동작 테스트
- [ ] 네비게이션 동작 확인
- [ ] 반응형 디자인 확인
- [ ] 불필요 코드 제거
- [ ] 문서 업데이트

---

## 8. 고려사항

### 8.1 하위 호환성

- 기존 API 엔드포인트는 모두 유지
- 새로운 기능별 API는 추가 형태로 구현
- 기존 스케줄러 Job ID 체계 유지

### 8.2 데이터 모델

- 현재 데이터베이스 스키마 변경 없음
- Settings 테이블의 category 필드 활용

### 8.3 향후 확장성

각 봇 페이지는 다음 기능 추가가 용이하도록 설계:

**Weather**:
- 다중 도시 지원
- 주간 예보 추가
- 미세먼지 상세 정보

**Finance**:
- 관심 종목 관리
- 가격 알림 (특정 가격 도달 시)
- 포트폴리오 추적

**Calendar**:
- 다중 캘린더 선택
- 일정 유형별 필터
- 일정 미리 알림 (30분 전 등)

**Reminders**:
- 반복 알림 지원
- 카테고리/태그 분류
- 첨부파일 지원

---

## 9. 위험 요소 및 대응

| 위험 요소 | 영향도 | 대응 방안 |
|-----------|--------|-----------|
| 기존 기능 손상 | 높음 | 단계별 구현 및 각 Phase 완료 후 테스트 |
| 코드 중복 | 중간 | 공통 컴포넌트/유틸리티 함수 활용 |
| UI 일관성 깨짐 | 중간 | base.html 공통 스타일 유지 |
| 성능 저하 | 낮음 | 페이지별 필요한 데이터만 로드 |

---

## 10. 수정 가능 여부 결론

**결론: 수정 가능**

현재 프로젝트 구조가 다음과 같이 잘 모듈화되어 있어 분리 작업이 수월합니다:

1. **봇 서비스 독립성**: 각 봇(`weather_bot.py`, `finance_bot.py`, `calendar_bot.py`, `memo_bot.py`)이 이미 독립적으로 구현되어 있음
2. **라우터 분리**: 기능별로 라우터가 분리되어 있어 확장 용이
3. **템플릿 상속**: `base.html`을 통한 일관된 레이아웃 유지
4. **JavaScript 모듈화**: 페이지별 스크립트 파일 분리

이 구조 개편을 통해:
- 각 기능별 독립적인 개발 및 고도화 가능
- 코드 유지보수성 향상
- 사용자 경험 개선 (명확한 네비게이션)
- 향후 새로운 봇 추가 시 기존 코드 영향 최소화
