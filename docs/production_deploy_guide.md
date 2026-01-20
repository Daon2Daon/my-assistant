# 프로덕션 배포 가이드

## 특수문자 포함 비밀번호 처리

### 문제 상황

로컬 환경에서는 로그인이 성공하지만, 프로덕션 Docker 환경에서는 실패하는 경우, 환경변수에 특수문자가 포함되어 있을 가능성이 높습니다.

### 원인

Docker Compose의 `environment` 섹션에서 `${VARIABLE}` 형식으로 환경변수를 참조할 때, 쉘이 특수문자(`$`, `!`, `@`, `#`, `&` 등)를 해석하면서 값이 변경될 수 있습니다.

### 해결 방법

**업데이트된 docker-compose.yml**은 `env_file`을 사용하여 이 문제를 해결했습니다.

---

## .env 파일 작성 규칙

### ✅ 올바른 작성 방법

```bash
# 특수문자가 포함된 경우 - 따옴표 없이 작성
ADMIN_PASSWORD=P@ssw0rd!2024#Secure

# 공백이 포함되지 않은 일반 값
ADMIN_USERNAME=admin
SECRET_KEY=your-secret-key-here

# URL이나 경로
DATABASE_URL=sqlite:///./data/assistant.db
KAKAO_REDIRECT_URI=https://yourdomain.com/auth/kakao/callback
```

### ❌ 잘못된 작성 방법

```bash
# 따옴표를 사용하면 따옴표까지 값에 포함됨
ADMIN_PASSWORD="P@ssw0rd!2024"  # ❌ 실제 값: "P@ssw0rd!2024" (따옴표 포함)
ADMIN_PASSWORD='P@ssw0rd!2024'  # ❌ 실제 값: 'P@ssw0rd!2024' (따옴표 포함)

# 주석이 값에 붙으면 안 됨
ADMIN_PASSWORD=secret#comment  # ❌ '#' 이후는 주석으로 처리됨
```

### 특수문자별 주의사항

| 특수문자 | 주의사항 | 해결 | 예시 |
|----------|----------|------|------|
| `#` | 주석으로 인식됨 | 사용 자제 | `P@ssw0rd#123` → `P@ssw0rd` (뒤 잘림) |
| `$` | 변수 치환 시도 | env_file 사용 | `Pass$word` → env_file로 안전 |
| `!` | **Bash 히스토리 확장** | **env_file 사용** | `Pass!123` → **env_file로 안전** |
| `"` `'` | 따옴표는 사용하지 말 것 | 절대 사용 안 함 | 값에 포함됨 |
| 공백 | 공백 포함 불가 | 공백 없이 작성 | 공백 없이 작성 |

### ⚠️ '!' 문자 특별 주의사항

**문제**: `!` 문자는 Bash의 히스토리 확장(history expansion) 기능을 트리거합니다.

**증상**:
```bash
# .env 파일
ADMIN_PASSWORD=MyP@ss!2024

# 로컬에서는 동작하지만, 프로덕션에서 로그인 실패
```

**해결 방법 1: docker-compose.yml 수정 (권장, 이미 적용됨)**

업데이트된 `docker-compose.yml`은 `environment` 섹션에서 변수 치환을 제거했습니다:

```yaml
# 변경 후 (안전)
env_file:
  - .env
environment:
  - TZ=Asia/Seoul  # 고정값만
```

**해결 방법 2: 비밀번호 변경 (대안)**

만약 여전히 문제가 발생한다면, `!` 문자를 다른 특수문자로 변경하세요:

```bash
# 대체 가능한 안전한 특수문자
@ % & * ( ) - _ + = [ ] { } ; : , . / ?

# 예시
ADMIN_PASSWORD=MyP@ss*2024  # ! → * 변경
ADMIN_PASSWORD=MyP@ss_2024  # ! → _ 변경
```

### 권장 비밀번호 형식

```bash
# 안전한 특수문자 조합 (추천)
ADMIN_PASSWORD=MySecureP@ssw0rd2024
SESSION_SECRET_KEY=AbCdEf123456GhIjKl789012MnOpQr345678

# 피해야 할 문자: # $ ! (가능하면 사용 안 함)
# 사용 가능: @ % & * ( ) - _ + = [ ] { } ; : , . / ?
```

---

## 프로덕션 배포 절차

### 1. .env 파일 생성

서버에서 `.env` 파일을 생성합니다:

```bash
cd /path/to/my-assistant
nano .env
```

`.env.example`을 참고하여 모든 환경변수를 설정하세요:

