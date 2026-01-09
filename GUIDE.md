# My-Kakao-Assistant 개발 가이드

## 1. 개발 규칙 (Development Rules)

### 1.1. 코드 스타일 및 컨벤션

```
Python Version: 3.10+
Formatter: Black (line-length=88)
Linter: Ruff
Type Checker: mypy (optional)
```

- **네이밍 규칙**
  - 파일명: snake_case (예: `kakao_auth.py`)
  - 클래스명: PascalCase (예: `KakaoAuthService`)
  - 함수/변수명: snake_case (예: `get_access_token`)
  - 상수: UPPER_SNAKE_CASE (예: `MAX_RETRY_COUNT`)

- **비동기 처리**
  - FastAPI 엔드포인트는 `async def` 사용
  - 외부 API 호출 시 `httpx.AsyncClient` 사용
  - 동기 작업(DB I/O 등)은 `run_in_executor` 활용

- **에러 처리**
  - 커스텀 예외 클래스 정의하여 일관된 에러 핸들링
  - 모든 외부 API 호출에 try-except 적용
  - 실패 시 Logs 테이블에 기록

### 1.2. 프로젝트 구조

```
my-assistant/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI 엔트리포인트
│   ├── config.py               # 환경변수 및 설정
│   ├── database.py             # SQLite 연결 및 세션 관리
│   │
│   ├── models/                 # SQLAlchemy ORM 모델
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── setting.py
│   │   ├── reminder.py
│   │   └── log.py
│   │
│   ├── schemas/                # Pydantic 스키마 (요청/응답)
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── setting.py
│   │   └── reminder.py
│   │
│   ├── services/               # 비즈니스 로직
│   │   ├── __init__.py
│   │   ├── auth/
│   │   │   ├── kakao_auth.py   # 카카오 OAuth
│   │   │   └── google_auth.py  # 구글 OAuth
│   │   ├── bots/
│   │   │   ├── weather_bot.py  # 날씨 알림
│   │   │   ├── finance_bot.py  # 금융 알림
│   │   │   ├── calendar_bot.py # 캘린더 알림
│   │   │   └── memo_bot.py     # 메모 알림
│   │   └── scheduler.py        # APScheduler 관리
│   │
│   ├── routers/                # API 라우터
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── settings.py
│   │   ├── reminders.py
│   │   └── dashboard.py
│   │
│   ├── templates/              # Jinja2 HTML 템플릿
│   │   ├── base.html
│   │   ├── dashboard.html
│   │   └── memo_form.html
│   │
│   └── static/                 # CSS, JS 정적 파일
│       ├── css/
│       └── js/
│
├── tests/                      # 테스트 코드
│   ├── __init__.py
│   ├── test_auth.py
│   └── test_bots.py
│
├── data/                       # SQLite DB 파일 저장
│   └── assistant.db
│
├── .env                        # 환경변수 (git 제외)
├── .env.example                # 환경변수 템플릿
├── requirements.txt            # 의존성 패키지
├── Dockerfile                  # Docker 이미지
├── docker-compose.yml          # Docker Compose 설정
└── README.md                   # 프로젝트 설명
```

### 1.3. 환경변수 관리

```bash
# .env.example
# Kakao API
KAKAO_REST_API_KEY=your_kakao_rest_api_key
KAKAO_REDIRECT_URI=http://localhost:8000/auth/kakao/callback

# Google API
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback

# OpenWeatherMap
OPENWEATHER_API_KEY=your_openweather_api_key

# Database
DATABASE_URL=sqlite:///./data/assistant.db

# App
SECRET_KEY=your_secret_key_for_session
DEBUG=True
```

### 1.4. 커밋 메시지 규칙

```
<type>(<scope>): <subject>

type: feat, fix, docs, style, refactor, test, chore
scope: auth, weather, finance, calendar, memo, ui, db
subject: 50자 이내 명령문

예시:
feat(auth): 카카오 OAuth 로그인 구현
fix(weather): API 응답 파싱 오류 수정
docs(readme): 설치 가이드 추가
```

---

## 2. 구현 단계 (Implementation Phases)

### Phase 0: 프로젝트 초기화 및 환경 구축

**목표**: 개발 환경 설정 및 프로젝트 기본 구조 생성

