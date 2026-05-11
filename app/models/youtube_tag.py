from sqlalchemy import BigInteger, Column, DateTime, String
from sqlalchemy.sql import func

from app.models.youtube_pg_base import YoutubePGBase


class YoutubeTag(YoutubePGBase):
    __tablename__ = "tags"
    __table_args__ = {"schema": "youtube"}

    tag_pk = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    tag_type = Column(String, nullable=False, default="topic")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

