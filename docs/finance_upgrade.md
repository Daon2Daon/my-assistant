# Finance 기능 업그레이드 계획서

## 1. 현재 구조 분석

### 1.1 현재 기능

| 항목 | 내용 |
|------|------|
| 미국 시장 | S&P 500, Nasdaq, Dow Jones 지수 |
| 한국 시장 | KOSPI, KOSDAQ 지수 |
| 알림 시간 | US 22:00, KR 09:00 (설정 가능) |
| 데이터 소스 | Yahoo Finance (yfinance), PyKRX |
| 제공 정보 | 일일 가격, 일일 변동률 |

### 1.2 현재 파일 구조

```
app/
├── services/bots/
│   └── finance_bot.py        # 증시 데이터 조회 및 알림 발송
├── routers/
│   └── finance.py            # API 엔드포인트
├── templates/
│   └── finance.html          # UI 템플릿
├── static/js/
│   └── finance.js            # 프론트엔드 로직
└── models/
    ├── user.py               # 사용자 모델
    ├── setting.py            # 설정 모델
    └── ...
```

### 1.3 현재 한계점

1. **종목 추적 불가**: 지수만 제공, 개별 종목 추적 기능 없음
2. **단기 정보만 제공**: 일일 변동률만 제공, 추세 파악 어려움
3. **맞춤화 부족**: 모든 사용자에게 동일한 정보 제공
4. **분석 기능 부재**: 단순 정보 전달, 분석/인사이트 없음

---

## 2. 업그레이드 목표

### 2.1 핵심 기능

1. **종목 등록 기능**: 사용자가 관심 종목을 티커로 등록
2. **다중 기간 비교**: 일일/주간/월간 변동률 비교 제공
3. **통합 알림**: 시장 지수 + 등록 종목 정보를 하나의 알림으로

### 2.2 추가 제안 기능

1. **가격 알림**: 목표가/손절가 도달 시 즉시 알림
2. **52주 고점/저점 표시**: 현재 가격의 위치 파악
3. **거래량 이상 감지**: 평균 대비 거래량 급증 시 알림
4. **포트폴리오 요약**: 등록 종목 전체 손익 요약

---

## 3. 변경 후 구조

### 3.1 새로운 파일 구조

```
app/
├── models/
│   ├── user.py
│   ├── setting.py
│   ├── watchlist.py          # (신규) 관심 종목 테이블
│   └── price_alert.py        # (신규) 가격 알림 테이블
├── services/bots/
│   └── finance_bot.py        # (수정) 종목 데이터 조회 추가
├── routers/
│   └── finance.py            # (수정) 종목 관리 API 추가
├── templates/
│   └── finance.html          # (수정) 종목 관리 UI 추가
└── static/js/
    └── finance.js            # (수정) 종목 관리 기능 추가
```

### 3.2 데이터베이스 스키마

#### Watchlist (관심 종목) 테이블

```python
class Watchlist(Base):
    __tablename__ = "watchlists"

    watchlist_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)

    # 종목 정보
    ticker = Column(String(20), nullable=False)      # 티커 (AAPL, 005930.KS)
    name = Column(String(100), nullable=True)        # 종목명 (Apple Inc.)
    market = Column(String(10), nullable=False)      # US / KR

    # 매수 정보 (선택)
    purchase_price = Column(Float, nullable=True)    # 매수가
    purchase_quantity = Column(Integer, nullable=True)  # 수량

    # 메타데이터
    created_at = Column(DateTime, default=func.now())
    is_active = Column(Boolean, default=True)
```

#### PriceAlert (가격 알림) 테이블

```python
class PriceAlert(Base):
    __tablename__ = "price_alerts"

    alert_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    watchlist_id = Column(Integer, ForeignKey("watchlists.watchlist_id"), nullable=False)

    # 알림 조건
    alert_type = Column(String(20), nullable=False)  # TARGET_HIGH / TARGET_LOW / PERCENT_CHANGE
    target_price = Column(Float, nullable=True)      # 목표 가격
    target_percent = Column(Float, nullable=True)    # 목표 변동률 (%)

    # 상태
    is_triggered = Column(Boolean, default=False)    # 발동 여부
    triggered_at = Column(DateTime, nullable=True)   # 발동 시간
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=func.now())
```

---

## 4. API 설계

### 4.1 종목 관리 API

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | /api/finance/watchlist | 등록된 종목 목록 조회 |
| POST | /api/finance/watchlist | 종목 등록 |
| PUT | /api/finance/watchlist/{id} | 종목 정보 수정 |
| DELETE | /api/finance/watchlist/{id} | 종목 삭제 |
| GET | /api/finance/watchlist/{id}/quote | 종목 실시간 시세 조회 |

