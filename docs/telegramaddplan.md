# 텔레그램 알림 채널 추가 계획서

## 1. 현재 구조 분석

### 1.1 현재 알림 발송 흐름

```
각 봇 (weather_bot, finance_bot, calendar_bot, memo_bot)
    ↓
kakao_auth_service.send_message_to_me(access_token, message)
    ↓
카카오톡 API (나에게 보내기)
```

### 1.2 현재 파일 구조

```
app/
├── services/
│   ├── auth/
│   │   ├── kakao_auth.py      # 카카오 OAuth + 메시지 발송
│   │   └── google_auth.py     # 구글 OAuth (캘린더용)
│   └── bots/
│       ├── weather_bot.py     # kakao_auth_service 직접 호출
│       ├── finance_bot.py     # kakao_auth_service 직접 호출
│       ├── calendar_bot.py    # kakao_auth_service 직접 호출
│       └── memo_bot.py        # kakao_auth_service 직접 호출
├── models/
│   └── user.py                # kakao_access_token, kakao_refresh_token
└── routers/
    └── auth.py                # 카카오 로그인 엔드포인트
```

### 1.3 문제점

1. **강한 결합**: 각 봇이 카카오톡 서비스에 직접 의존
2. **확장성 부족**: 새 알림 채널 추가 시 4개 봇 모두 수정 필요
3. **코드 중복**: 알림 발송 로직이 각 봇에 분산

---

## 2. 목표

1. **NotificationService 도입**: 알림 발송 로직 추상화
2. **텔레그램 채널 추가**: 카카오톡과 병행 사용 가능
3. **자동 채널 선택**: 연동된 채널로 자동 발송
4. **다중 채널 발송**: 둘 다 연동 시 양쪽 모두 발송
5. **확장성 확보**: 향후 다른 채널(Slack, Discord 등) 추가 용이

---

## 3. 변경 후 구조

### 3.1 새로운 알림 발송 흐름

```
각 봇 (weather_bot, finance_bot, calendar_bot, memo_bot)
    ↓
NotificationService.send(user, message)
    ↓
┌─────────────────────┬─────────────────────┐
│ KakaoService        │ TelegramService     │
│ (access_token 존재) │ (chat_id 존재)      │
└─────────────────────┴─────────────────────┘
    ↓                       ↓
카카오톡 API            텔레그램 Bot API
```

### 3.2 새로운 파일 구조

```
app/
├── services/
│   ├── auth/
│   │   ├── kakao_auth.py      # (유지) 카카오 OAuth
│   │   └── google_auth.py     # (유지) 구글 OAuth
│   ├── notification/          # (신규) 알림 서비스 디렉토리
│   │   ├── __init__.py
│   │   ├── notification_service.py  # (신규) 알림 발송 통합 서비스
│   │   ├── kakao_sender.py          # (신규) 카카오톡 발송 모듈
│   │   └── telegram_sender.py       # (신규) 텔레그램 발송 모듈
│   └── bots/
│       ├── weather_bot.py     # (수정) NotificationService 사용
│       ├── finance_bot.py     # (수정) NotificationService 사용
│       ├── calendar_bot.py    # (수정) NotificationService 사용
│       └── memo_bot.py        # (수정) NotificationService 사용
├── models/
│   └── user.py                # (수정) telegram_chat_id 필드 추가
├── routers/
│   ├── auth.py                # (수정) 텔레그램 연동 엔드포인트 추가
│   └── settings.py            # (수정) 알림 채널 상태 표시
├── templates/
│   └── settings.html          # (수정) 텔레그램 연동 UI 추가
└── static/js/
    └── settings.js            # (수정) 텔레그램 연동 기능 추가
```

---

## 4. 구현 단계

### Phase T-1: NotificationService 기반 구축

**작업 항목**:
- [x] `app/services/notification/` 디렉토리 생성
- [x] `notification_service.py` 생성 (알림 발송 통합 서비스)
- [x] `kakao_sender.py` 생성 (기존 카카오 발송 로직 분리)
- [x] `__init__.py` 생성 및 export 설정

**NotificationService 핵심 인터페이스**:
```python
class NotificationService:
    async def send(self, user: User, message: str) -> NotificationResult:
        """연동된 모든 채널로 메시지 발송"""

    async def send_to_kakao(self, user: User, message: str) -> bool:
        """카카오톡으로만 발송"""

    async def send_to_telegram(self, user: User, message: str) -> bool:
        """텔레그램으로만 발송"""
```

### Phase T-2: 봇 리팩토링

