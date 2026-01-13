# Telegram Bot 설정 및 테스트 가이드

## 1. Telegram Bot 생성

### 1.1 BotFather를 통한 봇 생성

1. Telegram 앱에서 @BotFather 검색 및 대화 시작
2. `/newbot` 명령어 입력
3. 봇 이름 입력 (예: My Assistant Bot)
4. 봇 사용자명 입력 (반드시 'bot'으로 끝나야 함, 예: my_assistant_bot)
5. BotFather가 제공하는 **Bot Token** 복사

### 1.2 환경변수 설정

`.env` 파일에 Bot Token 추가:

```env
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
```

### 1.3 Docker 컨테이너 재시작

```bash
docker compose restart
```

## 2. Telegram Bot 연동

### 2.1 Settings 페이지에서 연동

1. 브라우저에서 `http://localhost:8000/settings` 접속
2. **Authentication** 섹션에서 **Telegram Bot** 카드 찾기
3. **Connect** 버튼 클릭
4. 모달 창이 열리면 **Open [봇이름] in Telegram** 버튼 클릭
5. Telegram 앱이 열리면 `/start` 명령어 입력
6. 봇이 응답하는 **Chat ID** 복사 (예: 123456789)
7. Settings 페이지 모달로 돌아와서 Chat ID 입력
8. **Verify and Connect** 버튼 클릭
9. 연동 성공 메시지 확인

### 2.2 연동 상태 확인

연동이 완료되면:
- Status 배지가 **Connected**로 변경
- **Connect** 버튼이 사라지고 **Disconnect**, **Test** 버튼 표시

## 3. 기능 테스트

### 3.1 테스트 메시지 발송

Settings 페이지에서:
1. **Test** 버튼 클릭
2. Telegram 앱에서 테스트 메시지 수신 확인

### 3.2 각 봇별 알림 테스트

#### Weather Bot 테스트
1. `http://localhost:8000/weather` 접속
2. 알림 활성화 및 시간 설정
3. **Test** 버튼 클릭
4. Telegram에서 날씨 알림 수신 확인

#### Finance Bot 테스트
1. `http://localhost:8000/finance` 접속
2. US Market 또는 KR Market 활성화
3. **Test US Market** 또는 **Test KR Market** 버튼 클릭
4. Telegram에서 금융 알림 수신 확인

#### Calendar Bot 테스트
1. Google Calendar 연동 필요 (Settings 페이지)
2. `http://localhost:8000/calendar` 접속
3. 알림 활성화
4. **Test** 버튼 클릭
5. Telegram에서 캘린더 알림 수신 확인

#### Reminder (Memo) 테스트
1. `http://localhost:8000/reminders` 접속
2. 새 메모 등록 (미래 시간으로 설정)
3. 설정한 시간에 Telegram으로 알림 수신 확인

### 3.3 다중 채널 테스트

**전제 조건**: Kakao Talk과 Telegram 모두 연동된 상태

**테스트 방법**:
1. 위의 각 봇 테스트 실행
2. **Kakao Talk**과 **Telegram** 양쪽에서 알림 수신 확인

**예상 동작**:
- 양쪽 모두 연동: 양쪽 모두 알림 발송
- Kakao만 연동: Kakao로만 발송
- Telegram만 연동: Telegram으로만 발송
- 둘 다 미연동: 알림 발송 실패

### 3.4 에러 처리 테스트

#### Kakao 토큰 만료 시나리오
1. Kakao Talk 토큰이 만료되도록 대기 (또는 DB에서 임의로 삭제)
2. Weather 또는 Finance 테스트 실행
3. **예상 결과**: Telegram으로만 알림 발송, Logs에 Kakao 실패 기록

#### Telegram Chat ID 삭제 시나리오
1. Settings에서 Telegram **Disconnect** 클릭
2. Weather 또는 Finance 테스트 실행
3. **예상 결과**: Kakao로만 알림 발송

#### 잘못된 Chat ID 입력
1. Settings에서 Telegram Connect 클릭
2. 존재하지 않는 Chat ID 입력 (예: 99999999)
3. 테스트 메시지 발송
4. **예상 결과**: 발송 실패 (Telegram API에서 400 또는 403 에러)

