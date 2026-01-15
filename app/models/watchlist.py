"""
Watchlist 모델
사용자의 관심 종목을 관리하는 테이블
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class Watchlist(Base):
    """
    관심 종목 테이블
    사용자가 등록한 관심 종목 정보 저장
    """

    __tablename__ = "watchlists"

    watchlist_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False, index=True)

    # 종목 정보
    ticker = Column(String(20), nullable=False, index=True)
    name = Column(String(100), nullable=True)
    market = Column(String(10), nullable=False)  # US / KR

    # 매수 정보 (선택)
    purchase_price = Column(Float, nullable=True)
    purchase_quantity = Column(Integer, nullable=True)

    # 메타데이터
    created_at = Column(DateTime, default=func.now())
    is_active = Column(Boolean, default=True)

    def __repr__(self):
        return f"<Watchlist(watchlist_id={self.watchlist_id}, ticker={self.ticker}, market={self.market})>"
