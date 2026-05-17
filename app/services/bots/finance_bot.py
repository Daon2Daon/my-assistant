"""
금융 알림 봇
Yahoo Finance 및 PyKRX를 사용한 증시 정보 수집 및 알림
"""

import yfinance as yf
from pykrx import stock
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional
from app.database import SessionLocal
from app.crud import (
    get_or_create_user,
    create_log,
    is_setting_active,
    get_watchlists,
    get_watchlist,
    get_price_alerts,
    update_alert_triggered,
)
from app.services.notification import notification_service


def _is_trading_day(market: str) -> bool:
    """오늘이 해당 시장의 거래일인지 확인한다 (주말·공휴일 모두 제외).

    pandas_market_calendars의 NYSE/KRX 공식 캘린더를 사용한다.
    라이브러리 오류 시 True를 반환해 발송을 차단하지 않는다.
    """
    try:
        import pandas_market_calendars as mcal
        cal_name = "NYSE" if market == "US" else "KRX"
        tz = ZoneInfo("America/New_York" if market == "US" else "Asia/Seoul")
        today = datetime.now(tz).strftime("%Y-%m-%d")
        cal = mcal.get_calendar(cal_name)
        schedule = cal.schedule(start_date=today, end_date=today)
        return not schedule.empty
    except Exception as e:
        print(f"⚠️  거래일 체크 실패 ({market}): {e} — 발송 허용으로 처리")
        return True


