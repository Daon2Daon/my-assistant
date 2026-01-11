"""
금융 알림 봇
Yahoo Finance 및 PyKRX를 사용한 증시 정보 수집 및 알림
"""

import yfinance as yf
from pykrx import stock
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from app.database import SessionLocal
from app.crud import get_or_create_user, create_log, is_setting_active
from app.services.auth.kakao_auth import kakao_auth_service


class FinanceBot:
    """금융 알림 봇"""

    def __init__(self):
        # 주요 미국 지수 티커
        self.us_indices = {
            "^GSPC": "S&P 500",
            "^IXIC": "Nasdaq",
            "^DJI": "Dow Jones",
        }

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
        한국 증시 데이터 조회

        Returns:
            Dict: 증시 데이터 또는 None
        """
        try:
            # 최근 거래일 조회 (오늘 또는 어제)
            today = datetime.now()
            date_str = today.strftime("%Y%m%d")

            # 주말이면 금요일 데이터 조회
            if today.weekday() >= 5:  # 토요일(5) 또는 일요일(6)
                days_back = today.weekday() - 4  # 금요일까지
                date_str = (today - timedelta(days=days_back)).strftime("%Y%m%d")

            market_data = {}

            try:
                # KOSPI 지수
                kospi = stock.get_index_ohlcv(date_str, date_str, "1001")
                if not kospi.empty:
                    kospi_close = kospi["종가"].iloc[-1]
                    kospi_change = kospi["등락률"].iloc[-1]

                    market_data["KOSPI"] = {
                        "price": kospi_close,
                        "change_percent": kospi_change,
                    }

            except Exception as e:
                print(f"⚠️  KOSPI 데이터 조회 실패: {e}")

            try:
                # KOSDAQ 지수
                kosdaq = stock.get_index_ohlcv(date_str, date_str, "2001")
                if not kosdaq.empty:
                    kosdaq_close = kosdaq["종가"].iloc[-1]
                    kosdaq_change = kosdaq["등락률"].iloc[-1]

                    market_data["KOSDAQ"] = {
                        "price": kosdaq_close,
                        "change_percent": kosdaq_change,
                    }

            except Exception as e:
                print(f"⚠️  KOSDAQ 데이터 조회 실패: {e}")

            return market_data if market_data else None

        except Exception as e:
            print(f"❌ 한국 증시 데이터 조회 실패: {e}")
            return None

    def format_us_market_message(self, market_data: Dict) -> str:
        """
        미국 증시 메시지 포맷팅

        Args:
            market_data: 증시 데이터

        Returns:
            str: 포맷팅된 메시지
        """
        try:
            message = f"""📈 미국 증시 마감

📅 {datetime.now().strftime('%Y년 %m월 %d일')}

"""
            for name, data in market_data.items():
                price = data["price"]
                change = data["change"]
                change_percent = data["change_percent"]

                # 상승/하락 이모지
                emoji = "🔺" if change >= 0 else "🔻"
                sign = "+" if change >= 0 else ""

                message += f"""{emoji} {name}
  {price:,.2f} ({sign}{change_percent:.2f}%)

"""

            return message.strip()

        except Exception as e:
            print(f"❌ 메시지 포맷팅 실패: {e}")
            return "증시 정보를 가져올 수 없습니다."

    def format_kr_market_message(self, market_data: Dict) -> str:
        """
        한국 증시 메시지 포맷팅

        Args:
            market_data: 증시 데이터

        Returns:
            str: 포맷팅된 메시지
        """
        try:
            message = f"""📊 한국 증시 현황

📅 {datetime.now().strftime('%Y년 %m월 %d일')}

"""
            for name, data in market_data.items():
                price = data["price"]
                change_percent = data["change_percent"]

                # 상승/하락 이모지
                emoji = "🔺" if change_percent >= 0 else "🔻"
                sign = "+" if change_percent >= 0 else ""

                message += f"""{emoji} {name}
  {price:,.2f} ({sign}{change_percent:.2f}%)

"""

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

            # 메시지 포맷팅
            message = self.format_us_market_message(market_data)

            if not user.kakao_access_token:
                create_log(db, "finance", "FAIL", "카카오 토큰이 없습니다")
                print("⚠️  카카오 로그인이 필요합니다")
                return

            # 카카오톡 메시지 발송
            try:
                await kakao_auth_service.send_message_to_me(
                    user.kakao_access_token, message
                )

                # 성공 로그
                create_log(
                    db,
                    "finance",
                    "SUCCESS",
                    f"미국 증시 알림 발송 성공 (user_id: {user.user_id})",
                )
                print("✅ 미국 증시 알림 발송 완료")

            except Exception as e:
                create_log(db, "finance", "FAIL", f"메시지 발송 실패: {str(e)}")
                print(f"❌ 메시지 발송 실패: {e}")

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

            # 메시지 포맷팅
            message = self.format_kr_market_message(market_data)

            if not user.kakao_access_token:
                create_log(db, "finance", "FAIL", "카카오 토큰이 없습니다")
                print("⚠️  카카오 로그인이 필요합니다")
                return

            # 카카오톡 메시지 발송
            try:
                await kakao_auth_service.send_message_to_me(
                    user.kakao_access_token, message
                )

                # 성공 로그
                create_log(
                    db,
                    "finance",
                    "SUCCESS",
                    f"한국 증시 알림 발송 성공 (user_id: {user.user_id})",
                )
                print("✅ 한국 증시 알림 발송 완료")

            except Exception as e:
                create_log(db, "finance", "FAIL", f"메시지 발송 실패: {str(e)}")
                print(f"❌ 메시지 발송 실패: {e}")

        except Exception as e:
            create_log(db, "finance", "FAIL", f"한국 증시 알림 오류: {str(e)}")
            print(f"❌ 한국 증시 알림 오류: {e}")

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
