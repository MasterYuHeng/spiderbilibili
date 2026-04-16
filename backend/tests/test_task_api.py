from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.bootstrap import bootstrap_system_configs
from app.db.session import get_db_session
from app.main import app
from app.models.analysis import AiSummary, TopicCluster, TopicVideoRelation
from app.models.enums import LogLevel, TaskStage, TaskStatus
from app.models.task import CrawlTask, TaskVideo
from app.models.video import Video, VideoMetricSnapshot, VideoTextContent
from app.services.task_log_service import create_task_log
from app.services.task_service import TaskDispatchResult
from app.services.task_state_machine import transition_task_status


def build_session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    with session_factory() as session:
        bootstrap_system_configs(session, commit=True)
    return session_factory


def override_db_session(
    session_factory: sessionmaker[Session],
) -> Generator[Session, None, None]:
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def build_db_override(
    session_factory: sessionmaker[Session],
):
    def _override() -> Generator[Session, None, None]:
        yield from override_db_session(session_factory)

    return _override


def test_create_task_endpoint_persists_task_and_dispatch_metadata(monkeypatch) -> None:
    session_factory = build_session_factory()
    app.dependency_overrides[get_db_session] = build_db_override(session_factory)

    observed_dispatch_snapshot: dict[str, str] = {}

    def fake_enqueue(
        task_id: str,
        dispatch_generation: int | None = None,
    ) -> TaskDispatchResult:
        with session_factory() as verification_session:
            stored_task = verification_session.get(CrawlTask, task_id)
            assert stored_task is not None
            observed_dispatch_snapshot["task_id"] = stored_task.id
            observed_dispatch_snapshot["status"] = stored_task.status.value
        return TaskDispatchResult(celery_task_id=f"celery-{task_id[:8]}")

    monkeypatch.setattr(
        "app.services.task_service.enqueue_crawl_task",
        fake_enqueue,
    )

    client = TestClient(app)
    response = client.post(
        "/api/tasks",
        headers={"X-Request-ID": "task-create"},
        json={
            "keyword": "AI总结",
            "published_within_days": 7,
            "requested_video_limit": 12,
            "max_pages": 3,
            "hot_author_total_count": 5,
            "topic_hot_author_count": 1,
            "hot_author_video_limit": 10,
            "hot_author_summary_basis": "heat",
            "enable_proxy": True,
            "min_sleep_seconds": 2,
            "max_sleep_seconds": 4,
            "source_ip_strategy": "proxy_pool",
        },
    )

    app.dependency_overrides.clear()

    assert response.status_code == 201
    payload = response.json()
    assert payload["success"] is True
    assert payload["request_id"] == "task-create"
    assert payload["data"]["task"]["status"] == "queued"
    assert payload["data"]["task"]["current_stage"] == "task"
    assert payload["data"]["task"]["logs"][0]["message"] == (
        "Task created and waiting for queue dispatch."
    )
    assert (
        payload["data"]["task"]["extra_params"]["keyword_expansion"]["status"]
        == "skipped"
    )
    assert payload["data"]["task"]["extra_params"]["keyword_expansion"][
        "expanded_keywords"
    ] == [payload["data"]["task"]["keyword"]]
    assert payload["data"]["dispatch"]["celery_task_id"].startswith("celery-")
    assert observed_dispatch_snapshot["task_id"] == payload["data"]["task"]["id"]
    assert observed_dispatch_snapshot["status"] == "queued"

    with session_factory() as session:
        stored_task = session.get(CrawlTask, payload["data"]["task"]["id"])
        assert stored_task is not None
        assert stored_task.status == TaskStatus.QUEUED
        assert stored_task.extra_params["task_options"]["search_scope"] == "site"
        assert stored_task.extra_params["task_options"]["partition_tid"] is None
        assert stored_task.extra_params["task_options"]["published_within_days"] == 7
        assert stored_task.extra_params["task_options"]["hot_author_total_count"] == 5
        assert stored_task.extra_params["task_options"]["topic_hot_author_count"] == 1
        assert stored_task.extra_params["task_options"]["hot_author_video_limit"] == 10
        assert (
            stored_task.extra_params["task_options"]["hot_author_summary_basis"]
            == "heat"
        )
        assert (
            stored_task.extra_params["task_options"]["enable_keyword_synonym_expansion"]
            is False
        )
        assert stored_task.extra_params["task_options"]["keyword_synonym_count"] is None
        assert stored_task.extra_params["keyword_expansion"]["status"] == "skipped"
        assert stored_task.extra_params["keyword_expansion"]["generated_synonyms"] == []
        assert (
            stored_task.extra_params["dispatch"]["task_name"]
            == "app.worker.run_crawl_task"
        )


