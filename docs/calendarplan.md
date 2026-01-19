# Calendar 기능 업그레이드 계획서

## 1. 현재 구조 분석

### 1.1 현재 기능

| 항목 | 내용 |
|------|------|
| 캘린더 소스 | Google Calendar (Primary만 지원) |
| 알림 시간 | 설정 가능 (기본 08:00) |
| 알림 채널 | 카카오톡, 텔레그램 |
| 일정 조회 | 오늘 일정만 조회 |
| OAuth 스코프 | calendar.readonly (읽기 전용) |

### 1.2 현재 파일 구조

```
app/
├── services/
│   ├── auth/
│   │   └── google_auth.py      # Google OAuth 및 Calendar API
│   └── bots/
│       └── calendar_bot.py     # 캘린더 알림 봇
├── routers/
│   └── calendar.py             # 캘린더 API 엔드포인트
├── templates/
│   └── calendar.html           # 캘린더 UI
└── static/js/
    └── calendar.js             # 프론트엔드 로직
```

### 1.3 현재 API 엔드포인트

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | /api/calendar/status | 캘린더 모듈 상태 조회 |
| GET | /api/calendar/preview | 오늘 일정 미리보기 |
| POST | /api/calendar/test | 캘린더 알림 테스트 발송 |
| GET | /api/calendar/logs | 캘린더 로그 조회 |

### 1.4 현재 한계점

1. **Primary 캘린더만 지원**: `calendarId="primary"` 하드코딩
2. **다중 캘린더 미지원**: 캘린더 목록 조회 기능 없음
3. **일정 관리 불가**: 읽기 전용 스코프, 생성/수정/삭제 불가
4. **캘린더 선택 비활성**: UI에서 select 요소가 disabled 상태
5. **공유 캘린더 미지원**: 다른 사람이 공유한 캘린더 접근 불가
6. **일정 상세 정보 부족**: 위치, 참석자, 반복 정보 미표시

---

## 2. 업그레이드 목표

### 2.1 핵심 기능

1. **다중 캘린더 지원**: 사용자의 모든 캘린더 목록 표시 및 선택
2. **캘린더 선택 저장**: 선택한 캘린더를 DB에 저장
3. **복수 캘린더 일정 통합**: 여러 캘린더의 일정을 한 알림에 통합

### 2.2 추가 제안 기능

1. **일정 상세 정보**: 위치, 참석자, 화상회의 링크 표시
2. **주간 일정 미리보기**: 오늘뿐 아니라 향후 7일 일정 조회
3. **일정 생성 기능**: 앱에서 직접 Google Calendar에 일정 추가 (선택)
4. **색상 구분**: 캘린더별 색상으로 일정 구분
5. **알림 시간 다양화**: 일정 시작 전 N분 알림 (선택)

---

## 3. 변경 후 구조

### 3.1 파일 변경 계획

```
app/
├── models/
│   └── calendar_setting.py     # (신규) 캘린더 선택 저장 모델
├── services/
│   ├── auth/
│   │   └── google_auth.py      # (수정) 캘린더 목록 조회 추가
│   └── bots/
│       └── calendar_bot.py     # (수정) 다중 캘린더 일정 조회
├── routers/
│   └── calendar.py             # (수정) 캘린더 관리 API 추가
├── templates/
│   └── calendar.html           # (수정) 캘린더 선택 UI 활성화
└── static/js/
    └── calendar.js             # (수정) 캘린더 목록 로드 기능
```

### 3.2 데이터베이스 스키마

#### 옵션 A: 새 테이블 생성

```python
class CalendarSelection(Base):
    __tablename__ = "calendar_selections"

    selection_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)

    # 캘린더 정보
    calendar_id = Column(String(255), nullable=False)     # Google Calendar ID
    calendar_name = Column(String(100), nullable=True)    # 캘린더 이름
    calendar_color = Column(String(20), nullable=True)    # 색상 코드

    # 설정
    is_selected = Column(Boolean, default=True)           # 알림에 포함 여부
    created_at = Column(DateTime, default=func.now())
```

