from sqlalchemy import BigInteger, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.models.youtube_pg_base import YoutubePGBase


class YoutubeVideoDetail(YoutubePGBase):
    __tablename__ = "video_details"
    __table_args__ = {"schema": "youtube"}

    detail_pk = Column(BigInteger, primary_key=True, autoincrement=True)
    video_pk = Column(
        BigInteger,
        ForeignKey("youtube.videos.video_pk", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    full_transcript = Column(Text, nullable=True)
    full_analysis_md = Column(Text, nullable=False)
    key_points = Column(JSONB, nullable=True)
    insights = Column(JSONB, nullable=True)
    entities = Column(JSONB, nullable=True)
    sentiment = Column(String, nullable=True)
    confidence_score = Column(Float, nullable=True)
    model_name = Column(String, nullable=True)
    gateway_url = Column(String, nullable=True)
    prompt_version = Column(String, nullable=True)
    token_input = Column(Integer, nullable=True)
    token_output = Column(Integer, nullable=True)
    cost_usd = Column(Float, nullable=True)
    analyzed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