### 4.2 가격 알림 API

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | /api/finance/alerts | 등록된 알림 목록 조회 |
| POST | /api/finance/alerts | 가격 알림 등록 |
| DELETE | /api/finance/alerts/{id} | 가격 알림 삭제 |

### 4.3 종목 조회 API

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | /api/finance/search?q={keyword} | 종목 검색 (티커/종목명) |
| GET | /api/finance/quote/{ticker} | 개별 종목 시세 조회 |

---

## 5. 알림 메시지 형식

### 5.1 현재 형식 (시장 지수만)

```
[미국 증시 마감]
2026년 01월 15일

S&P 500: 5,842.91 (+0.78%)
Nasdaq: 19,478.88 (+1.01%)
Dow Jones: 43,153.13 (+0.52%)
```

### 5.2 개선 형식 (지수 + 관심 종목)

```
[미국 증시 마감] 2026년 01월 15일

[ 주요 지수 ]
S&P 500: 5,842.91 (+0.78%)
Nasdaq: 19,478.88 (+1.01%)
Dow Jones: 43,153.13 (+0.52%)

[ 관심 종목 ]
AAPL (Apple)
  $229.98 | 일: +1.24% | 주: +3.45% | 월: +8.12%
  52주: 164.08 ~ 237.49 (현재 96.8%)

NVDA (NVIDIA)
  $147.07 | 일: +2.31% | 주: -1.23% | 월: +15.67%
  52주: 47.32 ~ 153.13 (현재 95.1%)

TSLA (Tesla)
  $424.07 | 일: -0.87% | 주: +12.34% | 월: +45.23%
  52주: 138.80 ~ 479.86 (현재 87.8%)

[ 포트폴리오 요약 ]
총 평가금액: $15,234.56
총 수익률: +12.34% (+$1,678.90)
```

### 5.3 한국 시장 형식

```
[한국 증시 현황] 2026년 01월 15일

[ 주요 지수 ]
KOSPI: 2,523.55 (+0.45%)
KOSDAQ: 721.32 (-0.23%)

[ 관심 종목 ]
005930 (삼성전자)
  55,200원 | 일: +1.10% | 주: -2.34% | 월: +5.67%
  52주: 50,600 ~ 62,400 (현재 46.8%)

000660 (SK하이닉스)
  178,500원 | 일: +2.45% | 주: +5.12% | 월: +18.23%
  52주: 110,000 ~ 185,400 (현재 90.9%)
```

---

## 6. 구현 단계

### Phase F-1: 데이터베이스 확장

**작업 항목**:
- [ ] `app/models/watchlist.py` 생성
- [ ] `app/models/price_alert.py` 생성
- [ ] `app/models/__init__.py` 수정
- [ ] `app/crud.py`에 CRUD 함수 추가
- [ ] 데이터베이스 마이그레이션

**예상 코드량**: ~150줄

### Phase F-2: 종목 데이터 조회 기능

**작업 항목**:
- [ ] `finance_bot.py`에 개별 종목 조회 함수 추가
- [ ] 일일/주간/월간 변동률 계산 로직 구현
- [ ] 52주 고점/저점 조회 기능 추가
- [ ] 한국 종목 조회 기능 추가 (PyKRX 확장)

**핵심 함수**:
```python
def get_stock_quote(self, ticker: str) -> Optional[Dict]:
    """개별 종목 시세 조회"""

def get_stock_history(self, ticker: str, period: str) -> Optional[Dict]:
    """종목 기간별 데이터 조회 (1d, 1wk, 1mo, 1y)"""

def calculate_period_changes(self, ticker: str) -> Dict:
    """일/주/월 변동률 계산"""

def get_52week_range(self, ticker: str) -> Dict:
    """52주 고점/저점 조회"""
```

**예상 코드량**: ~200줄

### Phase F-3: 종목 관리 API

**작업 항목**:
- [ ] 종목 등록/수정/삭제 API 구현
- [ ] 종목 검색 API 구현
- [ ] 종목 시세 조회 API 구현
- [ ] 입력값 검증 (유효한 티커인지 확인)

**예상 코드량**: ~200줄

### Phase F-4: 알림 메시지 개선

**작업 항목**:
- [ ] `format_us_market_message()` 함수 개선
- [ ] `format_kr_market_message()` 함수 개선
- [ ] 관심 종목 정보 포함 로직 추가
- [ ] 포트폴리오 요약 계산 로직 추가

