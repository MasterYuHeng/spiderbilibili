from __future__ import annotations

from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.bootstrap import bootstrap_system_configs
from app.models.analysis import (
    AiSummary,
    SystemConfig,
    TopicCluster,
    TopicVideoRelation,
)
from app.models.enums import TaskStatus
from app.models.task import CrawlTask, TaskVideo
from app.models.video import Video, VideoTextContent
from app.services.topic_cluster_service import TopicClusterService


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    bootstrap_system_configs(session, commit=True)
    return session


def seed_task(session: Session, *, keyword: str = "AI") -> CrawlTask:
    task = CrawlTask(
        keyword=keyword,
        status=TaskStatus.RUNNING,
        requested_video_limit=20,
        max_pages=2,
        min_sleep_seconds=Decimal("0.01"),
        max_sleep_seconds=Decimal("0.01"),
        enable_proxy=False,
        source_ip_strategy="local_sleep",
    )
    session.add(task)
    session.flush()
    return task


def append_video_with_ai_summary(
    session: Session,
    *,
    task: CrawlTask,
    suffix: int,
    title: str,
    tags: list[str],
    topics: list[str],
    primary_topic: str,
    relevance_score: str = "0.9000",
    heat_score: str = "0.8000",
    confidence: str = "0.9000",
) -> Video:
    video = Video(
        bvid=f"BV1topic{suffix}",
        aid=suffix,
        title=title,
        url=f"https://www.bilibili.com/video/BV1topic{suffix}",
        tags=tags,
        duration_seconds=300 + suffix,
    )
    session.add(video)
    session.flush()

    session.add(
        TaskVideo(
            task_id=task.id,
            video_id=video.id,
            search_rank=suffix,
            keyword_hit_title=True,
            keyword_hit_description=True,
            keyword_hit_tags=True,
            relevance_score=Decimal(relevance_score),
            heat_score=Decimal(heat_score),
            composite_score=Decimal("0.8500"),
            is_selected=True,
        )
    )

    text_content = VideoTextContent(
        task_id=task.id,
        video_id=video.id,
        has_description=True,
        has_subtitle=False,
        description_text=title,
        subtitle_text=None,
        combined_text=f"Video Description:\n{title}",
        combined_text_hash=f"hash-{suffix}",
        language_code="zh-CN",
    )
    session.add(text_content)
    session.flush()

    session.add(
        AiSummary(
            task_id=task.id,
            video_id=video.id,
            text_content_id=text_content.id,
            summary=f"{title} summary",
            topics=topics,
            primary_topic=primary_topic,
            confidence=Decimal(confidence),
            model_name="gpt-test",
        )
    )
    session.commit()
    return video


def test_topic_cluster_service_merges_aliases_and_persists_relations() -> None:
    with build_session() as session:
        clustering_config = session.scalar(
            select(SystemConfig).where(
                SystemConfig.config_key == "analysis.topic_clustering"
            )
        )
        assert clustering_config is not None
        clustering_config.config_value = {
            "max_topic_keywords": 5,
            "min_cluster_size": 2,
            "max_cluster_count": 10,
            "fallback_primary_topic": "视频主题",
            "stop_topics": [],
            "topic_aliases": {
                "ai": ["artificial intelligence", "AI"],
                "product": ["Product"],
            },
        }
        session.commit()

        task = seed_task(session)
        append_video_with_ai_summary(
            session,
            task=task,
            suffix=1,
            title="AI product case study",
            tags=["AI", "Product"],
            topics=["AI", "Product"],
            primary_topic="AI",
        )
        append_video_with_ai_summary(
            session,
            task=task,
            suffix=2,
            title="Artificial intelligence product breakdown",
            tags=["artificial intelligence", "Product"],
            topics=["artificial intelligence", "Product"],
            primary_topic="artificial intelligence",
        )

        result = TopicClusterService(session).cluster_task(task)

        stored_clusters = session.scalars(
            select(TopicCluster).where(TopicCluster.task_id == task.id)
        ).all()
        stored_relations = session.scalars(
            select(TopicVideoRelation).where(TopicVideoRelation.task_id == task.id)
        ).all()

        normalized_names = {cluster.normalized_name for cluster in stored_clusters}

        assert result.cluster_count == len(stored_clusters)
        assert result.relation_count == len(stored_relations)
        assert "ai" in normalized_names
        assert "product" in normalized_names
        assert task.clustered_topics == len(stored_clusters)
        assert any(relation.is_primary for relation in stored_relations)


def test_topic_cluster_service_redistributes_small_secondary_topics() -> None:
    with build_session() as session:
        task = seed_task(session)
        append_video_with_ai_summary(
            session,
            task=task,
            suffix=1,
            title="AI game showdown",
            tags=["AI游戏"],
            topics=["冷门方向A", "冷门方向B"],
            primary_topic="AI游戏",
        )

        result = TopicClusterService(session).cluster_task(task)

        stored_clusters = session.scalars(
            select(TopicCluster).where(TopicCluster.task_id == task.id)
        ).all()
        stored_relations = session.scalars(
            select(TopicVideoRelation).where(TopicVideoRelation.task_id == task.id)
        ).all()

        assert result.cluster_count == 1
        assert result.relation_count == len(stored_relations) == 1
        assert {cluster.normalized_name for cluster in stored_clusters} == {"ai游戏"}
        assert all(
            cluster.normalized_name != "unclassified" for cluster in stored_clusters
        )


def test_topic_cluster_service_limits_clusters_to_ten() -> None:
    with build_session() as session:
        task = seed_task(session, keyword="主题聚类")
        topic_names = [
            "Alpha",
            "Bravo",
            "Charlie",
            "Delta",
            "Echo",
            "Foxtrot",
            "Golf",
            "Hotel",
            "India",
            "Juliet",
            "Kilo",
        ]
        for index in range(1, 12):
            append_video_with_ai_summary(
                session,
                task=task,
                suffix=index,
                title=f"Topic {topic_names[index - 1]}",
                tags=[topic_names[index - 1]],
                topics=[topic_names[index - 1]],
                primary_topic=topic_names[index - 1],
                relevance_score=f"0.{90 - index:04d}",
                heat_score=f"0.{80 - index:04d}",
                confidence="0.8800",
            )

        result = TopicClusterService(session).cluster_task(task)

        stored_clusters = session.scalars(
            select(TopicCluster).where(TopicCluster.task_id == task.id)
        ).all()
        stored_relations = session.scalars(
            select(TopicVideoRelation).where(TopicVideoRelation.task_id == task.id)
        ).all()

        assert result.cluster_count == len(stored_clusters) == 10
        assert result.relation_count == len(stored_relations) == 11
        assert all(
            cluster.normalized_name != "unclassified" for cluster in stored_clusters
        )