#### 옵션 B: 기존 Setting 테이블 활용 (권장)

```python
# Setting 테이블의 config_json 필드 활용
{
    "selected_calendars": [
        {"id": "primary", "name": "My Calendar", "color": "#4285f4"},
        {"id": "abc123@group.calendar.google.com", "name": "Work", "color": "#0b8043"}
    ],
    "show_location": true,
    "show_attendees": false,
    "preview_days": 1
}
```

---

## 4. API 설계

### 4.1 캘린더 목록 API

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | /api/calendar/list | 사용자의 캘린더 목록 조회 |
| POST | /api/calendar/select | 알림에 포함할 캘린더 선택 저장 |
| GET | /api/calendar/selected | 선택된 캘린더 목록 조회 |

### 4.2 일정 조회 API 개선

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | /api/calendar/events | 선택된 캘린더의 일정 조회 (다중) |
| GET | /api/calendar/events/week | 주간 일정 조회 |

### 4.3 일정 생성 API (선택)

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | /api/calendar/events | 새 일정 생성 |
| PUT | /api/calendar/events/{id} | 일정 수정 |
| DELETE | /api/calendar/events/{id} | 일정 삭제 |

---

## 5. 알림 메시지 형식

### 5.1 현재 형식

```
[오늘의 일정] 2026년 01월 19일

오늘 일정이 없습니다.
```

### 5.2 개선 형식 (단일 캘린더)

```
[오늘의 일정] 2026년 01월 19일 (월)

[ 종일 일정 ]
- 신정 연휴

[ 시간별 일정 ]
09:00 - 10:00 | 팀 미팅
  장소: 회의실 A
  참석자: 홍길동, 김철수

14:00 - 15:00 | 고객 미팅
  장소: 온라인 (Google Meet)
  링크: https://meet.google.com/xxx

총 3개의 일정이 있습니다.
```

### 5.3 개선 형식 (다중 캘린더)

```
[오늘의 일정] 2026년 01월 19일 (월)

[ My Calendar ]
09:00 - 10:00 | 팀 미팅 (회의실 A)

[ Work ]
14:00 - 15:00 | 고객 미팅 (온라인)
18:00 - 19:00 | 저녁 약속

[ 가족 ]
- 종일: 엄마 생신

총 4개의 일정 (3개 캘린더)
```

---

## 6. 구현 단계

### Phase C-1: 캘린더 목록 조회

**작업 항목**:
- [ ] `google_auth.py`에 `get_calendar_list()` 함수 추가
- [ ] `calendar.py`에 GET `/api/calendar/list` 엔드포인트 추가
- [ ] 캘린더 목록 응답 스키마 정의

**핵심 코드**:
```python
def get_calendar_list(self, credentials) -> List[Dict]:
    """사용자의 캘린더 목록 조회"""
    service = build("calendar", "v3", credentials=credentials)
    calendar_list = service.calendarList().list().execute()
    return calendar_list.get("items", [])
```

**예상 코드량**: ~80줄

### Phase C-2: 캘린더 선택 저장

**작업 항목**:
- [ ] `Setting.config_json`에 선택된 캘린더 저장 로직 구현
- [ ] `calendar.py`에 POST `/api/calendar/select` 엔드포인트 추가
- [ ] `calendar.py`에 GET `/api/calendar/selected` 엔드포인트 추가
- [ ] `crud.py`에 캘린더 설정 CRUD 함수 추가

**예상 코드량**: ~100줄

### Phase C-3: 다중 캘린더 일정 조회

**작업 항목**:
- [ ] `google_auth.py`의 `get_calendar_events()` 함수 수정
- [ ] 여러 캘린더 ID를 받아 일정 통합 조회
- [ ] 캘린더별 색상 및 이름 포함

**핵심 코드**:
```python
def get_multiple_calendars_events(
    self, credentials, calendar_ids: List[str], date: datetime
) -> Dict[str, List[Dict]]:
    """여러 캘린더의 일정 조회"""
    service = build("calendar", "v3", credentials=credentials)
    results = {}
    for cal_id in calendar_ids:
        events = service.events().list(
            calendarId=cal_id,
            timeMin=...,
            timeMax=...,
        ).execute()
        results[cal_id] = events.get("items", [])
    return results
```

