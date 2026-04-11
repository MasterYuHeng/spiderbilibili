from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
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

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.task import CrawlTask
    from app.models.video import Video, VideoTextContent


class AiSummary(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_summary"
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
    text_content_id: Mapped[str] = mapped_column(
        ForeignKey("video_text_content.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    topics: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    primary_topic: Mapped[str | None] = mapped_column(String(255))
    tone: Mapped[str | None] = mapped_column(String(64))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    model_name: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(
        String(64), default="v1", nullable=False
    )
    raw_response: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    task: Mapped["CrawlTask"] = relationship(back_populates="ai_summaries")
    video: Mapped["Video"] = relationship(back_populates="ai_summaries")
    text_content: Mapped["VideoTextContent"] = relationship(
        back_populates="ai_summaries"
    )
    topic_relations: Mapped[list["TopicVideoRelation"]] = relationship(
        back_populates="ai_summary"
    )


class TopicCluster(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "topic_cluster"
    __table_args__ = (
        UniqueConstraint("task_id", "normalized_name"),
        Index("ix_topic_cluster_task_id_cluster_order", "task_id", "cluster_order"),
    )

    task_id: Mapped[str] = mapped_column(
        ForeignKey("crawl_task.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    video_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_heat_score: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), default=Decimal("0"), nullable=False
    )
    average_heat_score: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), default=Decimal("0"), nullable=False
    )
    cluster_order: Mapped[int | None] = mapped_column(Integer)

    task: Mapped["CrawlTask"] = relationship(back_populates="topic_clusters")
    video_relations: Mapped[list["TopicVideoRelation"]] = relationship(
        back_populates="topic_cluster",
        cascade="all, delete-orphan",
    )


class TopicVideoRelation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "topic_video_relation"
    __table_args__ = (
        UniqueConstraint("task_id", "topic_cluster_id", "video_id"),
        Index("ix_topic_video_relation_task_id_video_id", "task_id", "video_id"),
        Index(
            "ix_topic_video_relation_task_id_topic_cluster_id",
            "task_id",
            "topic_cluster_id",
        ),
    )

    task_id: Mapped[str] = mapped_column(
        ForeignKey("crawl_task.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    topic_cluster_id: Mapped[str] = mapped_column(
        ForeignKey("topic_cluster.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    video_id: Mapped[str] = mapped_column(
        ForeignKey("video.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ai_summary_id: Mapped[str | None] = mapped_column(
        ForeignKey("ai_summary.id", ondelete="SET NULL"),
        index=True,
    )
    relevance_score: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), default=Decimal("0"), nullable=False
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    task: Mapped["CrawlTask"] = relationship(back_populates="topic_relations")
    topic_cluster: Mapped["TopicCluster"] = relationship(
        back_populates="video_relations"
    )
    video: Mapped["Video"] = relationship(back_populates="topic_relations")
    ai_summary: Mapped["AiSummary | None"] = relationship(
        back_populates="topic_relations"
    )


class SystemConfig(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "system_config"

    config_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    config_name: Mapped[str] = mapped_column(String(255), nullable=False)
    config_group: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    config_value: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
