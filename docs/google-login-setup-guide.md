# 구글 로그인 설정 가이드

이 문서는 My Assistant 프로젝트에서 구글 로그인(Google OAuth 2.0)을 설정하는 방법을 안내합니다.

## 개요

구글 로그인을 통해 Google Calendar API에 접근하여 일정 정보를 조회할 수 있습니다. OAuth 2.0 인증 방식을 사용하며, 다음 권한이 필요합니다:

- `https://www.googleapis.com/auth/calendar.readonly` - 캘린더 읽기 권한
- `openid` - 사용자 인증
- `https://www.googleapis.com/auth/userinfo.email` - 이메일 정보 조회

## 설정 단계

### 1단계: Google Cloud Console 프로젝트 생성

1. [Google Cloud Console](https://console.cloud.google.com/)에 접속합니다.
2. 상단 프로젝트 선택 메뉴에서 **"새 프로젝트"**를 클릭합니다.
3. 프로젝트 이름을 입력하고 **"만들기"**를 클릭합니다.
   - 예: `my-assistant`
4. 프로젝트가 생성되면 해당 프로젝트를 선택합니다.

### 2단계: OAuth 동의 화면 구성

1. 좌측 메뉴에서 **"API 및 서비스"** > **"OAuth 동의 화면"**을 선택합니다.
2. 사용자 유형을 선택합니다:
   - **외부**: 일반 사용자들이 사용하는 앱인 경우
   - **내부**: Google Workspace 조직 내부에서만 사용하는 경우
3. 앱 정보를 입력합니다:
   - **앱 이름**: 예) `My Assistant`
   - **사용자 지원 이메일**: 본인의 이메일 주소
   - **앱 로고**: 선택사항
   - **앱 도메인**: 선택사항
   - **개발자 연락처 정보**: 본인의 이메일 주소
4. **"저장 후 계속"**을 클릭합니다.
5. **"범위"** 단계에서:
   - **"범위 추가 또는 삭제"**를 클릭합니다.
   - 다음 범위를 추가합니다:
     - `https://www.googleapis.com/auth/calendar.readonly`
     - `openid`
     - `https://www.googleapis.com/auth/userinfo.email`
   - **"업데이트"**를 클릭합니다.
6. **"저장 후 계속"**을 클릭합니다.
7. **"테스트 사용자"** 단계에서:
   - 본인의 구글 계정 이메일을 추가합니다 (외부 앱인 경우 필수).
   - 여러 계정을 사용할 경우 모두 추가합니다.
8. **"저장 후 계속"**을 클릭하고 마지막 단계에서 **"대시보드로 돌아가기"**를 클릭합니다.

### 3단계: OAuth 2.0 클라이언트 ID 생성

1. 좌측 메뉴에서 **"API 및 서비스"** > **"사용자 인증 정보"**를 선택합니다.
2. 상단의 **"+ 사용자 인증 정보 만들기"** > **"OAuth 클라이언트 ID"**를 선택합니다.
3. 애플리케이션 유형을 **"웹 애플리케이션"**으로 선택합니다.
4. 이름을 입력합니다 (예: `My Assistant Web Client`).
5. **승인된 리디렉션 URI**에 다음을 추가합니다:
   - 개발 환경: `http://localhost:8000/auth/google/callback`
   - 프로덕션 환경: `https://your-domain.com/auth/google/callback`
   - 여러 환경을 사용하는 경우 모두 추가합니다.
6. **"만들기"**를 클릭합니다.
7. 팝업 창에서 **클라이언트 ID**와 **클라이언트 보안 비밀번호**를 복사합니다.
   - 이 정보는 나중에 다시 확인할 수 없으므로 안전한 곳에 보관하세요.

### 4단계: Google Calendar API 활성화

1. 좌측 메뉴에서 **"API 및 서비스"** > **"라이브러리"**를 선택합니다.
2. 검색창에 **"Google Calendar API"**를 입력합니다.
3. **"Google Calendar API"**를 선택하고 **"사용 설정"**을 클릭합니다.

### 5단계: 환경 변수 설정

프로젝트 루트 디렉토리에 `.env` 파일을 생성하거나 기존 파일을 수정합니다.

```env
# Google OAuth 설정
GOOGLE_CLIENT_ID=your_client_id_here.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_client_secret_here
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback
```

**중요 사항:**
- `GOOGLE_CLIENT_ID`: 3단계에서 복사한 클라이언트 ID를 입력합니다.
- `GOOGLE_CLIENT_SECRET`: 3단계에서 복사한 클라이언트 보안 비밀번호를 입력합니다.
- `GOOGLE_REDIRECT_URI`: 3단계에서 설정한 리디렉션 URI와 정확히 일치해야 합니다.
  - 개발 환경: `http://localhost:8000/auth/google/callback`
  - 프로덕션 환경: 실제 도메인으로 변경

