# 로그인 기능 테스트 가이드

## 1. 사전 준비

### 1.1 환경변수 설정

`.env` 파일에 다음 항목이 설정되어 있는지 확인하세요:

```bash
# Admin Login
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your_secure_password_change_this
SESSION_SECRET_KEY=your_session_secret_key_min_32_chars_change_this
SESSION_MAX_AGE=86400
```

**중요 사항:**
- `ADMIN_PASSWORD`: 실제로 사용할 비밀번호로 변경
- `SESSION_SECRET_KEY`: 최소 32자 이상의 랜덤 문자열로 변경
  - 예: `openssl rand -hex 32` 명령으로 생성 가능
- `SESSION_MAX_AGE`: 세션 유효 시간 (초 단위, 기본 24시간)

### 1.2 의존성 확인

필요한 패키지가 모두 설치되어 있는지 확인:

```bash
pip install -r requirements.txt
```

---

## 2. 서버 시작

### 2.1 로컬 서버 실행

```bash
# 프로젝트 루트 디렉토리에서
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2.2 서버 시작 확인

터미널에서 다음 메시지가 출력되는지 확인:
```
🚀 My Assistant 시작
🔧 DEBUG 모드: True
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

---

## 3. 기능 테스트

### 3.1 로그인 페이지 접근

**테스트 1: 미인증 상태에서 메인 페이지 접근**

1. 브라우저에서 `http://localhost:8000/` 접속
2. **예상 결과**: 자동으로 `/login` 페이지로 리다이렉트
3. **확인 사항**:
   - 보라색 그라데이션 배경
   - 로그인 폼 표시
   - Username, Password 입력 필드
   - 로그인 버튼

**테스트 2: 로그인 페이지 직접 접근**

1. 브라우저에서 `http://localhost:8000/login` 접속
2. **예상 결과**: 로그인 페이지 정상 표시

---

### 3.2 로그인 기능 테스트

**테스트 3: 잘못된 인증 정보로 로그인 시도**

1. Username: `wrong`
2. Password: `wrong`
3. 로그인 버튼 클릭
4. **예상 결과**:
   - `/login?error=1`으로 리다이렉트
   - 에러 메시지 표시: "아이디 또는 비밀번호가 올바르지 않습니다."
   - 빨간색 경고 알림 표시

**테스트 4: 올바른 인증 정보로 로그인**

1. Username: `.env` 파일의 `ADMIN_USERNAME` 값
2. Password: `.env` 파일의 `ADMIN_PASSWORD` 값
3. 로그인 버튼 클릭
4. **예상 결과**:
   - 메인 페이지(`/`)로 리다이렉트
   - 네비게이션 바 표시
   - "Logout" 버튼 표시

**테스트 5: 로그인 상태에서 로그인 페이지 접근**

1. 로그인한 상태에서 `http://localhost:8000/login` 접속
2. **예상 결과**: 자동으로 `/`로 리다이렉트

---

### 3.3 인증된 페이지 접근 테스트

**테스트 6: 모든 페이지 접근**

로그인 후 다음 페이지들이 정상적으로 접근되는지 확인:

- [ ] Home: `http://localhost:8000/`
- [ ] Weather: `http://localhost:8000/weather`
- [ ] Finance: `http://localhost:8000/finance`
- [ ] Calendar: `http://localhost:8000/calendar`
- [ ] Reminders: `http://localhost:8000/reminders`
- [ ] Logs: `http://localhost:8000/logs`
- [ ] Settings: `http://localhost:8000/settings`

**예상 결과**: 모든 페이지 정상 접근

---

### 3.4 API 인증 테스트

**테스트 7: 미인증 API 접근**

1. 브라우저 개발자 도구 콘솔 열기 (F12)
2. 새 시크릿 창 열기 (로그아웃 상태)
3. 콘솔에서 다음 실행:
```javascript
fetch('http://localhost:8000/api/finance/watchlist')
  .then(r => r.json())
  .then(console.log)
```
4. **예상 결과**: `{"detail": "Not authenticated"}` (401 에러)

**테스트 8: 인증된 API 접근**

1. 로그인한 상태에서 콘솔 실행:
```javascript
fetch('http://localhost:8000/api/finance/watchlist')
  .then(r => r.json())
  .then(console.log)
```
2. **예상 결과**: 정상 응답 (빈 배열 또는 종목 목록)

---

### 3.5 로그아웃 기능 테스트

**테스트 9: 로그아웃**

1. 네비게이션 바의 "Logout" 버튼 클릭
2. **예상 결과**:
   - `/login` 페이지로 리다이렉트
   - 세션 제거됨
   - 다시 메인 페이지 접근 시 로그인 페이지로 이동

**테스트 10: 로그아웃 후 브라우저 뒤로가기**

1. 로그아웃 후 브라우저 뒤로가기 버튼 클릭
2. **예상 결과**: 로그인 페이지로 리다이렉트 (캐시된 페이지 접근 차단)

---

### 3.6 세션 상태 API 테스트

**테스트 11: 세션 상태 확인**

1. 로그인 전:
```bash
curl http://localhost:8000/auth/session/status
```
**예상 결과**: `{"authenticated": false, "username": null}`

2. 로그인 후 (브라우저 개발자 도구 콘솔):
```javascript
fetch('/auth/session/status')
  .then(r => r.json())
  .then(console.log)
```
**예상 결과**: `{"authenticated": true, "username": "admin"}`

---

### 3.7 정적 파일 접근 테스트

**테스트 12: 인증 없이 정적 파일 접근**

1. 로그아웃 상태에서 `http://localhost:8000/static/css/style.css` 접속
2. **예상 결과**: CSS 파일 정상 로드 (인증 불필요)

---

## 4. 로그 확인

