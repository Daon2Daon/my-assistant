"""
Chartbot - 종목 차트 생성 및 텔레그램 발송
ta-charts 형식: 4패널 (캔들스틱 + RSI + MACD + 거래량), 일봉/주봉
"""

import os
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf
from pykrx import stock as krx_stock
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib import font_manager

from app.config import settings
from app.database import SessionLocal
from app.crud import (
    get_or_create_user,
    get_setting_by_category,
    create_log,
)
from app.services.notification.telegram_sender import telegram_sender


# 한글 폰트 설정
def _setup_korean_font():
    """한글 표시를 위한 폰트 설정"""
    try:
        font_path = "/System/Library/Fonts/AppleSDGothicNeo.ttc"  # macOS
        if os.path.exists(font_path):
            font_manager.fontManager.addfont(font_path)
            plt.rcParams['font.family'] = 'Apple SD Gothic Neo'
        else:
            plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
    except Exception:
        plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False


_setup_korean_font()


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """OHLCV 컬럼명 정규화 (Open, High, Low, Close, Volume)"""
    # yfinance: multi-level columns
    if df.columns.nlevels > 1:
        df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]
    # pykrx: 시가, 고가, 저가, 종가, 거래량
    kr_map = {
        '시가': 'Open', '고가': 'High', '저가': 'Low',
        '종가': 'Close', '거래량': 'Volume'
    }
    df = df.rename(columns=kr_map)
    # 필요한 컬럼만 선택 (Adj Close 제외)
    required = ['Open', 'High', 'Low', 'Close', 'Volume']
    for c in required:
        if c not in df.columns:
            return df  # 필수 컬럼 없으면 그대로 반환 (에러 유발)
    return df[required].copy()


def _calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """기술적 지표 계산 (EMA, SMA, Bollinger, RSI, MACD)"""
    df = _normalize_columns(df.copy())
    df['EMA12'] = df['Close'].ewm(span=12, adjust=False).mean()
    df['EMA26'] = df['Close'].ewm(span=26, adjust=False).mean()
    df['SMA20'] = df['Close'].rolling(window=20).mean()
    df['SMA50'] = df['Close'].rolling(window=50).mean()
    df['BB20'] = df['Close'].rolling(window=20).mean()
    df['BB_std'] = df['Close'].rolling(window=20).std()
    df['BB_upper'] = df['BB20'] + (df['BB_std'] * 2)
    df['BB_lower'] = df['BB20'] - (df['BB_std'] * 2)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    loss_safe = loss.replace(0, np.nan)
    rs = gain / loss_safe
    df['RSI'] = 100 - (100 / (1 + rs))
    df['RSI'] = df['RSI'].fillna(50)
    df['MACD'] = df['EMA12'] - df['EMA26']
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['Histogram'] = (df['MACD'] - df['Signal']).fillna(0)
    return df


def _calculate_volume_profile(df: pd.DataFrame, bins: int = 50) -> Tuple[np.ndarray, np.ndarray]:
    """Volume Profile 계산"""
    price_min, price_max = df['Low'].min(), df['High'].max()
    if price_min >= price_max:
        price_max = price_min + 1
    price_bins = np.linspace(price_min, price_max, bins)
    volume_profile = np.zeros(bins - 1)
    for _, row in df.iterrows():
        candle_low = float(row['Low'])
        candle_high = float(row['High'])
        candle_volume = float(row['Volume'])
        bin_indices = np.where((price_bins[:-1] <= candle_high) & (price_bins[1:] >= candle_low))[0]
        if len(bin_indices) > 0:
            vol_per_bin = candle_volume / len(bin_indices)
            for bi in bin_indices:
                if bi < len(volume_profile):
                    volume_profile[bi] += vol_per_bin
    price_centers = (price_bins[:-1] + price_bins[1:]) / 2
    return price_centers, volume_profile


def _plot_candlesticks(ax, df: pd.DataFrame, width: float = 0.6) -> None:
    """캔들스틱 그리기"""
    for i, (_, row) in enumerate(df.iterrows()):
        o = float(row['Open'])
        c = float(row['Close'])
        h = float(row['High'])
        l = float(row['Low'])
        color = 'green' if c >= o else 'red'
        ax.plot([i, i], [l, h], color=color, linewidth=0.8)
        body_h = abs(c - o)
        body_b = min(o, c)
        if body_h < 1e-10:
            body_h = 0.001
        rect = Rectangle((i - width/2, body_b), width, body_h,
                          facecolor=color, edgecolor=color, linewidth=0.5)
        ax.add_patch(rect)


