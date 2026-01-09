"""
Setting 모델
정기 알림(날씨, 금융, 캘린더) 설정을 관리하는 테이블
"""

from sqlalchemy import Column, Integer, String, ForeignKey, Boolean
from app.database import Base


class Setting(Base):
    """
    설정 테이블
    각 알림 모듈의 설정 정보 저장
    """

    __tablename__ = "settings"

    setting_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)

    # 알림 카테고리 ('weather', 'finance', 'calendar')
    category = Column(String, nullable=False)

    # 알림 시간 (예: '06:30', '17:00')
    notification_time = Column(String, nullable=False)

    # 추가 설정 (JSON 문자열, 예: {"location":"Seoul"})
    config_json = Column(String, nullable=True)

    # 활성화 여부 (0: 비활성, 1: 활성)
    is_active = Column(Boolean, default=True)

    def __repr__(self):
        return f"<Setting(id={self.setting_id}, category={self.category}, active={self.is_active})>"