**예상 코드량**: ~120줄

### Phase C-4: 알림 메시지 개선

**작업 항목**:
- [ ] `calendar_bot.py`의 `format_calendar_message()` 함수 개선
- [ ] 캘린더별 일정 그룹화
- [ ] 위치, 참석자, 화상회의 링크 표시 옵션
- [ ] 요일 표시 추가

**예상 코드량**: ~100줄

### Phase C-5: UI 개선

**작업 항목**:
- [ ] `calendar.html`의 캘린더 선택 드롭다운 활성화
- [ ] 체크박스로 다중 선택 가능하도록 변경
- [ ] 캘린더 색상 표시
- [ ] 선택 저장 버튼 추가
- [ ] `calendar.js`에 캘린더 목록 로드 함수 추가

**UI 변경**:
```
변경 전:                          변경 후:
+-- 캘린더 ---------------------+    +-- 캘린더 선택 ----------------+
| [Primary Calendar v] disabled |    | [x] My Calendar (파랑)       |
| 현재는 Primary 캘린더만 지원    |    | [x] Work (초록)              |
+-------------------------------+    | [ ] 가족 (보라)              |
                                     | [저장]                       |
                                     +-------------------------------+
```

**예상 코드량**: HTML ~80줄, JS ~120줄

### Phase C-6: 일정 상세 정보 (선택)

**작업 항목**:
- [ ] 일정 상세 조회 API 추가
- [ ] 위치, 참석자, 설명, 첨부파일 정보 표시
- [ ] 화상회의 링크 (Google Meet, Zoom 등) 추출
- [ ] UI에 일정 클릭 시 상세 정보 모달

**예상 코드량**: ~150줄

### Phase C-7: 일정 생성 기능 (선택)

**작업 항목**:
- [ ] OAuth 스코프 확장 (`calendar.readonly` → `calendar`)
- [ ] 기존 사용자 재인증 필요 알림
- [ ] `google_auth.py`에 `create_event()` 함수 추가
- [ ] POST `/api/calendar/events` 엔드포인트 추가
- [ ] 일정 생성 폼 UI

**주의사항**:
- 스코프 변경 시 기존 사용자의 토큰 무효화
- 재인증 안내 메시지 필요

**예상 코드량**: ~200줄

### Phase C-8: 테스트 및 문서화

**작업 항목**:
- [ ] 캘린더 목록 조회 테스트
- [ ] 다중 캘린더 일정 조회 테스트
- [ ] 알림 메시지 형식 테스트
- [ ] UI 동작 테스트
- [ ] 본 문서 업데이트

---

## 7. OAuth 스코프 고려사항

### 7.1 현재 스코프

```python
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly"
]
```

### 7.2 확장 스코프 (일정 생성 시 필요)

```python
SCOPES = [
    "https://www.googleapis.com/auth/calendar"  # 읽기 + 쓰기
]
```

### 7.3 스코프 변경 시 영향

1. **기존 토큰 무효화**: 스코프가 변경되면 기존 토큰으로 새 권한 사용 불가
2. **재인증 필요**: 사용자에게 Google 재연동 요청 필요
3. **권한 동의**: 사용자가 새 권한(쓰기)에 동의해야 함

### 7.4 권장 접근법

**Phase C-1 ~ C-5**: 기존 `calendar.readonly` 스코프로 구현 가능
**Phase C-7**: 일정 생성 기능 추가 시에만 스코프 확장

---

## 8. 예상 작업량

| Phase | 신규 파일 | 수정 파일 | 예상 코드량 | 필수/선택 |
|-------|----------|----------|------------|----------|
| C-1 | 0 | 2 | ~80줄 | 필수 |
| C-2 | 0 | 2 | ~100줄 | 필수 |
| C-3 | 0 | 1 | ~120줄 | 필수 |
| C-4 | 0 | 1 | ~100줄 | 필수 |
| C-5 | 0 | 2 | ~200줄 | 필수 |
| C-6 | 0 | 3 | ~150줄 | 선택 |
| C-7 | 0 | 3 | ~200줄 | 선택 |
| C-8 | 0 | 1 | ~20줄 | 필수 |
| **합계** | **0** | **15** | **~970줄** | - |

