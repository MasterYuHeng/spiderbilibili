from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.bootstrap import bootstrap_system_configs
from app.models.analysis import AiSummary
from app.models.enums import TaskStatus
from app.models.task import CrawlTask, TaskVideo
from app.schemas.task import (
    TaskAnalysisPopularAuthorRead,
    TaskAnalysisTopicHotAuthorRead,
)
from app.services.popular_author_service import PopularAuthorAnalysisResult
from app.models.video import Video, VideoMetricSnapshot, VideoTextContent
from app.services.statistics_service import StatisticsService
from app.services.topic_cluster_service import TopicClusterService


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    bootstrap_system_configs(session, commit=True)
    return session


def seed_statistics_task(session: Session) -> CrawlTask:
    task = CrawlTask(
        keyword="AI",
        status=TaskStatus.RUNNING,
        requested_video_limit=10,
        max_pages=2,
        min_sleep_seconds=Decimal("0.01"),
        max_sleep_seconds=Decimal("0.01"),
        enable_proxy=False,
        source_ip_strategy="local_sleep",
    )
    session.add(task)
    session.flush()

    videos = [
        Video(
            bvid="BV1stat1",
            aid=1,
            title="AI 工具评测",
            url="https://www.bilibili.com/video/BV1stat1",
            tags=["AI", "工具"],
            published_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            duration_seconds=180,
        ),
        Video(
            bvid="BV1stat2",
            aid=2,
            title="AI 机器人拆解",
            url="https://www.bilibili.com/video/BV1stat2",
            tags=["AI", "机器人"],
            published_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
            duration_seconds=480,
        ),
    ]
    session.add_all(videos)
    session.flush()

    session.add_all(
        [
            TaskVideo(
                task_id=task.id,
                video_id=videos[0].id,
                search_rank=1,
                keyword_hit_title=True,
                keyword_hit_description=True,
                keyword_hit_tags=True,
                relevance_score=Decimal("0.9000"),
                heat_score=Decimal("0.6000"),
                composite_score=Decimal("0.7800"),
                is_selected=True,
            ),
            TaskVideo(
                task_id=task.id,
                video_id=videos[1].id,
                search_rank=2,
                keyword_hit_title=True,
                keyword_hit_description=True,
                keyword_hit_tags=True,
                relevance_score=Decimal("0.8500"),
                heat_score=Decimal("0.9000"),
                composite_score=Decimal("0.8700"),
                is_selected=True,
            ),
        ]
    )

    text_rows = [
        VideoTextContent(
            task_id=task.id,
            video_id=videos[0].id,
            has_description=True,
            has_subtitle=False,
            description_text="AI 工具评测",
            subtitle_text=None,
            combined_text="Video Description:\nAI 工具评测",
            combined_text_hash="stat1",
            language_code="zh-CN",
        ),
        VideoTextContent(
            task_id=task.id,
            video_id=videos[1].id,
            has_description=True,
            has_subtitle=False,
            description_text="AI 机器人拆解",
            subtitle_text=None,
            combined_text="Video Description:\nAI 机器人拆解",
            combined_text_hash="stat2",
            language_code="zh-CN",
        ),
    ]
    session.add_all(text_rows)
    session.flush()

    session.add_all(
        [
            AiSummary(
                task_id=task.id,
                video_id=videos[0].id,
                text_content_id=text_rows[0].id,
                summary="视频介绍 AI 工具选择和体验。",
                topics=["AI", "工具"],
                primary_topic="AI",
                confidence=Decimal("0.90"),
                model_name="gpt-test",
            ),
            AiSummary(
                task_id=task.id,
                video_id=videos[1].id,
                text_content_id=text_rows[1].id,
                summary="视频讲解 AI 机器人方案和应用。",
                topics=["AI", "机器人"],
                primary_topic="AI",
                confidence=Decimal("0.88"),
                model_name="gpt-test",
            ),
        ]
    )

    session.add_all(
        [
            VideoMetricSnapshot(
                task_id=task.id,
                video_id=videos[0].id,
                view_count=820,
                like_count=96,
                coin_count=18,
                favorite_count=32,
                share_count=8,
                reply_count=6,
                danmaku_count=4,
                metrics_payload={"source": "history"},
                captured_at=datetime(2026, 4, 4, tzinfo=timezone.utc),
            ),
            VideoMetricSnapshot(
                task_id=task.id,
                video_id=videos[0].id,
                view_count=1000,
                like_count=120,
                coin_count=30,
                favorite_count=50,
                share_count=10,
                reply_count=8,
                danmaku_count=5,
                metrics_payload={
                    "search_metrics": {
                        "play_count": 700,
                        "like_count": 90,
                        "favorite_count": 28,
                        "comment_count": 6,
                        "danmaku_count": 3,
                    }
                },
                captured_at=datetime(2026, 4, 5, tzinfo=timezone.utc),
            ),
            VideoMetricSnapshot(
                task_id=task.id,
                video_id=videos[1].id,
                view_count=2000,
                like_count=200,
                coin_count=40,
                favorite_count=70,
                share_count=15,
                reply_count=10,
                danmaku_count=8,
                metrics_payload={},
                captured_at=datetime(2026, 4, 6, tzinfo=timezone.utc),
            ),
        ]
    )
    session.commit()
    return task