## 4. 로그 확인

### 4.1 Logs 페이지에서 확인

1. `http://localhost:8000/logs` 접속
2. 카테고리 필터 사용 (Weather, Finance, Calendar, Memo)
3. 각 알림의 발송 상태 확인
   - `SUCCESS (Sent to 2 channels)`: 양쪽 모두 성공
   - `SUCCESS (Sent to 1 channel)`: 한쪽만 성공
   - `FAIL`: 발송 실패

### 4.2 Docker 로그 확인

```bash
docker compose logs -f
```

**확인 항목**:
- Telegram API 호출 로그
- 발송 성공/실패 메시지
- 에러 메시지 (있을 경우)

## 5. 문제 해결

### 5.1 Telegram 연동 실패

**증상**: Connect 버튼 클릭 시 에러 또는 Chat ID 입력 후 실패

**해결 방법**:
1. `.env` 파일에 `TELEGRAM_BOT_TOKEN`이 올바르게 설정되었는지 확인
2. Docker 컨테이너 재시작: `docker compose restart`
3. Telegram 앱에서 봇에 `/start` 명령을 먼저 전송했는지 확인
4. Chat ID가 정확한지 확인 (숫자만 입력, 공백 없음)

### 5.2 테스트 메시지 발송 실패

**증상**: Test 버튼 클릭 시 메시지가 도착하지 않음

**해결 방법**:
1. Settings 페이지에서 연동 상태 확인 (Connected 상태여야 함)
2. Docker 로그 확인: `docker compose logs -f`
3. Telegram API 응답 확인
4. 봇이 차단되지 않았는지 확인 (Telegram에서 봇 대화 확인)

### 5.3 Chat ID를 모르는 경우

**해결 방법 1**: BotFather 봇 사용
1. Telegram에서 생성한 봇에 `/start` 전송
2. 봇의 자동 응답 메시지에서 Chat ID 확인 (현재 구현에서는 수동 방법 필요)

**해결 방법 2**: userinfobot 사용
1. Telegram에서 @userinfobot 검색
2. `/start` 전송
3. 봇이 응답하는 ID 값을 Chat ID로 사용

**해결 방법 3**: API를 통한 확인
```bash
curl https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
```
봇에 메시지를 보낸 후 위 명령어 실행하면 `chat.id` 값 확인 가능

## 6. 체크리스트

### 6.1 초기 설정
- [ ] Telegram 봇 생성 완료
- [ ] Bot Token을 `.env` 파일에 추가
- [ ] Docker 컨테이너 재시작
- [ ] Settings 페이지에서 Telegram 연동 완료

### 6.2 기능 테스트
- [ ] Settings 페이지에서 테스트 메시지 발송 성공
- [ ] Weather Bot 테스트 성공
- [ ] Finance Bot (US Market) 테스트 성공
- [ ] Finance Bot (KR Market) 테스트 성공
- [ ] Calendar Bot 테스트 성공
- [ ] Reminder 테스트 성공

### 6.3 다중 채널 테스트
- [ ] Kakao + Telegram 동시 발송 확인
- [ ] Kakao만 연동 시 정상 동작 확인
- [ ] Telegram만 연동 시 정상 동작 확인

### 6.4 에러 처리 테스트
- [ ] 한쪽 채널 실패 시 다른 쪽 정상 발송 확인
- [ ] Logs 페이지에서 에러 로그 확인

## 7. 참고사항

### 7.1 Telegram Bot API 제한사항
- 초당 최대 30개 메시지 발송
- 같은 사용자에게 초당 1개 메시지
- 메시지 최대 길이: 4096자

### 7.2 보안
- Bot Token은 절대 공개 저장소에 커밋하지 않기
- `.env` 파일은 `.gitignore`에 포함
- Chat ID는 사용자별로 고유하므로 다른 사용자와 공유하지 않기

### 7.3 향후 개선 가능 항목
- Webhook 방식으로 자동 연동
- 텔레그램 인라인 키보드로 알림 On/Off 제어
- 텔레그램에서 직접 메모 등록
- 그룹 채팅 지원