**작업 항목**:
- [x] `weather_bot.py` 수정 (NotificationService 사용)
- [x] `finance_bot.py` 수정 (NotificationService 사용)
- [x] `calendar_bot.py` 수정 (NotificationService 사용)
- [x] `memo_bot.py` 수정 (NotificationService 사용)
- [x] 기존 기능 테스트 (카카오톡 발송 정상 동작 확인)

**변경 예시**:
```python
# 변경 전
from app.services.auth.kakao_auth import kakao_auth_service
await kakao_auth_service.send_message_to_me(user.kakao_access_token, message)

# 변경 후
from app.services.notification import notification_service
await notification_service.send(user, message)
```

### Phase T-3: 텔레그램 서비스 구현

**작업 항목**:
- [x] `telegram_sender.py` 생성
- [x] 텔레그램 Bot API 연동 구현
- [x] `notification_service.py`에 텔레그램 발송 통합
- [x] 환경변수 추가 (`TELEGRAM_BOT_TOKEN`)
- [x] `config.py`에 텔레그램 설정 추가

**TelegramSender 핵심 인터페이스**:
```python
class TelegramSender:
    async def send_message(self, chat_id: str, message: str) -> bool:
        """텔레그램 메시지 발송"""

    async def get_bot_info(self) -> dict:
        """봇 정보 조회 (연결 테스트용)"""
```

### Phase T-4: 데이터베이스 스키마 수정

**작업 항목**:
- [x] `models/user.py`에 `telegram_chat_id` 필드 추가
- [x] 마이그레이션 또는 테이블 재생성
- [x] CRUD 함수 추가 (`update_user_telegram_chat_id`, `disconnect_user_telegram`)

**User 모델 변경**:
```python
class User(Base):
    # 기존 필드
    kakao_access_token = Column(String)
    kakao_refresh_token = Column(String)

    # 신규 필드
    telegram_chat_id = Column(String, nullable=True)
```

### Phase T-5: 텔레그램 연동 API

**작업 항목**:
- [x] `routers/auth.py`에 텔레그램 연동 엔드포인트 추가
- [x] 텔레그램 연동 시작 API (`/auth/telegram/start`)
- [x] 텔레그램 연동 확인 API (`/auth/telegram/verify`)
- [x] 텔레그램 연동 해제 API (`/auth/telegram/disconnect`)
- [x] 텔레그램 연동 상태 API (`/auth/telegram/status`)
- [x] 텔레그램 테스트 발송 API (`/auth/telegram/test`)

**API 엔드포인트**:
```
GET  /api/auth/telegram/start      - 연동 시작 (봇 링크 반환)
POST /api/auth/telegram/verify     - 연동 확인 (chat_id 저장)
POST /api/auth/telegram/disconnect - 연동 해제
GET  /api/auth/telegram/status     - 연동 상태 조회
POST /api/auth/telegram/test       - 테스트 메시지 발송
```

### Phase T-6: UI 구현

**작업 항목**:
- [ ] `settings.html`에 텔레그램 연동 섹션 추가
- [ ] `settings.js`에 텔레그램 연동 기능 추가
- [ ] 연동 상태 표시 (연동됨/미연동)
- [ ] 연동/해제 버튼
- [ ] 테스트 메시지 발송 버튼

**UI 구성**:
```
[알림 채널 설정]
┌─────────────────────────────────────────────────┐
│ 카카오톡                                         │
│ ● 연동됨                        [연동 해제]      │
├─────────────────────────────────────────────────┤
│ 텔레그램                                         │
│ ○ 미연동                        [연동하기]       │
│                                                 │
│ 연동 방법:                                       │
│ 1. 아래 버튼을 클릭하여 텔레그램 봇 열기          │
│ 2. /start 명령어 입력                            │
│ 3. 표시된 코드를 아래에 입력                      │
│                                                 │
│ [텔레그램 봇 열기]                                │
│ 인증 코드: [____________] [확인]                 │
└─────────────────────────────────────────────────┘
```

### Phase T-7: 테스트 및 문서화

**작업 항목**:
- [ ] 카카오톡 단독 발송 테스트
- [ ] 텔레그램 단독 발송 테스트
- [ ] 양쪽 동시 발송 테스트
- [ ] 각 봇별 알림 발송 테스트
- [ ] 에러 처리 테스트 (한쪽 실패 시 다른 쪽 정상 발송)
- [ ] 본 문서 업데이트 (완료 체크)

---

## 5. 텔레그램 연동 흐름

### 5.1 사용자 연동 프로세스

```
1. 사용자가 Settings 페이지에서 "텔레그램 연동하기" 클릭
    ↓
2. 텔레그램 봇 링크 표시 (t.me/YourBotName)
    ↓
3. 사용자가 텔레그램에서 봇에 /start 명령 전송
    ↓
4. 봇이 인증 코드 생성 및 사용자에게 전송
    ↓
5. 사용자가 Settings 페이지에 인증 코드 입력
    ↓
6. 서버에서 코드 검증 후 chat_id 저장
    ↓
7. 연동 완료 - 이후 알림 발송 시 텔레그램으로도 발송
```

