"""
User 모델
카카오 및 구글 OAuth 토큰 정보를 관리하는 테이블
"""

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    """
    사용자 테이블
    OAuth 인증 토큰 및 사용자 정보 저장
    """

    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # Kakao OAuth 토큰
    kakao_access_token = Column(String, nullable=True)
    kakao_refresh_token = Column(String, nullable=True)

    # Google OAuth 토큰
    google_access_token = Column(String, nullable=True)
    google_refresh_token = Column(String, nullable=True)
    google_token_expiry = Column(DateTime, nullable=True)

    # Telegram 연동
    telegram_chat_id = Column(String, nullable=True)

    # 메타데이터
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<User(user_id={self.user_id})>"