**작업 항목**:
- [x] Python 가상환경 생성 (`python -m venv venv`)
- [x] `requirements.txt` 작성 및 패키지 설치
- [x] 프로젝트 디렉토리 구조 생성
- [x] `.env.example` 파일 작성
- [x] FastAPI 기본 앱 생성 및 실행 테스트
- [x] Git 저장소 초기화 및 `.gitignore` 설정

**핵심 의존성**:
```
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
sqlalchemy>=2.0.0
apscheduler>=3.10.0
httpx>=0.26.0
python-dotenv>=1.0.0
jinja2>=3.1.0
python-multipart>=0.0.6
```

**완료 기준**:
- `uvicorn app.main:app --reload` 실행 시 서버 정상 구동
- `/` 엔드포인트 접근 시 "Hello World" 응답 확인

---

### Phase 1: 데이터베이스 및 기본 인프라 구축

**목표**: SQLite 데이터베이스 설정 및 ORM 모델 정의

**작업 항목**:
- [x] SQLAlchemy 데이터베이스 연결 설정 (`database.py`)
- [x] ORM 모델 정의
  - [x] `User` 모델 (토큰 정보 관리)
  - [x] `Setting` 모델 (알림 설정)
  - [x] `Reminder` 모델 (예약 메모)
  - [x] `Log` 모델 (시스템 로그)
- [x] Pydantic 스키마 정의 (요청/응답 검증)
- [x] 데이터베이스 초기화 스크립트 작성
- [x] CRUD 유틸리티 함수 작성

**핵심 파일**:
```python
# app/database.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

SQLALCHEMY_DATABASE_URL = "sqlite:///./data/assistant.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

**완료 기준**:
- `data/assistant.db` 파일 생성 확인
- 모든 테이블 스키마가 DDL 명세와 일치
- 기본 CRUD 테스트 통과

---

### Phase 2: 인증 모듈 개발

**목표**: 카카오/구글 OAuth 2.0 인증 구현

#### Phase 2-1: 카카오 OAuth 구현

**작업 항목**:
- [ ] Kakao Developers 앱 등록 및 설정
  - REST API 키 발급
  - Redirect URI 등록
  - 동의항목 설정 (talk_message 필수)
- [x] 카카오 로그인 플로우 구현
  - [x] `/auth/kakao/login` - 인증 URL 리다이렉트
  - [x] `/auth/kakao/callback` - 콜백 처리 및 토큰 저장
- [x] Access Token 갱신 로직 구현
- [x] "나에게 보내기" API 래퍼 함수 작성

**API 엔드포인트**:
```
GET  /auth/kakao/login     - 카카오 로그인 페이지로 리다이렉트
GET  /auth/kakao/callback  - 인증 코드 수신 및 토큰 발급
POST /auth/kakao/refresh   - Access Token 갱신
GET  /auth/kakao/status    - 인증 상태 확인
```

#### Phase 2-2: 구글 OAuth 구현

**작업 항목**:
- [ ] Google Cloud Console 프로젝트 설정
  - OAuth 2.0 클라이언트 ID 생성
  - Calendar API 활성화
  - 승인된 리디렉션 URI 등록
- [x] 구글 로그인 플로우 구현
  - [x] `/auth/google/login` - 인증 URL 리다이렉트
  - [x] `/auth/google/callback` - 콜백 처리 및 토큰 저장
- [x] Offline Access를 통한 Refresh Token 확보

**완료 기준**:
- 카카오 로그인 후 "나에게 보내기" 테스트 메시지 발송 성공
- 구글 로그인 후 캘린더 일정 조회 성공
- 토큰 DB 저장 및 갱신 정상 동작

---

### Phase 3: 코어 알림 모듈 개발

**목표**: 날씨/금융 정보 수집 및 정기 알림 발송

#### Phase 3-1: APScheduler 설정

**작업 항목**:
- [ ] BackgroundScheduler 초기화 및 FastAPI 라이프사이클 연동
- [ ] 스케줄러 상태 관리 (시작/중지/재시작)
- [ ] Job 등록/삭제/조회 유틸리티 함수 작성
- [ ] 서버 재시작 시 Job 복원 로직 구현

**핵심 파일**:
```python
# app/services/scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