### 4.1 데이터베이스 로그 확인

로그인/로그아웃 시 데이터베이스에 로그가 기록되는지 확인:

```bash
# SQLite 데이터베이스 확인
sqlite3 data/assistant.db "SELECT * FROM logs WHERE category='auth' ORDER BY created_at DESC LIMIT 10;"
```

**예상 결과**:
```
로그인 성공 메시지
로그아웃 메시지
로그인 실패 메시지 (잘못된 인증 정보 시)
```

### 4.2 서버 로그 확인

터미널에서 다음 로그가 출력되는지 확인:
```
✅ 관리자 로그인 성공 (username: admin)
⚠️  관리자 로그인 실패 (username: wrong)
✅ 관리자 로그아웃 (username: admin)
```

---

## 5. 브라우저 호환성 테스트

다음 브라우저에서 테스트:
- [ ] Chrome/Edge (Chromium)
- [ ] Firefox
- [ ] Safari

**확인 사항**:
- 로그인 페이지 디자인 정상 표시
- 폼 제출 정상 작동
- 세션 유지 정상 작동

---

## 6. 모바일 반응형 테스트

### 6.1 모바일 화면 크기 테스트

1. 브라우저 개발자 도구 열기 (F12)
2. 디바이스 툴바 활성화 (Ctrl+Shift+M)
3. 다양한 화면 크기로 테스트:
   - iPhone SE (375px)
   - iPhone 12 Pro (390px)
   - iPad (768px)

**확인 사항**:
- 로그인 카드 크기 적절히 조정
- 입력 필드 모바일에서 사용 가능
- 버튼 터치하기 적절한 크기

---

## 7. 보안 테스트

### 7.1 CSRF 보호 확인

**테스트 13: Cross-Site 폼 제출 차단**

외부 사이트에서 로그인 폼 제출 시도:
```html
<!-- 다른 도메인에서 -->
<form action="http://localhost:8000/auth/login" method="post">
    <input name="username" value="admin">
    <input name="password" value="password">
    <button>Submit</button>
</form>
```
**예상 결과**: `same_site="lax"` 설정으로 인해 세션 쿠키 전송 차단

### 7.2 세션 고정 공격 방어

**테스트 14: 로그인 후 세션 ID 변경**

1. 로그인 전 세션 쿠키 확인
2. 로그인 수행
3. 로그인 후 세션 쿠키 확인
4. **예상 결과**: 세션 ID 변경됨 (Starlette SessionMiddleware의 기본 동작)

---

## 8. 성능 테스트

### 8.1 세션 조회 성능

**테스트 15: 세션 체크 오버헤드**

1. 로그인 상태에서 여러 페이지 빠르게 이동
2. **예상 결과**: 빠른 응답 시간 (세션 조회는 매우 빠름)

---

## 9. 에러 처리 테스트

### 9.1 환경변수 누락 시나리오

**테스트 16: 관리자 비밀번호 미설정**

1. `.env` 파일에서 `ADMIN_PASSWORD` 제거 또는 빈 값으로 설정
2. 서버 재시작
3. 로그인 시도
4. **예상 결과**: 어떤 비밀번호로도 로그인 불가

### 9.2 세션 키 누락 시나리오

**테스트 17: SESSION_SECRET_KEY 미설정**

1. `.env` 파일에서 `SESSION_SECRET_KEY` 제거
2. 서버 재시작
3. **예상 결과**: 기본값으로 동작 (경고 권장)

---

## 10. 체크리스트

### 기본 기능
- [ ] 미인증 시 로그인 페이지로 리다이렉트
- [ ] 올바른 인증 정보로 로그인 성공
- [ ] 잘못된 인증 정보로 로그인 실패
- [ ] 로그인 후 모든 페이지 접근 가능
- [ ] 로그아웃 정상 작동
- [ ] 세션 상태 API 정상 동작

### UI/UX
- [ ] 로그인 페이지 디자인 정상 표시
- [ ] 에러 메시지 정상 표시
- [ ] 로그아웃 버튼 네비게이션에 표시
- [ ] 모바일 반응형 정상 작동

### 보안
- [ ] API 접근 인증 체크
- [ ] 정적 파일은 인증 불필요
- [ ] `/health` 엔드포인트는 인증 불필요
- [ ] 세션 쿠키 보안 설정 확인

### 로그
- [ ] 로그인 성공 로그 기록
- [ ] 로그인 실패 로그 기록
- [ ] 로그아웃 로그 기록

---

## 11. 알려진 이슈 및 해결 방법

### 이슈 1: 로그인 후에도 계속 로그인 페이지로 리다이렉트

**원인**: SESSION_SECRET_KEY가 서버 재시작 시 변경됨

**해결**: `.env` 파일에 고정된 SESSION_SECRET_KEY 설정

### 이슈 2: 로그아웃 버튼 클릭 시 아무 일도 일어나지 않음

**원인**: 브라우저 캐시 또는 CSRF 토큰 문제

**해결**: 브라우저 캐시 삭제 후 재시도

### 이슈 3: 개발 환경에서 HTTPS 경고

**원인**: `https_only=True` 설정이지만 HTTP 사용

**해결**: `.env`에서 `DEBUG=True` 설정 확인 (자동으로 `https_only=False` 적용)

---

## 12. 결론

모든 테스트가 통과하면 로그인 기능이 정상적으로 구현된 것입니다.

**최종 확인 사항**:
1. `.env` 파일에 실제 관리자 계정 정보 설정
2. `SESSION_SECRET_KEY`를 강력한 랜덤 문자열로 설정
3. 프로덕션 환경에서는 `DEBUG=False` 설정
4. HTTPS 사용 시 `https_only=True` 적용 확인

---

**작성일**: 2026-01-19
**버전**: 1.0.0