```bash
# App
SECRET_KEY=your_production_secret_key_min_32_chars
DEBUG=False

# Admin Login
ADMIN_USERNAME=admin
ADMIN_PASSWORD=YourSecureP@ssw0rd2024
SESSION_SECRET_KEY=your_session_secret_key_min_32_chars
SESSION_MAX_AGE=86400

# Kakao API
KAKAO_REST_API_KEY=your_kakao_key
KAKAO_REDIRECT_URI=https://yourdomain.com/auth/kakao/callback

# Google API
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=https://yourdomain.com/auth/google/callback

# OpenWeatherMap
OPENWEATHER_API_KEY=your_weather_api_key

# Telegram Bot
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
```

### 2. .env 파일 권한 설정

보안을 위해 .env 파일의 권한을 제한합니다:

```bash
chmod 600 .env
```

### 3. Docker Compose 실행

```bash
# 기존 컨테이너 중지 및 삭제
docker compose down

# 새 컨테이너 시작
docker compose up -d

# 로그 확인
docker compose logs -f my-assistant
```

### 4. 환경변수 검증 (중요!)

컨테이너 시작 후 반드시 환경변수가 올바르게 설정되었는지 확인하세요:

```bash
# 1. 비밀번호 길이 확인
docker compose exec my-assistant python -c "import os; pwd=os.getenv('ADMIN_PASSWORD'); print(f'Password length: {len(pwd) if pwd else 0}')"

# 2. 비밀번호에 '!' 문자 포함 여부 확인
docker compose exec my-assistant python -c "import os; pwd=os.getenv('ADMIN_PASSWORD'); print(f'Contains !: {chr(33) in pwd if pwd else False}')"

# 3. 비밀번호 앞 3글자 확인 (디버깅용)
docker compose exec my-assistant python -c "import os; pwd=os.getenv('ADMIN_PASSWORD'); print(f'First 3 chars: {pwd[:3] if pwd and len(pwd) >= 3 else pwd}')"

# 4. 모든 환경변수 확인
docker compose exec my-assistant printenv | grep ADMIN
```

**예상 출력**:
```
Password length: 16
Contains !: True
First 3 chars: MyP
ADMIN_USERNAME=admin
ADMIN_PASSWORD=MyP@ss!2024
```

### 5. 로그인 테스트

1. 브라우저에서 `https://yourdomain.com/login` 접속
2. .env 파일에 설정한 `ADMIN_USERNAME`과 `ADMIN_PASSWORD`로 로그인
3. 로그인 실패 시:
   ```bash
   # 컨테이너 로그에서 디버그 정보 확인
   docker compose logs my-assistant | grep "AUTH DEBUG"
   ```

---

## 문제 해결

### 🚨 긴급 트러블슈팅 ('!' 문자 문제)

**증상**: 로컬에서는 로그인 성공, 프로덕션에서는 로그인 실패, 비밀번호에 '!' 포함

**즉시 실행할 명령어**:

```bash
# 서버에서 실행
cd /path/to/my-assistant

# 1. 현재 컨테이너의 비밀번호 확인
docker compose exec my-assistant python -c "import os; pwd=os.getenv('ADMIN_PASSWORD'); print(f'Has !: {chr(33) in pwd if pwd else False}'); print(f'Len: {len(pwd) if pwd else 0}')"

# 2. .env 파일 확인
cat .env | grep ADMIN_PASSWORD

# 3. 비교
# - .env 파일의 비밀번호 길이와 컨테이너 내부 길이가 다르면 → 변수 치환 문제
# - '!' 문자가 사라졌으면 → Bash 히스토리 확장 문제
```

**즉시 해결 방법**:

1. **최신 docker-compose.yml로 업데이트**:
   ```bash
   # Git에서 최신 버전 받기
   git pull origin main

   # 또는 수동으로 수정
   nano docker-compose.yml
   ```

   확인할 내용:
   ```yaml
   env_file:
     - .env
   environment:
     - TZ=Asia/Seoul  # 이것만 있어야 함!
   ```

2. **컨테이너 재시작**:
   ```bash
   docker compose down
   docker compose up -d
   ```

3. **검증**:
   ```bash
   docker compose exec my-assistant python -c "import os; pwd=os.getenv('ADMIN_PASSWORD'); print(f'Contains !: {chr(33) in pwd if pwd else False}')"
   # 출력: Contains !: True (이렇게 나와야 정상)
   ```

4. **여전히 실패한다면 - 비밀번호 임시 변경**:
   ```bash
   # .env 파일에서 '!'를 다른 문자로 변경
   nano .env
   # ADMIN_PASSWORD=MyP@ss*2024  (! → * 변경)

   docker compose restart
   ```

### 로그인 실패 시 디버깅