def _create_ta_chart(
    df: pd.DataFrame,
    ticker: str,
    name: str,
    chart_type: str,
    period_name: str,
    output_path: str,
) -> None:
    """
    ta-charts 형식 4패널 차트 생성
    Panel 1: 캔들스틱 + Volume Profile + 이동평균 + Bollinger
    Panel 2: RSI
    Panel 3: MACD
    Panel 4: Volume
    """
    fig, (ax1, ax2, ax3, ax4) = plt.subplots(
        4, 1, figsize=(14, 10),
        gridspec_kw={'height_ratios': [3, 1, 1, 1]}
    )
    fig.suptitle(f'{name} ({ticker}) - {chart_type.upper()} - Technical Analysis',
                 fontsize=14, fontweight='bold')

    x_range = np.arange(len(df))

    # Panel 1: Price
    _plot_candlesticks(ax1, df)
    price_centers, volume_profile = _calculate_volume_profile(df, bins=50)
    vmax = volume_profile.max()
    if vmax > 0:
        ax1_vol = ax1.twiny()
        h = (price_centers[1] - price_centers[0]) * 0.95 if len(price_centers) > 1 else 1
        ax1_vol.barh(price_centers, volume_profile, height=h, color='orange', alpha=0.12, zorder=0)
        ax1_vol.set_xlim([0, vmax])
        ax1_vol.set_xticks([])
    ax1.plot(x_range, df['EMA12'].values, color='red', alpha=0.7, linewidth=1.5, label='EMA 12')
    ax1.plot(x_range, df['EMA26'].values, color='blue', alpha=0.7, linewidth=1.5, label='EMA 26')
    ax1.plot(x_range, df['SMA20'].values, color='darkgreen', alpha=0.6, linewidth=1.5, label='SMA 20')
    ax1.plot(x_range, df['SMA50'].values, color='orange', alpha=0.6, linewidth=1.5, label='SMA 50')
    ax1.fill_between(x_range, df['BB_upper'].values, df['BB_lower'].values,
                     color='gray', alpha=0.15, label='Bollinger Bands')
    ax1.plot(x_range, df['BB_upper'].values, color='gray', linewidth=0.8, linestyle='--', alpha=0.5)
    ax1.plot(x_range, df['BB_lower'].values, color='gray', linewidth=0.8, linestyle='--', alpha=0.5)
    ax1.set_ylabel('Price', fontweight='bold')
    ax1.legend(loc='upper left', fontsize=8)
    ax1.grid(True, alpha=0.3)
    ax1.set_title(f'Price Chart with Candlesticks ({period_name}, {len(df)} candles)')
    ax1.set_xlim(-1, len(df))

    # Panel 2: RSI
    ax2.plot(x_range, df['RSI'].values, color='purple', linewidth=1.5)
    ax2.axhline(y=70, color='red', linestyle='--', alpha=0.5, label='Overbought(70)')
    ax2.axhline(y=30, color='green', linestyle='--', alpha=0.5, label='Oversold(30)')
    ax2.fill_between(x_range, 30, 70, color='yellow', alpha=0.1)
    ax2.set_ylabel('RSI(14)', fontweight='bold')
    ax2.set_ylim(0, 100)
    ax2.legend(loc='upper left', fontsize=8)
    ax2.grid(True, alpha=0.3)
    ax2.set_xlim(-1, len(df))

    # Panel 3: MACD
    hist_colors = ['green' if x >= 0 else 'red' for x in df['Histogram'].values]
    ax3.bar(x_range, df['Histogram'].values, color=hist_colors, alpha=0.3, label='Histogram')
    ax3.plot(x_range, df['MACD'].values, color='blue', linewidth=1.5, label='MACD')
    ax3.plot(x_range, df['Signal'].values, color='red', linewidth=1.5, label='Signal')
    ax3.axhline(y=0, color='black', linestyle='-', alpha=0.3)
    ax3.set_ylabel('MACD', fontweight='bold')
    ax3.legend(loc='upper left', fontsize=8)
    ax3.grid(True, alpha=0.3)
    ax3.set_xlim(-1, len(df))

    # Panel 4: Volume
    close_prices = df['Close'].values
    volumes = df['Volume'].values
    for i in range(len(close_prices)):
        color = 'green' if (i == 0 or close_prices[i] >= close_prices[i-1]) else 'red'
        ax4.bar(i, volumes[i], color=color, alpha=0.6)
    ax4.plot(x_range, df['Volume'].rolling(20).mean().values, color='blue',
             linewidth=2, label='SMA 20')
    ax4.set_ylabel('Volume', fontweight='bold')
    ax4.set_xlabel('Date', fontweight='bold')
    ax4.legend(loc='upper left', fontsize=8)
    ax4.grid(True, alpha=0.3)
    ax4.set_xlim(-1, len(df))

    dates = df.index
    date_labels = [d.strftime('%Y-%m') for d in dates]
    label_step = max(1, len(dates) // 12)
    tick_positions = np.arange(0, len(dates), label_step)
    tick_labels = [date_labels[i] if i < len(date_labels) else '' for i in tick_positions]
    for ax in [ax1, ax2, ax3, ax4]:
        ax.set_xticks(tick_positions)
        ax.set_xticklabels(tick_labels, rotation=45, ha='right')

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()


class ChartBot:
    """종목 차트 생성 및 발송 봇 (ta-charts 형식)"""

    def __init__(self):
        self.charts_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "static", "charts"
        )
        os.makedirs(self.charts_dir, exist_ok=True)

    def _get_us_ohlcv(self, ticker: str, period: str = "5y") -> Optional[pd.DataFrame]:
        """미국 종목 OHLCV 조회 (yfinance)"""
        try:
            data = yf.download(ticker, period=period, progress=False, auto_adjust=False)
            if data.empty or len(data) < 20:
                return None
            return _normalize_columns(data.copy())
        except Exception as e:
            print(f"❌ US 데이터 조회 실패 ({ticker}): {e}")
            return None

    def _get_kr_ohlcv(self, ticker: str, days: int = 1825) -> Optional[pd.DataFrame]:
        """한국 종목 OHLCV 조회 (pykrx)"""
        try:
            today = datetime.now(ZoneInfo("Asia/Seoul"))
            end_date = today.strftime("%Y%m%d")
            start_date = (today - timedelta(days=days)).strftime("%Y%m%d")
            df = krx_stock.get_market_ohlcv_by_date(start_date, end_date, ticker)
            if df.empty or len(df) < 20:
                return None
            df = df.rename(columns={
                '시가': 'Open', '고가': 'High', '저가': 'Low',
                '종가': 'Close', '거래량': 'Volume'
            })
            return df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
        except Exception as e:
            print(f"❌ KR 데이터 조회 실패 ({ticker}): {e}")
            return None

    def generate_chart(
        self, ticker: str, market: str = "US", days: int = 30
    ) -> Optional[str]:
        """
        단일 차트 생성 (기존 API 호환 - 일봉만, 30일)
        하위 호환용. send_all_charts에서는 generate_ta_charts 사용.
        """
        return self._generate_single_daily(ticker, market, days)

    def _generate_single_daily(
        self, ticker: str, market: str, days: int
    ) -> Optional[str]:
        """일봉 차트 1장 생성 (간단 호환용)"""
        if market == "US":
            df = self._get_us_ohlcv(ticker, period=f"{days}d")
        elif market == "KR":
            df = self._get_kr_ohlcv(ticker, days=days)
        else:
            return None
        if df is None or len(df) < 2:
            return None
        df = _calculate_indicators(df)
        suffix = ticker.replace('-', '_').replace('.', '_').lower()
        filename = f"{suffix}_{market}_daily_{uuid.uuid4().hex[:8]}.png"
        filepath = os.path.join(self.charts_dir, filename)
        name = self._get_name(ticker, market)
        _create_ta_chart(df, ticker, name, 'daily', f'{days} days', filepath)
        return f"charts/{filename}"

    def generate_ta_charts(
        self, ticker: str, market: str, name: str
    ) -> List[Tuple[str, str]]:
        """
        ta-charts 형식: 일봉 + 주봉 차트 생성

        Returns:
            [(chart_path, caption), ...]  예: [("charts/xxx_daily.png", "일봉"), ...]
        """
        results = []
        if market == "US":
            df = self._get_us_ohlcv(ticker, period="5y")
        elif market == "KR":
            df = self._get_kr_ohlcv(ticker, days=1825)
        else:
            return []

        if df is None or len(df) < 20:
            return []

        df = _calculate_indicators(df)
        suffix = ticker.replace('-', '_').replace('.', '_').lower()

        # 일봉 (1년)
        df_daily = df.tail(252) if len(df) >= 252 else df
        fname_daily = f"{suffix}_{market}_daily_{uuid.uuid4().hex[:8]}.png"
        path_daily = os.path.join(self.charts_dir, fname_daily)
        _create_ta_chart(df_daily, ticker, name, 'daily', '1 year', path_daily)
        results.append((path_daily, f"{name} ({ticker}) 일봉"))

        # 주봉 (5년)
        df_weekly = df[['Open', 'High', 'Low', 'Close', 'Volume']].resample('W').agg({
            'Open': 'first', 'High': 'max', 'Low': 'min',
            'Close': 'last', 'Volume': 'sum'
        }).dropna()
        if len(df_weekly) >= 20:
            df_weekly = _calculate_indicators(df_weekly)
            fname_weekly = f"{suffix}_{market}_weekly_{uuid.uuid4().hex[:8]}.png"
            path_weekly = os.path.join(self.charts_dir, fname_weekly)
            _create_ta_chart(df_weekly, ticker, name, 'weekly', '5 years', path_weekly)
            results.append((path_weekly, f"{name} ({ticker}) 주봉"))

        return results

    def _get_name(self, ticker: str, market: str) -> str:
        """종목명 조회 (개별 종목, ETF, ETN 지원)"""
        if market == "US":
            try:
                info = yf.Ticker(ticker).info
                return info.get("longName", info.get("shortName", ticker))
            except Exception:
                return ticker
        try:
            name = krx_stock.get_market_ticker_name(ticker)
            if isinstance(name, str) and len(name) > 0:
                return name
            # ETF/ETN: get_market_ticker_name이 DataFrame 또는 빈값 반환 시
            for getter in (krx_stock.get_etf_ticker_name, krx_stock.get_etn_ticker_name):
                try:
                    n = getter(ticker)
                    if isinstance(n, str) and len(n) > 0:
                        return n
                except Exception:
                    pass
        except Exception:
            pass
        return ticker

    def get_chart_image_url(self, relative_path: str) -> str:
        """차트 이미지의 공개 URL 생성"""
        base = settings.BASE_URL.rstrip("/")
        path = relative_path.lstrip("/")
        if not path.startswith("static/"):
            path = f"static/{path}"
        return f"{base}/{path}"

    async def send_chart_notification(
        self, ticker: str, market: str, chart_path: str, name: str
    ) -> bool:
        """차트 1장을 텔레그램으로 발송 (기존 API 호환)"""
        db = SessionLocal()
        try:
            user = get_or_create_user(db)
            if not telegram_sender.is_available(user):
                print("❌ 텔레그램 연동이 필요합니다")
                create_log(db, "chartbot", "FAIL", "텔레그램 연동 필요")
                return False
            filename = os.path.basename(chart_path)
            photo_path = os.path.join(self.charts_dir, filename)
            caption = f"📈 <b>{name}</b> ({ticker})\n{market} 시장 - 기술적 분석"
            sent = await telegram_sender.send_photo(
                user=user, photo_path=photo_path, caption=caption
            )
            if sent:
                create_log(db, "chartbot", "SUCCESS", f"차트 발송: {ticker} ({market})")
                print(f"✅ Chartbot 차트 발송 완료: {ticker}")
            return sent
        except Exception as e:
            print(f"❌ Chartbot 발송 실패 ({ticker}): {e}")
            create_log(db, "chartbot", "FAIL", str(e))
            return False
        finally:
            db.close()

    async def send_ta_charts(
        self, ticker: str, market: str, name: str
    ) -> int:
        """
        ta-charts 형식: 일봉 + 주봉 차트를 텔레그램으로 발송
        Returns: 성공 발송 건수
        """
        db = SessionLocal()
        try:
            user = get_or_create_user(db)
            if not telegram_sender.is_available(user):
                print("❌ 텔레그램 연동이 필요합니다")
                create_log(db, "chartbot", "FAIL", "텔레그램 연동 필요")
                return 0

            charts = self.generate_ta_charts(ticker, market, name)
            if not charts:
                create_log(db, "chartbot", "FAIL", f"차트 생성 실패: {ticker}")
                return 0

            success = 0
            for photo_path, caption in charts:
                sent = await telegram_sender.send_photo(
                    user=user, photo_path=photo_path, caption=f"📊 {caption}"
                )
                if sent:
                    success += 1
                try:
                    os.remove(photo_path)
                except Exception:
                    pass

            if success > 0:
                create_log(db, "chartbot", "SUCCESS", f"차트 발송: {ticker} ({market}) - {success}건")
                print(f"✅ Chartbot 차트 발송 완료: {ticker} ({success}건)")
            return success
        except Exception as e:
            print(f"❌ Chartbot 발송 실패 ({ticker}): {e}")
            create_log(db, "chartbot", "FAIL", str(e))
            return 0
        finally:
            db.close()

    async def send_all_charts(self) -> Dict[str, int]:
        """
        설정된 모든 종목의 차트를 ta-charts 형식(일봉+주봉)으로 발송
        """
        db = SessionLocal()
        success_count = 0
        fail_count = 0

        try:
            user = get_or_create_user(db)
            setting = get_setting_by_category(db, user.user_id, "chartbot")
            if not setting or not setting.is_active:
                create_log(db, "chartbot", "SKIP", "Chartbot 비활성화됨")
                return {"success": 0, "fail": 0}

            tickers = []
            if setting.config_json:
                import json
                try:
                    config = json.loads(setting.config_json)
                    tickers = config.get("tickers", [])
                except Exception:
                    pass

            if not tickers:
                create_log(db, "chartbot", "SKIP", "등록된 종목 없음")
                return {"success": 0, "fail": 0}

            for item in tickers:
                ticker = item.get("ticker") if isinstance(item, dict) else str(item)
                market = item.get("market", "US") if isinstance(item, dict) else "US"
                name = self._get_name(ticker, market)

                sent = await self.send_ta_charts(ticker, market, name)
                if sent > 0:
                    success_count += 1
                else:
                    fail_count += 1

            create_log(
                db, "chartbot", "SUCCESS",
                f"차트 발송 완료: 성공 {success_count}건, 실패 {fail_count}건"
            )
            return {"success": success_count, "fail": fail_count}
        except Exception as e:
            print(f"❌ Chartbot 일괄 발송 실패: {e}")
            create_log(db, "chartbot", "FAIL", str(e))
            return {"success": success_count, "fail": fail_count}
        finally:
            db.close()


