from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.enums import TaskStage, TaskStatus
from app.models.task import CrawlTask
from app.services.task_log_service import create_task_log
from app.services.task_service import (
    TaskDispatchResult,
    _build_celery_runtime_state_resolver,
    calculate_task_progress,
    delete_crawl_task,
    get_task_progress,
    restore_crawl_task,
    resume_crawl_task,
    retry_crawl_task,
)
from app.worker import record_task_runtime_heartbeat


def _build_analysis_snapshot() -> dict:
    return {
        "generated_at": "2026-04-11T00:00:00+00:00",
        "summary": {},
        "topics": [],
        "top_videos": [],
        "advanced": {
            "topic_insights": [],
            "video_insights": [],
            "recommendations": [],
            "popular_authors": [],
            "topic_hot_authors": [],
            "author_analysis_notes": [],
            "data_notes": [],
            "metric_definitions": [],
        },
    }


def _build_report_snapshot() -> dict:
    return {
        "generated_at": "2026-04-11T00:00:00+00:00",
        "sections": [],
        "ai_outputs": [{"key": "melon_reader", "content": "ok"}],
        "featured_videos": [],
        "popular_authors": [],
        "topic_hot_authors": [],
        "report_markdown": "# report",
    }


def test_retry_crawl_task_creates_a_new_queued_task(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with factory() as session:
        source_task = CrawlTask(
            keyword="AI",
            status=TaskStatus.FAILED,
            requested_video_limit=10,
            max_pages=2,
            min_sleep_seconds=Decimal("1.50"),
            max_sleep_seconds=Decimal("3.00"),
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            extra_params={
                "task_options": {
                    "published_within_days": 7,
                    "requested_video_limit": 10,
                    "max_pages": 2,
                    "enable_proxy": False,
                    "source_ip_strategy": "local_sleep",
                    "enable_keyword_synonym_expansion": True,
                    "keyword_synonym_count": 3,
                },
                "keyword_expansion": {
                    "source_keyword": "AI",
                    "enabled": True,
                    "requested_synonym_count": 3,
                    "generated_synonyms": ["人工智能", "AI工具", "大模型"],
                    "expanded_keywords": ["AI", "人工智能", "AI工具", "大模型"],
                    "status": "success",
                    "model_name": "gpt-4.1-mini",
                    "error_message": None,
                    "generated_at": "2026-04-13T10:00:00Z",
                },
            },
        )
        session.add(source_task)
        session.commit()
        source_task_id = source_task.id

    monkeypatch.setattr(
        "app.services.task_service.enqueue_crawl_task",
        lambda task_id, dispatch_generation=None: TaskDispatchResult(
            celery_task_id=f"celery-{task_id}",
            task_name="app.worker.run_crawl_task",
        ),
    )

    with factory() as session:
        detail, dispatch = retry_crawl_task(session, source_task_id)

    with factory() as session:
        tasks = session.scalars(
            select(CrawlTask).order_by(CrawlTask.created_at.asc())
        ).all()

    assert len(tasks) == 2
    assert detail.id != source_task_id
    assert detail.status == "queued"
    assert detail.extra_params["retry_context"]["retry_of_task_id"] == source_task_id
    assert detail.extra_params["task_options"]["published_within_days"] == 7
    assert (
        detail.extra_params["task_options"]["enable_keyword_synonym_expansion"] is True
    )
    assert detail.extra_params["task_options"]["keyword_synonym_count"] == 3
    assert detail.extra_params["keyword_expansion"]["status"] == "success"
    assert detail.extra_params["keyword_expansion"]["generated_synonyms"] == [
        "人工智能",
        "AI工具",
        "大模型",
    ]
    assert detail.extra_params["keyword_expansion"]["expanded_keywords"] == [
        "AI",
        "人工智能",
        "AI工具",
        "大模型",
    ]
    assert (
        detail.extra_params["keyword_expansion"]["generated_at"]
        == "2026-04-13T10:00:00Z"
    )
    assert dispatch.celery_task_id == f"celery-{detail.id}"


def test_retry_crawl_task_resets_unsuccessful_keyword_expansion_to_pending(
    monkeypatch,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with factory() as session:
        source_task = CrawlTask(
            keyword="和平精英",
            status=TaskStatus.FAILED,
            requested_video_limit=10,
            max_pages=2,
            min_sleep_seconds=Decimal("1.50"),
            max_sleep_seconds=Decimal("3.00"),
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            extra_params={
                "task_options": {
                    "crawl_mode": "keyword",
                    "search_scope": "site",
                    "requested_video_limit": 10,
                    "max_pages": 2,
                    "enable_proxy": False,
                    "source_ip_strategy": "local_sleep",
                    "enable_keyword_synonym_expansion": True,
                    "keyword_synonym_count": 2,
                },
                "keyword_expansion": {
                    "source_keyword": "和平精英",
                    "enabled": True,
                    "requested_synonym_count": 2,
                    "generated_synonyms": [],
                    "expanded_keywords": ["和平精英"],
                    "status": "fallback",
                    "model_name": None,
                    "error_message": "AI returned empty synonyms.",
                    "generated_at": "2026-04-13T11:00:00Z",
                },
            },
        )
        session.add(source_task)
        session.commit()
        source_task_id = source_task.id

    monkeypatch.setattr(
        "app.services.task_service.enqueue_crawl_task",
        lambda task_id, dispatch_generation=None: TaskDispatchResult(
            celery_task_id=f"celery-{task_id}",
            task_name="app.worker.run_crawl_task",
        ),
    )

    with factory() as session:
        detail, _dispatch = retry_crawl_task(session, source_task_id)

    keyword_expansion = detail.extra_params["keyword_expansion"]
    assert keyword_expansion["status"] == "pending"
    assert keyword_expansion["generated_synonyms"] == []
    assert keyword_expansion["expanded_keywords"] == ["和平精英"]
    assert keyword_expansion["model_name"] is None
    assert keyword_expansion["error_message"] is None
    assert keyword_expansion["generated_at"] is None


def test_resume_crawl_task_preserves_keyword_expansion_payload(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with factory() as session:
        task = CrawlTask(
            keyword="和平精英",
            status=TaskStatus.PAUSED,
            requested_video_limit=10,
            max_pages=2,
            min_sleep_seconds=Decimal("1.50"),
            max_sleep_seconds=Decimal("3.00"),
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            extra_params={
                "dispatch": {"dispatch_generation": 2, "celery_task_id": "celery-old"},
                "control": {"requested_action": "pause"},
                "task_options": {
                    "crawl_mode": "keyword",
                    "search_scope": "site",
                    "requested_video_limit": 10,
                    "max_pages": 2,
                    "enable_proxy": False,
                    "source_ip_strategy": "local_sleep",
                    "enable_keyword_synonym_expansion": True,
                    "keyword_synonym_count": 2,
                },
                "keyword_expansion": {
                    "source_keyword": "和平精英",
                    "enabled": True,
                    "requested_synonym_count": 2,
                    "generated_synonyms": ["吃鸡"],
                    "expanded_keywords": ["和平精英", "吃鸡"],
                    "status": "success",
                    "model_name": "gpt-4.1-mini",
                    "error_message": None,
                    "generated_at": "2026-04-13T12:00:00Z",
                },
            },
        )
        session.add(task)
        session.commit()
        task_id = task.id

    monkeypatch.setattr(
        "app.services.task_service.enqueue_crawl_task",
        lambda task_id, dispatch_generation=None: TaskDispatchResult(
            celery_task_id=f"celery-{task_id}",
            task_name="app.worker.run_crawl_task",
        ),
    )

    with factory() as session:
        detail, _dispatch = resume_crawl_task(session, task_id)

    assert detail.status == "queued"
    assert detail.extra_params["keyword_expansion"]["status"] == "success"
    assert detail.extra_params["keyword_expansion"]["generated_synonyms"] == ["吃鸡"]
    assert detail.extra_params["keyword_expansion"]["expanded_keywords"] == [
        "和平精英",
        "吃鸡",
    ]


def test_celery_runtime_state_resolver_reuses_single_inspector_snapshot(
    monkeypatch,
) -> None:
    inspect_calls = {"count": 0}

    class FakeInspector:
        def active(self):
            return {"worker-a": [{"id": "active-task"}]}

        def reserved(self):
            return {"worker-a": [{"id": "reserved-task"}]}

        def scheduled(self):
            return {"worker-a": [{"request": {"id": "scheduled-task"}}]}

    class FakeControl:
        def inspect(self, timeout: float):
            inspect_calls["count"] += 1
            assert timeout == 0.2
            return FakeInspector()

    class FakeCeleryApp:
        control = FakeControl()

    monkeypatch.setattr("app.worker.celery_app", FakeCeleryApp())

    resolver = _build_celery_runtime_state_resolver()

    assert resolver("active-task") == "active"
    assert resolver("reserved-task") == "reserved"
    assert resolver("scheduled-task") == "scheduled"
    assert resolver("missing-task") == "missing"
    assert resolver(None) == "missing"
    assert inspect_calls["count"] == 1


def test_delete_crawl_task_moves_task_to_trash_and_restore_brings_it_back() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with factory() as session:
        task = CrawlTask(
            keyword="trash-me",
            status=TaskStatus.PAUSED,
            requested_video_limit=10,
            max_pages=2,
            min_sleep_seconds=Decimal("1.50"),
            max_sleep_seconds=Decimal("3.00"),
            enable_proxy=False,
            source_ip_strategy="local_sleep",
        )
        session.add(task)
        session.commit()
        task_id = task.id

    with factory() as session:
        payload = delete_crawl_task(session, task_id)
        assert payload.deleted is True
        assert payload.deleted_at is not None

    with factory() as session:
        stored_task = session.get(CrawlTask, task_id)
        assert stored_task is not None
        assert stored_task.deleted_at is not None

    with factory() as session:
        restored = restore_crawl_task(session, task_id)
        assert restored.restored is True

    with factory() as session:
        stored_task = session.get(CrawlTask, task_id)
        assert stored_task is not None
        assert stored_task.deleted_at is None


def test_terminal_success_progress_waits_for_analysis_snapshot() -> None:
    task = CrawlTask(
        keyword="artifact-check",
        status=TaskStatus.SUCCESS,
        requested_video_limit=10,
        max_pages=2,
        min_sleep_seconds=Decimal("1.50"),
        max_sleep_seconds=Decimal("3.00"),
        enable_proxy=False,
        source_ip_strategy="local_sleep",
        extra_params={},
    )

    assert calculate_task_progress(task) == 92


def test_terminal_success_progress_waits_for_report_snapshot() -> None:
    task = CrawlTask(
        keyword="artifact-check",
        status=TaskStatus.SUCCESS,
        requested_video_limit=10,
        max_pages=2,
        min_sleep_seconds=Decimal("1.50"),
        max_sleep_seconds=Decimal("3.00"),
        enable_proxy=False,
        source_ip_strategy="local_sleep",
        extra_params={"analysis_snapshot": _build_analysis_snapshot()},
    )

    assert calculate_task_progress(task) == 98


def test_get_task_progress_stays_on_report_stage_until_artifacts_complete() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with factory() as session:
        task = CrawlTask(
            keyword="artifact-check",
            status=TaskStatus.SUCCESS,
            requested_video_limit=10,
            max_pages=2,
            min_sleep_seconds=Decimal("1.50"),
            max_sleep_seconds=Decimal("3.00"),
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            extra_params={"analysis_snapshot": _build_analysis_snapshot()},
        )
        session.add(task)
        session.flush()
        create_task_log(
            session,
            task=task,
            stage=TaskStage.TASK,
            message="Bilibili crawl pipeline finished.",
        )
        session.commit()
        task_id = task.id

    with factory() as session:
        progress = get_task_progress(session, task_id)

    assert progress.current_stage == TaskStage.REPORT.value
    assert progress.progress_percent == 98


def test_get_task_progress_keeps_running_task_active_after_worker_heartbeat(
    monkeypatch,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with factory() as session:
        task = CrawlTask(
            keyword="heartbeat-active-task",
            status=TaskStatus.RUNNING,
            requested_video_limit=10,
            max_pages=2,
            min_sleep_seconds=Decimal("1.50"),
            max_sleep_seconds=Decimal("3.00"),
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            extra_params={"dispatch": {"celery_task_id": "celery-heartbeat-active"}},
        )
        session.add(task)
        session.flush()
        task.updated_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        session.commit()
        task_id = task.id

    assert (
        record_task_runtime_heartbeat(
            factory,
            task_id,
            "celery-heartbeat-active",
        )
        is True
    )

    monkeypatch.setattr(
        "app.services.task_service._get_celery_task_runtime_state",
        lambda celery_task_id: "missing",
    )

    with factory() as session:
        progress = get_task_progress(session, task_id)

    assert progress.status == TaskStatus.RUNNING.value


def test_terminal_success_reaches_100_only_with_analysis_and_report_snapshots() -> None:
    task = CrawlTask(
        keyword="artifact-check",
        status=TaskStatus.SUCCESS,
        requested_video_limit=10,
        max_pages=2,
        min_sleep_seconds=Decimal("1.50"),
        max_sleep_seconds=Decimal("3.00"),
        enable_proxy=False,
        source_ip_strategy="local_sleep",
        extra_params={
            "analysis_snapshot": _build_analysis_snapshot(),
            "report_snapshot": _build_report_snapshot(),
        },
    )

    assert calculate_task_progress(task) == 100
