# 관리자 로그인 기능 구현 계획서

## 1. 개요

### 1.1 목표
- 개인용 프로젝트를 위한 단일 관리자 로그인 기능 구현
- 환경변수 기반 관리자 계정 관리
- 인증되지 않은 접근 차단

### 1.2 요구사항
- 관리자 1인만 로그인 대상
- 아이디/패스워드는 환경변수에 저장
- 세션 기반 인증 (간단하고 안전)
- 로그인 페이지 UI 제공
- 로그아웃 기능

---

## 2. 기술 선택

### 2.1 인증 방식 비교

| 방식 | 장점 | 단점 | 적합성 |
|------|------|------|--------|
| **세션 기반** | 간단, 서버 제어 용이, 로그아웃 확실 | 서버 메모리/저장소 필요 | 적합 |
| JWT 토큰 | Stateless, 확장성 | 로그아웃 복잡, 토큰 탈취 위험 | 과도함 |
| Basic Auth | 매우 간단 | 매 요청마다 인증, 보안 취약 | 부적합 |

**선택: 세션 기반 인증**
- 단일 사용자이므로 복잡한 JWT 불필요
- 서버 재시작 시 재로그인 필요 (보안상 오히려 장점)
- FastAPI의 `starlette-session` 활용

### 2.2 사용 라이브러리

```
itsdangerous>=2.1.0          # 세션 서명
python-multipart>=0.0.6      # 폼 데이터 파싱
passlib[bcrypt]>=1.7.4       # 비밀번호 해싱 (선택)
```

---

## 3. 구현 설계

### 3.1 환경변수

`.env` 파일에 추가:
```
# Admin Login
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your_secure_password
SESSION_SECRET_KEY=your_session_secret_key_32_chars_min
```

### 3.2 파일 구조

```
app/
├── config.py                 # (수정) 관리자 계정 설정 추가
├── main.py                   # (수정) 세션 미들웨어 추가
├── routers/
│   ├── auth.py               # (수정) 로그인/로그아웃 API 추가
│   └── pages.py              # (수정) 로그인 페이지 라우팅
├── services/
│   └── auth/
│       └── session_auth.py   # (신규) 세션 인증 로직
├── templates/
│   └── login.html            # (신규) 로그인 페이지
└── static/js/
    └── login.js              # (신규) 로그인 폼 처리 (선택)
```

### 3.3 인증 흐름

```
[미인증 사용자]
     │
     ▼
┌─────────────────┐
│  모든 페이지     │
│  (pages.py)     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     No      ┌─────────────────┐
│ 세션 유효 확인?  │ ──────────▶ │  /login 리다이렉트│
└────────┬────────┘             └─────────────────┘
         │ Yes                           │
         ▼                               ▼
┌─────────────────┐             ┌─────────────────┐
│   페이지 렌더링   │             │  로그인 폼 표시  │
└─────────────────┘             └────────┬────────┘
                                         │
                                         ▼
                                ┌─────────────────┐
                                │ POST /auth/login│
                                │ (아이디/비밀번호) │
                                └────────┬────────┘
                                         │
                                         ▼
                                ┌─────────────────┐     No
                                │  인증 성공?      │ ──────────▶ 에러 메시지
                                └────────┬────────┘
                                         │ Yes
                                         ▼
                                ┌─────────────────┐
                                │  세션 생성       │
                                │  메인 페이지 이동 │
                                └─────────────────┘
```

### 3.4 보호 범위

| 경로 | 인증 필요 | 비고 |
|------|----------|------|
| `/login` | X | 로그인 페이지 |
| `/auth/login` | X | 로그인 API |
| `/auth/logout` | O | 로그아웃 API |
| `/` | O | 메인 페이지 |
| `/settings` | O | 설정 페이지 |
| `/finance` | O | 금융 페이지 |
| `/weather` | O | 날씨 페이지 |
| `/calendar` | O | 캘린더 페이지 |
| `/api/*` | O | 모든 API |
| `/static/*` | X | 정적 파일 (CSS, JS) |

---

## 4. 상세 구현

### 4.1 config.py 수정

```python
class Settings:
    # ... 기존 설정 ...

    # Admin Login
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")
    SESSION_SECRET_KEY: str = os.getenv("SESSION_SECRET_KEY", "change-this-secret-key")
    SESSION_MAX_AGE: int = int(os.getenv("SESSION_MAX_AGE", "86400"))  # 24시간
```

### 4.2 세션 인증 서비스

**파일**: `app/services/auth/session_auth.py`

```python
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

def verify_admin_credentials(username: str, password: str) -> bool:
    """관리자 인증 확인"""
    return (
        username == settings.ADMIN_USERNAME and
        password == settings.ADMIN_PASSWORD
    )

def create_session(request: Request):
    """세션 생성"""
    request.session["authenticated"] = True
    request.session["username"] = settings.ADMIN_USERNAME

def destroy_session(request: Request):
    """세션 제거"""
    request.session.clear()

def is_authenticated(request: Request) -> bool:
    """인증 상태 확인"""
    return request.session.get("authenticated", False)

async def require_auth(request: Request):
    """인증 필요 의존성"""
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Not authenticated")
```

