from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from app.models.youtube_pg_base import YoutubePGBase


class YoutubeVideo(YoutubePGBase):
    __tablename__ = "videos"
    __table_args__ = {"schema": "youtube"}

    video_pk = Column(BigInteger, primary_key=True, autoincrement=True)
    channel_pk = Column(
        BigInteger,
        ForeignKey("youtube.channels.channel_pk", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    video_id = Column(String, nullable=False, unique=True)
    video_url = Column(String, nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    thumbnail_url = Column(String, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=False, index=True)
    duration_seconds = Column(Integer, nullable=True)
    view_count = Column(BigInteger, nullable=True)
    like_count = Column(BigInteger, nullable=True)
    sequence_in_channel = Column(Integer, nullable=True)
    analysis_status = Column(String, nullable=False, default="pending")
    analysis_error = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    notified_at = Column(DateTime(timezone=True), nullable=True)
    # 즉시 분석(추가 영상)용: 등록되지 않은 채널의 실제 채널명 보존
    source_channel_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