**예상 코드량**: ~150줄

### Phase F-5: UI 구현

**작업 항목**:
- [ ] 종목 등록 UI 추가 (검색 + 등록 폼)
- [ ] 등록된 종목 목록 표시
- [ ] 종목별 상세 정보 카드
- [ ] 종목 삭제 기능
- [ ] 가격 알림 설정 UI (Phase F-6의 선택 기능)

**UI 구성**:
```
[Finance 페이지]
├── 상태 카드 (기존)
├── 설정 카드 (기존)
├── 관심 종목 관리 (신규)
│   ├── 종목 검색/등록 폼
│   ├── 등록된 종목 목록
│   │   ├── 종목 카드 (가격, 변동률, 52주 범위)
│   │   └── 삭제 버튼
│   └── 포트폴리오 요약
├── US/KR Market 테스트 (기존)
└── 최근 로그 (기존)
```

**예상 코드량**: HTML ~200줄, JS ~250줄

### Phase F-5.1: UI 개선 (US/KR 분리)

**변경 배경**:
- 관심 종목 관리를 US Market과 KR Market으로 분리하여 직관성 향상
- 매수가/수량 입력 기능 제거로 UI 간소화
- 각 시장별 알림에 해당 시장 종목만 포함

**작업 항목**:
- [ ] `finance.py` - WatchlistCreateRequest에서 매수가/수량 필드 제거
- [ ] `finance.html` - US/KR 섹션 분리, 매수가/수량 입력 필드 제거
- [ ] `finance.js` - 함수 분리 (loadUSWatchlist, loadKRWatchlist, addWatchlist(market))

**UI 변경**:
```
변경 전:                          변경 후:
+-- 관심 종목 관리 -------------+    +-- US Market 관심 종목 --------+
| 시장: [US v]                 |    | 티커: [____] [등록]           |
| 티커: [____]                 |    | +-----+-----+-----+           |
| 매수가: [____]               |    | |AAPL |NVDA |TSLA |           |
| 수량: [____]                 |    | +-----+-----+-----+           |
| [등록]                       |    +-------------------------------+
| +-----+------+               |    +-- KR Market 관심 종목 --------+
| |AAPL |005930|               |    | 종목코드: [____] [등록]       |
| | US  | KR   |               |    | +------+------+               |
| +-----+------+               |    | |005930|000660|               |
+------------------------------+    | +------+------+               |
                                    +-------------------------------+
```

**예상 코드량**: ~150줄

### Phase F-6: 가격 알림 기능 (선택)

**작업 항목**:
- [ ] 가격 알림 API 구현
- [ ] 가격 체크 스케줄러 추가 (5분 간격)
- [ ] 알림 발동 시 즉시 메시지 발송
- [ ] 가격 알림 UI 구현

**예상 코드량**: ~200줄

### Phase F-7: 테스트 및 문서화

**작업 항목**:
- [ ] 종목 등록/삭제 테스트
- [ ] 알림 메시지 형식 테스트
- [ ] 미국/한국 종목 모두 테스트
- [ ] 에러 처리 테스트 (잘못된 티커 등)
- [ ] 본 문서 업데이트

---

## 7. 티커 형식

### 7.1 미국 종목

Yahoo Finance 형식 사용:
- 일반 종목: `AAPL`, `NVDA`, `TSLA`
- ETF: `SPY`, `QQQ`, `VOO`
- 지수: `^GSPC` (S&P 500), `^IXIC` (Nasdaq)

### 7.2 한국 종목

PyKRX 형식 사용:
- 6자리 종목코드: `005930` (삼성전자), `000660` (SK하이닉스)
- Yahoo Finance 대안: `005930.KS` (KOSPI), `035720.KQ` (KOSDAQ)

### 7.3 티커 검증

```python
def validate_ticker(ticker: str, market: str) -> bool:
    """티커 유효성 검증"""
    try:
        if market == "US":
            stock = yf.Ticker(ticker)
            info = stock.info
            return "regularMarketPrice" in info
        elif market == "KR":
            # PyKRX로 검증
            name = stock.get_market_ticker_name(ticker)
            return name is not None
    except:
        return False
```

---

## 8. 고려사항

### 8.1 API 호출 제한

| 서비스 | 제한 |
|--------|------|
| Yahoo Finance | 무료, 제한 느슨함 (분당 ~100회 권장) |
| PyKRX | 무료, 제한 없음 |

- 등록 종목 10개 이하 권장
- 캐싱 적용으로 API 호출 최소화