scheduler = BackgroundScheduler(
    jobstores={
        'default': SQLAlchemyJobStore(url='sqlite:///./data/assistant.db')
    }
)
```

#### Phase 3-2: 날씨 알림 봇 (Weather Bot)

**작업 항목**:
- [ ] OpenWeatherMap API 클라이언트 구현
- [ ] 날씨 데이터 파싱 및 메시지 포맷팅
  - 최저/최고 기온
  - 강수 확률
  - 미세먼지 농도 (별도 API 필요 시 추가)
  - 우산 필요 여부 판단 로직
- [ ] 카카오톡 메시지 템플릿 작성
- [ ] 정기 발송 Job 등록 (CronTrigger)

**메시지 예시**:
```
[오늘의 날씨] 서울
- 기온: 최저 -2°C / 최고 7°C
- 강수확률: 20%
- 미세먼지: 보통
- 우산: 필요없음
```

#### Phase 3-3: 금융 알림 봇 (Finance Bot)

**작업 항목**:
- [ ] Yahoo Finance API 클라이언트 구현 (yfinance 라이브러리)
- [ ] PyKRX를 통한 국내 증시 데이터 수집
- [ ] 시황 데이터 파싱 및 메시지 포맷팅
  - S&P500, Nasdaq, Dow Jones
  - KOSPI, KOSDAQ
  - 관심 종목 변동률
- [ ] 미국/한국 시황 발송 시간 분리 설정

**메시지 예시**:
```
[미국 증시 마감] 2024-01-15
- S&P 500: 4,783.45 (+0.82%)
- Nasdaq: 15,055.65 (+1.15%)
- Dow Jones: 37,592.98 (+0.54%)
```

**완료 기준**:
- 설정된 시간에 날씨/금융 메시지 자동 발송
- Settings 테이블을 통한 ON/OFF 제어 동작
- 발송 성공/실패 로그 기록

---

### Phase 4: 확장 모듈 개발

**목표**: 구글 캘린더 연동 및 예약 메모 기능 구현

#### Phase 4-1: 캘린더 브리핑 봇 (Calendar Bot)

**작업 항목**:
- [ ] Google Calendar API 클라이언트 구현
- [ ] Primary 캘린더 일정 조회 로직
  - 당일 일정 필터링 (00:00 ~ 23:59)
  - 종일 일정 / 시간 지정 일정 구분
- [ ] 일정 메시지 포맷팅
- [ ] 정기 발송 Job 등록

**메시지 예시**:
```
[오늘의 일정] 2024-01-15 (월)

종일 일정:
- 프로젝트 마감일

시간 일정:
- 09:00~10:00 팀 미팅
- 14:00~15:00 고객사 미팅
- 18:30~19:30 헬스장
```

#### Phase 4-2: 예약 메모 봇 (Memo Bot)

**작업 항목**:
- [ ] 메모 CRUD API 구현
  - `POST /reminders` - 메모 등록
  - `GET /reminders` - 메모 목록 조회
  - `DELETE /reminders/{id}` - 메모 삭제
- [ ] 메모 등록 시 APScheduler Job 동적 추가
  - DateTrigger를 사용한 일회성 작업
- [ ] 메모 발송 후 `is_sent` 상태 업데이트
- [ ] 서버 재시작 시 미발송 메모 Job 복원 로직

**핵심 로직**:
```python
# 메모 등록 시 스케줄러에 Job 추가
def schedule_reminder(reminder_id: int, target_datetime: datetime, message: str):
    scheduler.add_job(
        send_kakao_message,
        trigger=DateTrigger(run_date=target_datetime),
        args=[message],
        id=f"reminder_{reminder_id}",
        replace_existing=True
    )