def test_create_task_endpoint_rejects_empty_keyword() -> None:
    session_factory = build_session_factory()
    app.dependency_overrides[get_db_session] = build_db_override(session_factory)

    client = TestClient(app)
    response = client.post(
        "/api/tasks",
        headers={"X-Request-ID": "task-empty-keyword"},
        json={"keyword": "   "},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 422
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "request_validation_error"
    assert payload["request_id"] == "task-empty-keyword"


def test_create_task_endpoint_accepts_custom_published_within_days(monkeypatch) -> None:
    session_factory = build_session_factory()
    app.dependency_overrides[get_db_session] = build_db_override(session_factory)

    monkeypatch.setattr(
        "app.services.task_service.enqueue_crawl_task",
        lambda task_id, dispatch_generation=None: TaskDispatchResult(
            celery_task_id=f"celery-{task_id[:8]}",
            task_name="app.worker.run_crawl_task",
        ),
    )

    client = TestClient(app)
    response = client.post(
        "/api/tasks",
        headers={"X-Request-ID": "task-custom-published-within-days"},
        json={
            "keyword": "自定义时间窗",
            "published_within_days": 45,
        },
    )

    app.dependency_overrides.clear()

    assert response.status_code == 201
    payload = response.json()
    assert payload["success"] is True
    assert (
        payload["data"]["task"]["extra_params"]["task_options"]["published_within_days"]
        == 45
    )

    with session_factory() as session:
        stored_task = session.get(CrawlTask, payload["data"]["task"]["id"])
        assert stored_task is not None
        assert stored_task.extra_params["task_options"]["published_within_days"] == 45


def test_create_hot_task_endpoint_accepts_blank_keyword(monkeypatch) -> None:
    session_factory = build_session_factory()
    app.dependency_overrides[get_db_session] = build_db_override(session_factory)

    monkeypatch.setattr(
        "app.services.task_service.enqueue_crawl_task",
        lambda task_id, dispatch_generation=None: TaskDispatchResult(
            celery_task_id=f"celery-{task_id[:8]}",
            task_name="app.worker.run_crawl_task",
        ),
    )

    client = TestClient(app)
    response = client.post(
        "/api/tasks",
        headers={"X-Request-ID": "task-hot-create"},
        json={
            "crawl_mode": "hot",
            "keyword": "   ",
            "requested_video_limit": 20,
            "max_pages": 2,
        },
    )

    app.dependency_overrides.clear()

    assert response.status_code == 201
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["task"]["keyword"] == "当前热度"

    with session_factory() as session:
        stored_task = session.get(CrawlTask, payload["data"]["task"]["id"])
        assert stored_task is not None
        assert stored_task.keyword == "当前热度"
        assert stored_task.extra_params["task_options"]["crawl_mode"] == "hot"
        assert stored_task.extra_params["task_options"]["search_scope"] == "site"
        assert (
            stored_task.extra_params["task_options"]["enable_keyword_synonym_expansion"]
            is False
        )
        assert stored_task.extra_params["task_options"]["keyword_synonym_count"] is None


def test_create_task_endpoint_accepts_keyword_synonym_expansion_params(
    monkeypatch,
) -> None:
    session_factory = build_session_factory()
    app.dependency_overrides[get_db_session] = build_db_override(session_factory)

    monkeypatch.setattr(
        "app.services.task_service.enqueue_crawl_task",
        lambda task_id, dispatch_generation=None: TaskDispatchResult(
            celery_task_id=f"celery-{task_id[:8]}",
            task_name="app.worker.run_crawl_task",
        ),
    )

    client = TestClient(app)
    response = client.post(
        "/api/tasks",
        headers={"X-Request-ID": "task-create-expansion"},
        json={
            "keyword": "和平精英",
            "enable_keyword_synonym_expansion": True,
            "keyword_synonym_count": 2,
        },
    )

    app.dependency_overrides.clear()

    assert response.status_code == 201
    payload = response.json()
    task_options = payload["data"]["task"]["extra_params"]["task_options"]
    keyword_expansion = payload["data"]["task"]["extra_params"]["keyword_expansion"]
    assert task_options["enable_keyword_synonym_expansion"] is True
    assert task_options["keyword_synonym_count"] == 2
    assert (
        payload["data"]["task"]["keyword_expansion"]["source_keyword"]
        == payload["data"]["task"]["keyword"]
    )
    assert payload["data"]["task"]["keyword_expansion"]["enabled"] is True
    assert payload["data"]["task"]["search_keywords_used"] == [
        payload["data"]["task"]["keyword"]
    ]
    assert payload["data"]["task"]["expanded_keyword_count"] == 0
    assert keyword_expansion["source_keyword"] == payload["data"]["task"]["keyword"]
    assert keyword_expansion["enabled"] is True
    assert keyword_expansion["requested_synonym_count"] == 2
    assert keyword_expansion["generated_synonyms"] == []
    assert keyword_expansion["expanded_keywords"] == [
        payload["data"]["task"]["keyword"]
    ]
    assert keyword_expansion["status"] == "pending"
    assert keyword_expansion["model_name"] is None
    assert keyword_expansion["error_message"] is None
    assert keyword_expansion["generated_at"] is None

    with session_factory() as session:
        stored_task = session.get(CrawlTask, payload["data"]["task"]["id"])
        assert stored_task is not None
        assert (
            stored_task.extra_params["task_options"]["enable_keyword_synonym_expansion"]
            is True
        )
        assert stored_task.extra_params["task_options"]["keyword_synonym_count"] == 2
        assert stored_task.extra_params["keyword_expansion"]["status"] == "pending"


def test_create_hot_task_endpoint_ignores_keyword_synonym_expansion_params(
    monkeypatch,
) -> None:
    session_factory = build_session_factory()
    app.dependency_overrides[get_db_session] = build_db_override(session_factory)

    monkeypatch.setattr(
        "app.services.task_service.enqueue_crawl_task",
        lambda task_id, dispatch_generation=None: TaskDispatchResult(
            celery_task_id=f"celery-{task_id[:8]}",
            task_name="app.worker.run_crawl_task",
        ),
    )

    client = TestClient(app)
    response = client.post(
        "/api/tasks",
        headers={"X-Request-ID": "task-hot-ignore-expansion"},
        json={
            "crawl_mode": "hot",
            "keyword": "",
            "enable_keyword_synonym_expansion": True,
            "keyword_synonym_count": 5,
        },
    )

    app.dependency_overrides.clear()

    assert response.status_code == 201
    payload = response.json()
    task_options = payload["data"]["task"]["extra_params"]["task_options"]
    keyword_expansion = payload["data"]["task"]["extra_params"]["keyword_expansion"]
    assert task_options["enable_keyword_synonym_expansion"] is False
    assert task_options["keyword_synonym_count"] is None
    assert payload["data"]["task"]["keyword_expansion"]["status"] == "skipped"
    assert payload["data"]["task"]["search_keywords_used"] == []
    assert payload["data"]["task"]["expanded_keyword_count"] == 0
    assert keyword_expansion["status"] == "skipped"
    assert keyword_expansion["generated_synonyms"] == []


def test_create_task_endpoint_rejects_missing_keyword_synonym_count_when_enabled() -> (
    None
):
    session_factory = build_session_factory()
    app.dependency_overrides[get_db_session] = build_db_override(session_factory)

    client = TestClient(app)
    response = client.post(
        "/api/tasks",
        headers={"X-Request-ID": "task-expansion-missing-count"},
        json={
            "keyword": "和平精英",
            "enable_keyword_synonym_expansion": True,
        },
    )

    app.dependency_overrides.clear()

    assert response.status_code == 422
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "request_validation_error"


def test_create_task_endpoint_rejects_invalid_keyword_synonym_count() -> None:
    session_factory = build_session_factory()
    app.dependency_overrides[get_db_session] = build_db_override(session_factory)

    client = TestClient(app)
    response = client.post(
        "/api/tasks",
        headers={"X-Request-ID": "task-expansion-invalid-count"},
        json={
            "keyword": "和平精英",
            "enable_keyword_synonym_expansion": True,
            "keyword_synonym_count": 4,
        },
    )

    app.dependency_overrides.clear()

    assert response.status_code == 422
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "request_validation_error"


def test_create_partition_hot_task_requires_partition_tid(monkeypatch) -> None:
    session_factory = build_session_factory()
    app.dependency_overrides[get_db_session] = build_db_override(session_factory)

    monkeypatch.setattr(
        "app.services.task_service.enqueue_crawl_task",
        lambda task_id, dispatch_generation=None: TaskDispatchResult(
            celery_task_id=f"celery-{task_id[:8]}",
            task_name="app.worker.run_crawl_task",
        ),
    )

    client = TestClient(app)
    response = client.post(
        "/api/tasks",
        headers={"X-Request-ID": "task-hot-partition-missing"},
        json={
            "crawl_mode": "hot",
            "search_scope": "partition",
            "keyword": "",
        },
    )

    app.dependency_overrides.clear()

    assert response.status_code == 422
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "request_validation_error"


def test_retry_task_endpoint_clones_retryable_task(monkeypatch) -> None:
    session_factory = build_session_factory()

    with session_factory() as session:
        source_task = CrawlTask(
            keyword="retry-me",
            status=TaskStatus.FAILED,
            requested_video_limit=20,
            max_pages=5,
            min_sleep_seconds=1.5,
            max_sleep_seconds=5,
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            extra_params={
                "task_options": {
                    "crawl_mode": "keyword",
                    "search_scope": "site",
                    "requested_video_limit": 20,
                    "max_pages": 5,
                    "enable_proxy": False,
                    "source_ip_strategy": "local_sleep",
                    "enable_keyword_synonym_expansion": True,
                    "keyword_synonym_count": 2,
                },
                "keyword_expansion": {
                    "source_keyword": "retry-me",
                    "enabled": True,
                    "requested_synonym_count": 2,
                    "generated_synonyms": [],
                    "expanded_keywords": ["retry-me"],
                    "status": "fallback",
                    "model_name": None,
                    "error_message": "No valid synonyms returned.",
                    "generated_at": "2026-04-13T11:00:00Z",
                },
            },
        )
        session.add(source_task)
        session.commit()
        source_task_id = source_task.id

    app.dependency_overrides[get_db_session] = build_db_override(session_factory)
    monkeypatch.setattr(
        "app.services.task_service.enqueue_crawl_task",
        lambda task_id, dispatch_generation=None: TaskDispatchResult(
            celery_task_id=f"celery-{task_id[:8]}",
            task_name="app.worker.run_crawl_task",
        ),
    )

    client = TestClient(app)
    response = client.post(
        f"/api/tasks/{source_task_id}/retry",
        headers={"X-Request-ID": "task-retry"},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 201
    payload = response.json()
    assert payload["success"] is True
    assert payload["request_id"] == "task-retry"
    assert payload["data"]["task"]["id"] != source_task_id
    assert payload["data"]["task"]["status"] == "queued"
    assert (
        payload["data"]["task"]["extra_params"]["retry_context"]["retry_of_task_id"]
        == source_task_id
    )
    assert (
        payload["data"]["task"]["extra_params"]["keyword_expansion"]["status"]
        == "pending"
    )
    assert payload["data"]["task"]["extra_params"]["keyword_expansion"][
        "expanded_keywords"
    ] == ["retry-me"]


def test_retry_task_endpoint_rejects_non_retryable_status() -> None:
    session_factory = build_session_factory()

    with session_factory() as session:
        source_task = CrawlTask(
            keyword="no-retry",
            status=TaskStatus.SUCCESS,
            requested_video_limit=20,
            max_pages=5,
            min_sleep_seconds=1.5,
            max_sleep_seconds=5,
            enable_proxy=False,
            source_ip_strategy="local_sleep",
        )
        session.add(source_task)
        session.commit()
        source_task_id = source_task.id

    app.dependency_overrides[get_db_session] = build_db_override(session_factory)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(f"/api/tasks/{source_task_id}/retry")
    app.dependency_overrides.clear()

    assert response.status_code == 422
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "validation_error"


def test_pause_task_endpoint_marks_running_task_paused() -> None:
    session_factory = build_session_factory()

    with session_factory() as session:
        task = CrawlTask(
            keyword="pause-me",
            status=TaskStatus.RUNNING,
            requested_video_limit=20,
            max_pages=5,
            min_sleep_seconds=1.5,
            max_sleep_seconds=5,
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            extra_params={
                "dispatch": {
                    "dispatch_generation": 1,
                    "celery_task_id": "celery-old",
                }
            },
        )
        session.add(task)
        session.commit()
        task_id = task.id

    app.dependency_overrides[get_db_session] = build_db_override(session_factory)
    client = TestClient(app)
    response = client.post(
        f"/api/tasks/{task_id}/pause",
        headers={"X-Request-ID": "task-pause"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["status"] == "paused"
    assert payload["data"]["extra_params"]["control"]["requested_action"] == "pause"
    assert payload["data"]["extra_params"]["dispatch"]["dispatch_generation"] == 2


def test_pause_task_endpoint_is_idempotent_for_paused_task() -> None:
    session_factory = build_session_factory()

    with session_factory() as session:
        task = CrawlTask(
            keyword="already-paused",
            status=TaskStatus.PAUSED,
            requested_video_limit=20,
            max_pages=5,
            min_sleep_seconds=1.5,
            max_sleep_seconds=5,
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            extra_params={
                "control": {"requested_action": "pause"},
            },
        )
        session.add(task)
        session.commit()
        task_id = task.id

    app.dependency_overrides[get_db_session] = build_db_override(session_factory)
    client = TestClient(app)
    response = client.post(f"/api/tasks/{task_id}/pause")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["status"] == "paused"


def test_resume_task_endpoint_requeues_paused_task(monkeypatch) -> None:
    session_factory = build_session_factory()

    with session_factory() as session:
        task = CrawlTask(
            keyword="resume-me",
            status=TaskStatus.PAUSED,
            requested_video_limit=20,
            max_pages=5,
            min_sleep_seconds=1.5,
            max_sleep_seconds=5,
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            extra_params={
                "dispatch": {"dispatch_generation": 3, "celery_task_id": "celery-old"},
                "control": {"requested_action": "pause"},
                "task_options": {
                    "crawl_mode": "keyword",
                    "search_scope": "site",
                    "requested_video_limit": 20,
                    "max_pages": 5,
                    "enable_proxy": False,
                    "source_ip_strategy": "local_sleep",
                    "enable_keyword_synonym_expansion": True,
                    "keyword_synonym_count": 1,
                },
                "keyword_expansion": {
                    "source_keyword": "resume-me",
                    "enabled": True,
                    "requested_synonym_count": 1,
                    "generated_synonyms": ["alias"],
                    "expanded_keywords": ["resume-me", "alias"],
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
            celery_task_id=f"celery-{task_id[:8]}",
            task_name="app.worker.run_crawl_task",
        ),
    )
    app.dependency_overrides[get_db_session] = build_db_override(session_factory)
    client = TestClient(app)
    response = client.post(
        f"/api/tasks/{task_id}/resume",
        headers={"X-Request-ID": "task-resume"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 201
    payload = response.json()
    assert payload["data"]["task"]["status"] == "queued"
    assert (
        payload["data"]["task"]["extra_params"]["dispatch"]["dispatch_generation"] == 4
    )
    assert "control" not in payload["data"]["task"]["extra_params"]
    assert (
        payload["data"]["task"]["extra_params"]["keyword_expansion"]["status"]
        == "success"
    )
    assert payload["data"]["task"]["extra_params"]["keyword_expansion"][
        "expanded_keywords"
    ] == ["resume-me", "alias"]


def test_cancel_task_endpoint_marks_task_cancelled() -> None:
    session_factory = build_session_factory()

    with session_factory() as session:
        task = CrawlTask(
            keyword="cancel-me",
            status=TaskStatus.QUEUED,
            requested_video_limit=20,
            max_pages=5,
            min_sleep_seconds=1.5,
            max_sleep_seconds=5,
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            extra_params={
                "dispatch": {
                    "dispatch_generation": 2,
                    "celery_task_id": "celery-old",
                }
            },
        )
        session.add(task)
        session.commit()
        task_id = task.id

    app.dependency_overrides[get_db_session] = build_db_override(session_factory)
    client = TestClient(app)
    response = client.post(
        f"/api/tasks/{task_id}/cancel",
        headers={"X-Request-ID": "task-cancel"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["status"] == "cancelled"
    assert payload["data"]["error_message"] == "Task was cancelled by user."


def test_list_tasks_endpoint_reconciles_stale_queued_task(
    monkeypatch,
) -> None:
    session_factory = build_session_factory()

    with session_factory() as session:
        task = CrawlTask(
            keyword="stale-queued",
            status=TaskStatus.QUEUED,
            requested_video_limit=20,
            max_pages=5,
            min_sleep_seconds=1.5,
            max_sleep_seconds=5,
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            extra_params={
                "dispatch": {"celery_task_id": "celery-stale-queued"},
            },
        )
        session.add(task)
        session.flush()
        task.updated_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        create_task_log(
            session,
            task=task,
            stage=TaskStage.TASK,
            message="Task queued successfully.",
        )
        session.commit()
        task_id = task.id

    monkeypatch.setattr(
        "app.services.task_service._get_celery_task_runtime_state",
        lambda celery_task_id: "missing",
    )
    app.dependency_overrides[get_db_session] = build_db_override(session_factory)
    client = TestClient(app)
    response = client.get("/api/tasks", headers={"X-Request-ID": "task-list-reconcile"})
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["items"][0]["id"] == task_id
    assert payload["data"]["items"][0]["status"] == "failed"

    with session_factory() as session:
        stored_task = session.get(CrawlTask, task_id)
        assert stored_task is not None
        assert stored_task.status == TaskStatus.FAILED


def test_delete_task_endpoint_moves_paused_task_to_trash() -> None:
    session_factory = build_session_factory()

    with session_factory() as session:
        task = CrawlTask(
            keyword="delete-me",
            status=TaskStatus.PAUSED,
            requested_video_limit=20,
            max_pages=5,
            min_sleep_seconds=1.5,
            max_sleep_seconds=5,
            enable_proxy=False,
            source_ip_strategy="local_sleep",
        )
        session.add(task)
        session.commit()
        task_id = task.id

    app.dependency_overrides[get_db_session] = build_db_override(session_factory)
    client = TestClient(app)
    response = client.delete(
        f"/api/tasks/{task_id}",
        headers={"X-Request-ID": "task-delete"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["task_id"] == task_id
    assert payload["data"]["deleted"] is True
    assert payload["data"]["deleted_at"] is not None

    with session_factory() as session:
        stored_task = session.get(CrawlTask, task_id)
        assert stored_task is not None
        assert stored_task.deleted_at is not None


def test_delete_task_endpoint_allows_running_task_and_marks_it_cancelled() -> None:
    session_factory = build_session_factory()

    with session_factory() as session:
        task = CrawlTask(
            keyword="running-delete-me",
            status=TaskStatus.RUNNING,
            requested_video_limit=20,
            max_pages=5,
            min_sleep_seconds=1.5,
            max_sleep_seconds=5,
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            extra_params={
                "dispatch": {
                    "dispatch_generation": 1,
                    "celery_task_id": "celery-running-delete",
                }
            },
        )
        session.add(task)
        session.commit()
        task_id = task.id

    app.dependency_overrides[get_db_session] = build_db_override(session_factory)
    client = TestClient(app)
    response = client.delete(
        f"/api/tasks/{task_id}",
        headers={"X-Request-ID": "task-delete-running"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["task_id"] == task_id

    with session_factory() as session:
        stored_task = session.get(CrawlTask, task_id)
        assert stored_task is not None
        assert stored_task.deleted_at is not None
        assert stored_task.status == TaskStatus.CANCELLED
        assert stored_task.error_message == "Task was removed to trash by user."


def test_delete_all_tasks_endpoint_moves_deletable_tasks_to_trash(monkeypatch) -> None:
    session_factory = build_session_factory()

    with session_factory() as session:
        queued_task = CrawlTask(
            keyword="stale-queued",
            status=TaskStatus.QUEUED,
            requested_video_limit=20,
            max_pages=5,
            min_sleep_seconds=1.5,
            max_sleep_seconds=5,
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            extra_params={
                "dispatch": {"celery_task_id": "celery-stale-queued"},
            },
        )
        paused_task = CrawlTask(
            keyword="paused-task",
            status=TaskStatus.PAUSED,
            requested_video_limit=20,
            max_pages=5,
            min_sleep_seconds=1.5,
            max_sleep_seconds=5,
            enable_proxy=False,
            source_ip_strategy="local_sleep",
        )
        session.add_all([queued_task, paused_task])
        session.flush()
        queued_task.updated_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        session.commit()

    monkeypatch.setattr(
        "app.services.task_service._get_celery_task_runtime_state",
        lambda celery_task_id: "missing",
    )
    app.dependency_overrides[get_db_session] = build_db_override(session_factory)
    client = TestClient(app)
    response = client.delete("/api/tasks", headers={"X-Request-ID": "task-delete-all"})
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["deleted_count"] == 2
    assert payload["data"]["blocked_count"] == 0

    with session_factory() as session:
        remaining = session.scalars(select(CrawlTask)).all()
        assert len(remaining) == 2
        assert all(task.deleted_at is not None for task in remaining)


def test_trash_endpoints_list_restore_and_permanently_delete_task() -> None:
    session_factory = build_session_factory()

    with session_factory() as session:
        task = CrawlTask(
            keyword="trashed-task",
            status=TaskStatus.SUCCESS,
            requested_video_limit=20,
            max_pages=5,
            min_sleep_seconds=1.5,
            max_sleep_seconds=5,
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            deleted_at=datetime.now(timezone.utc),
        )
        session.add(task)
        session.commit()
        task_id = task.id

    app.dependency_overrides[get_db_session] = build_db_override(session_factory)
    client = TestClient(app)

    list_response = client.get(
        "/api/tasks/trash", headers={"X-Request-ID": "task-trash-list"}
    )
    restore_response = client.post(
        f"/api/tasks/{task_id}/restore",
        headers={"X-Request-ID": "task-trash-restore"},
    )
    delete_response = client.delete(
        f"/api/tasks/{task_id}/permanent",
        headers={"X-Request-ID": "task-trash-permanent-delete"},
    )
    app.dependency_overrides.clear()

    assert list_response.status_code == 200
    assert list_response.json()["data"]["items"][0]["id"] == task_id

    assert restore_response.status_code == 200
    assert restore_response.json()["data"] == {"task_id": task_id, "restored": True}

    assert delete_response.status_code == 404

    with session_factory() as session:
        stored_task = session.get(CrawlTask, task_id)
        assert stored_task is not None
        assert stored_task.deleted_at is None


def test_empty_trash_endpoint_permanently_deletes_trashed_tasks() -> None:
    session_factory = build_session_factory()

    with session_factory() as session:
        active_task = CrawlTask(
            keyword="active-task",
            status=TaskStatus.SUCCESS,
            requested_video_limit=20,
            max_pages=5,
            min_sleep_seconds=1.5,
            max_sleep_seconds=5,
            enable_proxy=False,
            source_ip_strategy="local_sleep",
        )
        trashed_task = CrawlTask(
            keyword="trashed-task",
            status=TaskStatus.SUCCESS,
            requested_video_limit=20,
            max_pages=5,
            min_sleep_seconds=1.5,
            max_sleep_seconds=5,
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            deleted_at=datetime.now(timezone.utc),
        )
        session.add_all([active_task, trashed_task])
        session.commit()

    app.dependency_overrides[get_db_session] = build_db_override(session_factory)
    client = TestClient(app)
    response = client.delete(
        "/api/tasks/trash", headers={"X-Request-ID": "task-trash-empty"}
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["data"]["deleted_count"] == 1

    with session_factory() as session:
        tasks = session.scalars(
            select(CrawlTask).order_by(CrawlTask.keyword.asc())
        ).all()
        assert len(tasks) == 1
        assert tasks[0].keyword == "active-task"


def test_task_acceptance_endpoint_returns_stage15_report() -> None:
    session_factory = build_session_factory()

    with session_factory() as session:
        task = CrawlTask(
            keyword="acceptance",
            status=TaskStatus.PARTIAL_SUCCESS,
            requested_video_limit=10,
            max_pages=3,
            min_sleep_seconds=1.5,
            max_sleep_seconds=3,
            enable_proxy=False,
            source_ip_strategy="local_sleep",
        )
        session.add(task)
        session.flush()

        video = Video(
            bvid="BV1acceptapi",
            aid=12345,
            title="Acceptance API sample",
            url="https://www.bilibili.com/video/BV1acceptapi",
            author_name="Acceptance UP",
            description="Acceptance API dataset",
            published_at=datetime(2026, 4, 8, tzinfo=timezone.utc),
            duration_seconds=180,
        )
        session.add(video)
        session.flush()

        task_video = TaskVideo(
            task_id=task.id,
            video_id=video.id,
            search_rank=1,
            keyword_hit_title=True,
            keyword_hit_description=True,
            keyword_hit_tags=False,
            relevance_score=Decimal("0.91"),
            heat_score=Decimal("0.83"),
            composite_score=Decimal("0.87"),
            is_selected=True,
        )
        metric_snapshot = VideoMetricSnapshot(
            task_id=task.id,
            video_id=video.id,
            view_count=500,
            like_count=60,
            coin_count=8,
            favorite_count=11,
            share_count=3,
            reply_count=5,
            danmaku_count=2,
            metrics_payload={"source": "acceptance-api"},
        )
        text_content = VideoTextContent(
            task_id=task.id,
            video_id=video.id,
            has_description=True,
            has_subtitle=True,
            description_text="Acceptance API dataset",
            subtitle_text="Subtitle for acceptance",
            combined_text="Acceptance API dataset\nSubtitle for acceptance",
            combined_text_hash="acceptance-api-hash",
            language_code="zh-CN",
        )
        session.add_all([task_video, metric_snapshot, text_content])
        session.flush()

        ai_summary = AiSummary(
            task_id=task.id,
            video_id=video.id,
            text_content_id=text_content.id,
            summary="Acceptance API summary",
            topics=["AI"],
            primary_topic="AI",
            tone="neutral",
            confidence=Decimal("0.96"),
            model_name="gpt-test",
            raw_response={"ok": True},
        )
        topic = TopicCluster(
            task_id=task.id,
            name="AI",
            normalized_name="ai",
            description="Readable acceptance topic",
            keywords=["AI"],
            video_count=1,
            total_heat_score=Decimal("0.83"),
            average_heat_score=Decimal("0.83"),
            cluster_order=1,
        )
        session.add_all([ai_summary, topic])
        session.flush()
        session.add(
            TopicVideoRelation(
                task_id=task.id,
                topic_cluster_id=topic.id,
                video_id=video.id,
                ai_summary_id=ai_summary.id,
                relevance_score=Decimal("0.91"),
                is_primary=True,
            )
        )
        create_task_log(
            session,
            task=task,
            stage=TaskStage.TOPIC,
            message="Acceptance API task completed.",
        )
        session.commit()
        task_id = task.id

    app.dependency_overrides[get_db_session] = build_db_override(session_factory)
    client = TestClient(app)
    response = client.get(
        f"/api/tasks/{task_id}/acceptance",
        headers={"X-Request-ID": "task-acceptance"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["request_id"] == "task-acceptance"
    assert payload["data"]["task_id"] == task_id
    assert payload["data"]["overall_status"] == "pass"
    section_names = [section["name"] for section in payload["data"]["sections"]]
    assert section_names == ["functional", "data", "stability", "compliance"]
    assert any(
        check["code"] == "task-videos-available" and check["status"] == "pass"
        for section in payload["data"]["sections"]
        for check in section["checks"]
    )


def test_task_query_endpoints_return_list_detail_and_progress(monkeypatch) -> None:
    session_factory = build_session_factory()

    with session_factory() as session:
        task = CrawlTask(
            keyword="机器学习",
            status=TaskStatus.PENDING,
            requested_video_limit=20,
            max_pages=5,
            min_sleep_seconds=1.5,
            max_sleep_seconds=5,
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            total_candidates=10,
            processed_videos=4,
            analyzed_videos=2,
            clustered_topics=1,
            extra_params={
                "task_options": {
                    "crawl_mode": "keyword",
                    "enable_keyword_synonym_expansion": True,
                    "keyword_synonym_count": 2,
                },
                "keyword_expansion": {
                    "source_keyword": "鏈哄櫒瀛︿範",
                    "enabled": True,
                    "requested_synonym_count": 2,
                    "generated_synonyms": ["AI", "ML"],
                    "expanded_keywords": ["鏈哄櫒瀛︿範", "AI", "ML"],
                    "status": "success",
                    "model_name": "gpt-4.1-mini",
                    "error_message": None,
                    "generated_at": "2026-04-13T13:00:00Z",
                },
                "crawl_stats": {
                    "success_count": 4,
                    "subtitle_count": 1,
                    "search_keywords_used": ["鏈哄櫒瀛︿範", "AI", "ML"],
                    "expanded_keyword_count": 2,
                },
            },
        )
        session.add(task)
        session.flush()
        transition_task_status(task, to_status=TaskStatus.QUEUED)
        transition_task_status(task, to_status=TaskStatus.RUNNING)
        create_task_log(
            session,
            task=task,
            level=LogLevel.INFO,
            stage=TaskStage.SEARCH,
            message="Collected the first four candidate videos.",
            payload={"processed_videos": 4, "total_candidates": 10},
        )
        session.commit()
        task_id = task.id

    app.dependency_overrides[get_db_session] = build_db_override(session_factory)
    client = TestClient(app)

    list_response = client.get("/api/tasks", headers={"X-Request-ID": "task-list"})
    detail_response = client.get(
        f"/api/tasks/{task_id}",
        headers={"X-Request-ID": "task-detail"},
    )
    progress_response = client.get(
        f"/api/tasks/{task_id}/progress",
        headers={"X-Request-ID": "task-progress"},
    )

    app.dependency_overrides.clear()

    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["data"]["total"] == 1
    assert list_payload["data"]["items"][0]["status"] == "running"

    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["data"]["current_stage"] == "search"
    assert detail_payload["data"]["progress_percent"] == 40
    assert detail_payload["data"]["keyword_expansion"]["status"] == "success"
    assert detail_payload["data"]["keyword_expansion"]["generated_synonyms"] == [
        "AI",
        "ML",
    ]
    assert detail_payload["data"]["search_keywords_used"] == [
        "鏈哄櫒瀛︿範",
        "AI",
        "ML",
    ]
    assert detail_payload["data"]["expanded_keyword_count"] == 2
    assert detail_payload["data"]["logs"][-1]["message"] == (
        "Collected the first four candidate videos."
    )

    assert progress_response.status_code == 200
    progress_payload = progress_response.json()
    assert progress_payload["data"]["status"] == "running"
    assert progress_payload["data"]["current_stage"] == "search"
    assert progress_payload["data"]["progress_percent"] == 40
    assert progress_payload["data"]["keyword_expansion"]["status"] == "success"
    assert progress_payload["data"]["search_keywords_used"] == [
        "鏈哄櫒瀛︿範",
        "AI",
        "ML",
    ]
    assert progress_payload["data"]["expanded_keyword_count"] == 2
    assert progress_payload["data"]["extra_params"]["crawl_stats"]["success_count"] == 4
    assert progress_payload["data"]["latest_log"]["stage"] == "search"


def test_task_detail_endpoint_supports_log_limit_and_reports_truncation() -> None:
    session_factory = build_session_factory()

    with session_factory() as session:
        task = CrawlTask(
            keyword="日志裁剪",
            status=TaskStatus.RUNNING,
            requested_video_limit=20,
            max_pages=5,
            min_sleep_seconds=1.5,
            max_sleep_seconds=5,
            enable_proxy=False,
            source_ip_strategy="local_sleep",
        )
        session.add(task)
        session.flush()

        for index in range(5):
            create_task_log(
                session,
                task=task,
                stage=TaskStage.DETAIL,
                message=f"log-{index}",
                payload={"index": index},
            )

        session.commit()
        task_id = task.id

    app.dependency_overrides[get_db_session] = build_db_override(session_factory)
    client = TestClient(app)
    response = client.get(
        f"/api/tasks/{task_id}?log_limit=2",
        headers={"X-Request-ID": "task-detail-log-limit"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["log_total"] == 5
    assert payload["logs_truncated"] is True
    assert [item["message"] for item in payload["logs"]] == ["log-3", "log-4"]
    assert payload["current_stage"] == "detail"


def test_progress_endpoint_keeps_actual_ratio_for_failed_task() -> None:
    session_factory = build_session_factory()

    with session_factory() as session:
        task = CrawlTask(
            keyword="失败任务",
            status=TaskStatus.FAILED,
            requested_video_limit=20,
            max_pages=5,
            min_sleep_seconds=1.5,
            max_sleep_seconds=5,
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            total_candidates=10,
            processed_videos=4,
            analyzed_videos=1,
            clustered_topics=0,
            error_message="crawl interrupted",
        )
        session.add(task)
        session.flush()
        create_task_log(
            session,
            task=task,
            level=LogLevel.ERROR,
            stage=TaskStage.SEARCH,
            message="Task failed after processing four candidates.",
            payload={"processed_videos": 4, "total_candidates": 10},
        )
        session.commit()
        task_id = task.id

    app.dependency_overrides[get_db_session] = build_db_override(session_factory)
    client = TestClient(app)
    response = client.get(
        f"/api/tasks/{task_id}/progress",
        headers={"X-Request-ID": "task-failed-progress"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["status"] == "failed"
    assert payload["data"]["progress_percent"] == 40


def test_create_task_endpoint_returns_503_when_dispatch_fails(monkeypatch) -> None:
    session_factory = build_session_factory()
    app.dependency_overrides[get_db_session] = build_db_override(session_factory)

    def raise_dispatch_error(
        task_id: str,
        dispatch_generation: int | None = None,
    ) -> TaskDispatchResult:
        raise RuntimeError(f"broker unavailable for {task_id}")

    monkeypatch.setattr(
        "app.services.task_service.enqueue_crawl_task",
        raise_dispatch_error,
    )

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/api/tasks",
        headers={"X-Request-ID": "task-dispatch-error"},
        json={"keyword": "异常任务"},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 503
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "service_unavailable"

    with session_factory() as session:
        task = session.scalar(
            select(CrawlTask).order_by(CrawlTask.created_at.desc(), CrawlTask.id.desc())
        )
        assert task is not None
        assert task.status == TaskStatus.FAILED
        assert task.error_message == "Failed to enqueue crawl task."


def test_task_result_endpoints_return_videos_topics_and_analysis() -> None:
    session_factory = build_session_factory()

    with session_factory() as session:
        task = CrawlTask(
            keyword="AI",
            status=TaskStatus.PARTIAL_SUCCESS,
            requested_video_limit=20,
            max_pages=5,
            min_sleep_seconds=1.5,
            max_sleep_seconds=5,
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            total_candidates=2,
            processed_videos=2,
        )
        session.add(task)
        session.flush()

        video = Video(
            bvid="BV1review",
            aid=123,
            title="AI Review Demo",
            url="https://www.bilibili.com/video/BV1review",
            author_name="Test UP",
            author_mid="1001",
            description="A concise AI review sample.",
            tags=["AI", "Review"],
            published_at=datetime(2026, 4, 7, tzinfo=timezone.utc),
            duration_seconds=600,
        )
        session.add(video)
        session.flush()

        task_video = TaskVideo(
            task_id=task.id,
            video_id=video.id,
            search_rank=1,
            keyword_hit_title=True,
            keyword_hit_description=True,
            keyword_hit_tags=True,
            relevance_score=Decimal("0.9000"),
            heat_score=Decimal("0.7500"),
            composite_score=Decimal("0.8400"),
            is_selected=True,
        )
        metric_snapshot = VideoMetricSnapshot(
            task_id=task.id,
            video_id=video.id,
            view_count=1000,
            like_count=120,
            coin_count=30,
            favorite_count=40,
            share_count=10,
            reply_count=15,
            danmaku_count=5,
            metrics_payload={"source": "test"},
        )
        text_content = VideoTextContent(
            task_id=task.id,
            video_id=video.id,
            has_description=True,
            has_subtitle=True,
            description_text="A concise AI review sample.",
            subtitle_text="AI subtitle line",
            combined_text=(
                "Video Description:\n"
                "A concise AI review sample.\n\n"
                "Video Subtitle:\n"
                "AI subtitle line"
            ),
            combined_text_hash="hash123",
            language_code="zh-CN",
        )
        session.add_all([task_video, metric_snapshot, text_content])
        session.flush()

        ai_summary = AiSummary(
            task_id=task.id,
            video_id=video.id,
            text_content_id=text_content.id,
            summary="This video summarizes current AI product trends.",
            topics=["AI", "Product"],
            primary_topic="AI",
            tone="neutral",
            confidence=Decimal("0.9300"),
            model_name="gpt-test",
            raw_response={"ok": True},
        )
        topic = TopicCluster(
            task_id=task.id,
            name="AI",
            normalized_name="ai",
            description="AI related videos",
            keywords=["AI", "Product"],
            video_count=1,
            total_heat_score=Decimal("0.7500"),
            average_heat_score=Decimal("0.7500"),
            cluster_order=1,
        )
        session.add_all([ai_summary, topic])
        session.flush()

        relation = TopicVideoRelation(
            task_id=task.id,
            topic_cluster_id=topic.id,
            video_id=video.id,
            ai_summary_id=ai_summary.id,
            relevance_score=Decimal("0.9000"),
            is_primary=True,
        )
        session.add(relation)
        session.commit()
        task_id = task.id

    app.dependency_overrides[get_db_session] = build_db_override(session_factory)
    client = TestClient(app)

    videos_response = client.get(
        f"/api/tasks/{task_id}/videos",
        headers={"X-Request-ID": "task-videos"},
    )
    topics_response = client.get(
        f"/api/tasks/{task_id}/topics",
        headers={"X-Request-ID": "task-topics"},
    )
    analysis_response = client.get(
        f"/api/tasks/{task_id}/analysis",
        headers={"X-Request-ID": "task-analysis"},
    )

    app.dependency_overrides.clear()

    assert videos_response.status_code == 200
    videos_payload = videos_response.json()
    assert videos_payload["data"]["total"] == 1
    assert videos_payload["data"]["items"][0]["bvid"] == "BV1review"
    assert videos_payload["data"]["items"][0]["metrics"]["view_count"] == 1000
    assert videos_payload["data"]["items"][0]["ai_summary"]["primary_topic"] == "AI"

    assert topics_response.status_code == 200
    topics_payload = topics_response.json()
    assert topics_payload["data"]["items"][0]["normalized_name"] == "ai"
    assert (
        topics_payload["data"]["items"][0]["representative_video"]["bvid"]
        == "BV1review"
    )

    assert analysis_response.status_code == 200
    analysis_payload = analysis_response.json()
    assert analysis_payload["data"]["summary"]["total_videos"] == 1
    assert analysis_payload["data"]["summary"]["average_view_count"] == 1000.0
    assert analysis_payload["data"]["has_ai_summaries"] is True
    assert analysis_payload["data"]["has_topics"] is True
    assert analysis_payload["data"]["top_videos"][0]["bvid"] == "BV1review"
    assert (
        analysis_payload["data"]["advanced"]["momentum_topics"][0]["topic_name"] == "AI"
    )
    assert analysis_payload["data"]["advanced"]["depth_topics"][0]["topic_name"] == "AI"
    assert (
        analysis_payload["data"]["advanced"]["community_topics"][0]["topic_name"]
        == "AI"
    )
    assert analysis_payload["data"]["advanced"]["metric_weight_configs"]
    assert (
        analysis_payload["data"]["advanced"]["metric_weight_configs"][0]["metric_key"]
        == "burst_score"
    )
    assert (
        analysis_payload["data"]["advanced"]["recommendations"][0]["videos"][0]["bvid"]
        == "BV1review"
    )


def test_analysis_endpoint_uses_lightweight_author_analysis_without_external_fetch(
    monkeypatch,
) -> None:
    session_factory = build_session_factory()

    with session_factory() as session:
        task = CrawlTask(
            keyword="AI",
            status=TaskStatus.PARTIAL_SUCCESS,
            requested_video_limit=20,
            max_pages=5,
            min_sleep_seconds=1.5,
            max_sleep_seconds=5,
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            total_candidates=1,
            processed_videos=1,
            extra_params={
                "task_options": {
                    "hot_author_total_count": 5,
                    "topic_hot_author_count": 1,
                    "hot_author_video_limit": 10,
                    "hot_author_summary_basis": "time",
                }
            },
        )
        session.add(task)
        session.flush()

        video = Video(
            bvid="BV1authorlight",
            aid=321,
            title="AI Author Demo",
            url="https://www.bilibili.com/video/BV1authorlight",
            author_name="Author Demo",
            author_mid="2001",
            description="A concise AI author sample.",
            tags=["AI", "Author"],
            published_at=datetime(2026, 4, 7, tzinfo=timezone.utc),
            duration_seconds=360,
        )
        session.add(video)
        session.flush()

        task_video = TaskVideo(
            task_id=task.id,
            video_id=video.id,
            search_rank=1,
            keyword_hit_title=True,
            keyword_hit_description=True,
            keyword_hit_tags=True,
            relevance_score=Decimal("0.9100"),
            heat_score=Decimal("0.7800"),
            composite_score=Decimal("0.8500"),
            is_selected=True,
        )
        metric_snapshot = VideoMetricSnapshot(
            task_id=task.id,
            video_id=video.id,
            view_count=1800,
            like_count=220,
            coin_count=45,
            favorite_count=60,
            share_count=20,
            reply_count=18,
            danmaku_count=7,
            metrics_payload={"source": "test"},
            captured_at=datetime(2026, 4, 7, tzinfo=timezone.utc),
        )
        text_content = VideoTextContent(
            task_id=task.id,
            video_id=video.id,
            has_description=True,
            has_subtitle=False,
            description_text="A concise AI author sample.",
            subtitle_text=None,
            combined_text="Video Description:\nA concise AI author sample.",
            combined_text_hash="author-light-hash",
            language_code="zh-CN",
        )
        session.add_all([task_video, metric_snapshot, text_content])
        session.flush()
        ai_summary = AiSummary(
            task_id=task.id,
            video_id=video.id,
            text_content_id=text_content.id,
            summary="This video introduces an AI creator sample.",
            topics=["AI", "Author"],
            primary_topic="AI",
            tone="neutral",
            confidence=Decimal("0.9200"),
            model_name="gpt-test",
            raw_response={"ok": True},
        )
        topic = TopicCluster(
            task_id=task.id,
            name="AI",
            normalized_name="ai",
            description="AI related videos",
            keywords=["AI", "Author"],
            video_count=1,
            total_heat_score=Decimal("0.7800"),
            average_heat_score=Decimal("0.7800"),
            cluster_order=1,
        )
        session.add_all([ai_summary, topic])
        session.flush()
        session.add(
            TopicVideoRelation(
                task_id=task.id,
                topic_cluster_id=topic.id,
                video_id=video.id,
                ai_summary_id=ai_summary.id,
                relevance_score=Decimal("0.9100"),
                is_primary=True,
            )
        )
        session.commit()
        task_id = task.id

    def fail_fetch_author_videos(*args, **kwargs):
        raise AssertionError("analysis endpoint should not fetch author videos on read")

    monkeypatch.setattr(
        "app.services.popular_author_service.PopularAuthorAnalysisService._fetch_author_videos",
        fail_fetch_author_videos,
    )

    app.dependency_overrides[get_db_session] = build_db_override(session_factory)
    client = TestClient(app)
    analysis_response = client.get(
        f"/api/tasks/{task_id}/analysis",
        headers={"X-Request-ID": "task-analysis-light-author"},
    )
    app.dependency_overrides.clear()

    assert analysis_response.status_code == 200
    analysis_payload = analysis_response.json()
    assert analysis_payload["data"]["advanced"]["popular_authors"]
    assert (
        analysis_payload["data"]["advanced"]["popular_authors"][0]["author_name"]
        == "Author Demo"
    )
    assert (
        analysis_payload["data"]["advanced"]["popular_authors"][0][
            "fetched_video_count"
        ]
        == 0
    )
    assert analysis_payload["data"]["advanced"]["popular_authors"][0]["videos"] == []


def test_analysis_weights_update_endpoint_regenerates_analysis_and_report() -> None:
    session_factory = build_session_factory()

    with session_factory() as session:
        task = CrawlTask(
            keyword="AI",
            status=TaskStatus.SUCCESS,
            requested_video_limit=20,
            max_pages=5,
            min_sleep_seconds=1.5,
            max_sleep_seconds=5,
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            total_candidates=1,
            processed_videos=1,
            analyzed_videos=1,
            clustered_topics=1,
        )
        session.add(task)
        session.flush()

        video = Video(
            bvid="BV1weight",
            aid=456,
            title="AI Weight Demo",
            url="https://www.bilibili.com/video/BV1weight",
            author_name="Weight UP",
            author_mid="1002",
            description="A sample for analysis weight updates.",
            tags=["AI", "Weight"],
            published_at=datetime(2026, 4, 7, tzinfo=timezone.utc),
            duration_seconds=420,
        )
        session.add(video)
        session.flush()

        task_video = TaskVideo(
            task_id=task.id,
            video_id=video.id,
            search_rank=1,
            keyword_hit_title=True,
            keyword_hit_description=True,
            keyword_hit_tags=True,
            relevance_score=Decimal("0.9300"),
            heat_score=Decimal("0.7900"),
            composite_score=Decimal("0.8600"),
            is_selected=True,
        )
        metric_snapshot = VideoMetricSnapshot(
            task_id=task.id,
            video_id=video.id,
            view_count=1200,
            like_count=180,
            coin_count=40,
            favorite_count=52,
            share_count=12,
            reply_count=16,
            danmaku_count=6,
            metrics_payload={
                "source": "test",
                "search_metrics": {
                    "play_count": 800,
                    "like_count": 110,
                    "favorite_count": 30,
                    "comment_count": 8,
                    "danmaku_count": 4,
                },
            },
            captured_at=datetime(2026, 4, 7, tzinfo=timezone.utc),
        )
        history_snapshot = VideoMetricSnapshot(
            task_id=task.id,
            video_id=video.id,
            view_count=1500,
            like_count=220,
            coin_count=48,
            favorite_count=60,
            share_count=18,
            reply_count=20,
            danmaku_count=9,
            metrics_payload={"source": "history"},
            captured_at=datetime(2026, 4, 8, tzinfo=timezone.utc),
        )
        text_content = VideoTextContent(
            task_id=task.id,
            video_id=video.id,
            has_description=True,
            has_subtitle=False,
            description_text="A sample for analysis weight updates.",
            subtitle_text=None,
            combined_text="Video Description:\nA sample for analysis weight updates.",
            combined_text_hash="weight-hash",
            language_code="zh-CN",
        )
        session.add_all([task_video, metric_snapshot, history_snapshot, text_content])
        session.flush()

        ai_summary = AiSummary(
            task_id=task.id,
            video_id=video.id,
            text_content_id=text_content.id,
            summary="This video tracks how AI samples change after updating weights.",
            topics=["AI", "Weight"],
            primary_topic="AI",
            tone="neutral",
            confidence=Decimal("0.9500"),
            model_name="gpt-test",
            raw_response={"ok": True},
        )
        topic = TopicCluster(
            task_id=task.id,
            name="AI",
            normalized_name="ai",
            description="AI topic cluster",
            keywords=["AI", "Weight"],
            video_count=1,
            total_heat_score=Decimal("0.7900"),
            average_heat_score=Decimal("0.7900"),
            cluster_order=1,
        )
        session.add_all([ai_summary, topic])
        session.flush()

        session.add(
            TopicVideoRelation(
                task_id=task.id,
                topic_cluster_id=topic.id,
                video_id=video.id,
                ai_summary_id=ai_summary.id,
                relevance_score=Decimal("0.9300"),
                is_primary=True,
            )
        )
        session.commit()
        task_id = task.id

    app.dependency_overrides[get_db_session] = build_db_override(session_factory)
    client = TestClient(app)
    response = client.post(
        f"/api/tasks/{task_id}/analysis/weights",
        headers={"X-Request-ID": "task-analysis-weight-update"},
        json={
            "metrics": [
                {
                    "metric_key": "burst_score",
                    "components": [
                        {"key": "search_growth", "weight": 0.9},
                        {"key": "publish_velocity", "weight": 0.1},
                        {"key": "history_velocity", "weight": 0.0},
                    ],
                },
                {
                    "metric_key": "topic_heat_index",
                    "components": [
                        {"key": "total_heat_score", "weight": 0.6},
                        {"key": "average_burst_score", "weight": 0.25},
                        {"key": "average_community_score", "weight": 0.15},
                    ],
                },
            ]
        },
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["request_id"] == "task-analysis-weight-update"
    burst_config = next(
        item
        for item in payload["data"]["advanced"]["metric_weight_configs"]
        if item["metric_key"] == "burst_score"
    )
    assert burst_config["customized"] is True
    assert burst_config["formula"].startswith("0.90 *")
    assert burst_config["components"][0]["weight"] == 0.9
    assert payload["data"]["advanced"]["data_notes"]

    with session_factory() as session:
        stored_task = session.get(CrawlTask, task_id)
        assert stored_task is not None
        weight_payload = stored_task.extra_params["analysis_metric_weights"]
        assert weight_payload["updated_at"]
        assert weight_payload["metrics"]["burst_score"]["search_growth"] == 0.9
        assert weight_payload["metrics"]["burst_score"]["publish_velocity"] == 0.1
        assert weight_payload["metrics"]["topic_heat_index"]["total_heat_score"] == 0.6
        assert stored_task.extra_params["analysis_snapshot"]["advanced"][
            "metric_weight_configs"
        ]
        assert stored_task.extra_params["report_snapshot"]["generated_at"]
        assert (
            stored_task.extra_params["pipeline_progress"]["analysis_weight_updated_at"]
            == weight_payload["updated_at"]
        )


def test_analysis_endpoints_reuse_persisted_snapshot_for_terminal_tasks(
    monkeypatch,
) -> None:
    session_factory = build_session_factory()

    with session_factory() as session:
        task = CrawlTask(
            keyword="AI",
            status=TaskStatus.SUCCESS,
            requested_video_limit=20,
            max_pages=5,
            min_sleep_seconds=1.5,
            max_sleep_seconds=5,
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            total_candidates=1,
            processed_videos=1,
            analyzed_videos=1,
            clustered_topics=1,
            extra_params={
                "analysis_snapshot": {
                    "summary": {
                        "total_videos": 1,
                        "average_view_count": 1280.0,
                        "average_like_count": 120.0,
                        "average_coin_count": 18.0,
                        "average_favorite_count": 35.0,
                        "average_share_count": 9.0,
                        "average_reply_count": 6.0,
                        "average_danmaku_count": 4.0,
                        "average_composite_score": 0.88,
                        "average_engagement_rate": 0.15,
                    },
                    "topics": [
                        {
                            "id": "topic-ai",
                            "name": "AI",
                            "normalized_name": "ai",
                            "description": "Cached topic snapshot",
                            "keywords": ["AI", "Workflow"],
                            "video_count": 1,
                            "total_heat_score": 0.81,
                            "average_heat_score": 0.81,
                            "video_ratio": 1.0,
                            "average_engagement_rate": 0.15,
                            "cluster_order": 1,
                            "representative_video": None,
                        }
                    ],
                    "advanced": {
                        "hot_topics": [
                            {
                                "id": "topic-ai",
                                "name": "AI",
                                "normalized_name": "ai",
                                "description": "Cached topic snapshot",
                                "keywords": ["AI", "Workflow"],
                                "video_count": 1,
                                "total_heat_score": 0.81,
                                "average_heat_score": 0.81,
                                "video_ratio": 1.0,
                                "average_engagement_rate": 0.15,
                                "cluster_order": 1,
                                "representative_video": None,
                            }
                        ],
                        "keyword_cooccurrence": [
                            {
                                "left": "AI",
                                "right": "Workflow",
                                "count": 1,
                            }
                        ],
                        "publish_date_distribution": [
                            {
                                "bucket": "2026-04-07",
                                "video_count": 1,
                            }
                        ],
                        "duration_heat_correlation": {
                            "metric": "duration_seconds_vs_heat_score",
                            "correlation": None,
                        },
                        "momentum_topics": [],
                        "explosive_videos": [],
                        "depth_topics": [],
                        "deep_videos": [],
                        "community_topics": [],
                        "community_videos": [],
                        "topic_evolution": [],
                        "latest_hot_topic": {
                            "topic": None,
                            "reason": None,
                            "supporting_points": [],
                        },
                        "topic_insights": [],
                        "video_insights": [],
                        "metric_definitions": [],
                        "metric_weight_configs": [],
                        "recommendations": [],
                        "data_notes": [],
                    },
                    "generated_at": "2026-04-07T00:00:00+00:00",
                    "has_ai_summaries": True,
                    "top_videos": [
                        {
                            "video_id": "video-top",
                            "bvid": "BV1cache",
                            "aid": 1001,
                            "title": "Cached top video",
                            "url": "https://www.bilibili.com/video/BV1cache",
                            "author_name": "Cache UP",
                            "author_mid": "10001",
                            "cover_url": None,
                            "description": "Cached top video description",
                            "tags": ["AI"],
                            "published_at": "2026-04-07T00:00:00+00:00",
                            "duration_seconds": 600,
                            "search_rank": 1,
                            "keyword_hit_title": True,
                            "keyword_hit_description": True,
                            "keyword_hit_tags": True,
                            "relevance_score": 0.9,
                            "heat_score": 0.8,
                            "composite_score": 0.88,
                            "is_selected": True,
                            "metrics": {
                                "view_count": 1280,
                                "like_count": 120,
                                "coin_count": 18,
                                "favorite_count": 35,
                                "share_count": 9,
                                "reply_count": 6,
                                "danmaku_count": 4,
                                "captured_at": "2026-04-07T00:00:00+00:00",
                            },
                            "text_content": None,
                            "ai_summary": {
                                "summary": "Cached top video summary",
                                "topics": ["AI", "Workflow"],
                                "primary_topic": "AI",
                                "tone": "neutral",
                                "confidence": 0.95,
                                "model_name": "gpt-cache",
                            },
                        }
                    ],
                }
            },
        )
        session.add(task)
        session.commit()
        task_id = task.id

    def fail_statistics(*args, **kwargs):
        raise AssertionError(
            "Statistics recalculation should not run for cached snapshots."
        )

    monkeypatch.setattr(
        "app.services.task_result_service.StatisticsService.calculate_task_statistics",
        fail_statistics,
    )

    app.dependency_overrides[get_db_session] = build_db_override(session_factory)
    client = TestClient(app)

    topics_response = client.get(f"/api/tasks/{task_id}/topics")
    analysis_response = client.get(f"/api/tasks/{task_id}/analysis")
    report_response = client.get(f"/api/tasks/{task_id}/report")

    app.dependency_overrides.clear()

    assert topics_response.status_code == 200
    assert topics_response.json()["data"]["items"][0]["name"] == "AI"

    assert analysis_response.status_code == 200
    analysis_payload = analysis_response.json()["data"]
    assert analysis_payload["generated_at"] == "2026-04-07T00:00:00Z"
    assert analysis_payload["summary"]["average_view_count"] == 1280.0
    assert analysis_payload["topics"][0]["description"] == "Cached topic snapshot"
    assert (
        analysis_payload["advanced"]["keyword_cooccurrence"][0]["right"] == "Workflow"
    )
    assert analysis_payload["top_videos"][0]["bvid"] == "BV1cache"
    assert analysis_payload["has_ai_summaries"] is True
    assert analysis_payload["has_topics"] is True
    assert analysis_payload["advanced"]["momentum_topics"] == []
    assert analysis_payload["advanced"]["metric_definitions"] == []
    assert analysis_payload["advanced"]["metric_weight_configs"] == []
    assert analysis_payload["advanced"]["recommendations"] == []

    assert report_response.status_code == 200
    report_payload = report_response.json()["data"]
    assert report_payload["title"] == "AI 热点内容分析报告"
    assert report_payload["sections"][0]["key"] == "overview"
    assert report_payload["ai_outputs"][0]["key"] == "melon_reader"
    assert "执行摘要" in report_payload["report_markdown"]


def test_task_videos_endpoint_supports_sort_topic_filter_and_latest_snapshot() -> None:
    session_factory = build_session_factory()

    with session_factory() as session:
        task = CrawlTask(
            keyword="AI",
            status=TaskStatus.SUCCESS,
            requested_video_limit=20,
            max_pages=5,
            min_sleep_seconds=1.5,
            max_sleep_seconds=5,
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            total_candidates=2,
            processed_videos=2,
            analyzed_videos=2,
        )
        session.add(task)
        session.flush()

        old_video = Video(
            bvid="BV1old",
            aid=101,
            title="Older AI Video",
            url="https://www.bilibili.com/video/BV1old",
            author_name="UP Old",
            description="Older video description",
            tags=["AI"],
            published_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            duration_seconds=300,
        )
        new_video = Video(
            bvid="BV1new",
            aid=102,
            title="New Robotics Video",
            url="https://www.bilibili.com/video/BV1new",
            author_name="UP New",
            description="New video description",
            tags=["机器人"],
            published_at=datetime(2026, 4, 7, tzinfo=timezone.utc),
            duration_seconds=420,
        )
        session.add_all([old_video, new_video])
        session.flush()

        session.add_all(
            [
                TaskVideo(
                    task_id=task.id,
                    video_id=old_video.id,
                    search_rank=1,
                    matched_keywords=["AI"],
                    primary_matched_keyword="AI",
                    keyword_match_count=1,
                    keyword_hit_title=True,
                    keyword_hit_description=True,
                    keyword_hit_tags=True,
                    relevance_score=Decimal("0.9500"),
                    heat_score=Decimal("0.3000"),
                    composite_score=Decimal("0.8100"),
                    is_selected=True,
                ),
                TaskVideo(
                    task_id=task.id,
                    video_id=new_video.id,
                    search_rank=2,
                    matched_keywords=["AI", "AIGC"],
                    primary_matched_keyword="AI",
                    keyword_match_count=2,
                    keyword_hit_title=True,
                    keyword_hit_description=False,
                    keyword_hit_tags=True,
                    relevance_score=Decimal("0.7000"),
                    heat_score=Decimal("0.9500"),
                    composite_score=Decimal("0.7800"),
                    is_selected=True,
                ),
            ]
        )

        session.add_all(
            [
                VideoMetricSnapshot(
                    task_id=task.id,
                    video_id=old_video.id,
                    view_count=100,
                    like_count=10,
                    coin_count=1,
                    favorite_count=2,
                    share_count=1,
                    reply_count=0,
                    danmaku_count=0,
                    metrics_payload={"version": "stale"},
                    captured_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
                ),
                VideoMetricSnapshot(
                    task_id=task.id,
                    video_id=old_video.id,
                    view_count=999,
                    like_count=99,
                    coin_count=9,
                    favorite_count=19,
                    share_count=4,
                    reply_count=3,
                    danmaku_count=2,
                    metrics_payload={"version": "latest"},
                    captured_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
                ),
                VideoMetricSnapshot(
                    task_id=task.id,
                    video_id=new_video.id,
                    view_count=5000,
                    like_count=500,
                    coin_count=120,
                    favorite_count=150,
                    share_count=45,
                    reply_count=36,
                    danmaku_count=18,
                    metrics_payload={"version": "latest"},
                    captured_at=datetime(2026, 4, 7, tzinfo=timezone.utc),
                ),
            ]
        )

        session.add_all(
            [
                VideoTextContent(
                    task_id=task.id,
                    video_id=old_video.id,
                    has_description=True,
                    has_subtitle=False,
                    description_text="Older video description",
                    subtitle_text=None,
                    combined_text="Video Description:\nOlder video description",
                    combined_text_hash="hash-old",
                    language_code="zh-CN",
                ),
                VideoTextContent(
                    task_id=task.id,
                    video_id=new_video.id,
                    has_description=True,
                    has_subtitle=False,
                    description_text="New video description",
                    subtitle_text=None,
                    combined_text="Video Description:\nNew video description",
                    combined_text_hash="hash-new",
                    language_code="zh-CN",
                ),
            ]
        )

        ai_topic = TopicCluster(
            task_id=task.id,
            name="AI",
            normalized_name="ai",
            video_count=1,
            total_heat_score=Decimal("0.3000"),
            average_heat_score=Decimal("0.3000"),
            keywords=["AI"],
            cluster_order=1,
        )
        robotics_topic = TopicCluster(
            task_id=task.id,
            name="Robotics",
            normalized_name="robotics",
            video_count=1,
            total_heat_score=Decimal("0.9500"),
            average_heat_score=Decimal("0.9500"),
            keywords=["机器人"],
            cluster_order=2,
        )
        session.add_all([ai_topic, robotics_topic])
        session.flush()

        session.add_all(
            [
                TopicVideoRelation(
                    task_id=task.id,
                    topic_cluster_id=ai_topic.id,
                    video_id=old_video.id,
                    relevance_score=Decimal("0.9500"),
                    is_primary=True,
                ),
                TopicVideoRelation(
                    task_id=task.id,
                    topic_cluster_id=robotics_topic.id,
                    video_id=new_video.id,
                    relevance_score=Decimal("0.9500"),
                    is_primary=True,
                ),
            ]
        )
        session.commit()
        task_id = task.id

    app.dependency_overrides[get_db_session] = build_db_override(session_factory)
    client = TestClient(app)

    default_response = client.get(
        f"/api/tasks/{task_id}/videos",
        headers={"X-Request-ID": "task-videos-default"},
    )
    sorted_response = client.get(
        f"/api/tasks/{task_id}/videos?sort_by=published_at&sort_order=desc",
        headers={"X-Request-ID": "task-videos-sorted"},
    )
    metric_sorted_response = client.get(
        f"/api/tasks/{task_id}/videos?sort_by=like_view_ratio&sort_order=desc",
        headers={"X-Request-ID": "task-videos-metric-sorted"},
    )
    filtered_response = client.get(
        f"/api/tasks/{task_id}/videos?topic=robotics&sort_by=heat_score&sort_order=desc",
        headers={"X-Request-ID": "task-videos-filtered"},
    )
    metric_filtered_response = client.get(
        (f"/api/tasks/{task_id}/videos?" "min_coin_count=100&min_like_view_ratio=0.1"),
        headers={"X-Request-ID": "task-videos-metric-filtered"},
    )

    app.dependency_overrides.clear()

    assert default_response.status_code == 200
    default_payload = default_response.json()
    assert default_payload["data"]["total"] == 2
    assert len(default_payload["data"]["items"]) == 2
    assert default_payload["data"]["items"][0]["bvid"] == "BV1old"
    assert default_payload["data"]["items"][0]["matched_keywords"] == ["AI"]
    assert default_payload["data"]["items"][0]["primary_matched_keyword"] == "AI"
    assert default_payload["data"]["items"][0]["keyword_match_count"] == 1
    assert default_payload["data"]["items"][0]["metrics"]["view_count"] == 999
    assert (
        round(default_payload["data"]["items"][0]["metrics"]["like_view_ratio"], 4)
        == 0.0991
    )

    assert sorted_response.status_code == 200
    sorted_payload = sorted_response.json()
    assert [item["bvid"] for item in sorted_payload["data"]["items"]] == [
        "BV1new",
        "BV1old",
    ]

    assert metric_sorted_response.status_code == 200
    metric_sorted_payload = metric_sorted_response.json()
    assert [item["bvid"] for item in metric_sorted_payload["data"]["items"]] == [
        "BV1new",
        "BV1old",
    ]

    assert filtered_response.status_code == 200
    filtered_payload = filtered_response.json()
    assert filtered_payload["data"]["total"] == 1
    assert filtered_payload["data"]["items"][0]["bvid"] == "BV1new"
    assert filtered_payload["data"]["items"][0]["matched_keywords"] == ["AI", "AIGC"]
    assert filtered_payload["data"]["items"][0]["keyword_match_count"] == 2
    assert filtered_payload["data"]["items"][0]["heat_score"] == 0.95

    assert metric_filtered_response.status_code == 200
    metric_filtered_payload = metric_filtered_response.json()
    assert metric_filtered_payload["data"]["total"] == 1
    assert metric_filtered_payload["data"]["items"][0]["bvid"] == "BV1new"
    assert metric_filtered_payload["data"]["items"][0]["metrics"]["coin_count"] == 120
    assert (
        metric_filtered_payload["data"]["items"][0]["metrics"]["like_view_ratio"] == 0.1
    )


def test_task_export_endpoint_supports_json_csv_and_excel_downloads() -> None:
    session_factory = build_session_factory()
    long_combined_text = "Video Description:\n" + ("Structured export sample. " * 40)

    with session_factory() as session:
        task = CrawlTask(
            keyword="AI",
            status=TaskStatus.SUCCESS,
            requested_video_limit=20,
            max_pages=5,
            min_sleep_seconds=1.5,
            max_sleep_seconds=5,
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            total_candidates=1,
            processed_videos=1,
            analyzed_videos=1,
            clustered_topics=1,
            extra_params={
                "task_options": {
                    "crawl_mode": "keyword",
                    "enable_keyword_synonym_expansion": True,
                    "keyword_synonym_count": 1,
                },
                "keyword_expansion": {
                    "source_keyword": "AI",
                    "enabled": True,
                    "requested_synonym_count": 1,
                    "generated_synonyms": ["AIGC"],
                    "expanded_keywords": ["AI", "AIGC"],
                    "status": "success",
                    "model_name": "gpt-export",
                    "error_message": None,
                    "generated_at": "2026-04-13T13:30:00Z",
                },
                "crawl_stats": {
                    "search_keywords_used": ["AI", "AIGC"],
                    "expanded_keyword_count": 1,
                },
            },
        )
        session.add(task)
        session.flush()

        video = Video(
            bvid="BV1export",
            aid=321,
            title="AI Export Demo",
            url="https://www.bilibili.com/video/BV1export",
            author_name="Export UP",
            author_mid="2002",
            description="Structured export sample.",
            tags=["AI", "Export"],
            published_at=datetime(2026, 4, 7, tzinfo=timezone.utc),
            duration_seconds=360,
        )
        session.add(video)
        session.flush()

        task_video = TaskVideo(
            task_id=task.id,
            video_id=video.id,
            search_rank=1,
            matched_keywords=["AI", "AIGC"],
            primary_matched_keyword="AI",
            keyword_match_count=2,
            keyword_hit_title=True,
            keyword_hit_description=True,
            keyword_hit_tags=True,
            relevance_score=Decimal("0.9100"),
            heat_score=Decimal("0.8100"),
            composite_score=Decimal("0.8700"),
            is_selected=True,
        )
        metric_snapshot = VideoMetricSnapshot(
            task_id=task.id,
            video_id=video.id,
            view_count=2000,
            like_count=300,
            coin_count=40,
            favorite_count=80,
            share_count=16,
            reply_count=12,
            danmaku_count=6,
            metrics_payload={"source": "export-test"},
        )
        text_content = VideoTextContent(
            task_id=task.id,
            video_id=video.id,
            has_description=True,
            has_subtitle=False,
            description_text="Structured export sample.",
            subtitle_text=None,
            combined_text=long_combined_text,
            combined_text_hash="export-hash",
            language_code="zh-CN",
        )
        session.add_all([task_video, metric_snapshot, text_content])
        session.flush()

        ai_summary = AiSummary(
            task_id=task.id,
            video_id=video.id,
            text_content_id=text_content.id,
            summary="This exported summary describes the AI export scenario.",
            topics=["AI", "Export"],
            primary_topic="AI",
            tone="neutral",
            confidence=Decimal("0.9600"),
            model_name="gpt-export",
            raw_response={"ok": True},
        )
        topic = TopicCluster(
            task_id=task.id,
            name="AI",
            normalized_name="ai",
            description="AI export topic",
            keywords=["AI", "Export"],
            video_count=1,
            total_heat_score=Decimal("0.8100"),
            average_heat_score=Decimal("0.8100"),
            cluster_order=1,
        )
        side_topic = TopicCluster(
            task_id=task.id,
            name="Robotics",
            normalized_name="robotics",
            description="A filtered out topic",
            keywords=["Robot"],
            video_count=0,
            total_heat_score=Decimal("0.1100"),
            average_heat_score=Decimal("0.1100"),
            cluster_order=2,
        )
        session.add_all([ai_summary, topic, side_topic])
        session.flush()

        session.add(
            TopicVideoRelation(
                task_id=task.id,
                topic_cluster_id=topic.id,
                video_id=video.id,
                ai_summary_id=ai_summary.id,
                relevance_score=Decimal("0.9100"),
                is_primary=True,
            )
        )
        session.commit()
        task_id = task.id

    app.dependency_overrides[get_db_session] = build_db_override(session_factory)
    client = TestClient(app)

    json_response = client.get(
        (
            f"/api/tasks/{task_id}/export?"
            "dataset=videos&format=json&sort_by=like_view_ratio&min_like_view_ratio=0.15"
        ),
        headers={"X-Request-ID": "task-export-json"},
    )
    video_csv_response = client.get(
        f"/api/tasks/{task_id}/export?dataset=videos&format=csv",
        headers={"X-Request-ID": "task-export-video-csv"},
    )
    csv_response = client.get(
        f"/api/tasks/{task_id}/export?dataset=topics&format=csv&topic=AI",
        headers={"X-Request-ID": "task-export-csv"},
    )
    excel_response = client.get(
        f"/api/tasks/{task_id}/export?dataset=summaries&format=excel",
        headers={"X-Request-ID": "task-export-excel"},
    )

    app.dependency_overrides.clear()

    assert json_response.status_code == 200
    assert "task-export-json" == json_response.headers["X-Request-ID"]
    assert 'attachment; filename="task-' in json_response.headers["content-disposition"]
    assert json_response.json()["total"] == 1
    assert json_response.json()["items"][0]["bvid"] == "BV1export"
    assert json_response.json()["items"][0]["original_keyword"] == "AI"
    assert json_response.json()["items"][0]["enable_keyword_synonym_expansion"] is True
    assert json_response.json()["items"][0]["search_keywords_used"] == "AI | AIGC"
    assert json_response.json()["items"][0]["expanded_keyword_count"] == 1
    assert json_response.json()["items"][0]["matched_keywords"] == "AI | AIGC"
    assert json_response.json()["items"][0]["primary_matched_keyword"] == "AI"
    assert json_response.json()["items"][0]["keyword_match_count"] == 2
    assert json_response.json()["items"][0]["primary_topic"] == "AI"
    assert json_response.json()["items"][0]["combined_text"] == long_combined_text
    assert json_response.json()["items"][0]["like_view_ratio"] == 0.15
    assert len(json_response.json()["items"][0]["combined_text"]) > 500

    assert video_csv_response.status_code == 200
    video_csv_text = video_csv_response.content.decode("utf-8-sig")
    assert "original_keyword" in video_csv_text
    assert "enable_keyword_synonym_expansion" in video_csv_text
    assert "search_keywords_used" in video_csv_text
    assert "matched_keywords" in video_csv_text
    assert "primary_matched_keyword" in video_csv_text
    assert "keyword_match_count" in video_csv_text
    assert "AI | AIGC" in video_csv_text
    assert video_csv_response.headers["content-disposition"].endswith('-videos.csv"')

    assert csv_response.status_code == 200
    csv_text = csv_response.content.decode("utf-8-sig")
    assert "normalized_name" in csv_text
    assert "ai" in csv_text
    assert "AI export topic" in csv_text
    assert "robotics" not in csv_text
    assert csv_response.headers["content-disposition"].endswith('-topics.csv"')

    assert excel_response.status_code == 200
    workbook = load_workbook(filename=BytesIO(excel_response.content))
    sheet = workbook.active
    assert sheet.title == "summaries"
    assert sheet["B2"].value == "BV1export"
    assert sheet["H2"].value == "AI | Export"
    assert sheet["P2"].value == long_combined_text
    assert excel_response.headers["content-disposition"].endswith('-summaries.xlsx"')
    workbook.close()


def test_progress_endpoint_uses_selected_video_target() -> None:
    session_factory = build_session_factory()

    with session_factory() as session:
        task = CrawlTask(
            keyword="AI",
            status=TaskStatus.RUNNING,
            requested_video_limit=20,
            max_pages=5,
            min_sleep_seconds=1.5,
            max_sleep_seconds=5,
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            total_candidates=100,
            processed_videos=10,
        )
        session.add(task)
        session.flush()
        create_task_log(
            session,
            task=task,
            stage=TaskStage.DETAIL,
            message="Processed ten selected videos.",
            payload={"processed_videos": 10, "selected_target": 20},
        )
        session.commit()
        task_id = task.id

    app.dependency_overrides[get_db_session] = build_db_override(session_factory)
    client = TestClient(app)
    response = client.get(
        f"/api/tasks/{task_id}/progress",
        headers={"X-Request-ID": "task-progress-selected-target"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["progress_percent"] == 50


def test_progress_endpoint_uses_crawl_progress_before_persisted_outputs() -> None:
    session_factory = build_session_factory()

    with session_factory() as session:
        task = CrawlTask(
            keyword="AI",
            status=TaskStatus.RUNNING,
            requested_video_limit=20,
            max_pages=5,
            min_sleep_seconds=1.5,
            max_sleep_seconds=5,
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            total_candidates=38,
            processed_videos=0,
            extra_params={
                "crawl_progress": {
                    "selected_count": 20,
                    "detail_processed_count": 6,
                    "detail_success_count": 5,
                    "detail_failure_count": 1,
                    "current_phase": "detail",
                }
            },
        )
        session.add(task)
        session.flush()
        create_task_log(
            session,
            task=task,
            stage=TaskStage.DETAIL,
            message="Started candidate detail crawl.",
            payload={"selected_count": 20, "video_concurrency": 4},
        )
        session.commit()
        task_id = task.id

    app.dependency_overrides[get_db_session] = build_db_override(session_factory)
    client = TestClient(app)
    response = client.get(
        f"/api/tasks/{task_id}/progress",
        headers={"X-Request-ID": "task-progress-crawl-progress"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["progress_percent"] == 30


def test_progress_endpoint_shows_non_zero_after_detail_stage_starts() -> None:
    session_factory = build_session_factory()

    with session_factory() as session:
        task = CrawlTask(
            keyword="AI",
            status=TaskStatus.RUNNING,
            requested_video_limit=20,
            max_pages=5,
            min_sleep_seconds=1.5,
            max_sleep_seconds=5,
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            total_candidates=38,
            processed_videos=0,
            extra_params={
                "crawl_progress": {
                    "selected_count": 20,
                    "detail_processed_count": 0,
                    "detail_success_count": 0,
                    "detail_failure_count": 0,
                    "current_phase": "detail",
                }
            },
        )
        session.add(task)
        session.flush()
        create_task_log(
            session,
            task=task,
            stage=TaskStage.DETAIL,
            message="Started candidate detail crawl.",
            payload={"selected_count": 20, "video_concurrency": 4},
        )
        session.commit()
        task_id = task.id

    app.dependency_overrides[get_db_session] = build_db_override(session_factory)
    client = TestClient(app)
    response = client.get(
        f"/api/tasks/{task_id}/progress",
        headers={"X-Request-ID": "task-progress-detail-start"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["progress_percent"] == 5


def test_progress_endpoint_shows_non_zero_for_legacy_running_task() -> None:
    session_factory = build_session_factory()

    with session_factory() as session:
        task = CrawlTask(
            keyword="AI",
            status=TaskStatus.RUNNING,
            requested_video_limit=20,
            max_pages=5,
            min_sleep_seconds=1.5,
            max_sleep_seconds=5,
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            total_candidates=38,
            processed_videos=0,
        )
        session.add(task)
        session.flush()
        create_task_log(
            session,
            task=task,
            stage=TaskStage.SEARCH,
            message="Collected candidate videos from search results.",
            payload={"candidate_count": 38, "selected_count": 20},
        )
        session.commit()
        task_id = task.id

    app.dependency_overrides[get_db_session] = build_db_override(session_factory)
    client = TestClient(app)
    response = client.get(
        f"/api/tasks/{task_id}/progress",
        headers={"X-Request-ID": "task-progress-legacy-running"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["progress_percent"] == 5


def test_progress_endpoint_includes_report_generation_stage() -> None:
    session_factory = build_session_factory()

    with session_factory() as session:
        task = CrawlTask(
            keyword="AI",
            status=TaskStatus.RUNNING,
            requested_video_limit=20,
            max_pages=5,
            min_sleep_seconds=1.5,
            max_sleep_seconds=5,
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            total_candidates=20,
            processed_videos=20,
            analyzed_videos=20,
            clustered_topics=4,
            extra_params={
                "pipeline_progress": {
                    "current_phase": "report",
                    "completed_phases": [
                        "search",
                        "detail",
                        "text",
                        "ai",
                        "topic",
                        "author",
                        "report",
                    ],
                }
            },
        )
        session.add(task)
        session.flush()
        create_task_log(
            session,
            task=task,
            stage=TaskStage.REPORT,
            message="Generated task report snapshot.",
            payload={"section_count": 8},
        )
        session.commit()
        task_id = task.id

    app.dependency_overrides[get_db_session] = build_db_override(session_factory)
    client = TestClient(app)
    response = client.get(
        f"/api/tasks/{task_id}/progress",
        headers={"X-Request-ID": "task-progress-report-stage"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["current_stage"] == "report"
    assert payload["data"]["progress_percent"] == 98


def test_progress_endpoint_marks_stale_running_task_failed(
    monkeypatch,
) -> None:
    session_factory = build_session_factory()

    with session_factory() as session:
        task = CrawlTask(
            keyword="stale-task",
            status=TaskStatus.RUNNING,
            requested_video_limit=20,
            max_pages=5,
            min_sleep_seconds=1.5,
            max_sleep_seconds=5,
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            total_candidates=38,
            processed_videos=0,
            extra_params={
                "dispatch": {"celery_task_id": "celery-stale-task"},
            },
        )
        session.add(task)
        session.flush()
        task.updated_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        create_task_log(
            session,
            task=task,
            stage=TaskStage.SEARCH,
            message="Collected candidate videos from search results.",
            payload={"candidate_count": 38, "selected_count": 20},
        )
        session.commit()
        task_id = task.id

    monkeypatch.setattr(
        "app.services.task_service._get_celery_task_runtime_state",
        lambda celery_task_id: "missing",
    )
    app.dependency_overrides[get_db_session] = build_db_override(session_factory)
    client = TestClient(app)
    response = client.get(
        f"/api/tasks/{task_id}/progress",
        headers={"X-Request-ID": "task-progress-stale-running"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["status"] == "failed"
    assert payload["data"]["error_message"] == (
        "Task execution became stale because no worker is actively processing it. "
        "Please retry the task."
    )

    with session_factory() as session:
        stored_task = session.get(CrawlTask, task_id)
        assert stored_task is not None
        assert stored_task.status == TaskStatus.FAILED


def test_progress_endpoint_keeps_stale_task_running_when_celery_reports_active(
    monkeypatch,
) -> None:
    session_factory = build_session_factory()

    with session_factory() as session:
        task = CrawlTask(
            keyword="active-task",
            status=TaskStatus.RUNNING,
            requested_video_limit=20,
            max_pages=5,
            min_sleep_seconds=1.5,
            max_sleep_seconds=5,
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            total_candidates=38,
            processed_videos=0,
            extra_params={
                "dispatch": {"celery_task_id": "celery-active-task"},
            },
        )
        session.add(task)
        session.flush()
        task.updated_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        create_task_log(
            session,
            task=task,
            stage=TaskStage.SEARCH,
            message="Collected candidate videos from search results.",
            payload={"candidate_count": 38, "selected_count": 20},
        )
        session.commit()
        task_id = task.id

    monkeypatch.setattr(
        "app.services.task_service._get_celery_task_runtime_state",
        lambda celery_task_id: "active",
    )
    app.dependency_overrides[get_db_session] = build_db_override(session_factory)
    client = TestClient(app)
    response = client.get(
        f"/api/tasks/{task_id}/progress",
        headers={"X-Request-ID": "task-progress-stale-but-active"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["status"] == "running"
    assert payload["data"]["progress_percent"] == 5