### 8.2 성능 최적화

1. **병렬 조회**: 여러 종목 데이터 동시 조회
2. **캐싱**: 같은 종목 반복 조회 시 캐시 활용 (5분)
3. **지연 로딩**: UI에서 필요한 데이터만 조회

### 8.3 에러 처리

1. **잘못된 티커**: 등록 시 유효성 검증
2. **데이터 조회 실패**: 개별 종목 실패 시 다른 종목은 계속 진행
3. **API 오류**: 재시도 로직 (3회)

### 8.4 메시지 길이 제한

| 채널 | 최대 길이 |
|------|----------|
| 카카오톡 | 2,000자 |
| 텔레그램 | 4,096자 |

- 등록 종목이 많을 경우 메시지 분할 발송
- 카카오톡: 최대 5종목 권장
- 텔레그램: 최대 10종목 권장

---

## 9. 예상 작업량

| Phase | 신규 파일 | 수정 파일 | 예상 코드량 |
|-------|----------|----------|------------|
| F-1 | 2 | 2 | ~150줄 |
| F-2 | 0 | 1 | ~200줄 |
| F-3 | 0 | 1 | ~200줄 |
| F-4 | 0 | 1 | ~150줄 |
| F-5 | 0 | 2 | ~450줄 |
| F-6 | 0 | 2 | ~200줄 (선택) |
| F-7 | 0 | 1 | ~20줄 |
| **합계** | **2** | **10** | **~1,170줄** |

---

## 10. 완료 체크리스트

### Phase F-1: 데이터베이스 확장
- [x] `app/models/watchlist.py` 생성
- [x] `app/models/price_alert.py` 생성
- [x] `app/models/__init__.py` 수정
- [x] `app/crud.py` CRUD 함수 추가
- [x] 데이터베이스 마이그레이션

### Phase F-2: 종목 데이터 조회 기능
- [x] 개별 종목 시세 조회 함수
- [x] 일/주/월 변동률 계산 로직
- [x] 52주 고점/저점 조회
- [x] 한국 종목 조회 (Yahoo Finance)

### Phase F-3: 종목 관리 API
- [x] GET /api/finance/watchlist
- [x] POST /api/finance/watchlist
- [x] PUT /api/finance/watchlist/{id}
- [x] DELETE /api/finance/watchlist/{id}
- [x] GET /api/finance/search
- [x] GET /api/finance/quote/{ticker}

### Phase F-4: 알림 메시지 개선
- [x] 미국 시장 메시지 형식 개선
- [x] 한국 시장 메시지 형식 개선
- [x] 관심 종목 정보 포함
- [ ] 포트폴리오 요약 (선택)

### Phase F-5: UI 구현
- [x] 종목 검색/등록 폼
- [x] 등록된 종목 목록
- [x] 종목 상세 정보 카드
- [x] 종목 삭제 기능

### Phase F-5.1: UI 개선 (US/KR 분리)
- [x] `finance.py` - 매수가/수량 필드 제거
- [x] `finance.html` - US/KR 섹션 분리
- [x] `finance.js` - 함수 분리
- [x] `finance_bot.py` - KR Market 데이터 소스 변경 (PyKRX → Yahoo Finance)

### Phase F-6: 가격 알림 기능 (선택)
- [x] 가격 알림 API (GET/POST/DELETE)
- [x] 가격 체크 스케줄러 (5분 간격)
- [x] 알림 발동 로직 (목표가/손절가/변동률)
- [x] 가격 알림 UI

### Phase F-7: 테스트 및 문서화
- [x] 미국 종목 테스트
- [x] 한국 종목 테스트
- [x] 알림 메시지 테스트
- [x] 에러 처리 테스트
- [x] 본 문서 업데이트

---

## 11. 우선순위 권장

### 필수 구현 (MVP)
1. **Phase F-1**: 데이터베이스 - 종목 저장 기반
2. **Phase F-2**: 종목 조회 - 핵심 데이터 조회 로직
3. **Phase F-3**: API - 종목 관리 인터페이스
4. **Phase F-4**: 알림 개선 - 사용자 가치 전달
5. **Phase F-5**: UI - 사용자 경험

### 선택 구현
6. **Phase F-6**: 가격 알림 - 추가 기능

### 구현 순서 권장
```
F-1 (DB) → F-2 (조회) → F-3 (API) → F-5 (UI) → F-4 (알림) → F-7 (테스트)
```

---

## 12. 구현 완료 요약

