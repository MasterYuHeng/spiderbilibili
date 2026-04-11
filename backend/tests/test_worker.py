from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.enums import LogLevel, TaskStatus
from app.models.task import CrawlTask, CrawlTaskLog
from app.models.video import Video
from app.worker import (
    record_task_runtime_heartbeat,
    resolve_celery_worker_concurrency,
    resolve_celery_worker_pool,
    run_crawl_task,
)


class DummyExecutionLease:
    def release(self) -> None:
        return None


class DummyTaskExecutionGate:
    def __init__(self, *args, **kwargs) -> None:
        return None

    def acquire(self, owner_id: str) -> DummyExecutionLease:
        return DummyExecutionLease()


class SaturatedTaskExecutionGate:
    def __init__(self, *args, **kwargs) -> None:
        return None

    def acquire(self, owner_id: str) -> DummyExecutionLease:
        raise RuntimeError(
            "Global task concurrency throttle is saturated. "
            "Please retry after active tasks finish."
        )


def test_worker_defaults_to_solo_pool_on_windows() -> None:
    assert resolve_celery_worker_pool("nt") == "solo"
    assert resolve_celery_worker_concurrency("solo") == 1


def test_worker_defaults_to_prefork_pool_off_windows() -> None:
    assert resolve_celery_worker_pool("posix") == "prefork"
    assert resolve_celery_worker_concurrency("prefork") is None


def test_record_task_runtime_heartbeat_refreshes_running_task() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with factory() as session:
        task = CrawlTask(
            keyword="heartbeat",
            status=TaskStatus.RUNNING,
            requested_video_limit=5,
            max_pages=2,
            min_sleep_seconds=Decimal("0.01"),
            max_sleep_seconds=Decimal("0.01"),
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            extra_params={"dispatch": {"celery_task_id": "celery-heartbeat"}},
        )
        session.add(task)
        session.flush()
        task.updated_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        session.commit()
        task_id = task.id

    updated = record_task_runtime_heartbeat(
        factory,
        task_id,
        "celery-heartbeat",
    )

    assert updated is True

    with factory() as session:
        task = session.scalar(select(CrawlTask).where(CrawlTask.id == task_id))
        assert task is not None
        refreshed_at = task.updated_at
        if refreshed_at.tzinfo is None:
            refreshed_at = refreshed_at.replace(tzinfo=timezone.utc)
        assert refreshed_at > datetime.now(timezone.utc) - timedelta(minutes=1)
        assert task.extra_params["dispatch"]["celery_task_id"] == "celery-heartbeat"
        assert task.extra_params["dispatch"]["acknowledged_by_worker"] is True
        assert task.extra_params["dispatch"]["last_worker_heartbeat_at"]


def test_worker_rolls_back_failed_pipeline_before_marking_task_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with factory() as session:
        task = CrawlTask(
            keyword="AI",
            status=TaskStatus.QUEUED,
            requested_video_limit=5,
            max_pages=2,
            min_sleep_seconds=Decimal("0.01"),
            max_sleep_seconds=Decimal("0.01"),
            enable_proxy=False,
            source_ip_strategy="local_sleep",
        )
        session.add(task)
        session.commit()
        task_id = task.id

    class ExplodingPipeline:
        def __init__(self, session):
            self.session = session

        def run_task(self, task: CrawlTask, **kwargs):
            self.session.add(Video(bvid="BVbad-worker"))
            self.session.flush()

        def close(self) -> None:
            return None

    monkeypatch.setattr("app.worker.get_session_factory", lambda: factory)
    monkeypatch.setattr("app.worker.CrawlPipelineService", ExplodingPipeline)
    monkeypatch.setattr("app.worker.TaskExecutionGate", DummyTaskExecutionGate)

    with pytest.raises(IntegrityError):
        run_crawl_task.__wrapped__(task_id)

    with factory() as session:
        task = session.scalar(select(CrawlTask).where(CrawlTask.id == task_id))
        logs = session.scalars(
            select(CrawlTaskLog).where(CrawlTaskLog.task_id == task_id)
        ).all()

        assert task is not None
        assert task.status == TaskStatus.FAILED
        assert task.error_message
        assert any(log.level == LogLevel.ERROR for log in logs)