#### 1. 환경변수 확인

컨테이너 내부에서 환경변수가 올바르게 설정되었는지 확인:

```bash
docker compose exec my-assistant printenv | grep ADMIN
```

**확인 사항**:
- `ADMIN_PASSWORD`에 따옴표가 포함되어 있지 않은지
- 특수문자가 올바르게 전달되었는지
- 공백이나 개행문자가 없는지

#### 2. 로그 확인

```bash
docker compose logs my-assistant | tail -50
```

**디버그 로그 예시**:
```
[AUTH DEBUG] 입력된 username: admin
[AUTH DEBUG] 설정된 ADMIN_USERNAME: admin
[AUTH DEBUG] username 일치: True
[AUTH DEBUG] password 일치: False
[AUTH DEBUG] 입력된 password의 특수문자: ['@', '!']
[AUTH DEBUG] 설정된 ADMIN_PASSWORD의 특수문자: []
```

위와 같이 특수문자가 사라졌다면 `.env` 파일 작성 문제입니다.

#### 3. .env 파일 재확인

```bash
cat .env | grep ADMIN_PASSWORD
```

**출력 예시**:
```bash
# 올바른 경우
ADMIN_PASSWORD=P@ssw0rd!2024

# 잘못된 경우
ADMIN_PASSWORD="P@ssw0rd!2024"  # ❌ 따옴표 포함
ADMIN_PASSWORD=P@ssw0rd#2024    # ❌ #이 주석으로 인식됨
```

### 일반적인 오류 패턴

| 증상 | 원인 | 해결 |
|------|------|------|
| 비밀번호 끝부분이 잘림 | `#` 문자 사용 | `.env`에서 `#` 제거 또는 다른 문자 사용 |
| 따옴표가 비밀번호에 포함됨 | `.env`에 따옴표 사용 | 따옴표 제거 |
| 환경변수가 비어있음 | `.env` 파일 누락 | `.env` 파일 생성 확인 |
| 변수명 오타 | 대소문자 불일치 | 정확한 변수명 사용 |

---

## 보안 권장사항

### 1. .env 파일 관리

```bash
# .gitignore에 .env 추가 (이미 포함되어 있음)
echo ".env" >> .gitignore

# .env 파일 권한 설정
chmod 600 .env

# 소유자 확인
ls -la .env
# -rw------- 1 user group ... .env
```

### 2. 강력한 비밀번호 생성

```bash
# 랜덤 비밀번호 생성 (32자, 특수문자 포함)
openssl rand -base64 32

# 또는 Python으로 생성
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 3. SESSION_SECRET_KEY 설정

```bash
# 최소 32자 이상의 랜덤 문자열
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 4. 정기적인 비밀번호 변경

- 관리자 비밀번호: 3-6개월마다 변경
- SECRET_KEY, SESSION_SECRET_KEY: 변경 시 모든 세션 무효화됨 (주의)

---

## 컨테이너 재시작 (환경변수 변경 후)

`.env` 파일을 수정한 후에는 반드시 컨테이너를 재시작해야 합니다:

```bash
# 방법 1: 재시작만
docker compose restart

# 방법 2: 중지 후 재시작 (권장)
docker compose down
docker compose up -d

# 로그 확인
docker compose logs -f my-assistant
```

---

## 체크리스트

배포 전 확인 사항:

- [ ] `.env` 파일 생성 완료
- [ ] `.env` 파일 권한 `600`으로 설정
- [ ] `ADMIN_PASSWORD`에 따옴표 없이 작성
- [ ] `#` 문자를 주석이 아닌 곳에서 사용하지 않음
- [ ] 모든 필수 환경변수 설정 완료
- [ ] `DEBUG=False` 설정 (프로덕션)
- [ ] REDIRECT_URI가 실제 도메인으로 설정됨
- [ ] 컨테이너 재시작 완료
- [ ] 로그인 테스트 성공

---

## 추가 도움말

### env_file vs environment 차이

**기존 방식 (environment)**:
```yaml
environment:
  - ADMIN_PASSWORD=${ADMIN_PASSWORD}  # 쉘이 특수문자 해석
```

**새 방식 (env_file)**:
```yaml
env_file:
  - .env  # Docker가 직접 파일 읽음, 특수문자 안전
environment:
  - TZ=Asia/Seoul  # 기본값만 설정
```

`env_file`을 사용하면:
- ✅ 특수문자가 안전하게 처리됨
- ✅ 쉘 확장 없이 값이 그대로 전달됨
- ✅ 보안이 향상됨 (.env 파일 권한 관리)

---

**작성일**: 2026-01-19
**최종 업데이트**: 2026-01-19
