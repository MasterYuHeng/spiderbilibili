import os
import threading
from importlib import import_module
from typing import Any, cast

from celery import Celery
from celery.signals import heartbeat_sent, worker_ready
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import get_session_factory
from app.models.base import utc_now
from app.models.enums import LogLevel, TaskStage, TaskStatus
from app.models.task import CrawlTask
from app.services.alerting import AlertEvent, send_alert
from app.services.monitoring import (
    record_ai_batch_outcomes,
    record_task_stage_failure,
    record_task_terminal_status,
    record_worker_heartbeat,
)
from app.services.task_concurrency_service import TaskExecutionGate
from app.services.task_log_service import create_task_log
from app.services.task_service import (
    TASK_DISPATCH_NAME,
    TaskControlSignal,
    assert_task_execution_allowed,
)
from app.services.task_state_machine import transition_task_status

settings = get_settings()
configure_logging()

_WORKER_SERVICE_IMPORTS = {
    "CrawlPipelineService": (
        "app.services.crawl_pipeline_service",
        "CrawlPipelineService",
    ),
    "StatisticsService": (
        "app.services.statistics_service",
        "StatisticsService",
    ),
    "TaskReportService": (
        "app.services.task_report_service",
        "TaskReportService",
    ),
    "TopicClusterService": (
        "app.services.topic_cluster_service",
        "TopicClusterService",
    ),
    "VideoAiService": (
        "app.services.video_ai_service",
        "VideoAiService",
    ),
}

CrawlPipelineService = None
StatisticsService = None
TaskReportService = None
TopicClusterService = None
VideoAiService = None


def _load_worker_service(service_name: str) -> type[Any]:
    service = globals().get(service_name)
    if service is not None:
        return cast(type[Any], service)

    module_name, attribute_name = _WORKER_SERVICE_IMPORTS[service_name]
    service = getattr(import_module(module_name), attribute_name)
    globals()[service_name] = service
    return cast(type[Any], service)


def resolve_celery_worker_pool(platform_name: str | None = None) -> str:
    resolved_platform = platform_name or os.name
    return "solo" if resolved_platform == "nt" else "prefork"


def resolve_celery_worker_concurrency(pool_name: str) -> int | None:
    if pool_name == "solo":
        return 1
    return None


def resolve_task_runtime_heartbeat_interval(
    stale_after_seconds: int | float | None = None,
) -> float:
    stale_after = float(
        stale_after_seconds or settings.worker_task_stale_after_seconds or 180
    )
    return max(15.0, min(60.0, stale_after / 3.0))


def record_task_runtime_heartbeat(
    session_factory,
    task_id: str,
    celery_task_id: str | None = None,
) -> bool:
    with session_factory() as session:
        task = session.scalar(select(CrawlTask).where(CrawlTask.id == task_id))
        if task is None:
            return False

        if task.status not in {TaskStatus.QUEUED, TaskStatus.RUNNING}:
            return False

        heartbeat_at = utc_now()
        dispatch_payload: dict[str, object] = {
            "acknowledged_by_worker": True,
            "last_worker_heartbeat_at": heartbeat_at.isoformat(),
        }
        if celery_task_id:
            dispatch_payload["celery_task_id"] = celery_task_id

        task.updated_at = heartbeat_at
        task.extra_params = _merge_dispatch_metadata(
            task.extra_params,
            dispatch_payload,
        )
        session.commit()
        return True


def _supports_background_task_runtime_heartbeat(session_factory) -> bool:
    bind = getattr(getattr(session_factory, "kw", {}), "get", lambda *_: None)("bind")
    bind_url = str(getattr(bind, "url", "") or "").lower()
    return ":memory:" not in bind_url


