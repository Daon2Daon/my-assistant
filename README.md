# [통합 기능 명세서] 개인용 카카오톡 비서 앱 (My-Kakao-Assistant)

## 1. 개요 및 목표

* **프로젝트명**: My-Kakao-Assistant
* **목표**: 파이썬 자동화 스크립트를 통해 반복적인 정보 확인 과정을 생략하고, 중요한 일정과 메모를 적시에 메신저로 수신함.
* **주요 기능**: 날씨/금융/일정 정기 브리핑 + **예약 메모 알림**.
* **플랫폼**: Web Dashboard (설정용) + KakaoTalk (수신용).

## 2. 시스템 아키텍처

* **Core**: Python 3.10+
* **Web Framework**: FastAPI (가볍고 빠른 비동기 처리, UI 및 API 제공)
* **Database**: SQLite (파일 기반 RDBMS, 백업 및 관리 용이)
* **Scheduler**: APScheduler (`BackgroundScheduler` - 정기 작업 및 예약 작업 처리)
* **External APIs**:
* **Messaging**: Kakao Developers (REST API - 나에게 보내기)
* **Data**: OpenWeatherMap(날씨), Yahoo Finance/PyKRX(금융), Google Calendar API(일정)



## 3. 상세 기능 명세

### 3.1. 인증 및 사용자 관리 (Auth Module)

* **카카오 로그인 연동**
* OAuth 2.0 기반 인증.
* Access/Refresh Token 발급 및 DB 저장.
* Token 만료 전 자동 갱신 로직 구현 (데몬 프로세스).


* **구글 계정 연동**
* Google Calendar API (`calendar.readonly`) 권한 획득.
* Offline Access 설정을 통해 장기 사용 가능한 Refresh Token 확보.



### 3.2. 설정 대시보드 (Web UI)

* **대시보드 메인**
* 현재 서비스 상태(Running/Stopped) 모니터링.
* 각 모듈(날씨, 금융 등) ON/OFF 토글 스위치 제공.


* **메모 작성 UI (신규)**
* 입력 폼: 메모 내용(Text Area), 발송 날짜 및 시간(Date/Time Picker).
* 등록 버튼: 클릭 시 DB 저장 및 스케줄러에 작업 등록.
* 예약 목록: 발송 대기 중인 메모 리스트 확인 및 취소 기능.



### 3.3. 알림 모듈 상세

#### A. 날씨 알림 (Weather Bot)

* **기능**: 사용자가 설정한 지역의 당일 예보 요약 발송.
* **주기**: 매일 지정된 시각 (예: 06:30).
* **내용**: 최저/최고 기온, 강수 확률, 미세먼지 농도, 우산 필요 여부.

#### B. 금융 알림 (Finance Bot)

* **기능**: 글로벌 증시 및 관심 종목 변동 사항 브리핑.
* **주기**:
* 미국 시황: 매일 08:00 (S&P500, Nasdaq 등).
* 한국 시황: 매일 17:00 (Kospi, Kosdaq, 상위 종목).
* 급등락 알림: 장중 실시간 모니터링(옵션) 또는 장 마감 후 변동폭 알림.



#### C. 구글 캘린더 브리핑 (Calendar Bot)

* **기능**: 구글 캘린더 '주(Primary)' 캘린더의 일정 조회 및 요약.
* **주기**: 매일 지정된 시각 (예: 07:00).
* **로직**:
* 당일(00:00~23:59) 일정 필터링.
* 전일(All-day) 일정과 시간 지정 일정을 구분하여 포맷팅.



#### D. 예약 메모 발송 (Memo Bot) - 신규

* **기능**: 사용자가 입력한 메시지를 지정된 시간에 1회 발송함.
* **입력값**: `메시지 내용`, `발송 타겟 시간(YYYY-MM-DD HH:MM)`.
* **로직**:
1. UI에서 메모 등록 시 DB `reminders` 테이블에 저장.
2. APScheduler에 `add_job(date)` 형태로 일회성 작업 동적 등록.
3. 발송 시점 도래 시 카카오톡 전송 후, DB 상태를 '발송 완료'로 변경.



## 4. 데이터베이스 설계 (Integrated DB Schema)

기존 설계에 일회성 메모 저장을 위한 `Reminders` 테이블을 추가함.

### 4.1. ERD 개요

* **Users**: API 인증 토큰 관리.
* **Settings**: 정기 알림(날씨, 금융, 캘린더) 설정값 관리.
* **Reminders (New)**: 예약된 메모 데이터 관리.
* **Logs**: 발송 이력 및 에러 로그.

### 4.2. DDL (SQL Script)

```sql
-- 1. Users: 계정 및 토큰 정보
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    kakao_access_token TEXT,
    kakao_refresh_token TEXT,
    google_access_token TEXT,
    google_refresh_token TEXT,
    google_token_expiry DATETIME,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 2. Settings: 정기 알림 설정 (날씨, 금융, 캘린더)
CREATE TABLE IF NOT EXISTS settings (
    setting_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    category TEXT NOT NULL, -- 'weather', 'finance', 'calendar'
    notification_time TEXT NOT NULL, -- '06:30' (매일 반복 시간)
    config_json TEXT, -- 예: {"location":"Seoul"}
    is_active INTEGER DEFAULT 1,
    FOREIGN KEY(user_id) REFERENCES users(user_id)
);

-- 3. Reminders: 예약 메모
CREATE TABLE IF NOT EXISTS reminders (
    reminder_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    message_content TEXT NOT NULL, -- 메모 내용
    target_datetime DATETIME NOT NULL, -- 발송 예정 시간
    is_sent INTEGER DEFAULT 0, -- 0: 대기, 1: 발송완료
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(user_id)
);

-- 4. Logs: 시스템 로그
CREATE TABLE IF NOT EXISTS logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT, -- 'memo', 'weather' 등
    status TEXT, -- 'SUCCESS', 'FAIL'
    message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

```

## 5. 개발 로드맵 (Updated)

1. **1주차: 환경 구축 및 인증**
* FastAPI 프로젝트 생성 및 SQLite 연동.
* Kakao / Google Developer Console 프로젝트 생성 및 OAuth 구현.


2. **2주차: 코어 모듈 개발 (정기 알림)**
* APScheduler 설정 (Background 모드).
* 날씨(OpenWeatherMap), 금융(Yahoo Finance) 데이터 파싱 로직 구현.
* Settings 테이블 연동하여 정해진 시간에 메시지 발송 테스트.


3. **3주차: 확장 모듈 개발 (캘린더 & 메모)**
* Google Calendar API 연동 및 일정 파싱.
* **메모 예약 기능 구현**:
* DB Insert 시 스케줄러에 Job을 동적으로 추가하는 로직 개발.
* 서버 재시작 시 미발송된 메모(`is_sent=0`)를 스케줄러에 다시 로드하는 로직 구현.




4. **4주차: UI 개발 및 배포**
* Jinja2 템플릿 또는 Streamlit을 이용한 관리자 대시보드 제작.
* 메모 입력 폼 및 예약 확인 리스트 UI 구현.
* Docker 패키징 및 로컬 서버(또는 NAS) 배포.# my-assistant
