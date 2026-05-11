from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.models.youtube_pg_base import YoutubePGBase


class YoutubeVideoSummary(YoutubePGBase):
    __tablename__ = "video_summaries"
    __table_args__ = {"schema": "youtube"}

    summary_pk = Column(BigInteger, primary_key=True, autoincrement=True)
    video_pk = Column(
        BigInteger,
        ForeignKey("youtube.videos.video_pk", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    one_line = Column(Text, nullable=False)
    short_summary_md = Column(Text, nullable=False)
    headline = Column(String, nullable=True)
    bullet_points = Column(JSONB, nullable=True)
    cta_text = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

