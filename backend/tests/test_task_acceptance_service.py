from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.analysis import AiSummary, TopicCluster, TopicVideoRelation
from app.models.enums import TaskStage, TaskStatus
from app.models.task import CrawlTask, TaskVideo
from app.models.video import Video, VideoMetricSnapshot, VideoTextContent
from app.services.task_acceptance_service import TaskAcceptanceService
from app.services.task_log_service import create_task_log


def build_session_factory():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def test_task_acceptance_service_builds_pass_report() -> None:
    factory = build_session_factory()

    with factory() as session:
        task = CrawlTask(
            keyword="AI",
            status=TaskStatus.PARTIAL_SUCCESS,
            requested_video_limit=10,
            max_pages=3,
            min_sleep_seconds=Decimal("1.00"),
            max_sleep_seconds=Decimal("2.00"),
            enable_proxy=False,
            source_ip_strategy="local_sleep",
        )
        session.add(task)
        session.flush()

        video = Video(
            bvid="BV1accept",
            aid=1001,
            title="Acceptance sample",
            url="https://www.bilibili.com/video/BV1accept",
            author_name="QA UP",
            description="Acceptance dataset",
            published_at=datetime(2026, 4, 7, tzinfo=timezone.utc),
            duration_seconds=120,
        )
        session.add(video)
        session.flush()

        session.add(
            TaskVideo(
                task_id=task.id,
                video_id=video.id,
                search_rank=1,
                keyword_hit_title=True,
                keyword_hit_description=True,
                keyword_hit_tags=False,
                relevance_score=Decimal("0.90"),
                heat_score=Decimal("0.80"),
                composite_score=Decimal("0.85"),
                is_selected=True,
            )
        )
        session.add(
            VideoMetricSnapshot(
                task_id=task.id,
                video_id=video.id,
                view_count=100,
                like_count=10,
                coin_count=2,
                favorite_count=3,
                share_count=1,
                reply_count=1,
                danmaku_count=1,
                metrics_payload={"source": "test"},
            )
        )
        text_content = VideoTextContent(
            task_id=task.id,
            video_id=video.id,
            has_description=True,
            has_subtitle=True,
            description_text="Acceptance dataset",
            subtitle_text="Subtitle",
            combined_text="Acceptance dataset\nSubtitle",
            combined_text_hash="hash-accept",
            language_code="zh-CN",
        )
        session.add(text_content)
        session.flush()

        ai_summary = AiSummary(
            task_id=task.id,
            video_id=video.id,
            text_content_id=text_content.id,
            summary="Acceptance summary",
            topics=["AI"],
            primary_topic="AI",
            confidence=Decimal("0.95"),
            model_name="gpt-test",
            raw_response={"ok": True},
        )
        session.add(ai_summary)
        session.flush()

        topic = TopicCluster(
            task_id=task.id,
            name="AI",
            normalized_name="ai",
            description="Readable description",
            keywords=["AI"],
            video_count=1,
            total_heat_score=Decimal("0.80"),
            average_heat_score=Decimal("0.80"),
            cluster_order=1,
        )
        session.add(topic)
        session.flush()
        session.add(
            TopicVideoRelation(
                task_id=task.id,
                topic_cluster_id=topic.id,
                video_id=video.id,
                ai_summary_id=ai_summary.id,
                relevance_score=Decimal("0.90"),
                is_primary=True,
            )
        )
        create_task_log(
            session,
            task=task,
            stage=TaskStage.TOPIC,
            message="Acceptance task completed.",
        )
        session.commit()
        task_id = task.id

    with factory() as session:
        report = TaskAcceptanceService(session).build_report(task_id).to_dict()

    assert report["overall_status"] == "pass"
    assert report["sections"]["functional"][1]["status"] == "pass"
    assert report["sections"]["data"][-1]["status"] == "pass"
    assert report["sections"]["compliance"][0]["status"] == "pass"


def test_task_acceptance_service_warns_when_task_has_no_data() -> None:
    factory = build_session_factory()

    with factory() as session:
        task = CrawlTask(
            keyword="empty",
            status=TaskStatus.RUNNING,
            requested_video_limit=10,
            max_pages=3,
            min_sleep_seconds=Decimal("1.00"),
            max_sleep_seconds=Decimal("2.00"),
            enable_proxy=False,
            source_ip_strategy="local_sleep",
        )
        session.add(task)
        session.flush()
        create_task_log(
            session,
            task=task,
            stage=TaskStage.TASK,
            message="Task queued for processing.",
        )
        session.commit()
        task_id = task.id

    with factory() as session:
        report = TaskAcceptanceService(session).build_report(task_id).to_dict()

    assert report["overall_status"] == "warn"
    assert report["sections"]["data"][0]["code"] == "data-unavailable"


def test_task_acceptance_service_handles_invalid_scores_without_crashing() -> None:
    factory = build_session_factory()

    with factory() as session:
        task = CrawlTask(
            keyword="invalid-scores",
            status=TaskStatus.SUCCESS,
            requested_video_limit=10,
            max_pages=3,
            min_sleep_seconds=Decimal("1.00"),
            max_sleep_seconds=Decimal("2.00"),
            enable_proxy=False,
            source_ip_strategy="local_sleep",
        )
        session.add(task)
        session.flush()

        video = Video(
            bvid="BV1noscore",
            aid=1002,
            title="Invalid score sample",
            url="https://www.bilibili.com/video/BV1noscore",
            author_name="QA UP",
            description="Invalid score dataset",
            published_at=datetime(2026, 4, 8, tzinfo=timezone.utc),
            duration_seconds=120,
        )
        session.add(video)
        session.flush()

        session.add(
            TaskVideo(
                task_id=task.id,
                video_id=video.id,
                search_rank=1,
                keyword_hit_title=True,
                keyword_hit_description=True,
                keyword_hit_tags=False,
                relevance_score=Decimal("0.90"),
                heat_score=Decimal("-0.10"),
                composite_score=Decimal("-0.20"),
                is_selected=True,
            )
        )
        create_task_log(
            session,
            task=task,
            stage=TaskStage.TOPIC,
            message="Acceptance task completed with invalid scores.",
        )
        session.commit()
        task_id = task.id

    with factory() as session:
        report = TaskAcceptanceService(session).build_report(task_id).to_dict()

    heat_score_check = next(
        check
        for check in report["sections"]["data"]
        if check["code"] == "heat-score-validity"
    )
    assert report["overall_status"] == "fail"
    assert heat_score_check["status"] == "fail"
    assert heat_score_check["actual"]["mean_heat_score"] == -0.1
    assert heat_score_check["actual"]["mean_composite_score"] == -0.2