### 4.3 로그인/로그아웃 API

**파일**: `app/routers/auth.py` (추가)

```python
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from app.services.auth.session_auth import (
    verify_admin_credentials,
    create_session,
    destroy_session,
    is_authenticated
)

# 로그인 API
@router.post("/auth/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    if verify_admin_credentials(username, password):
        create_session(request)
        return RedirectResponse(url="/", status_code=303)
    else:
        return RedirectResponse(url="/login?error=1", status_code=303)

# 로그아웃 API
@router.post("/auth/logout")
async def logout(request: Request):
    destroy_session(request)
    return RedirectResponse(url="/login", status_code=303)

# 인증 상태 API
@router.get("/auth/status")
async def auth_status(request: Request):
    return {"authenticated": is_authenticated(request)}
```

### 4.4 main.py 수정

```python
from starlette.middleware.sessions import SessionMiddleware

# 세션 미들웨어 추가 (라우터 등록 전)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET_KEY,
    max_age=settings.SESSION_MAX_AGE,
    same_site="lax",
    https_only=not settings.DEBUG  # 프로덕션에서는 HTTPS 강제
)
```

### 4.5 인증 미들웨어

**옵션 A: 의존성 주입 방식**

```python
# 보호가 필요한 라우터에 의존성 추가
@router.get("/api/finance/watchlist")
async def get_watchlist(
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_auth)  # 인증 체크
):
    ...
```

**옵션 B: 미들웨어 방식 (권장)**

```python
# app/middleware/auth.py
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse

EXCLUDE_PATHS = [
    "/login",
    "/auth/login",
    "/static",
    "/favicon.ico",
]

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 제외 경로 체크
        if any(path.startswith(p) for p in EXCLUDE_PATHS):
            return await call_next(request)

        # 인증 체크
        if not request.session.get("authenticated"):
            if path.startswith("/api/"):
                return JSONResponse(
                    {"detail": "Not authenticated"},
                    status_code=401
                )
            return RedirectResponse(url="/login", status_code=303)

        return await call_next(request)
```

### 4.6 로그인 페이지 UI

**파일**: `app/templates/login.html`

```html
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - My Assistant</title>
    <link rel="stylesheet" href="/static/css/style.css">
</head>
<body>
    <div class="login-container">
        <h1>My Assistant</h1>
        <form action="/auth/login" method="post">
            <div class="form-group">
                <label for="username">Username</label>
                <input type="text" id="username" name="username" required>
            </div>
            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" required>
            </div>
            {% if error %}
            <div class="error-message">
                아이디 또는 비밀번호가 올바르지 않습니다.
            </div>
            {% endif %}
            <button type="submit">로그인</button>
        </form>
    </div>
</body>
</html>
```

### 4.7 pages.py 수정

```python
# 로그인 페이지 라우트 추가
@router.get("/login")
async def login_page(request: Request, error: str = None):
    # 이미 로그인된 경우 메인으로
    if request.session.get("authenticated"):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": error}
    )
```

---

## 5. 구현 단계

### Phase L-1: 기본 설정
- [ ] `requirements.txt`에 의존성 추가
- [ ] `.env.example`에 관리자 설정 추가
- [ ] `config.py`에 관리자 설정 추가

### Phase L-2: 세션 인증 구현
- [ ] `app/services/auth/session_auth.py` 생성
- [ ] `app/middleware/auth.py` 생성
- [ ] `main.py`에 세션 미들웨어 등록

### Phase L-3: 로그인 API 구현
- [ ] `auth.py`에 로그인/로그아웃 API 추가
- [ ] `pages.py`에 로그인 페이지 라우트 추가

### Phase L-4: UI 구현
- [ ] `templates/login.html` 생성
- [ ] `static/css/style.css`에 로그인 스타일 추가

### Phase L-5: 통합 및 테스트
- [ ] 인증 미들웨어 적용
- [ ] 모든 페이지 접근 테스트
- [ ] 로그인/로그아웃 테스트
- [ ] 세션 만료 테스트

---

## 6. 보안 고려사항

### 6.1 비밀번호 저장
- 환경변수에 평문 저장 (개인 프로젝트이므로 허용)
- 프로덕션 환경에서는 bcrypt 해싱 권장

### 6.2 세션 보안
- `SESSION_SECRET_KEY`: 최소 32자 이상의 랜덤 문자열
- `same_site="lax"`: CSRF 방지
- `https_only=True`: 프로덕션에서 HTTPS 강제

### 6.3 브루트포스 방지 (선택)
- 로그인 실패 시 지연 응답
- 연속 실패 시 일시적 잠금

---

## 7. 예상 작업량

| Phase | 신규 파일 | 수정 파일 | 예상 코드량 |
|-------|----------|----------|------------|
| L-1 | 0 | 3 | ~20줄 |
| L-2 | 2 | 1 | ~80줄 |
| L-3 | 0 | 2 | ~50줄 |
| L-4 | 1 | 1 | ~100줄 |
| L-5 | 0 | 0 | 테스트 |
| **합계** | **3** | **7** | **~250줄** |

---

## 8. 완료 체크리스트