---

## 9. 우선순위 권장

### 필수 구현 (MVP)

1. **Phase C-1**: 캘린더 목록 조회 - 다중 캘린더의 기반
2. **Phase C-2**: 캘린더 선택 저장 - 사용자 설정 유지
3. **Phase C-3**: 다중 캘린더 일정 조회 - 핵심 기능
4. **Phase C-4**: 알림 메시지 개선 - 사용자 가치 전달
5. **Phase C-5**: UI 개선 - 사용자 경험

### 선택 구현

6. **Phase C-6**: 일정 상세 정보 - 추가 정보 제공
7. **Phase C-7**: 일정 생성 - 고급 기능 (OAuth 재인증 필요)

### 구현 순서 권장

```
C-1 (목록) → C-2 (선택) → C-3 (조회) → C-5 (UI) → C-4 (알림) → C-8 (테스트)
```

---

## 10. 완료 체크리스트

### Phase C-1: 캘린더 목록 조회
- [ ] `get_calendar_list()` 함수 구현
- [ ] GET `/api/calendar/list` 엔드포인트
- [ ] 응답 스키마 정의

### Phase C-2: 캘린더 선택 저장
- [ ] 캘린더 선택 저장 로직
- [ ] POST `/api/calendar/select` 엔드포인트
- [ ] GET `/api/calendar/selected` 엔드포인트

### Phase C-3: 다중 캘린더 일정 조회
- [ ] `get_multiple_calendars_events()` 함수 구현
- [ ] 기존 `get_calendar_events()` 수정
- [ ] 캘린더별 일정 분류

### Phase C-4: 알림 메시지 개선
- [ ] 캘린더별 일정 그룹화
- [ ] 위치/참석자 표시 옵션
- [ ] 요일 표시 추가

### Phase C-5: UI 개선
- [ ] 캘린더 선택 체크박스 UI
- [ ] 캘린더 색상 표시
- [ ] 선택 저장 기능
- [ ] 캘린더 목록 동적 로드

### Phase C-6: 일정 상세 정보 (선택)
- [ ] 일정 상세 조회 API
- [ ] 화상회의 링크 추출
- [ ] 상세 정보 모달 UI

### Phase C-7: 일정 생성 기능 (선택)
- [ ] OAuth 스코프 확장
- [ ] `create_event()` 함수
- [ ] 일정 생성 API
- [ ] 일정 생성 폼 UI

### Phase C-8: 테스트 및 문서화
- [ ] 캘린더 목록 테스트
- [ ] 다중 일정 조회 테스트
- [ ] 알림 메시지 테스트
- [ ] 본 문서 업데이트

---

## 11. 기술적 고려사항

### 11.1 API 호출 제한

| 서비스 | 제한 |
|--------|------|
| Google Calendar API | 1,000,000 요청/일 (무료) |
| 단일 사용자 | 충분한 여유 |

### 11.2 성능 최적화

1. **병렬 조회**: 여러 캘린더 동시 조회 (asyncio)
2. **캐싱**: 캘린더 목록 캐시 (5분)
3. **선택적 조회**: 선택된 캘린더만 일정 조회

### 11.3 에러 처리

1. **토큰 만료**: 자동 갱신 (기존 로직 활용)
2. **캘린더 삭제됨**: 선택 목록에서 자동 제거
3. **권한 없음**: 해당 캘린더 스킵 및 로그

---

## 12. 메시지 길이 제한

| 채널 | 최대 길이 | 권장 캘린더 수 |
|------|----------|---------------|
| 카카오톡 | 2,000자 | 3-5개 |
| 텔레그램 | 4,096자 | 5-10개 |

- 선택 캘린더가 많을 경우 요약 모드 적용
- 일정이 많을 경우 메시지 분할 발송

---

**작성일**: 2026-01-19
**상태**: 계획 수립 완료