def chartbot_dispatcher_sync():
    """
    스케줄러에서 매 분 호출
    설정된 요일과 시간에 맞는 종목의 차트만 발송
    - notification_days: [0,1,2,3,4,5,6] (0=월요일, 6=일요일, Python weekday)
    - notification_time: "HH:MM"
    """
    import json
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.database import SessionLocal
    from app.crud import get_setting_by_category, get_or_create_user

    db = SessionLocal()
    try:
        user = get_or_create_user(db)
        setting = get_setting_by_category(db, user.user_id, "chartbot")
        if not setting or not setting.is_active or not setting.config_json:
            return

        config = json.loads(setting.config_json)
        tickers = config.get("tickers", [])
        if not tickers:
            return

        now = datetime.now(ZoneInfo("Asia/Seoul"))
        current_weekday = now.weekday()  # 0=월요일, 6=일요일
        current_time = now.strftime("%H:%M")

        for item in tickers:
            t = item.get("ticker") if isinstance(item, dict) else item
            m = item.get("market", "US") if isinstance(item, dict) else "US"
            nt = item.get("notification_time", "09:00") if isinstance(item, dict) else "09:00"
            nd = item.get("notification_days", [0, 1, 2, 3, 4]) if isinstance(item, dict) else [0, 1, 2, 3, 4]
            if not isinstance(nd, list):
                try:
                    nd = [int(x.strip()) for x in str(nd).replace("[", "").replace("]", "").split(",") if x.strip().isdigit()]
                except (ValueError, TypeError):
                    nd = []
            if not nd:
                continue
            if nt == current_time and current_weekday in nd:
                try:
                    send_chart_ticker_sync(t, m)
                except Exception as e:
                    print(f"❌ Chartbot 종목 발송 실패 ({t}): {e}")
    finally:
        db.close()


def send_chartbot_notification_sync():
    """스케줄러에서 호출 - 등록된 모든 종목 즉시 발송 (테스트용)"""
    import asyncio
    asyncio.run(ChartBot().send_all_charts())


def send_chart_ticker_sync(ticker: str, market: str) -> bool:
    """
    스케줄러에서 호출 - 특정 종목 차트만 발송
    종목별 발송 시간에 맞춰 호출됨
    """
    import asyncio
    bot = ChartBot()
    name = bot._get_name(ticker, market)
    return asyncio.run(bot.send_ta_charts(ticker, market, name)) > 0


chart_bot = ChartBot()