class FinanceBot:
    """금융 알림 봇"""

    def __init__(self):
        # 주요 미국 지수 티커
        self.us_indices = {
            "^GSPC": "S&P 500",
            "^IXIC": "Nasdaq",
            "^DJI": "Dow Jones",
        }

    # ============================================================
    # 개별 종목 조회 기능
    # ============================================================

    def get_stock_quote(self, ticker: str, market: str = "US") -> Optional[Dict]:
        """
        개별 종목 실시간 시세 조회

        Args:
            ticker: 종목 티커 (예: AAPL, 005930)
            market: 시장 (US / KR)

        Returns:
            Dict: 종목 시세 정보 또는 None
            {
                "ticker": str,
                "name": str,
                "price": float,
                "change": float,
                "change_percent": float,
                "volume": int,
                "market_cap": float (선택)
            }
        """
        try:
            if market == "US":
                return self._get_us_stock_quote(ticker)
            elif market == "KR":
                return self._get_kr_stock_quote(ticker)
            else:
                print(f"⚠️  지원하지 않는 시장: {market}")
                return None
        except Exception as e:
            print(f"❌ 종목 시세 조회 실패 ({ticker}): {e}")
            return None

    def _get_us_stock_quote(self, ticker: str) -> Optional[Dict]:
        """미국 종목 시세 조회"""
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d")

            if len(hist) < 1:
                return None

            # 종목 정보
            info = stock.info
            current_price = hist["Close"].iloc[-1]

            # 전일 대비 변동
            if len(hist) >= 2:
                previous_price = hist["Close"].iloc[-2]
                change = current_price - previous_price
                change_percent = (change / previous_price) * 100
            else:
                change = 0
                change_percent = 0

            return {
                "ticker": ticker,
                "name": info.get("longName", info.get("shortName", ticker)),
                "price": current_price,
                "change": change,
                "change_percent": change_percent,
                "volume": hist["Volume"].iloc[-1],
                "market_cap": info.get("marketCap"),
            }

        except Exception as e:
            print(f"❌ 미국 종목 조회 실패 ({ticker}): {e}")
            return None

    def _get_kr_stock_quote(self, ticker: str) -> Optional[Dict]:
        """한국 종목 시세 조회 (pykrx → yfinance fallback)"""
        # 1차: pykrx 시도
        try:
            name = stock.get_market_ticker_name(ticker)
            if name and isinstance(name, str):
                today = datetime.now(ZoneInfo("Asia/Seoul"))
                end_date = today.strftime("%Y%m%d")
                start_date = (today - timedelta(days=7)).strftime("%Y%m%d")
                df = stock.get_market_ohlcv_by_date(start_date, end_date, ticker)
                if df is not None and not df.empty:
                    current_price = df["종가"].iloc[-1]
                    current_volume = df["거래량"].iloc[-1]
                    if len(df) >= 2:
                        previous_price = df["종가"].iloc[-2]
                        change = current_price - previous_price
                        change_percent = (change / previous_price) * 100
                    else:
                        change = 0
                        change_percent = 0
                    return {
                        "ticker": ticker,
                        "name": name,
                        "price": current_price,
                        "change": change,
                        "change_percent": change_percent,
                        "volume": current_volume,
                        "market_cap": None,
                    }
        except Exception as e:
            print(f"⚠️ pykrx 한국 종목 조회 실패 ({ticker}): {e}, yfinance fallback 시도")

        # 2차: yfinance fallback
        for suffix in (".KS", ".KQ"):
            try:
                yf_ticker = f"{ticker}{suffix}"
                stock_obj = yf.Ticker(yf_ticker)
                info = stock_obj.info
                price = info.get("currentPrice") or info.get("regularMarketPrice")
                if not price:
                    continue
                prev = info.get("previousClose") or info.get("regularMarketPreviousClose", price)
                change = price - prev
                change_percent = (change / prev) * 100 if prev else 0
                name = info.get("longName", info.get("shortName", ticker))
                return {
                    "ticker": ticker,
                    "name": name,
                    "price": price,
                    "change": change,
                    "change_percent": change_percent,
                    "volume": info.get("volume", 0),
                    "market_cap": info.get("marketCap"),
                }
            except Exception:
                pass

        print(f"❌ 한국 종목 조회 실패 ({ticker}): pykrx, yfinance 모두 실패")
        return None

    def calculate_period_changes(self, ticker: str, market: str = "US") -> Optional[Dict]:
        """
        종목의 일/주/월 변동률 계산

        Args:
            ticker: 종목 티커
            market: 시장 (US / KR)

        Returns:
            Dict: 기간별 변동률
            {
                "daily": float,
                "weekly": float,
                "monthly": float
            }
        """
        try:
            if market == "US":
                stock_obj = yf.Ticker(ticker)
                hist = stock_obj.history(period="2mo")

                if hist.empty:
                    return None

                current_price = hist["Close"].iloc[-1]

                # 일간 변동률
                daily_change = 0
                if len(hist) >= 2:
                    daily_change = ((current_price - hist["Close"].iloc[-2]) / hist["Close"].iloc[-2]) * 100

                # 주간 변동률 (5 거래일)
                weekly_change = 0
                if len(hist) >= 6:
                    weekly_change = ((current_price - hist["Close"].iloc[-6]) / hist["Close"].iloc[-6]) * 100

                # 월간 변동률 (21 거래일)
                monthly_change = 0
                if len(hist) >= 22:
                    monthly_change = ((current_price - hist["Close"].iloc[-22]) / hist["Close"].iloc[-22]) * 100

                return {
                    "daily": daily_change,
                    "weekly": weekly_change,
                    "monthly": monthly_change,
                }

            elif market == "KR":
                # 한국 종목
                today = datetime.now(ZoneInfo("Asia/Seoul"))
                start_date = (today - timedelta(days=60)).strftime("%Y%m%d")
                end_date = today.strftime("%Y%m%d")

                df = stock.get_market_ohlcv_by_date(start_date, end_date, ticker)

                if df.empty:
                    return None

                current_price = df["종가"].iloc[-1]

                # 일간 변동률
                daily_change = 0
                if len(df) >= 2:
                    daily_change = ((current_price - df["종가"].iloc[-2]) / df["종가"].iloc[-2]) * 100

                # 주간 변동률 (5 거래일)
                weekly_change = 0
                if len(df) >= 6:
                    weekly_change = ((current_price - df["종가"].iloc[-6]) / df["종가"].iloc[-6]) * 100

                # 월간 변동률 (21 거래일)
                monthly_change = 0
                if len(df) >= 22:
                    monthly_change = ((current_price - df["종가"].iloc[-22]) / df["종가"].iloc[-22]) * 100

                return {
                    "daily": daily_change,
                    "weekly": weekly_change,
                    "monthly": monthly_change,
                }

        except Exception as e:
            print(f"❌ 변동률 계산 실패 ({ticker}): {e}")
            return None

    def get_52week_range(self, ticker: str, market: str = "US") -> Optional[Dict]:
        """
        52주 고점/저점 조회

        Args:
            ticker: 종목 티커
            market: 시장 (US / KR)

        Returns:
            Dict: 52주 범위 정보
            {
                "low": float,
                "high": float,
                "current": float,
                "position_percent": float  # 현재가가 52주 범위에서 차지하는 위치 (%)
            }
        """
        try:
            if market == "US":
                stock_obj = yf.Ticker(ticker)
                hist = stock_obj.history(period="1y")

                if hist.empty:
                    return None

                low_52week = hist["Low"].min()
                high_52week = hist["High"].max()
                current_price = hist["Close"].iloc[-1]

                # 현재가 위치 계산 (0~100%)
                position_percent = 0
                if high_52week > low_52week:
                    position_percent = ((current_price - low_52week) / (high_52week - low_52week)) * 100

                return {
                    "low": low_52week,
                    "high": high_52week,
                    "current": current_price,
                    "position_percent": position_percent,
                }

            elif market == "KR":
                # 한국 종목
                today = datetime.now(ZoneInfo("Asia/Seoul"))
                start_date = (today - timedelta(days=365)).strftime("%Y%m%d")
                end_date = today.strftime("%Y%m%d")

                df = stock.get_market_ohlcv_by_date(start_date, end_date, ticker)

                if df.empty:
                    return None

                low_52week = df["저가"].min()
                high_52week = df["고가"].max()
                current_price = df["종가"].iloc[-1]

                # 현재가 위치 계산
                position_percent = 0
                if high_52week > low_52week:
                    position_percent = ((current_price - low_52week) / (high_52week - low_52week)) * 100

                return {
                    "low": low_52week,
                    "high": high_52week,
                    "current": current_price,
                    "position_percent": position_percent,
                }

        except Exception as e:
            print(f"❌ 52주 범위 조회 실패 ({ticker}): {e}")
            return None

    def _validate_kr_ticker(self, ticker: str) -> bool:
        """한국 시장 티커 유효성 검증 (pykrx → yfinance fallback)"""
        # 1차: pykrx 시도
        try:
            name = stock.get_market_ticker_name(ticker)
            if isinstance(name, str) and len(name) > 0:
                return True
            today = datetime.now(ZoneInfo("Asia/Seoul"))
            end_date = today.strftime("%Y%m%d")
            start_date = (today - timedelta(days=30)).strftime("%Y%m%d")
            for get_ohlcv in (
                stock.get_market_ohlcv_by_date,
                stock.get_etf_ohlcv_by_date,
            ):
                try:
                    df = get_ohlcv(start_date, end_date, ticker)
                    if df is not None and not df.empty and len(df) >= 1:
                        return True
                except Exception:
                    pass
        except Exception:
            pass

        # 2차: yfinance fallback
        for suffix in (".KS", ".KQ"):
            try:
                info = yf.Ticker(f"{ticker}{suffix}").info
                if info.get("regularMarketPrice") or info.get("currentPrice"):
                    return True
            except Exception:
                pass
        return False

    def validate_ticker(self, ticker: str, market: str = "US") -> bool:
        """
        티커 유효성 검증

        Args:
            ticker: 종목 티커
            market: 시장 (US / KR)

        Returns:
            bool: 유효한 티커 여부
        """
        ticker = (ticker or "").strip()
        if not ticker:
            return False
        try:
            if market == "US":
                stock_obj = yf.Ticker(ticker)
                info = stock_obj.info
                return "regularMarketPrice" in info or "currentPrice" in info

            elif market == "KR":
                return self._validate_kr_ticker(ticker)

            return False

        except Exception as e:
            print(f"⚠️  티커 검증 실패 ({ticker}): {e}")
            return False

    def search_ticker(self, keyword: str, market: str = "US") -> Optional[List[Dict]]:
        """
        종목 검색 (티커 또는 종목명)

        Args:
            keyword: 검색 키워드
            market: 시장 (US / KR)

        Returns:
            List[Dict]: 검색 결과 목록
            [
                {
                    "ticker": str,
                    "name": str,
                    "market": str
                }
            ]
        """
        try:
            if market == "KR":
                results = []
                # 1차: pykrx로 전체 종목 검색
                try:
                    tickers = stock.get_market_ticker_list(market="ALL")
                    for ticker_code in tickers:
                        name = stock.get_market_ticker_name(ticker_code)
                        if keyword.upper() in ticker_code or keyword in name:
                            results.append({
                                "ticker": ticker_code,
                                "name": name,
                                "market": "KR"
                            })
                            if len(results) >= 20:
                                break
                except Exception as e:
                    print(f"⚠️ pykrx 종목 검색 실패: {e}")

                # 2차: pykrx 실패 시 키워드가 6자리 숫자면 yfinance로 직접 조회
                if not results and keyword.strip().isdigit() and len(keyword.strip()) == 6:
                    for suffix in (".KS", ".KQ"):
                        try:
                            info = yf.Ticker(f"{keyword}{suffix}").info
                            price = info.get("currentPrice") or info.get("regularMarketPrice")
                            if price:
                                results.append({
                                    "ticker": keyword,
                                    "name": info.get("longName", info.get("shortName", keyword)),
                                    "market": "KR"
                                })
                                break
                        except Exception:
                            pass

                return results

            else:
                # 미국 시장은 yfinance에 검색 기능이 없으므로
                # 티커 검증만 수행
                if self.validate_ticker(keyword.upper(), "US"):
                    stock_obj = yf.Ticker(keyword.upper())
                    info = stock_obj.info
                    return [{
                        "ticker": keyword.upper(),
                        "name": info.get("longName", info.get("shortName", keyword.upper())),
                        "market": "US"
                    }]
                return []

        except Exception as e:
            print(f"❌ 종목 검색 실패: {e}")
            return []

    def get_us_market_data(self) -> Optional[Dict]:
        """
        미국 증시 데이터 조회

        Returns:
            Dict: 증시 데이터 또는 None
        """
        try:
            market_data = {}

            for ticker, name in self.us_indices.items():
                try:
                    # Yahoo Finance에서 데이터 조회
                    stock_info = yf.Ticker(ticker)
                    hist = stock_info.history(period="2d")

                    if len(hist) >= 2:
                        # 최신 데이터
                        current_price = hist["Close"].iloc[-1]
                        previous_price = hist["Close"].iloc[-2]

                        # 변동률 계산
                        change = current_price - previous_price
                        change_percent = (change / previous_price) * 100

                        market_data[name] = {
                            "price": current_price,
                            "change": change,
                            "change_percent": change_percent,
                        }

                except Exception as e:
                    print(f"⚠️  {name} 데이터 조회 실패: {e}")
                    continue

            return market_data if market_data else None

        except Exception as e:
            print(f"❌ 미국 증시 데이터 조회 실패: {e}")
            return None

    def get_kr_market_data(self) -> Optional[Dict]:
        """
        한국 증시 데이터 조회 (Yahoo Finance 사용)

        Returns:
            Dict: 증시 데이터 또는 None
        """
        try:
            market_data = {}

            # Yahoo Finance 한국 지수 티커
            kr_indices = {
                "^KS11": "KOSPI",
                "^KQ11": "KOSDAQ",
            }

            for ticker, name in kr_indices.items():
                try:
                    stock_obj = yf.Ticker(ticker)
                    hist = stock_obj.history(period="5d")

                    if hist.empty:
                        print(f"⚠️  {name} 데이터 없음")
                        continue

                    # 최근 데이터
                    current_price = hist["Close"].iloc[-1]

                    # 전일 대비 변동
                    if len(hist) >= 2:
                        previous_price = hist["Close"].iloc[-2]
                        change = current_price - previous_price
                        change_percent = (change / previous_price) * 100
                    else:
                        change = 0
                        change_percent = 0

                    market_data[name] = {
                        "price": current_price,
                        "change": change,
                        "change_percent": change_percent,
                    }
                    print(f"✅ {name} 데이터 조회 성공: {current_price:.2f} ({change_percent:+.2f}%)")

                except Exception as e:
                    print(f"⚠️  {name} 데이터 조회 실패: {e}")

            if not market_data:
                print("❌ 한국 증시 데이터 조회 실패")
                return None

            return market_data

        except Exception as e:
            print(f"❌ 한국 증시 데이터 조회 실패: {e}")
            import traceback
            print(traceback.format_exc())
            return None

    def format_us_market_message(self, market_data: Dict, watchlist_data: Optional[List[Dict]] = None) -> str:
        """
        미국 증시 메시지 포맷팅

        Args:
            market_data: 증시 데이터
            watchlist_data: 관심 종목 데이터 (선택)

        Returns:
            str: 포맷팅된 메시지
        """
        try:
            message = f"""📈 미국 증시 마감

📅 {datetime.now(ZoneInfo("Asia/Seoul")).strftime('%Y년 %m월 %d일')}

[ 주요 지수 ]
"""
            for name, data in market_data.items():
                price = data["price"]
                change = data["change"]
                change_percent = data["change_percent"]

                # 상승/하락 이모지
                emoji = "🟢" if change >= 0 else "🔴"
                sign = "+" if change >= 0 else ""

                message += f"""{emoji} {name}: {price:,.2f} ({sign}{change_percent:.2f}%)
"""

            # 관심 종목 정보 추가
            if watchlist_data and len(watchlist_data) > 0:
                message += "\n[ 관심 종목 ]\n"

                for stock in watchlist_data:
                    ticker = stock.get("ticker")
                    name = stock.get("name", ticker)
                    quote = stock.get("quote")
                    period_changes = stock.get("period_changes")
                    week_52 = stock.get("week_52_range")

                    if not quote:
                        continue

                    price = quote.get("price", 0)
                    change_pct = quote.get("change_percent", 0)
                    emoji = "🟢" if change_pct >= 0 else "🔴"
                    sign = "+" if change_pct >= 0 else ""

                    message += f"\n{emoji} {ticker} ({name})\n"

                    # 가격 및 기간별 변동률
                    if period_changes:
                        daily = period_changes.get("daily", 0)
                        weekly = period_changes.get("weekly", 0)
                        monthly = period_changes.get("monthly", 0)
                        message += f"  ${price:,.2f} | 일:{sign}{daily:.2f}% | 주:{weekly:+.2f}% | 월:{monthly:+.2f}%\n"
                    else:
                        message += f"  ${price:,.2f} ({sign}{change_pct:.2f}%)\n"

                    # 52주 범위
                    if week_52:
                        low = week_52.get("low", 0)
                        high = week_52.get("high", 0)
                        position = week_52.get("position_percent", 0)
                        message += f"  52주: {low:,.2f} ~ {high:,.2f} (현재 {position:.1f}%)\n"

            return message.strip()

        except Exception as e:
            print(f"❌ 메시지 포맷팅 실패: {e}")
            return "증시 정보를 가져올 수 없습니다."

    def format_kr_market_message(self, market_data: Dict, watchlist_data: Optional[List[Dict]] = None) -> str:
        """
        한국 증시 메시지 포맷팅

        Args:
            market_data: 증시 데이터
            watchlist_data: 관심 종목 데이터 (선택)

        Returns:
            str: 포맷팅된 메시지
        """
        try:
            message = f"""📊 한국 증시 현황

📅 {datetime.now(ZoneInfo("Asia/Seoul")).strftime('%Y년 %m월 %d일')}

[ 주요 지수 ]
"""
            for name, data in market_data.items():
                price = data["price"]
                change_percent = data["change_percent"]

                # 상승/하락 이모지
                emoji = "🟢" if change_percent >= 0 else "🔴"
                sign = "+" if change_percent >= 0 else ""

                message += f"""{emoji} {name}: {price:,.2f} ({sign}{change_percent:.2f}%)
"""

            # 관심 종목 정보 추가
            if watchlist_data and len(watchlist_data) > 0:
                message += "\n[ 관심 종목 ]\n"

                for stock in watchlist_data:
                    ticker = stock.get("ticker")
                    name = stock.get("name", ticker)
                    quote = stock.get("quote")
                    period_changes = stock.get("period_changes")
                    week_52 = stock.get("week_52_range")

                    if not quote:
                        continue

                    price = quote.get("price", 0)
                    change_pct = quote.get("change_percent", 0)
                    emoji = "🟢" if change_pct >= 0 else "🔴"
                    sign = "+" if change_pct >= 0 else ""

                    message += f"\n{emoji} {ticker} ({name})\n"

                    # 가격 및 기간별 변동률
                    if period_changes:
                        daily = period_changes.get("daily", 0)
                        weekly = period_changes.get("weekly", 0)
                        monthly = period_changes.get("monthly", 0)
                        message += f"  {price:,.0f}원 | 일:{sign}{daily:.2f}% | 주:{weekly:+.2f}% | 월:{monthly:+.2f}%\n"
                    else:
                        message += f"  {price:,.0f}원 ({sign}{change_pct:.2f}%)\n"

                    # 52주 범위
                    if week_52:
                        low = week_52.get("low", 0)
                        high = week_52.get("high", 0)
                        position = week_52.get("position_percent", 0)
                        message += f"  52주: {low:,.0f} ~ {high:,.0f} (현재 {position:.1f}%)\n"

            return message.strip()

        except Exception as e:
            print(f"❌ 메시지 포맷팅 실패: {e}")
            return "증시 정보를 가져올 수 없습니다."

    async def send_us_market_notification(self):
        """
        미국 증시 알림 발송
        """
        db = SessionLocal()

        try:
            # 거래일 체크 (NYSE 기준, 미국 동부 시간)
            if not _is_trading_day("US"):
                et_now = datetime.now(ZoneInfo("America/New_York"))
                today_str = et_now.strftime("%Y-%m-%d (%a)")
                print(f"⏸️  미국 증시 휴장일 — 발송 스킵 ({today_str} ET)")
                create_log(db, "finance", "SKIP", f"미국 증시 휴장일 ({today_str} ET)")
                return

            # 사용자 조회
            user = get_or_create_user(db)

            # Settings에서 금융 알림 활성화 여부 확인
            if not is_setting_active(db, user.user_id, "finance"):
                print("⏸️  금융 알림이 비활성화되어 있습니다")
                create_log(db, "finance", "SKIP", "미국 증시 알림 비활성화 상태")
                return

            # 증시 데이터 조회
            market_data = self.get_us_market_data()

            if not market_data:
                create_log(db, "finance", "FAIL", "미국 증시 데이터 조회 실패")
                return

            # 관심 종목 조회 (미국 시장만)
            watchlist_data = []
            try:
                watchlists = get_watchlists(db, user.user_id, is_active=True)
                us_watchlists = [w for w in watchlists if w.market == "US"]

                for watchlist in us_watchlists[:10]:  # 최대 10개
                    try:
                        # 종목 시세 조회
                        quote = self.get_stock_quote(watchlist.ticker, "US")
                        if not quote:
                            continue

                        # 기간별 변동률 조회
                        period_changes = self.calculate_period_changes(
                            watchlist.ticker, "US"
                        )

                        # 52주 범위 조회
                        week_52_range = self.get_52week_range(watchlist.ticker, "US")

                        watchlist_data.append({
                            "ticker": watchlist.ticker,
                            "name": watchlist.name,
                            "quote": quote,
                            "period_changes": period_changes,
                            "week_52_range": week_52_range,
                        })

                    except Exception as e:
                        print(f"⚠️  관심 종목 조회 실패 ({watchlist.ticker}): {e}")
                        continue

            except Exception as e:
                print(f"⚠️  관심 종목 목록 조회 실패: {e}")

            # 메시지 포맷팅
            message = self.format_us_market_message(market_data, watchlist_data)

            # 연동된 채널 확인
            available_channels = notification_service.get_available_channels(user)
            if not available_channels:
                create_log(db, "finance", "FAIL", "연동된 알림 채널이 없습니다")
                print("⚠️  알림 채널 연동이 필요합니다 (텔레그램)")
                return

            # 알림 발송 (연동된 모든 채널로 자동 발송)
            try:
                result = await notification_service.send(user, message)

                if result.success:
                    # 성공 로그
                    create_log(
                        db,
                        "finance",
                        "SUCCESS",
                        f"미국 증시 알림 발송 성공 ({result.message})",
                    )
                    print("✅ 미국 증시 알림 발송 완료")
                else:
                    # 실패 로그
                    create_log(db, "finance", "FAIL", f"알림 발송 실패: {result.message}")
                    print(f"❌ 알림 발송 실패: {result.message}")

            except Exception as e:
                create_log(db, "finance", "FAIL", f"알림 발송 오류: {str(e)}")
                print(f"❌ 알림 발송 오류: {e}")

        except Exception as e:
            create_log(db, "finance", "FAIL", f"미국 증시 알림 오류: {str(e)}")
            print(f"❌ 미국 증시 알림 오류: {e}")

        finally:
            db.close()

    async def send_kr_market_notification(self):
        """
        한국 증시 알림 발송
        """
        db = SessionLocal()

        try:
            # 거래일 체크 (KRX 기준, 한국 시간)
            if not _is_trading_day("KR"):
                kr_now = datetime.now(ZoneInfo("Asia/Seoul"))
                today_str = kr_now.strftime("%Y-%m-%d (%a)")
                print(f"⏸️  한국 증시 휴장일 — 발송 스킵 ({today_str} KST)")
                create_log(db, "finance", "SKIP", f"한국 증시 휴장일 ({today_str} KST)")
                return

            # 사용자 조회
            user = get_or_create_user(db)

            # Settings에서 금융 알림 활성화 여부 확인
            if not is_setting_active(db, user.user_id, "finance"):
                print("⏸️  금융 알림이 비활성화되어 있습니다")
                create_log(db, "finance", "SKIP", "한국 증시 알림 비활성화 상태")
                return

            # 증시 데이터 조회
            market_data = self.get_kr_market_data()

            if not market_data:
                create_log(db, "finance", "FAIL", "한국 증시 데이터 조회 실패")
                return

            # 관심 종목 조회 (한국 시장만)
            watchlist_data = []
            try:
                watchlists = get_watchlists(db, user.user_id, is_active=True)
                kr_watchlists = [w for w in watchlists if w.market == "KR"]

                for watchlist in kr_watchlists[:10]:  # 최대 10개
                    try:
                        # 종목 시세 조회
                        quote = self.get_stock_quote(watchlist.ticker, "KR")
                        if not quote:
                            continue

                        # 기간별 변동률 조회
                        period_changes = self.calculate_period_changes(
                            watchlist.ticker, "KR"
                        )

                        # 52주 범위 조회
                        week_52_range = self.get_52week_range(watchlist.ticker, "KR")

                        watchlist_data.append({
                            "ticker": watchlist.ticker,
                            "name": watchlist.name,
                            "quote": quote,
                            "period_changes": period_changes,
                            "week_52_range": week_52_range,
                        })

                    except Exception as e:
                        print(f"⚠️  관심 종목 조회 실패 ({watchlist.ticker}): {e}")
                        continue

            except Exception as e:
                print(f"⚠️  관심 종목 목록 조회 실패: {e}")

            # 메시지 포맷팅
            message = self.format_kr_market_message(market_data, watchlist_data)

            # 연동된 채널 확인
            available_channels = notification_service.get_available_channels(user)
            if not available_channels:
                create_log(db, "finance", "FAIL", "연동된 알림 채널이 없습니다")
                print("⚠️  알림 채널 연동이 필요합니다 (텔레그램)")
                return

            # 알림 발송 (연동된 모든 채널로 자동 발송)
            try:
                result = await notification_service.send(user, message)

                if result.success:
                    # 성공 로그
                    create_log(
                        db,
                        "finance",
                        "SUCCESS",
                        f"한국 증시 알림 발송 성공 ({result.message})",
                    )
                    print("✅ 한국 증시 알림 발송 완료")
                else:
                    # 실패 로그
                    create_log(db, "finance", "FAIL", f"알림 발송 실패: {result.message}")
                    print(f"❌ 알림 발송 실패: {result.message}")

            except Exception as e:
                create_log(db, "finance", "FAIL", f"알림 발송 오류: {str(e)}")
                print(f"❌ 알림 발송 오류: {e}")

        except Exception as e:
            create_log(db, "finance", "FAIL", f"한국 증시 알림 오류: {str(e)}")
            print(f"❌ 한국 증시 알림 오류: {e}")

        finally:
            db.close()

    async def check_price_alerts(self):
        """
        가격 알림 조건 체크 및 알림 발송
        5분마다 실행되어 등록된 가격 알림의 조건을 확인하고 알림 발송
        """
        print("🔍 가격 알림 조건 체크 시작...")
        db = SessionLocal()

        try:
            user = get_or_create_user(db)

            # 활성화된 가격 알림 조회
            alerts = get_price_alerts(db, user.user_id, is_active=True)
            if not alerts:
                print("ℹ️  등록된 가격 알림이 없습니다")
                return

            print(f"📋 체크할 가격 알림 {len(alerts)}개")

            # 각 알림 조건 체크
            for alert in alerts:
                try:
                    # 이미 발동된 알림은 스킵
                    if alert.is_triggered:
                        continue

                    # 관심 종목 정보 조회
                    watchlist = get_watchlist(db, alert.watchlist_id)
                    if not watchlist:
                        print(f"⚠️  관심 종목을 찾을 수 없습니다: {alert.watchlist_id}")
                        continue

                    # 현재 시세 조회
                    quote = self.get_stock_quote(watchlist.ticker, watchlist.market)
                    if not quote:
                        print(
                            f"⚠️  시세 조회 실패: {watchlist.ticker} ({watchlist.market})"
                        )
                        continue

                    current_price = quote.get("price")
                    if current_price is None:
                        continue

                    # 알림 조건 체크
                    should_alert = False
                    alert_message = ""

                    if alert.alert_type == "TARGET_HIGH":
                        # 목표가 도달 (상승)
                        if current_price >= alert.target_price:
                            should_alert = True
                            # 종목 표시 형식 (티커와 이름)
                            stock_display = f"{watchlist.ticker} ({watchlist.name})" if watchlist.name else watchlist.ticker
                            # 통화 단위 (시장별 구분)
                            if watchlist.market == "KR":
                                alert_message = (
                                    f"[가격 알림] {stock_display}\n"
                                    f"목표가 도달!\n"
                                    f"현재가: {current_price:,.0f}원\n"
                                    f"목표가: {alert.target_price:,.0f}원"
                                )
                            else:
                                alert_message = (
                                    f"[가격 알림] {stock_display}\n"
                                    f"목표가 도달!\n"
                                    f"현재가: ${current_price:,.2f}\n"
                                    f"목표가: ${alert.target_price:,.2f}"
                                )

                    elif alert.alert_type == "TARGET_LOW":
                        # 목표가 도달 (하락)
                        if current_price <= alert.target_price:
                            should_alert = True
                            # 종목 표시 형식 (티커와 이름)
                            stock_display = f"{watchlist.ticker} ({watchlist.name})" if watchlist.name else watchlist.ticker
                            # 통화 단위 (시장별 구분)
                            if watchlist.market == "KR":
                                alert_message = (
                                    f"[가격 알림] {stock_display}\n"
                                    f"손절가 도달!\n"
                                    f"현재가: {current_price:,.0f}원\n"
                                    f"손절가: {alert.target_price:,.0f}원"
                                )
                            else:
                                alert_message = (
                                    f"[가격 알림] {stock_display}\n"
                                    f"손절가 도달!\n"
                                    f"현재가: ${current_price:,.2f}\n"
                                    f"손절가: ${alert.target_price:,.2f}"
                                )

                    elif alert.alert_type == "PERCENT_CHANGE":
                        # 변동률 체크 (기준가 대비)
                        # reference_price가 없으면 현재가로 초기화
                        if alert.reference_price is None:
                            from app.crud import update_alert_reference_price

                            update_alert_reference_price(db, alert.alert_id, current_price)
                            print(
                                f"📌 기준가 초기화: {watchlist.ticker} = {current_price}"
                            )
                            continue

                        # 기준가 대비 변동률 계산
                        change_percent = (
                            (current_price - alert.reference_price)
                            / alert.reference_price
                        ) * 100

                        # 목표 변동률 달성 여부 체크
                        if abs(change_percent) >= abs(alert.target_percent):
                            direction = "상승" if change_percent > 0 else "하락"
                            should_alert = True

                            # 종목 표시 형식 (티커와 이름)
                            stock_display = (
                                f"{watchlist.ticker} ({watchlist.name})"
                                if watchlist.name
                                else watchlist.ticker
                            )

                            # 통화 단위 (시장별 구분)
                            if watchlist.market == "KR":
                                alert_message = (
                                    f"[가격 알림] {stock_display}\n"
                                    f"급격한 {direction}!\n"
                                    f"기준가: {alert.reference_price:,.0f}원\n"
                                    f"현재가: {current_price:,.0f}원\n"
                                    f"변동률: {change_percent:+.2f}%"
                                )
                            else:
                                alert_message = (
                                    f"[가격 알림] {stock_display}\n"
                                    f"급격한 {direction}!\n"
                                    f"기준가: ${alert.reference_price:,.2f}\n"
                                    f"현재가: ${current_price:,.2f}\n"
                                    f"변동률: {change_percent:+.2f}%"
                                )

                    # 알림 발송
                    if should_alert:
                        print(f"🚨 알림 발동: {watchlist.ticker} ({alert.alert_type})")

                        # 연동된 채널 확인
                        available_channels = notification_service.get_available_channels(
                            user
                        )
                        if not available_channels:
                            print("⚠️  알림 채널 연동이 필요합니다")
                            continue

                        # 알림 발송
                        result = await notification_service.send(user, alert_message)

                        if result.success:
                            # 알림 타입별 상태 업데이트
                            if alert.alert_type == "PERCENT_CHANGE":
                                # 변동률 알림: 기준가만 갱신 (계속 모니터링)
                                from app.crud import update_alert_reference_price

                                update_alert_reference_price(db, alert.alert_id, current_price)
                                print(
                                    f"📌 기준가 갱신: {watchlist.ticker} = {current_price}"
                                )
                            else:
                                # 목표가/손절가 알림: 발동됨으로 표시 (일회성)
                                update_alert_triggered(db, alert.alert_id)

                            create_log(
                                db,
                                "finance",
                                "SUCCESS",
                                f"가격 알림 발송 성공: {watchlist.ticker} ({alert.alert_type})",
                            )
                            print(f"✅ 가격 알림 발송 완료: {watchlist.ticker}")
                        else:
                            create_log(
                                db,
                                "finance",
                                "FAIL",
                                f"가격 알림 발송 실패: {result.message}",
                            )
                            print(f"❌ 가격 알림 발송 실패: {result.message}")

                except Exception as e:
                    print(f"⚠️  가격 알림 체크 중 오류 ({alert.alert_id}): {e}")
                    continue

        except Exception as e:
            create_log(db, "finance", "FAIL", f"가격 알림 체크 오류: {str(e)}")
            print(f"❌ 가격 알림 체크 오류: {e}")

        finally:
            db.close()


# 싱글톤 인스턴스
finance_bot = FinanceBot()


# 스케줄러에서 호출할 함수들
def send_us_market_notification_sync():
    """동기 방식으로 미국 증시 알림 발송"""
    import asyncio

    try:
        asyncio.run(finance_bot.send_us_market_notification())
    except Exception as e:
        print(f"❌ 미국 증시 알림 실행 오류: {e}")


def send_kr_market_notification_sync():
    """동기 방식으로 한국 증시 알림 발송"""
    import asyncio

    try:
        asyncio.run(finance_bot.send_kr_market_notification())
    except Exception as e:
        print(f"❌ 한국 증시 알림 실행 오류: {e}")


def check_price_alerts_sync():
    """동기 방식으로 가격 알림 조건 체크"""
    import asyncio

    try:
        asyncio.run(finance_bot.check_price_alerts())
    except Exception as e:
        print(f"❌ 가격 알림 체크 실행 오류: {e}")