### 5.2 인증 코드 방식 vs Webhook 방식

| 방식 | 장점 | 단점 |
|------|------|------|
| **인증 코드** | 구현 간단, 서버 노출 불필요 | 수동 입력 필요 |
| **Webhook** | 자동 연동 | 서버 URL 노출, 복잡한 구현 |

**선택: 인증 코드 방식** (보안성, 구현 용이성)

---

## 6. 환경변수 추가

```env
# 기존
KAKAO_REST_API_KEY=xxx
KAKAO_REDIRECT_URI=xxx

# 신규
TELEGRAM_BOT_TOKEN=xxx
```

---

## 7. 데이터 모델 변경

### 7.1 User 모델

```python
class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True)

    # 카카오 (기존)
    kakao_access_token = Column(String, nullable=True)
    kakao_refresh_token = Column(String, nullable=True)

    # 구글 (기존)
    google_access_token = Column(String, nullable=True)
    google_refresh_token = Column(String, nullable=True)
    google_token_expiry = Column(DateTime, nullable=True)

    # 텔레그램 (신규)
    telegram_chat_id = Column(String, nullable=True)

    # 메타데이터
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
```

---

## 8. 고려사항

### 8.1 에러 처리

- 한 채널 발송 실패 시 다른 채널은 정상 발송
- 각 채널별 발송 결과를 개별 로깅
- 전체 실패 시에만 FAIL 로그 기록

### 8.2 메시지 길이

| 채널 | 최대 길이 |
|------|----------|
| 카카오톡 | 2,000자 |
| 텔레그램 | 4,096자 |

- NotificationService에서 채널별 메시지 길이 제한 처리

### 8.3 Rate Limiting

| 채널 | 제한 |
|------|------|
| 카카오톡 | 일 1,000건 |
| 텔레그램 | 초당 30건 |

- 현재 사용량으로는 제한에 도달할 가능성 낮음

### 8.4 하위 호환성

- 기존 카카오톡 연동 사용자는 변경 없이 계속 사용 가능
- 텔레그램 미연동 시 기존과 동일하게 카카오톡으로만 발송

---

## 9. 예상 작업량

| Phase | 신규 파일 | 수정 파일 | 예상 코드량 |
|-------|----------|----------|------------|
| T-1 | 4 | 0 | ~150줄 |
| T-2 | 0 | 4 | ~80줄 (수정) |
| T-3 | 1 | 2 | ~100줄 |
| T-4 | 0 | 2 | ~30줄 |
| T-5 | 0 | 1 | ~100줄 |
| T-6 | 0 | 2 | ~150줄 |
| T-7 | 0 | 1 | ~20줄 |
| **합계** | **5** | **12** | **~630줄** |

---

## 10. 완료 체크리스트

### Phase T-1: NotificationService 기반 구축
- [x] `app/services/notification/__init__.py`
- [x] `app/services/notification/notification_service.py`
- [x] `app/services/notification/kakao_sender.py`

### Phase T-2: 봇 리팩토링
- [x] `weather_bot.py` 수정
- [x] `finance_bot.py` 수정
- [x] `calendar_bot.py` 수정
- [x] `memo_bot.py` 수정
- [x] 카카오톡 발송 테스트 통과

### Phase T-3: 텔레그램 서비스 구현
- [x] `app/services/notification/telegram_sender.py`
- [x] `app/config.py` 수정
- [x] `.env.example` 수정
- [ ] 텔레그램 발송 테스트 통과

### Phase T-4: 데이터베이스 스키마 수정
- [x] `app/models/user.py` 수정
- [x] `app/crud.py` 수정
- [ ] 데이터베이스 마이그레이션

### Phase T-5: 텔레그램 연동 API
- [x] `app/routers/auth.py` 수정
- [x] 연동 시작 API (GET /auth/telegram/start)
- [x] 연동 확인 API (POST /auth/telegram/verify)
- [x] 연동 해제 API (POST /auth/telegram/disconnect)
- [x] 연동 상태 API (GET /auth/telegram/status)
- [x] 테스트 발송 API (POST /auth/telegram/test)

### Phase T-6: UI 구현
- [ ] `app/templates/settings.html` 수정
- [ ] `app/static/js/settings.js` 수정
- [ ] 연동 UI 테스트

### Phase T-7: 테스트 및 문서화
- [ ] 전체 기능 테스트
- [ ] 문서 업데이트
