"""
Log 모델
시스템 로그 및 발송 이력을 관리하는 테이블
"""

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.database import Base


class Log(Base):
    """
    로그 테이블
    알림 발송 이력 및 시스템 에러 로그 저장
    """

    __tablename__ = "logs"

    log_id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # 로그 카테고리 ('memo', 'weather', 'finance', 'calendar', 'system')
    category = Column(String, nullable=False, index=True)

    # 상태 ('SUCCESS', 'FAIL', 'WARNING', 'INFO')
    status = Column(String, nullable=False)

    # 로그 메시지
    message = Column(String, nullable=False)

    # 메타데이터
    created_at = Column(DateTime, default=func.now(), index=True)

    def __repr__(self):
        return f"<Log(id={self.log_id}, category={self.category}, status={self.status})>"