### 6단계: 애플리케이션 재시작

환경 변수를 설정한 후 애플리케이션을 재시작합니다:

```bash
# 애플리케이션 중지 후 재시작
python -m uvicorn app.main:app --reload
```

또는 Docker를 사용하는 경우:

```bash
docker-compose restart
```

## 테스트 방법

1. 웹 브라우저에서 `http://localhost:8000/settings` 페이지로 이동합니다.
2. **"Google Calendar"** 섹션에서 **"연동하기"** 또는 **"Connect"** 버튼을 클릭합니다.
3. 구글 로그인 페이지로 리디렉션됩니다.
4. 본인의 구글 계정으로 로그인합니다.
5. 권한 동의 화면에서 **"허용"**을 클릭합니다.
6. 성공적으로 리디렉션되면 설정 페이지에 **"연동 완료"** 메시지가 표시됩니다.
7. **"테스트"** 버튼을 클릭하여 캘린더 일정 조회가 정상적으로 작동하는지 확인합니다.

## 문제 해결

### 오류: "invalid_client" (401 오류)

**원인:**
- 클라이언트 ID 또는 클라이언트 보안 비밀번호가 잘못되었습니다.
- 환경 변수가 제대로 로드되지 않았습니다.

**해결 방법:**
1. `.env` 파일의 `GOOGLE_CLIENT_ID`와 `GOOGLE_CLIENT_SECRET` 값이 정확한지 확인합니다.
2. Google Cloud Console에서 클라이언트 ID가 올바르게 생성되었는지 확인합니다.
3. 애플리케이션을 재시작하여 환경 변수를 다시 로드합니다.
4. `.env` 파일이 프로젝트 루트 디렉토리에 있는지 확인합니다.

### 오류: "redirect_uri_mismatch"

**원인:**
- 리디렉션 URI가 Google Cloud Console에 등록된 URI와 일치하지 않습니다.

**해결 방법:**
1. Google Cloud Console > 사용자 인증 정보 > OAuth 2.0 클라이언트 ID에서 등록된 리디렉션 URI를 확인합니다.
2. `.env` 파일의 `GOOGLE_REDIRECT_URI` 값이 정확히 일치하는지 확인합니다.
   - 프로토콜(`http://` 또는 `https://`) 포함
   - 포트 번호 포함
   - 경로 정확히 일치 (`/auth/google/callback`)
3. 필요시 Google Cloud Console에 올바른 리디렉션 URI를 추가합니다.

### 오류: "access_denied"

**원인:**
- 사용자가 권한 동의를 거부했습니다.
- 테스트 사용자로 등록되지 않은 계정으로 로그인했습니다.

**해결 방법:**
1. OAuth 동의 화면 설정에서 본인의 구글 계정을 테스트 사용자로 추가합니다.
2. 다시 로그인 시도 시 모든 권한에 동의합니다.

### 오류: "The OAuth client was not found"

**원인:**
- 클라이언트 ID가 존재하지 않거나 삭제되었습니다.
- 잘못된 프로젝트의 클라이언트 ID를 사용하고 있습니다.

**해결 방법:**
1. Google Cloud Console에서 올바른 프로젝트를 선택했는지 확인합니다.
2. 사용자 인증 정보 페이지에서 클라이언트 ID가 존재하는지 확인합니다.
3. 필요시 새로운 OAuth 클라이언트 ID를 생성하고 `.env` 파일을 업데이트합니다.

## 프로덕션 환경 설정

프로덕션 환경으로 배포할 때는 다음 사항을 확인하세요:

1. **리디렉션 URI 업데이트:**
   - Google Cloud Console에 프로덕션 도메인의 리디렉션 URI를 추가합니다.
   - `.env` 파일의 `GOOGLE_REDIRECT_URI`를 프로덕션 URL로 변경합니다.

2. **OAuth 동의 화면 게시:**
   - 외부 앱인 경우, 앱 검토를 통해 게시해야 일반 사용자가 사용할 수 있습니다.
   - 내부 앱인 경우, Google Workspace 관리자가 승인해야 합니다.

3. **보안:**
   - `.env` 파일이 버전 관리 시스템에 커밋되지 않도록 `.gitignore`에 추가되어 있는지 확인합니다.
   - 클라이언트 보안 비밀번호를 안전하게 관리합니다.

## 추가 참고 자료

- [Google OAuth 2.0 문서](https://developers.google.com/identity/protocols/oauth2)
- [Google Calendar API 문서](https://developers.google.com/calendar/api)
- [FastAPI OAuth 예제](https://fastapi.tiangolo.com/advanced/security/oauth2-scopes/)