def test_worker_runs_ai_analysis_after_crawl(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with factory() as session:
        task = CrawlTask(
            keyword="AI",
            status=TaskStatus.QUEUED,
            requested_video_limit=5,
            max_pages=2,
            min_sleep_seconds=Decimal("0.01"),
            max_sleep_seconds=Decimal("0.01"),
            enable_proxy=False,
            source_ip_strategy="local_sleep",
        )
        session.add(task)
        session.commit()
        task_id = task.id

    observed: dict[str, object] = {}

    class FakePipeline:
        def __init__(self, session):
            self.session = session

        def run_task(self, task: CrawlTask, **kwargs):
            return SimpleNamespace(
                candidate_count=1,
                selected_count=1,
                success_count=1,
                failure_count=0,
                subtitle_count=1,
            )

        def close(self) -> None:
            return None

    class FakeVideoAiService:
        def __init__(self, session):
            self.session = session

        def analyze_task(self, task: CrawlTask, **kwargs):
            observed["task_id"] = task.id
            task.analyzed_videos = 1
            return SimpleNamespace(
                total_count=1,
                success_count=1,
                failure_count=0,
                fallback_count=0,
                batch_count=1,
            )

    class FakeTopicClusterService:
        def __init__(self, session):
            self.session = session

        def cluster_task(self, task: CrawlTask, **kwargs):
            task.clustered_topics = 2
            return SimpleNamespace(
                cluster_count=2,
                relation_count=3,
                primary_cluster_count=2,
            )

    class FakeStatisticsService:
        def __init__(self, session):
            self.session = session

        def generate_and_persist(self, task: CrawlTask):
            task.extra_params = {"analysis_snapshot": {"summary": {"total_videos": 1}}}
            return SimpleNamespace(
                advanced=SimpleNamespace(hot_topics=[{"name": "AI"}]),
            )

    monkeypatch.setattr("app.worker.get_session_factory", lambda: factory)
    monkeypatch.setattr("app.worker.CrawlPipelineService", FakePipeline)
    monkeypatch.setattr("app.worker.VideoAiService", FakeVideoAiService)
    monkeypatch.setattr("app.worker.TopicClusterService", FakeTopicClusterService)
    monkeypatch.setattr("app.worker.StatisticsService", FakeStatisticsService)
    monkeypatch.setattr("app.worker.TaskExecutionGate", DummyTaskExecutionGate)

    result = run_crawl_task.__wrapped__(task_id)

    with factory() as session:
        task = session.scalar(select(CrawlTask).where(CrawlTask.id == task_id))
        logs = session.scalars(
            select(CrawlTaskLog).where(CrawlTaskLog.task_id == task_id)
        ).all()

        assert task is not None
        assert task.status == TaskStatus.SUCCESS
        assert task.analyzed_videos == 1
        assert task.clustered_topics == 2
        assert task.extra_params["analysis_snapshot"]["summary"]["total_videos"] == 1
        assert any(
            log.payload
            and log.payload.get("analyzed_videos") == 1
            and log.payload.get("clustered_topics") == 2
            for log in logs
        )

    assert observed["task_id"] == task_id
    assert result["status"] == "success"


def test_worker_marks_task_failed_when_ai_stage_fails_for_all_persisted_videos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with factory() as session:
        task = CrawlTask(
            keyword="AI",
            status=TaskStatus.QUEUED,
            requested_video_limit=5,
            max_pages=2,
            min_sleep_seconds=Decimal("0.01"),
            max_sleep_seconds=Decimal("0.01"),
            enable_proxy=False,
            source_ip_strategy="local_sleep",
        )
        session.add(task)
        session.commit()
        task_id = task.id

    class FakePipeline:
        def __init__(self, session):
            self.session = session

        def run_task(self, task: CrawlTask, **kwargs):
            return SimpleNamespace(
                candidate_count=1,
                selected_count=1,
                success_count=1,
                failure_count=0,
                subtitle_count=0,
            )

        def close(self) -> None:
            return None

    class FailingVideoAiService:
        def __init__(self, session):
            self.session = session

        def analyze_task(self, task: CrawlTask, **kwargs):
            return SimpleNamespace(
                total_count=1,
                success_count=0,
                failure_count=1,
                fallback_count=0,
                batch_count=1,
            )

    class FakeTopicClusterService:
        def __init__(self, session):
            self.session = session

        def cluster_task(self, task: CrawlTask, **kwargs):
            task.clustered_topics = 0
            return SimpleNamespace(
                cluster_count=0,
                relation_count=0,
                primary_cluster_count=0,
            )

    class FakeStatisticsService:
        def __init__(self, session):
            self.session = session

        def generate_and_persist(self, task: CrawlTask):
            return SimpleNamespace(
                advanced=SimpleNamespace(hot_topics=[]),
            )

    monkeypatch.setattr("app.worker.get_session_factory", lambda: factory)
    monkeypatch.setattr("app.worker.CrawlPipelineService", FakePipeline)
    monkeypatch.setattr("app.worker.VideoAiService", FailingVideoAiService)
    monkeypatch.setattr("app.worker.TopicClusterService", FakeTopicClusterService)
    monkeypatch.setattr("app.worker.StatisticsService", FakeStatisticsService)
    monkeypatch.setattr("app.worker.TaskExecutionGate", DummyTaskExecutionGate)

    result = run_crawl_task.__wrapped__(task_id)

    with factory() as session:
        task = session.scalar(select(CrawlTask).where(CrawlTask.id == task_id))
        logs = session.scalars(
            select(CrawlTaskLog).where(CrawlTaskLog.task_id == task_id)
        ).all()

        assert task is not None
        assert task.status == TaskStatus.FAILED
        assert task.error_message == "AI analysis failed for all persisted videos."
        assert any(
            log.payload and log.payload.get("ai_failure_count") == 1 for log in logs
        )

    assert result["status"] == "failed"


def test_worker_records_video_concurrency_and_ai_cache_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with factory() as session:
        task = CrawlTask(
            keyword="AI",
            status=TaskStatus.QUEUED,
            requested_video_limit=5,
            max_pages=2,
            min_sleep_seconds=Decimal("0.01"),
            max_sleep_seconds=Decimal("0.01"),
            enable_proxy=False,
            source_ip_strategy="local_sleep",
        )
        session.add(task)
        session.commit()
        task_id = task.id

    class FakePipeline:
        def __init__(self, session):
            self.session = session

        def run_task(self, task: CrawlTask, **kwargs):
            return SimpleNamespace(
                candidate_count=3,
                selected_count=3,
                video_concurrency=3,
                success_count=3,
                failure_count=0,
                subtitle_count=1,
            )

        def close(self) -> None:
            return None

    class FakeVideoAiService:
        def __init__(self, session):
            self.session = session

        def analyze_task(self, task: CrawlTask, **kwargs):
            task.analyzed_videos = 3
            return SimpleNamespace(
                total_count=3,
                success_count=2,
                failure_count=0,
                fallback_count=1,
                batch_count=1,
                cached_count=1,
                clipped_count=2,
            )

    class FakeTopicClusterService:
        def __init__(self, session):
            self.session = session

        def cluster_task(self, task: CrawlTask, **kwargs):
            return SimpleNamespace(cluster_count=2, relation_count=4)

    class FakeStatisticsService:
        def __init__(self, session):
            self.session = session

        def generate_and_persist(self, task: CrawlTask):
            return SimpleNamespace(
                advanced=SimpleNamespace(hot_topics=[{"name": "AI"}, {"name": "产品"}]),
            )

    monkeypatch.setattr("app.worker.get_session_factory", lambda: factory)
    monkeypatch.setattr("app.worker.CrawlPipelineService", FakePipeline)
    monkeypatch.setattr("app.worker.VideoAiService", FakeVideoAiService)
    monkeypatch.setattr("app.worker.TopicClusterService", FakeTopicClusterService)
    monkeypatch.setattr("app.worker.StatisticsService", FakeStatisticsService)
    monkeypatch.setattr("app.worker.TaskExecutionGate", DummyTaskExecutionGate)

    run_crawl_task.__wrapped__(task_id)

    with factory() as session:
        logs = session.scalars(
            select(CrawlTaskLog).where(CrawlTaskLog.task_id == task_id)
        ).all()

    assert any(
        log.payload
        and log.payload.get("video_concurrency") == 3
        and log.payload.get("ai_cached_count") == 1
        and log.payload.get("ai_clipped_count") == 2
        for log in logs
    )


def test_worker_skips_superseded_dispatch_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with factory() as session:
        task = CrawlTask(
            keyword="AI",
            status=TaskStatus.QUEUED,
            requested_video_limit=5,
            max_pages=2,
            min_sleep_seconds=Decimal("0.01"),
            max_sleep_seconds=Decimal("0.01"),
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            extra_params={"dispatch": {"dispatch_generation": 3}},
        )
        session.add(task)
        session.commit()
        task_id = task.id

    monkeypatch.setattr("app.worker.get_session_factory", lambda: factory)
    monkeypatch.setattr("app.worker.TaskExecutionGate", DummyTaskExecutionGate)

    result = run_crawl_task.__wrapped__(task_id, 2)

    with factory() as session:
        task = session.scalar(select(CrawlTask).where(CrawlTask.id == task_id))
        assert task is not None
        assert task.status == TaskStatus.QUEUED

    assert result["status"] == "superseded"


def test_worker_stops_when_task_is_paused_before_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with factory() as session:
        task = CrawlTask(
            keyword="AI",
            status=TaskStatus.PAUSED,
            requested_video_limit=5,
            max_pages=2,
            min_sleep_seconds=Decimal("0.01"),
            max_sleep_seconds=Decimal("0.01"),
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            extra_params={"dispatch": {"dispatch_generation": 1}},
        )
        session.add(task)
        session.commit()
        task_id = task.id

    monkeypatch.setattr("app.worker.get_session_factory", lambda: factory)
    monkeypatch.setattr("app.worker.TaskExecutionGate", DummyTaskExecutionGate)

    result = run_crawl_task.__wrapped__(task_id, 1)

    with factory() as session:
        task = session.scalar(select(CrawlTask).where(CrawlTask.id == task_id))
        assert task is not None
        assert task.status == TaskStatus.PAUSED

    assert result["status"] == "pause"


def test_worker_marks_task_failed_when_gate_is_saturated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with factory() as session:
        task = CrawlTask(
            keyword="AI",
            status=TaskStatus.QUEUED,
            requested_video_limit=5,
            max_pages=2,
            min_sleep_seconds=Decimal("0.01"),
            max_sleep_seconds=Decimal("0.01"),
            enable_proxy=False,
            source_ip_strategy="local_sleep",
        )
        session.add(task)
        session.commit()
        task_id = task.id

    monkeypatch.setattr("app.worker.get_session_factory", lambda: factory)
    monkeypatch.setattr("app.worker.TaskExecutionGate", SaturatedTaskExecutionGate)

    result = run_crawl_task.__wrapped__(task_id)

    with factory() as session:
        task = session.scalar(select(CrawlTask).where(CrawlTask.id == task_id))
        logs = session.scalars(
            select(CrawlTaskLog).where(CrawlTaskLog.task_id == task_id)
        ).all()

        assert task is not None
        assert task.status == TaskStatus.FAILED
        assert task.error_message == (
            "Global task concurrency throttle is saturated. "
            "Please retry after active tasks finish."
        )
        assert any(
            log.level == LogLevel.ERROR
            and "no global task slot was available" in log.message.lower()
            for log in logs
        )

    assert result["status"] == "failed"