```

**완료 기준**:
- 캘린더 일정 요약 메시지 정상 발송
- 예약 메모 지정 시간에 발송 확인
- 서버 재시작 후 미발송 메모 정상 복원

---

### Phase 5: Web UI 대시보드 개발

**목표**: 설정 관리 및 메모 입력을 위한 웹 인터페이스 구현

#### Phase 5-1: 기본 레이아웃 및 대시보드

**작업 항목**:
- [ ] Jinja2 템플릿 설정 및 기본 레이아웃 작성
- [ ] CSS 프레임워크 적용 (Tailwind CSS 또는 Bootstrap)
- [ ] 대시보드 메인 페이지
  - 서비스 상태 표시 (Running/Stopped)
  - 모듈별 ON/OFF 토글 스위치
  - 최근 발송 로그 표시

**페이지 구성**:
```
/ (Dashboard)
├── 서비스 상태 카드
├── 모듈 설정 카드들
│   ├── 날씨 알림 설정
│   ├── 금융 알림 설정
│   └── 캘린더 알림 설정
└── 최근 활동 로그
```

#### Phase 5-2: 인증 연동 UI

**작업 항목**:
- [ ] 카카오 로그인 버튼 및 연동 상태 표시
- [ ] 구글 로그인 버튼 및 연동 상태 표시
- [ ] 토큰 만료 경고 표시

#### Phase 5-3: 메모 관리 UI

**작업 항목**:
- [ ] 메모 입력 폼
  - 메시지 내용 입력 (Textarea)
  - 발송 날짜/시간 선택 (Date/Time Picker)
  - 등록 버튼
- [ ] 예약 메모 목록 테이블
  - 발송 대기 중인 메모 표시
  - 취소 버튼 (Job 삭제 연동)
- [ ] AJAX를 통한 비동기 등록/삭제

**완료 기준**:
- 모든 UI 페이지 정상 렌더링
- 설정 변경 시 DB 및 스케줄러 반영
- 메모 등록/삭제 기능 정상 동작

---

### Phase 6: 통합 테스트 및 배포

**목표**: 전체 시스템 안정성 검증 및 배포 준비

#### Phase 6-1: 테스트

**작업 항목**:
- [ ] 단위 테스트 작성 (pytest)
  - 각 Bot 서비스 테스트
  - 스케줄러 동작 테스트
  - API 엔드포인트 테스트
- [ ] 통합 테스트
  - 전체 발송 플로우 테스트
  - 토큰 갱신 시나리오 테스트
- [ ] 에러 핸들링 검증
  - 외부 API 실패 시 동작 확인
  - 네트워크 오류 시 재시도 로직

#### Phase 6-2: Docker 패키징

**작업 항목**:
- [ ] Dockerfile 작성
- [ ] docker-compose.yml 작성
- [ ] 볼륨 마운트 설정 (DB 파일 보존)
- [ ] 환경변수 주입 설정

**Dockerfile 예시**:
```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### Phase 6-3: 배포

**작업 항목**:
- [ ] 로컬 서버 또는 NAS 배포
- [ ] 시스템 서비스 등록 (systemd 또는 Docker)
- [ ] 로그 로테이션 설정
- [ ] 백업 스크립트 작성 (DB 파일)

**완료 기준**:
- Docker 컨테이너 정상 실행
- 24시간 이상 안정적 운영 확인
- 모든 정기 알림 정상 발송

---

## 3. API 엔드포인트 요약

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/` | 대시보드 메인 |
| GET | `/auth/kakao/login` | 카카오 로그인 |
| GET | `/auth/kakao/callback` | 카카오 콜백 |
| GET | `/auth/google/login` | 구글 로그인 |
| GET | `/auth/google/callback` | 구글 콜백 |
| GET | `/api/settings` | 설정 조회 |
| PUT | `/api/settings/{category}` | 설정 수정 |
| GET | `/api/reminders` | 메모 목록 |
| POST | `/api/reminders` | 메모 등록 |
| DELETE | `/api/reminders/{id}` | 메모 삭제 |
| GET | `/api/logs` | 로그 조회 |
| POST | `/api/scheduler/start` | 스케줄러 시작 |
| POST | `/api/scheduler/stop` | 스케줄러 중지 |

---

## 4. 체크리스트

### 개발 시작 전 확인사항
- [ ] Python 3.10+ 설치 확인
- [ ] Kakao Developers 앱 등록 완료
- [ ] Google Cloud Console 프로젝트 생성 완료
- [ ] OpenWeatherMap API 키 발급 완료
- [ ] `.env` 파일에 모든 키 설정 완료

### 각 Phase 완료 기준
- [x] Phase 0: 서버 기본 실행 확인
- [x] Phase 1: DB 테이블 생성 및 CRUD 동작 확인
- [x] Phase 2: OAuth 로그인 및 토큰 저장 확인
- [ ] Phase 3: 날씨/금융 정기 알림 발송 확인
- [ ] Phase 4: 캘린더/메모 알림 발송 확인
- [ ] Phase 5: Web UI 정상 동작 확인
- [ ] Phase 6: Docker 배포 및 안정성 확인