def test_statistics_service_returns_basic_and_advanced_metrics() -> None:
    with build_session() as session:
        task = seed_statistics_task(session)
        TopicClusterService(session).cluster_task(task)

        result = StatisticsService(session).calculate_task_statistics(task.id)

        assert result.summary.total_videos == 2
        assert result.summary.average_view_count == 1500.0
        assert result.topics
        assert result.topics[0].video_ratio is not None
        assert result.advanced.hot_topics
        assert result.advanced.keyword_cooccurrence
        assert result.advanced.publish_date_distribution[0].bucket == "2026-04-01"
        assert result.advanced.duration_heat_correlation.metric == (
            "duration_seconds_vs_heat_score"
        )
        assert result.advanced.momentum_topics
        assert result.advanced.depth_topics
        assert result.advanced.community_topics
        assert result.advanced.explosive_videos
        assert result.advanced.explosive_videos[0].history
        assert (
            result.advanced.explosive_videos[0].search_to_current_view_growth_ratio
            is not None
        )
        assert result.advanced.latest_hot_topic.topic is not None
        assert result.advanced.topic_insights
        assert result.advanced.video_insights
        assert result.advanced.metric_definitions
        assert result.advanced.metric_definitions[0].formula
        assert result.advanced.recommendations
        assert result.advanced.data_notes


def test_statistics_service_persists_analysis_snapshot_metadata() -> None:
    with build_session() as session:
        task = seed_statistics_task(session)
        TopicClusterService(session).cluster_task(task)

        StatisticsService(session).generate_and_persist(task)
        session.refresh(task)

        snapshot = task.extra_params["analysis_snapshot"]
        assert snapshot["generated_at"]
        assert snapshot["has_ai_summaries"] is True
        assert len(snapshot["top_videos"]) == 2
        assert snapshot["top_videos"][0]["bvid"] == "BV1stat2"
        assert snapshot["advanced"]["momentum_topics"]
        assert snapshot["advanced"]["topic_insights"]
        assert snapshot["advanced"]["video_insights"]
        assert snapshot["advanced"]["metric_definitions"]
        assert snapshot["advanced"]["recommendations"]


