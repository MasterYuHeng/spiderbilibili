from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import (
    Base,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    utc_now,
)

if TYPE_CHECKING:
    from app.models.analysis import AiSummary, TopicVideoRelation
    from app.models.task import CrawlTask, TaskVideo


class Video(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "video"

    bvid: Mapped[str] = mapped_column(
        String(32), unique=True, index=True, nullable=False
    )
    aid: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    author_name: Mapped[str | None] = mapped_column(String(255))
    author_mid: Mapped[str | None] = mapped_column(String(64))
    cover_url: Mapped[str | None] = mapped_column(String(1024))
    description: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str] | None] = mapped_column(JSON)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)

    task_links: Mapped[list["TaskVideo"]] = relationship(back_populates="video")
    metric_snapshots: Mapped[list["VideoMetricSnapshot"]] = relationship(
        back_populates="video",
        cascade="all, delete-orphan",
    )
    text_contents: Mapped[list["VideoTextContent"]] = relationship(
        back_populates="video",
        cascade="all, delete-orphan",
    )
    ai_summaries: Mapped[list["AiSummary"]] = relationship(
        back_populates="video",
        cascade="all, delete-orphan",
    )
    topic_relations: Mapped[list["TopicVideoRelation"]] = relationship(
        back_populates="video",
        cascade="all, delete-orphan",
    )


class VideoMetricSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "video_metric_snapshot"
    __table_args__ = (
        Index(
            "ix_video_metric_snapshot_task_video_captured_created",
            "task_id",
            "video_id",
            "captured_at",
            "created_at",
        ),
    )

    task_id: Mapped[str] = mapped_column(
        ForeignKey("crawl_task.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    video_id: Mapped[str] = mapped_column(
        ForeignKey("video.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    view_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    like_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    coin_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    favorite_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    share_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    reply_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    danmaku_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    metrics_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    task: Mapped["CrawlTask"] = relationship(back_populates="metric_snapshots")
    video: Mapped["Video"] = relationship(back_populates="metric_snapshots")


class VideoTextContent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "video_text_content"
    __table_args__ = (UniqueConstraint("task_id", "video_id"),)

    task_id: Mapped[str] = mapped_column(
        ForeignKey("crawl_task.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    video_id: Mapped[str] = mapped_column(
        ForeignKey("video.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    has_description: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    has_subtitle: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    description_text: Mapped[str | None] = mapped_column(Text)
    subtitle_text: Mapped[str | None] = mapped_column(Text)
    combined_text: Mapped[str] = mapped_column(Text, nullable=False)
    combined_text_hash: Mapped[str | None] = mapped_column(String(64))
    language_code: Mapped[str] = mapped_column(
        String(16), default="zh-CN", nullable=False
    )

    task: Mapped["CrawlTask"] = relationship(back_populates="text_contents")
    video: Mapped["Video"] = relationship(back_populates="text_contents")
    subtitle_segments: Mapped[list["VideoSubtitleSegment"]] = relationship(
        back_populates="text_content",
        cascade="all, delete-orphan",
    )
    ai_summaries: Mapped[list["AiSummary"]] = relationship(
        back_populates="text_content",
        cascade="all, delete-orphan",
    )


class VideoSubtitleSegment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "video_subtitle_segment"
    __table_args__ = (UniqueConstraint("text_content_id", "segment_index"),)

    text_content_id: Mapped[str] = mapped_column(
        ForeignKey("video_text_content.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_seconds: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    end_seconds: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    content: Mapped[str] = mapped_column(Text, nullable=False)

    text_content: Mapped["VideoTextContent"] = relationship(
        back_populates="subtitle_segments"
    )