### 12.1 완료 일자
- **Phase F-1 ~ F-5**: 2026-01-15 완료
- **Phase F-5.1**: 2026-01-15 완료
- **Phase F-6**: 2026-01-15 완료
- **Phase F-7**: 2026-01-15 완료

### 12.2 구현된 주요 기능

#### ✅ 종목 관리
- US Market / KR Market 분리된 관심 종목 관리
- 티커 기반 간편 등록 (매수가/수량 제거)
- 종목 삭제 및 시세 조회

#### ✅ 데이터 조회
- 미국 종목: Yahoo Finance (yfinance)
- 한국 종목: Yahoo Finance (^KS11, ^KQ11)
- 개별 종목: 일/주/월 변동률, 52주 범위

#### ✅ 알림 메시지
- 시장 지수 + 관심 종목 통합 알림
- US Market: 최대 5종목 포함
- KR Market: 최대 5종목 포함
- 다중 채널 발송 (카카오톡, 텔레그램)

#### ✅ 가격 알림 (Phase F-6)
- 목표가 도달 알림 (상승/하락)
- 일일 변동률 기반 알림
- 5분 간격 자동 체크
- 조건 도달 시 즉시 알림 발송

#### ✅ API 엔드포인트
- GET/POST/PUT/DELETE `/api/finance/watchlist` - 관심 종목 관리
- GET `/api/finance/search` - 종목 검색
- GET `/api/finance/quote/{ticker}` - 시세 조회
- GET `/api/finance/preview/us` - US 미리보기
- GET `/api/finance/preview/kr` - KR 미리보기
- POST `/api/finance/test/us` - US 테스트 발송
- POST `/api/finance/test/kr` - KR 테스트 발송
- GET/POST/DELETE `/api/finance/alerts` - 가격 알림 관리

### 12.3 기술적 개선사항

#### 데이터 소스 변경
- **변경 전**: PyKRX (불안정한 API, 라이브러리 오류)
- **변경 후**: Yahoo Finance (안정적, 일관된 인터페이스)
- **이점**: US/KR 동일한 방식으로 처리, 에러 감소

#### UI/UX 개선
- 시장별 섹션 분리로 직관성 향상
- 불필요한 입력 필드 제거 (매수가/수량)
- 실시간 시세 조회 모달

#### JSON 직렬화 문제 해결
- NumPy 타입 → Python native 타입 변환
- NaN/Infinity → None 처리
- `sanitize_for_json()` 헬퍼 함수 추가

### 12.4 테스트 완료 항목
- ✅ 미국 종목 등록/삭제/시세 조회
- ✅ 한국 종목 등록/삭제/시세 조회
- ✅ US Market 알림 메시지 (지수 + 종목)
- ✅ KR Market 알림 메시지 (지수 + 종목)
- ✅ 다중 채널 발송 (카카오톡, 텔레그램)
- ✅ 에러 처리 (잘못된 티커, API 오류)

### 12.5 구현 완료된 선택 기능

#### Phase F-6: 가격 알림 기능
- ✅ 목표가/손절가 설정
- ✅ 5분 간격 가격 체크
- ✅ 조건 도달 시 즉시 알림
- ✅ 3가지 알림 유형 (TARGET_HIGH, TARGET_LOW, PERCENT_CHANGE)
- **상태**: 구현 완료 (2026-01-15)

### 12.6 파일 변경 내역

| 파일 | 상태 | 변경 내용 |
|------|------|----------|
| `models/watchlist.py` | 신규 | 관심 종목 모델 |
| `models/price_alert.py` | 신규 | 가격 알림 모델 |
| `routers/finance.py` | 수정 | 종목 관리 API, 가격 알림 API 추가 |
| `services/bots/finance_bot.py` | 수정 | 종목 조회 함수, 가격 체크 함수, KR Yahoo Finance 적용 |
| `services/scheduler.py` | 수정 | Interval Job 지원 추가 |
| `templates/finance.html` | 수정 | US/KR 섹션 분리, 가격 알림 UI 추가 |
| `static/js/finance.js` | 수정 | loadUSWatchlist/loadKRWatchlist 분리, 가격 알림 함수 추가 |
| `crud.py` | 수정 | Watchlist, PriceAlert CRUD 함수 추가 |
| `database.py` | 수정 | watchlist, price_alert 모델 import |
| `main.py` | 수정 | 가격 알림 체크 스케줄러 등록 |

---

**작성일**: 2026-01-15
**완료일**: 2026-01-15
**버전**: 1.0.0
**상태**: ✅ Phase F-1 ~ F-5.1, F-7 완료 (MVP 구현 완료)
