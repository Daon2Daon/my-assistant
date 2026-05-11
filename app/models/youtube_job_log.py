from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.models.youtube_pg_base import YoutubePGBase


class YoutubeJobLog(YoutubePGBase):
    __tablename__ = "job_logs"
    __table_args__ = {"schema": "youtube"}

    log_pk = Column(BigInteger, primary_key=True, autoincrement=True)
    job_type = Column(String, nullable=False)
    channel_pk = Column(BigInteger, nullable=True)
    video_pk = Column(BigInteger, nullable=True)
    status = Column(String, nullable=False)
    message = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

