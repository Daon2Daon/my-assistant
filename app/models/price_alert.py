"""
PriceAlert 모델
종목의 가격 알림 조건을 관리하는 테이블
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from datetime import datetime
from zoneinfo import ZoneInfo
from app.database import Base


class PriceAlert(Base):
    """
    가격 알림 테이블
    종목의 목표가/손절가 도달 시 알림 발송
    """

    __tablename__ = "price_alerts"

    alert_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False, index=True)
    watchlist_id = Column(
        Integer, ForeignKey("watchlists.watchlist_id"), nullable=False, index=True
    )

    # 알림 조건
    alert_type = Column(
        String(20), nullable=False
    )  # TARGET_HIGH / TARGET_LOW / PERCENT_CHANGE
    target_price = Column(Float, nullable=True)
    target_percent = Column(Float, nullable=True)

    # 상태
    is_triggered = Column(Boolean, default=False)
    triggered_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)

    # 메타데이터
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(ZoneInfo("Asia/Seoul")))

    def __repr__(self):
        return f"<PriceAlert(alert_id={self.alert_id}, watchlist_id={self.watchlist_id}, alert_type={self.alert_type})>"