def test_statistics_service_includes_popular_author_analysis() -> None:
    class FakePopularAuthorService:
        def build_for_task(
            self,
            task,
            *,
            video_insights,
            topic_insights,
            fetch_author_videos=True,
        ):
            assert video_insights
            assert topic_insights
            assert fetch_author_videos is True
            return PopularAuthorAnalysisResult(
                popular_authors=[
                    TaskAnalysisPopularAuthorRead(
                        author_name="测试 UP",
                        author_mid="1001",
                        source_video_count=2,
                        source_topic_count=1,
                        source_total_heat_score=1.5,
                        source_total_composite_score=1.65,
                        source_average_engagement_rate=0.12,
                        source_average_view_count=1500,
                        popularity_score=0.91,
                        dominant_topics=["AI"],
                        style_tags=["AI持续输出"],
                        selection_reasons=["overall_hot"],
                        summary_basis="time",
                        summary_text="测试 UP 在热点视频里持续出现。",
                        analysis_points=["热点样本集中度高。"],
                    )
                ],
                topic_hot_authors=[
                    TaskAnalysisTopicHotAuthorRead(
                        topic_id="topic-ai",
                        topic_name="AI",
                        authors=[
                            TaskAnalysisPopularAuthorRead(
                                author_name="测试 UP",
                                author_mid="1001",
                                source_video_count=2,
                                source_topic_count=1,
                                source_total_heat_score=1.5,
                                source_total_composite_score=1.65,
                                source_average_engagement_rate=0.12,
                                source_average_view_count=1500,
                                popularity_score=0.91,
                                dominant_topics=["AI"],
                                style_tags=[],
                                selection_reasons=["topic:AI"],
                                summary_basis="time",
                            )
                        ],
                    )
                ],
                author_analysis_notes=["热门 up 主来自热点视频样本汇总。"],
            )

        def close(self) -> None:
            return None

    with build_session() as session:
        task = seed_statistics_task(session)
        task.extra_params = {
            "task_options": {
                "hot_author_total_count": 3,
                "topic_hot_author_count": 1,
                "hot_author_video_limit": 5,
                "hot_author_summary_basis": "time",
            }
        }
        session.commit()
        TopicClusterService(session).cluster_task(task)

        result = StatisticsService(
            session,
            popular_author_service=FakePopularAuthorService(),
        ).calculate_task_statistics(task.id)

        assert result.advanced.popular_authors
        assert result.advanced.popular_authors[0].author_name == "测试 UP"
        assert result.advanced.topic_hot_authors
        assert result.advanced.author_analysis_notes


def test_statistics_service_applies_custom_metric_weights() -> None:
    with build_session() as session:
        task = seed_statistics_task(session)
        task.extra_params = {
            "analysis_metric_weights": {
                "updated_at": "2026-04-14T12:00:00Z",
                "metrics": {
                    "burst_score": {
                        "search_growth": 0.9,
                        "publish_velocity": 0.1,
                        "history_velocity": 0.0,
                    }
                },
            }
        }
        session.commit()
        TopicClusterService(session).cluster_task(task)

        customized_result = StatisticsService(session).calculate_task_statistics(task.id)

    burst_config = next(
        item
        for item in customized_result.advanced.metric_weight_configs
        if item.metric_key == "burst_score"
    )
    assert burst_config.customized is True
    assert burst_config.formula.startswith("0.90 *")
    assert burst_config.components[0].weight == 0.9
    assert any("自定义指标权重" in note for note in customized_result.advanced.data_notes)

    with build_session() as session:
        task = seed_statistics_task(session)
        TopicClusterService(session).cluster_task(task)
        default_result = StatisticsService(session).calculate_task_statistics(task.id)

    default_by_bvid = {
        item.bvid: item.burst_score for item in default_result.advanced.video_insights
    }
    customized_by_bvid = {
        item.bvid: item.burst_score
        for item in customized_result.advanced.video_insights
    }
    assert customized_by_bvid
    assert customized_by_bvid != default_by_bvid


def test_statistics_service_limits_history_snapshots_to_current_task() -> None:
    with build_session() as session:
        task = seed_statistics_task(session)
        topic_service = TopicClusterService(session)
        topic_service.cluster_task(task)

        shared_video = session.query(Video).filter_by(bvid="BV1stat1").one()
        other_task = CrawlTask(
            keyword="AI-other",
            status=TaskStatus.SUCCESS,
            requested_video_limit=10,
            max_pages=2,
            min_sleep_seconds=Decimal("0.01"),
            max_sleep_seconds=Decimal("0.01"),
            enable_proxy=False,
            source_ip_strategy="local_sleep",
        )
        session.add(other_task)
        session.flush()
        session.add(
            VideoMetricSnapshot(
                task_id=other_task.id,
                video_id=shared_video.id,
                view_count=99999,
                like_count=1,
                coin_count=1,
                favorite_count=1,
                share_count=1,
                reply_count=1,
                danmaku_count=1,
                metrics_payload={"source": "other-task"},
                captured_at=datetime(2026, 4, 8, tzinfo=timezone.utc),
            )
        )
        session.commit()

        result = StatisticsService(session).calculate_task_statistics(task.id)

        explosive_video = next(
            item for item in result.advanced.video_insights if item.bvid == "BV1stat1"
        )
        assert explosive_video.historical_snapshot_count == 2
        assert [point.view_count for point in explosive_video.history if point.label == "snapshot"] == [
            820,
            1000,
        ]
