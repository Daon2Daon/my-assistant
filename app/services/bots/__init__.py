"""
Bots 패키지
모든 알림 봇을 임포트
"""

from app.services.bots.weather_bot import weather_bot, send_weather_notification_sync
from app.services.bots.finance_bot import (
    finance_bot,
    send_us_market_notification_sync,
    send_kr_market_notification_sync,
)
from app.services.bots.calendar_bot import calendar_bot, send_calendar_notification_sync
from app.services.bots.memo_bot import memo_bot, send_memo_notification_sync

__all__ = [
    "weather_bot",
    "send_weather_notification_sync",
    "finance_bot",
    "send_us_market_notification_sync",
    "send_kr_market_notification_sync",
    "calendar_bot",
    "send_calendar_notification_sync",
    "memo_bot",
    "send_memo_notification_sync",
]
