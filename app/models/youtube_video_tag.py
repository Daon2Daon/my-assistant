from sqlalchemy import BigInteger, Column, Float, ForeignKey

from app.models.youtube_pg_base import YoutubePGBase


class YoutubeVideoTag(YoutubePGBase):
    __tablename__ = "video_tags"
    __table_args__ = {"schema": "youtube"}

    video_pk = Column(
        BigInteger,
        ForeignKey("youtube.videos.video_pk", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_pk = Column(
        BigInteger,
        ForeignKey("youtube.tags.tag_pk", ondelete="CASCADE"),
        primary_key=True,
    )
    weight = Column(Float, nullable=True, default=1.0)

