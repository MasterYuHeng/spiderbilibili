from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
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

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import LogLevel, TaskStage, TaskStatus, enum_values

if TYPE_CHECKING:
    from app.models.analysis import AiSummary, TopicCluster, TopicVideoRelation
    from app.models.video import Video, VideoMetricSnapshot, VideoTextContent


class CrawlTask(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "crawl_task"

    keyword: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, native_enum=False, values_callable=enum_values),
        default=TaskStatus.PENDING,
        nullable=False,
        index=True,
    )
    requested_video_limit: Mapped[int] = mapped_column(
        Integer, default=100, nullable=False
    )
    max_pages: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    min_sleep_seconds: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("1.50"), nullable=False
    )
    max_sleep_seconds: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("5.00"), nullable=False
    )
    enable_proxy: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_ip_strategy: Mapped[str] = mapped_column(
        String(50), default="local_sleep", nullable=False
    )
    total_candidates: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_videos: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    analyzed_videos: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    clustered_topics: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    extra_params: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    logs: Mapped[list["CrawlTaskLog"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
    )
    task_videos: Mapped[list["TaskVideo"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
    )
    metric_snapshots: Mapped[list["VideoMetricSnapshot"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
    )
    text_contents: Mapped[list["VideoTextContent"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
    )
    ai_summaries: Mapped[list["AiSummary"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
    )
    topic_clusters: Mapped[list["TopicCluster"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
    )
    topic_relations: Mapped[list["TopicVideoRelation"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
    )


class CrawlTaskLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "crawl_task_log"
    __table_args__ = (
        Index("ix_crawl_task_log_task_id_created_at", "task_id", "created_at"),
    )

    task_id: Mapped[str] = mapped_column(
        ForeignKey("crawl_task.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    level: Mapped[LogLevel] = mapped_column(
        Enum(LogLevel, native_enum=False, values_callable=enum_values),
        default=LogLevel.INFO,
        nullable=False,
    )
    stage: Mapped[TaskStage] = mapped_column(
        Enum(TaskStage, native_enum=False, values_callable=enum_values),
        default=TaskStage.TASK,
        nullable=False,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    task: Mapped["CrawlTask"] = relationship(back_populates="logs")


class TaskVideo(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "task_video"
    __table_args__ = (
        UniqueConstraint("task_id", "video_id"),
        Index(
            "ix_task_video_task_id_composite_score_search_rank",
            "task_id",
            "composite_score",
            "search_rank",
        ),
        Index("ix_task_video_task_id_heat_score", "task_id", "heat_score"),
        Index(
            "ix_task_video_primary_matched_keyword",
            "primary_matched_keyword",
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
    search_rank: Mapped[int | None] = mapped_column(Integer)
    matched_keywords: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    primary_matched_keyword: Mapped[str | None] = mapped_column(String(255))
    keyword_match_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    keyword_hit_title: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    keyword_hit_description: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    keyword_hit_tags: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    relevance_score: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), default=Decimal("0"), nullable=False
    )
    heat_score: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), default=Decimal("0"), nullable=False
    )
    composite_score: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), default=Decimal("0"), nullable=False
    )
    is_selected: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    task: Mapped["CrawlTask"] = relationship(back_populates="task_videos")
    video: Mapped["Video"] = relationship(back_populates="task_links")
