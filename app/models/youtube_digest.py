from sqlalchemy import BigInteger, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.models.youtube_pg_base import YoutubePGBase


class YoutubeDigest(YoutubePGBase):
    """주간 리뷰(Weekly Review) 결과 테이블.

    일정 기간(period_weeks 주) 동안 분석 완료된 영상을 카테고리별로 묶어
    합성한 리뷰를 카테고리별 1행으로 저장한다.
    category 가 NULL/빈값이면 '미분류' 그룹을 의미하며, 향후 정식 모니터링
    그룹 도입 시 group_pk 로 승격할 수 있다.
    """

    __tablename__ = "digests"
    __table_args__ = {"schema": "youtube"}

    digest_pk = Column(BigInteger, primary_key=True, autoincrement=True)

    # 기간
    period_type = Column(String, nullable=False, default="weekly")
    period_weeks = Column(Integer, nullable=False, default=1)
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False, index=True)

    # 분류
    category = Column(String, nullable=True)
    video_count = Column(Integer, nullable=False, default=0)

    # 리뷰 본문
    headline = Column(Text, nullable=True)
    summary_md = Column(Text, nullable=True)          # 웹 표시용
    telegram_summary = Column(Text, nullable=True)    # 텔레그램 요약

    # 집계 결과
    sentiment_breakdown = Column(JSONB, nullable=True)
    top_tags = Column(JSONB, nullable=True)
    top_channels = Column(JSONB, nullable=True)

    # 모델/비용 메타
    model_name = Column(String, nullable=True)
    token_input = Column(Integer, nullable=True)
    token_output = Column(Integer, nullable=True)
    cost_usd = Column(Float, nullable=True)

    # 상태
    status = Column(String, nullable=False, default="pending")  # pending|done|failed
    error = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
