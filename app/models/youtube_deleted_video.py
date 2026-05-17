from sqlalchemy import BigInteger, Column, DateTime, Text
from sqlalchemy.sql import func

from app.models.youtube_pg_base import YoutubePGBase


class YoutubeDeletedVideo(YoutubePGBase):
    """사용자가 삭제한 영상의 video_id 보관 테이블.

    채널 폴링 시 이 테이블에 존재하는 video_id는 재수집하지 않는다.
    """

    __tablename__ = "deleted_videos"
    __table_args__ = {"schema": "youtube"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    video_id = Column(Text, nullable=False, unique=True, index=True)
    deleted_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