class TaskRuntimeHeartbeat:
    def __init__(
        self,
        *,
        session_factory,
        task_id: str,
        celery_task_id: str | None,
        interval_seconds: float | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.task_id = task_id
        self.celery_task_id = celery_task_id
        self.interval_seconds = (
            interval_seconds or resolve_task_runtime_heartbeat_interval()
        )
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "TaskRuntimeHeartbeat":
        if not _supports_background_task_runtime_heartbeat(self.session_factory):
            return self

        self._thread = threading.Thread(
            target=self._run,
            name=f"task-heartbeat-{self.task_id[:8]}",
            daemon=True,
        )
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._thread is None:
            return

        self._stop_event.set()
        self._thread.join(timeout=min(2.0, self.interval_seconds))

    def _run(self) -> None:
        while not self._stop_event.wait(self.interval_seconds):
            keep_running = record_task_runtime_heartbeat(
                self.session_factory,
                self.task_id,
                self.celery_task_id,
            )
            if not keep_running:
                return


default_worker_pool = resolve_celery_worker_pool()
default_worker_concurrency = resolve_celery_worker_concurrency(default_worker_pool)

celery_app = Celery(
    "spiderbilibili",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=False,
    worker_pool=default_worker_pool,
    worker_concurrency=default_worker_concurrency,
)


@worker_ready.connect
def handle_worker_ready(**kwargs: object) -> None:
    record_worker_heartbeat(state="ready")


@heartbeat_sent.connect
def handle_worker_heartbeat(**kwargs: object) -> None:
    record_worker_heartbeat()


@celery_app.task(name="app.worker.ping")
def ping() -> str:
    return "pong"


@celery_app.task(name=TASK_DISPATCH_NAME, bind=True)
def run_crawl_task(
    self,
    task_id: str,
    dispatch_generation: int | None = None,
) -> dict[str, str | None]:
    crawl_pipeline_service_cls = _load_worker_service("CrawlPipelineService")
    statistics_service_cls = _load_worker_service("StatisticsService")
    task_report_service_cls = _load_worker_service("TaskReportService")
    topic_cluster_service_cls = _load_worker_service("TopicClusterService")
    video_ai_service_cls = _load_worker_service("VideoAiService")
    session_factory = get_session_factory()
    celery_task_id = getattr(getattr(self, "request", None), "id", None)
    try:
        execution_lease = TaskExecutionGate(settings=settings).acquire(task_id)
    except RuntimeError as exc:
        _persist_gate_acquire_failure(
            session_factory=session_factory,
            task_id=task_id,
            celery_task_id=celery_task_id,
            error_message=str(exc),
        )
        return {
            "task_id": task_id,
            "status": TaskStatus.FAILED.value,
            "celery_task_id": celery_task_id,
        }
    with session_factory() as session:
        try:
            try:
                task = assert_task_execution_allowed(
                    session,
                    task_id,
                    expected_dispatch_generation=dispatch_generation,
                )
            except TaskControlSignal as control_signal:
                return {
                    "task_id": task_id,
                    "status": control_signal.action,
                    "celery_task_id": celery_task_id,
                }

            if task.status == TaskStatus.QUEUED:
                transition_task_status(task, to_status=TaskStatus.RUNNING)

            task.extra_params = _merge_dispatch_metadata(
                task.extra_params,
                {
                    "celery_task_id": celery_task_id,
                    "acknowledged_by_worker": True,
                    "global_task_concurrency": settings.worker_global_task_concurrency,
                },
            )
            create_task_log(
                session,
                task=task,
                level=LogLevel.INFO,
                stage=TaskStage.TASK,
                message="Queue worker acknowledged the task and moved it to running.",
                payload={
                    "celery_task_id": celery_task_id,
                    "status": task.status.value,
                    "global_task_concurrency": settings.worker_global_task_concurrency,
                },
            )
            session.commit()

            with TaskRuntimeHeartbeat(
                session_factory=session_factory,
                task_id=task_id,
                celery_task_id=celery_task_id,
            ):
                try:
                    pipeline = crawl_pipeline_service_cls(session)
                    try:
                        result = pipeline.run_task(
                            task,
                            expected_dispatch_generation=dispatch_generation,
                        )
                    finally:
                        pipeline.close()
                    task = assert_task_execution_allowed(
                        session,
                        task_id,
                        expected_dispatch_generation=dispatch_generation,
                    )
                    ai_result = video_ai_service_cls(session).analyze_task(
                        task,
                        expected_dispatch_generation=dispatch_generation,
                    )
                    task.extra_params = _merge_pipeline_progress(
                        task.extra_params,
                        {
                            "current_phase": TaskStage.AI.value,
                            "completed_phases": [
                                TaskStage.SEARCH.value,
                                TaskStage.DETAIL.value,
                                TaskStage.TEXT.value,
                                TaskStage.AI.value,
                            ],
                            "ai_target_count": ai_result.total_count,
                            "ai_success_count": ai_result.success_count,
                            "ai_failure_count": ai_result.failure_count,
                        },
                    )
                    session.commit()
                    task = assert_task_execution_allowed(
                        session,
                        task_id,
                        expected_dispatch_generation=dispatch_generation,
                    )
                    topic_result = topic_cluster_service_cls(session).cluster_task(
                        task,
                        expected_dispatch_generation=dispatch_generation,
                    )
                    task.extra_params = _merge_pipeline_progress(
                        task.extra_params,
                        {
                            "current_phase": TaskStage.TOPIC.value,
                            "completed_phases": [
                                TaskStage.SEARCH.value,
                                TaskStage.DETAIL.value,
                                TaskStage.TEXT.value,
                                TaskStage.AI.value,
                                TaskStage.TOPIC.value,
                            ],
                            "cluster_count": topic_result.cluster_count,
                            "relation_count": topic_result.relation_count,
                        },
                    )
                    session.commit()
                    statistics_result = statistics_service_cls(
                        session
                    ).generate_and_persist(task)
                    final_status = _resolve_final_task_status(
                        crawl_success_count=result.success_count,
                        crawl_failure_count=result.failure_count,
                        ai_total_count=ai_result.total_count,
                        ai_success_count=ai_result.success_count,
                        ai_failure_count=ai_result.failure_count,
                    )
                    task.extra_params = _merge_pipeline_progress(
                        task.extra_params,
                        {
                            "current_phase": TaskStage.AUTHOR.value,
                            "completed_phases": [
                                TaskStage.SEARCH.value,
                                TaskStage.DETAIL.value,
                                TaskStage.TEXT.value,
                                TaskStage.AI.value,
                                TaskStage.TOPIC.value,
                                TaskStage.AUTHOR.value,
                            ],
                            "popular_author_count": len(
                                getattr(
                                    statistics_result.advanced,
                                    "popular_authors",
                                    [],
                                )
                            ),
                        },
                    )
                    session.commit()
                    report_result = task_report_service_cls(
                        session
                    ).generate_and_persist(
                        task,
                        status_override=final_status.value,
                    )
                    task.extra_params = _merge_pipeline_progress(
                        task.extra_params,
                        {
                            "current_phase": TaskStage.REPORT.value,
                            "completed_phases": [
                                TaskStage.SEARCH.value,
                                TaskStage.DETAIL.value,
                                TaskStage.TEXT.value,
                                TaskStage.AI.value,
                                TaskStage.TOPIC.value,
                                TaskStage.AUTHOR.value,
                                TaskStage.REPORT.value,
                            ],
                            "report_section_count": len(report_result.sections),
                            "report_generated_at": (
                                report_result.generated_at.isoformat()
                            ),
                        },
                    )
                    session.commit()
                except TaskControlSignal as control_signal:
                    session.rollback()
                    task = _reload_task_or_raise(session, task_id)
                    session.refresh(task)
                    create_task_log(
                        session,
                        task=task,
                        level=LogLevel.INFO,
                        stage=TaskStage.TASK,
                        message="Task execution stopped after a control action.",
                        payload={
                            "action": control_signal.action,
                            "detail": control_signal.message,
                        },
                    )
                    session.commit()
                    return {
                        "task_id": task_id,
                        "status": task.status.value,
                        "celery_task_id": celery_task_id,
                    }
                except Exception as exc:
                    session.rollback()
                    task = _reload_task_or_raise(session, task_id)
                    transition_task_status(
                        task,
                        to_status=TaskStatus.FAILED,
                        error_message=str(exc),
                    )
                    create_task_log(
                        session,
                        task=task,
                        level=LogLevel.ERROR,
                        stage=TaskStage.TASK,
                        message="Bilibili crawl pipeline failed.",
                        payload={
                            "exception_type": type(exc).__name__,
                            "detail": str(exc),
                        },
                    )
                    session.commit()
                    record_task_stage_failure(TaskStage.TASK.value)
                    record_task_terminal_status(TaskStatus.FAILED.value)
                    send_alert(
                        AlertEvent(
                            event_type="task_pipeline_exception",
                            severity="critical",
                            title="spiderbilibili task execution failed",
                            message=(
                                f"Task {task.id} failed while executing "
                                "the crawl pipeline."
                            ),
                            details={
                                "task_id": task.id,
                                "keyword": task.keyword,
                                "exception_type": type(exc).__name__,
                                "detail": str(exc),
                            },
                            dedupe_key=f"task-exception:{task.id}",
                        )
                    )
                    raise

                record_ai_batch_outcomes(
                    total_count=ai_result.total_count,
                    success_count=ai_result.success_count,
                    failure_count=ai_result.failure_count,
                    fallback_count=ai_result.fallback_count,
                    cached_count=getattr(ai_result, "cached_count", 0),
                )

                transition_task_status(
                    task,
                    to_status=final_status,
                    error_message=(
                        None
                        if final_status != TaskStatus.FAILED
                        else (
                            "All candidate video crawls failed."
                            if result.success_count == 0
                            else "AI analysis failed for all persisted videos."
                        )
                    ),
                )
                task.extra_params = _merge_pipeline_progress(
                    task.extra_params,
                    {
                        "current_phase": "completed",
                        "completed_phases": [
                            TaskStage.SEARCH.value,
                            TaskStage.DETAIL.value,
                            TaskStage.TEXT.value,
                            TaskStage.AI.value,
                            TaskStage.TOPIC.value,
                            TaskStage.AUTHOR.value,
                            TaskStage.REPORT.value,
                        ],
                    },
                )
                create_task_log(
                    session,
                    task=task,
                    level=LogLevel.INFO,
                    stage=TaskStage.TASK,
                    message="Bilibili crawl pipeline finished.",
                    payload={
                        "candidate_count": result.candidate_count,
                        "selected_count": result.selected_count,
                        "video_concurrency": getattr(result, "video_concurrency", 1),
                        "success_count": result.success_count,
                        "failure_count": result.failure_count,
                        "subtitle_count": result.subtitle_count,
                        "analyzed_videos": task.analyzed_videos,
                        "ai_cached_count": getattr(ai_result, "cached_count", 0),
                        "ai_failure_count": ai_result.failure_count,
                        "ai_fallback_count": ai_result.fallback_count,
                        "ai_clipped_count": getattr(ai_result, "clipped_count", 0),
                        "clustered_topics": topic_result.cluster_count,
                        "topic_relation_count": topic_result.relation_count,
                        "hot_topic_count": len(
                            getattr(statistics_result.advanced, "hot_topics", [])
                        ),
                        "status": task.status.value,
                    },
                )
                session.commit()
                record_task_terminal_status(task.status.value)

                if task.status in {TaskStatus.FAILED, TaskStatus.PARTIAL_SUCCESS}:
                    send_alert(
                        AlertEvent(
                            event_type="task_terminal_status",
                            severity=(
                                "critical"
                                if task.status == TaskStatus.FAILED
                                else "warning"
                            ),
                            title="spiderbilibili task completed with issues",
                            message=(
                                f"Task {task.id} finished with status "
                                f"{task.status.value}."
                            ),
                            details={
                                "task_id": task.id,
                                "keyword": task.keyword,
                                "status": task.status.value,
                                "crawl_failure_count": result.failure_count,
                                "ai_failure_count": ai_result.failure_count,
                                "subtitle_count": result.subtitle_count,
                            },
                            dedupe_key=f"task-terminal:{task.id}:{task.status.value}",
                        )
                    )

                return {
                    "task_id": task_id,
                    "status": task.status.value,
                    "celery_task_id": celery_task_id,
                }
        finally:
            execution_lease.release()


@celery_app.task(name="app.worker.run_ai_analysis_batch")
def run_ai_analysis_batch(task_id: str) -> dict[str, int | str]:
    video_ai_service_cls = _load_worker_service("VideoAiService")
    session_factory = get_session_factory()
    with session_factory() as session:
        task = session.scalar(select(CrawlTask).where(CrawlTask.id == task_id))
        if task is None:
            raise ValueError(f"Task {task_id} does not exist.")

        result = video_ai_service_cls(session).analyze_task(task)
        return {
            "task_id": task_id,
            "success_count": result.success_count,
            "failure_count": result.failure_count,
            "fallback_count": result.fallback_count,
            "batch_count": result.batch_count,
            "cached_count": getattr(result, "cached_count", 0),
            "clipped_count": getattr(result, "clipped_count", 0),
        }


@celery_app.task(name="app.worker.run_topic_analysis_batch")
def run_topic_analysis_batch(task_id: str) -> dict[str, int | str]:
    statistics_service_cls = _load_worker_service("StatisticsService")
    topic_cluster_service_cls = _load_worker_service("TopicClusterService")
    session_factory = get_session_factory()
    with session_factory() as session:
        task = session.scalar(select(CrawlTask).where(CrawlTask.id == task_id))
        if task is None:
            raise ValueError(f"Task {task_id} does not exist.")

        cluster_result = topic_cluster_service_cls(session).cluster_task(task)
        statistics_result = statistics_service_cls(session).generate_and_persist(task)
        return {
            "task_id": task_id,
            "cluster_count": cluster_result.cluster_count,
            "relation_count": cluster_result.relation_count,
            "hot_topic_count": len(statistics_result.advanced.hot_topics),
        }


def _merge_dispatch_metadata(
    extra_params: dict | None,
    dispatch_payload: dict[str, object],
) -> dict:
    merged = dict(extra_params or {})
    current_dispatch = dict(merged.get("dispatch", {}))
    current_dispatch.update(dispatch_payload)
    merged["dispatch"] = current_dispatch
    return merged


def _merge_pipeline_progress(
    extra_params: dict | None,
    progress_payload: dict[str, object],
) -> dict:
    merged = dict(extra_params or {})
    current_progress = dict(merged.get("pipeline_progress", {}))
    current_progress.update(progress_payload)
    merged["pipeline_progress"] = current_progress
    return merged


def _resolve_final_task_status(
    *,
    crawl_success_count: int,
    crawl_failure_count: int,
    ai_total_count: int,
    ai_success_count: int,
    ai_failure_count: int,
) -> TaskStatus:
    if crawl_failure_count > 0 and crawl_success_count == 0:
        return TaskStatus.FAILED

    if ai_total_count > 0 and ai_success_count == 0 and ai_failure_count > 0:
        return TaskStatus.FAILED

    if crawl_failure_count > 0 or ai_failure_count > 0:
        return TaskStatus.PARTIAL_SUCCESS

    return TaskStatus.SUCCESS


def _reload_task_or_raise(session: Session, task_id: str) -> CrawlTask:
    task = session.scalar(select(CrawlTask).where(CrawlTask.id == task_id))
    if task is None:
        raise ValueError(f"Task {task_id} does not exist.")
    return task


def _persist_gate_acquire_failure(
    *,
    session_factory,
    task_id: str,
    celery_task_id: str | None,
    error_message: str,
) -> None:
    with session_factory() as session:
        task = session.scalar(select(CrawlTask).where(CrawlTask.id == task_id))
        if task is None:
            return

        if task.status in {TaskStatus.PAUSED, TaskStatus.CANCELLED}:
            return

        transition_task_status(
            task,
            to_status=TaskStatus.FAILED,
            error_message=error_message,
        )
        task.extra_params = _merge_dispatch_metadata(
            task.extra_params,
            {
                "celery_task_id": celery_task_id,
                "acknowledged_by_worker": False,
                "global_task_concurrency": settings.worker_global_task_concurrency,
            },
        )
        create_task_log(
            session,
            task=task,
            level=LogLevel.ERROR,
            stage=TaskStage.TASK,
            message=(
                "Task failed before worker execution because no global task slot "
                "was available."
            ),
            payload={
                "celery_task_id": celery_task_id,
                "detail": error_message,
                "global_task_concurrency": settings.worker_global_task_concurrency,
            },
        )
        session.commit()