### Phase L-1: 기본 설정
- [x] `requirements.txt` 의존성 추가 (`itsdangerous>=2.1.0` 추가)
- [x] `.env.example` 관리자 설정 추가
- [x] `config.py` 관리자 설정 추가

### Phase L-2: 세션 인증 구현
- [x] `session_auth.py` 생성
- [x] `auth.py` 미들웨어 생성
- [x] `main.py` 세션 미들웨어 등록

### Phase L-3: 로그인 API 구현
- [x] POST `/auth/login` 구현
- [x] POST `/auth/logout` 구현
- [x] GET `/auth/session/status` 구현
- [x] GET `/login` 페이지 라우트 구현

### Phase L-4: UI 구현
- [x] `login.html` 생성
- [x] 로그인 페이지 스타일 추가
- [x] `base.html`에 로그아웃 버튼 추가

### Phase L-5: 통합 및 테스트
- [x] 인증 미들웨어 적용 확인
- [x] 전체 기능 테스트 가이드 작성
- [x] 문서 업데이트

---

## 9. 구현 완료 요약

### 9.1 완료 일자
- **Phase L-1 ~ L-5**: 2026-01-19 완료

### 9.2 구현된 주요 기능

#### ✅ 세션 기반 인증
- 관리자 아이디/비밀번호 환경변수 관리
- 세션 생성 및 검증
- 자동 로그인 페이지 리다이렉트
- 24시간 세션 유지 (설정 가능)

#### ✅ 인증 미들웨어
- 모든 요청에 대한 세션 검증
- 제외 경로 설정 (로그인, 정적 파일 등)
- API 요청 시 401 JSON 응답
- 페이지 요청 시 리다이렉트

#### ✅ 로그인 UI
- 현대적인 그라데이션 디자인
- 반응형 레이아웃 (모바일 최적화)
- 에러 메시지 표시
- 로그아웃 버튼 (네비게이션 바)

#### ✅ API 엔드포인트
- POST `/auth/login` - 로그인 처리
- POST `/auth/logout` - 로그아웃 처리
- GET `/auth/session/status` - 세션 상태 확인
- GET `/login` - 로그인 페이지

#### ✅ 보안 기능
- 세션 암호화 (SESSION_SECRET_KEY)
- CSRF 방지 (same_site="lax")
- HTTPS 강제 (프로덕션)
- 로그인 실패 로그 기록

### 9.3 파일 변경 내역

| 파일 | 상태 | 변경 내용 |
|------|------|----------|
| `.env.example` | 수정 | 관리자 로그인 환경변수 추가 |
| `app/config.py` | 수정 | 관리자 로그인 설정 추가 |
| `app/services/auth/session_auth.py` | 신규 | 세션 인증 서비스 |
| `app/middleware/__init__.py` | 신규 | 미들웨어 패키지 초기화 |
| `app/middleware/auth.py` | 신규 | 인증 미들웨어 |
| `app/main.py` | 수정 | 세션/인증 미들웨어 등록 |
| `app/routers/auth.py` | 수정 | 로그인/로그아웃 API 추가 |
| `app/routers/pages.py` | 수정 | 로그인 페이지 라우트 추가 |
| `app/templates/login.html` | 신규 | 로그인 페이지 템플릿 |
| `app/templates/base.html` | 수정 | 로그아웃 버튼 추가 |
| `app/static/css/style.css` | 수정 | 로그인 페이지 스타일 추가 |
| `docs/login_test_guide.md` | 신규 | 테스트 가이드 문서 |

### 9.4 환경변수 설정 필요

`.env` 파일에 다음 항목을 추가해야 합니다:

```bash
# Admin Login
ADMIN_USERNAME=admin
ADMIN_PASSWORD=실제_사용할_비밀번호
SESSION_SECRET_KEY=최소_32자_이상의_랜덤_문자열
SESSION_MAX_AGE=86400
```

**중요**: `SESSION_SECRET_KEY`는 다음 명령으로 생성 권장:
```bash
openssl rand -hex 32
```

### 9.5 테스트 방법

상세한 테스트 가이드는 `docs/login_test_guide.md` 참조

**간단한 테스트 순서**:
1. `.env` 파일에 관리자 계정 설정
2. 서버 시작: `uvicorn app.main:app --reload`
3. 브라우저에서 `http://localhost:8000` 접속
4. 로그인 페이지로 자동 리다이렉트 확인
5. 관리자 계정으로 로그인
6. 모든 페이지 접근 가능 확인
7. 로그아웃 버튼으로 로그아웃

### 9.6 보안 권장사항

1. **강력한 비밀번호 사용**: 최소 12자 이상, 특수문자 포함
2. **SESSION_SECRET_KEY 보안**: 절대 공개 저장소에 커밋하지 않기
3. **프로덕션 환경**:
   - `DEBUG=False` 설정
   - HTTPS 사용
   - 방화벽 설정으로 접근 제한
4. **로그 모니터링**: 로그인 실패 시도 주기적 확인

---

**작성일**: 2026-01-19
**완료일**: 2026-01-19
**상태**: ✅ 모든 Phase 완료 (구현 완료)
