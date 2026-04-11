from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from math import ceil
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import NotFoundError, ServiceUnavailableError, ValidationError
from app.models.base import utc_now
from app.models.enums import LogLevel, TaskStage, TaskStatus
from app.models.task import CrawlTask
from app.schemas.task import (
    TaskBulkDeletePayload,
    TaskCreateRequest,
    TaskDeletePayload,
    TaskDetail,
    TaskDispatchRead,
    TaskListPayload,
    TaskLogRead,
    TaskProgressPayload,
    TaskRestorePayload,
    TaskSummary,
)
from app.services.monitoring import collect_monitoring_snapshot
from app.services.system_config_service import get_task_creation_defaults
from app.services.task_log_service import (
    create_task_log,
    get_latest_task_log,
    get_task_log_count,
    get_task_logs,
)
from app.services.task_state_machine import transition_task_status

TASK_DISPATCH_NAME = "app.worker.run_crawl_task"
ACTIVE_TASK_STATUSES = {
    TaskStatus.PENDING,
    TaskStatus.QUEUED,
    TaskStatus.RUNNING,
}
LIST_RUNTIME_STATE_CACHE_SECONDS = 5
_runtime_state_resolver_cache: tuple[datetime, RuntimeStateResolver] | None = None


@dataclass
class TaskDispatchResult:
    celery_task_id: str | None
    task_name: str = TASK_DISPATCH_NAME


class TaskControlSignal(RuntimeError):
    def __init__(self, action: str, message: str) -> None:
        super().__init__(message)
        self.action = action
        self.message = message


RuntimeStateResolver = Callable[[str | None], str]


def create_crawl_task(
    session: Session,
    payload: TaskCreateRequest,
) -> tuple[TaskDetail, TaskDispatchRead]:
    resolved_values = resolve_task_create_payload(session, payload)
    task = CrawlTask(
        keyword=resolved_values["keyword"],
        status=TaskStatus.PENDING,
        requested_video_limit=resolved_values["requested_video_limit"],
        max_pages=resolved_values["max_pages"],
        min_sleep_seconds=resolved_values["min_sleep_seconds"],
        max_sleep_seconds=resolved_values["max_sleep_seconds"],
        enable_proxy=resolved_values["enable_proxy"],
        source_ip_strategy=resolved_values["source_ip_strategy"],
        extra_params={
            "task_options": {
                "crawl_mode": resolved_values["crawl_mode"],
                "search_scope": resolved_values["search_scope"],
                "partition_tid": resolved_values["partition_tid"],
                "partition_name": resolved_values["partition_name"],
                "published_within_days": resolved_values["published_within_days"],
                "requested_video_limit": resolved_values["requested_video_limit"],
                "max_pages": resolved_values["max_pages"],
                "hot_author_total_count": resolved_values["hot_author_total_count"],
                "topic_hot_author_count": resolved_values["topic_hot_author_count"],
                "hot_author_video_limit": resolved_values["hot_author_video_limit"],
                "hot_author_summary_basis": resolved_values["hot_author_summary_basis"],
                "enable_proxy": resolved_values["enable_proxy"],
                "source_ip_strategy": resolved_values["source_ip_strategy"],
            }
        },
    )
    session.add(task)
    session.flush()

    create_task_log(
        session,
        task=task,
        stage=TaskStage.TASK,
        message="Task created and waiting for queue dispatch.",
        payload={
            "crawl_mode": resolved_values["crawl_mode"],
            "keyword": task.keyword,
            "search_scope": resolved_values["search_scope"],
            "partition_tid": resolved_values["partition_tid"],
            "partition_name": resolved_values["partition_name"],
            "published_within_days": resolved_values["published_within_days"],
            "hot_author_total_count": resolved_values["hot_author_total_count"],
            "topic_hot_author_count": resolved_values["topic_hot_author_count"],
            "hot_author_video_limit": resolved_values["hot_author_video_limit"],
            "hot_author_summary_basis": resolved_values["hot_author_summary_basis"],
        },
    )
    dispatch_generation = _advance_dispatch_generation(task)
    transition_task_status(task, to_status=TaskStatus.QUEUED)
    session.commit()

    try:
        dispatch_result = enqueue_crawl_task(task.id, dispatch_generation)
    except Exception as exc:
        transition_task_status(
            task,
            to_status=TaskStatus.FAILED,
            error_message="Failed to enqueue crawl task.",
        )
        create_task_log(
            session,
            task=task,
            level=LogLevel.ERROR,
            stage=TaskStage.TASK,
            message="Failed to enqueue crawl task.",
            payload={
                "exception_type": type(exc).__name__,
                "detail": str(exc),
            },
        )
        session.commit()
        raise ServiceUnavailableError(
            message="Failed to enqueue crawl task.",
            details={
                "task_id": task.id,
                "exception_type": type(exc).__name__,
                "detail": str(exc),
            },
        ) from exc

    task.extra_params = _merge_dispatch_metadata(
        task.extra_params,
        {
            "celery_task_id": dispatch_result.celery_task_id,
            "task_name": dispatch_result.task_name,
            "dispatch_generation": dispatch_generation,
        },
    )
    create_task_log(
        session,
        task=task,
        stage=TaskStage.TASK,
        message="Task queued successfully.",
        payload={
            "celery_task_id": dispatch_result.celery_task_id,
            "task_name": dispatch_result.task_name,
        },
    )
    session.commit()

    detail = get_task_detail(session, task.id)
    dispatch = TaskDispatchRead(
        celery_task_id=dispatch_result.celery_task_id,
        task_name=dispatch_result.task_name,
    )
    return detail, dispatch


def list_crawl_tasks(
    session: Session,
    *,
    page: int,
    page_size: int | None,
    status: TaskStatus | None = None,
    deleted_only: bool = False,
) -> TaskListPayload:
    settings = get_settings()
    resolved_page_size = resolve_page_size(
        page_size,
        settings.pagination_default_page_size,
    )
    deleted_filter = (
        CrawlTask.deleted_at.is_not(None)
        if deleted_only
        else CrawlTask.deleted_at.is_(None)
    )
    base_statement = select(CrawlTask).where(deleted_filter)
    count_statement = select(func.count()).select_from(CrawlTask).where(deleted_filter)

    if status is not None:
        base_statement = base_statement.where(CrawlTask.status == status)
        count_statement = count_statement.where(CrawlTask.status == status)

    total = int(session.scalar(count_statement) or 0)
    total_pages = ceil(total / resolved_page_size) if total else 0

    order_columns = (
        [CrawlTask.deleted_at.desc(), CrawlTask.created_at.desc(), CrawlTask.id.desc()]
        if deleted_only
        else [CrawlTask.created_at.desc(), CrawlTask.id.desc()]
    )
    statement = (
        base_statement.order_by(*order_columns)
        .offset((page - 1) * resolved_page_size)
        .limit(resolved_page_size)
    )
    tasks = list(session.scalars(statement).all())

    if not deleted_only:
        active_task_ids = [
            task.id for task in tasks if task.status in {TaskStatus.QUEUED, TaskStatus.RUNNING}
        ]
        if active_task_ids:
            reconcile_task_list_runtime_states(
                session,
                status=status,
                task_ids=active_task_ids,
                runtime_state_resolver=_get_cached_runtime_state_resolver(),
            )
            tasks = list(session.scalars(statement).all())

    return TaskListPayload(
        items=[build_task_summary(task) for task in tasks],
        page=page,
        page_size=resolved_page_size,
        total=total,
        total_pages=total_pages,
    )


def get_task_detail(session: Session, task_id: str) -> TaskDetail:
    task = get_task_or_raise(session, task_id)
    task = reconcile_task_runtime_state(session, task)
    logs = get_task_logs(session, task.id)
    log_total = len(logs)
    latest_log = logs[-1] if logs else None

    return build_task_detail(
        task,
        logs=logs,
        log_total=log_total,
        logs_truncated=False,
        current_stage=latest_log.stage.value if latest_log else TaskStage.TASK.value,
    )


def get_task_detail_with_logs(
    session: Session,
    task_id: str,
    *,
    log_limit: int | None = None,
) -> TaskDetail:
    task = get_task_or_raise(session, task_id)
    task = reconcile_task_runtime_state(session, task)
    log_total = get_task_log_count(session, task.id)

    if log_limit is None or log_total <= log_limit:
        logs = get_task_logs(session, task.id)
        logs_truncated = False
    else:
        logs = get_task_logs(session, task.id, descending=True, limit=log_limit)
        logs.reverse()
        logs_truncated = True

    latest_log = logs[-1] if logs else None

    return build_task_detail(
        task,
        logs=logs,
        log_total=log_total,
        logs_truncated=logs_truncated,
        current_stage=latest_log.stage.value if latest_log else TaskStage.TASK.value,
    )


def get_task_progress(session: Session, task_id: str) -> TaskProgressPayload:
    task = get_task_or_raise(session, task_id)
    task = reconcile_task_runtime_state(session, task)
    latest_log = get_latest_task_log(session, task.id)
    current_stage = _resolve_display_stage(task, latest_log)

    return TaskProgressPayload(
        task_id=task.id,
        status=task.status.value,
        current_stage=current_stage,
        progress_percent=calculate_task_progress(task),
        total_candidates=task.total_candidates,
        processed_videos=task.processed_videos,
        analyzed_videos=task.analyzed_videos,
        clustered_topics=task.clustered_topics,
        started_at=task.started_at,
        finished_at=task.finished_at,
        error_message=task.error_message,
        extra_params=task.extra_params,
        latest_log=build_task_log_read(latest_log) if latest_log is not None else None,
    )


def get_task_or_raise(session: Session, task_id: str) -> CrawlTask:
    statement = select(CrawlTask).where(CrawlTask.id == task_id, CrawlTask.deleted_at.is_(None))
    task = session.scalar(statement)
    if task is None:
        raise NotFoundError(
            message="Task not found.",
            details={"task_id": task_id},
        )
    return task


def get_any_task_or_raise(session: Session, task_id: str) -> CrawlTask:
    task = session.scalar(select(CrawlTask).where(CrawlTask.id == task_id))
    if task is None:
        raise NotFoundError(
            message="Task not found.",
            details={"task_id": task_id},
        )
    return task


def get_trashed_task_or_raise(session: Session, task_id: str) -> CrawlTask:
    statement = select(CrawlTask).where(
        CrawlTask.id == task_id,
        CrawlTask.deleted_at.is_not(None),
    )
    task = session.scalar(statement)
    if task is None:
        raise NotFoundError(
            message="Task not found in trash.",
            details={"task_id": task_id},
        )
    return task


def reconcile_task_runtime_state(
    session: Session,
    task: CrawlTask,
    *,
    runtime_state_resolver: RuntimeStateResolver | None = None,
) -> CrawlTask:
    if not _should_reconcile_running_task(task):
        return task

    if not _is_task_runtime_stale(task):
        return task

    resolver = runtime_state_resolver or _get_celery_task_runtime_state
    celery_task_id = _get_dispatched_celery_task_id(task)
    runtime_state = resolver(celery_task_id)
    if _is_runtime_state_active_for_task(task, runtime_state):
        return task

    session.refresh(task)
    if not _should_reconcile_running_task(task):
        return task

    celery_task_id = _get_dispatched_celery_task_id(task)
    runtime_state = resolver(celery_task_id)
    if _is_runtime_state_active_for_task(task, runtime_state):
        return task

    previous_status = task.status.value
    transition_task_status(
        task,
        to_status=TaskStatus.FAILED,
        error_message=_build_stale_task_error_message(task),
    )
    create_task_log(
        session,
        task=task,
        level=LogLevel.ERROR,
        stage=TaskStage.TASK,
        message=_build_stale_task_log_message(previous_status),
        payload={
            "celery_task_id": celery_task_id,
            "stale_after_seconds": get_settings().worker_task_stale_after_seconds,
            "runtime_state": runtime_state,
            "previous_status": previous_status,
        },
    )
    session.commit()
    session.refresh(task)
    return task


def resolve_task_create_payload(
    session: Session,
    payload: TaskCreateRequest,
) -> dict[str, Any]:
    settings = get_settings()
    defaults = get_task_creation_defaults(session, settings)

    requested_video_limit = (
        payload.requested_video_limit or defaults["requested_video_limit"]
    )
    max_pages = payload.max_pages or defaults["max_pages"]
    hot_author_total_count = int(payload.hot_author_total_count or 0)
    topic_hot_author_count = int(payload.topic_hot_author_count or 0)
    hot_author_video_limit = int(payload.hot_author_video_limit or 10)
    hot_author_summary_basis = payload.hot_author_summary_basis or "time"
    enable_proxy = (
        payload.enable_proxy
        if payload.enable_proxy is not None
        else bool(defaults["enable_proxy"])
    )
    source_ip_strategy = resolve_source_ip_strategy(
        enable_proxy=enable_proxy,
        requested_strategy=payload.source_ip_strategy,
        default_strategy=str(defaults["source_ip_strategy"]),
    )
    min_sleep_seconds = payload.min_sleep_seconds or defaults["min_sleep_seconds"]
    max_sleep_seconds = payload.max_sleep_seconds or defaults["max_sleep_seconds"]
    crawl_mode = payload.crawl_mode or "keyword"
    search_scope = payload.search_scope or "site"
    partition_tid = payload.partition_tid if search_scope == "partition" else None
    partition_name = payload.partition_name if search_scope == "partition" else None
    published_within_days = payload.published_within_days

    if requested_video_limit > settings.crawler_max_videos:
        raise ValidationError(
            message="requested_video_limit exceeds the configured maximum.",
            details={
                "requested_video_limit": requested_video_limit,
                "max_allowed": settings.crawler_max_videos,
            },
        )

    if max_pages > settings.crawler_max_pages:
        raise ValidationError(
            message="max_pages exceeds the configured maximum.",
            details={
                "max_pages": max_pages,
                "max_allowed": settings.crawler_max_pages,
            },
        )

    if min_sleep_seconds > max_sleep_seconds:
        raise ValidationError(
            message="min_sleep_seconds cannot be greater than max_sleep_seconds.",
            details={
                "min_sleep_seconds": min_sleep_seconds,
                "max_sleep_seconds": max_sleep_seconds,
            },
        )

    return {
        "crawl_mode": crawl_mode,
        "keyword": (payload.keyword or "").strip(),
        "search_scope": search_scope,
        "partition_tid": partition_tid,
        "partition_name": partition_name,
        "published_within_days": published_within_days,
        "requested_video_limit": int(requested_video_limit),
        "max_pages": int(max_pages),
        "hot_author_total_count": hot_author_total_count,
        "topic_hot_author_count": topic_hot_author_count,
        "hot_author_video_limit": hot_author_video_limit,
        "hot_author_summary_basis": hot_author_summary_basis,
        "enable_proxy": enable_proxy,
        "source_ip_strategy": source_ip_strategy,
        "min_sleep_seconds": quantize_decimal(min_sleep_seconds),
        "max_sleep_seconds": quantize_decimal(max_sleep_seconds),
    }


def resolve_page_size(page_size: int | None, default_page_size: int) -> int:
    settings = get_settings()
    resolved_page_size = page_size or default_page_size
    if resolved_page_size > settings.pagination_max_page_size:
        raise ValidationError(
            message="page_size exceeds the configured maximum.",
            details={
                "page_size": resolved_page_size,
                "max_allowed": settings.pagination_max_page_size,
            },
        )
    return resolved_page_size


def resolve_source_ip_strategy(
    *,
    enable_proxy: bool,
    requested_strategy: str | None,
    default_strategy: str,
) -> str:
    if requested_strategy is not None:
        strategy = requested_strategy
    elif enable_proxy:
        strategy = "proxy_pool"
    else:
        strategy = default_strategy or "local_sleep"

    if not enable_proxy and strategy != "local_sleep":
        raise ValidationError(
            message="Non-proxy tasks must use the local_sleep IP strategy.",
            details={
                "enable_proxy": enable_proxy,
                "source_ip_strategy": strategy,
            },
        )

    return strategy


def enqueue_crawl_task(
    task_id: str,
    dispatch_generation: int | None = None,
) -> TaskDispatchResult:
    from app.worker import celery_app

    async_result = celery_app.send_task(
        TASK_DISPATCH_NAME,
        args=[task_id, dispatch_generation],
    )
    return TaskDispatchResult(
        celery_task_id=async_result.id,
        task_name=TASK_DISPATCH_NAME,
    )


def retry_crawl_task(
    session: Session,
    task_id: str,
) -> tuple[TaskDetail, TaskDispatchRead]:
    source_task = get_task_or_raise(session, task_id)
    if source_task.status not in {
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
        TaskStatus.PARTIAL_SUCCESS,
    }:
        raise ValidationError(
            message="Only failed, cancelled, or partial_success tasks can be retried.",
            details={
                "task_id": source_task.id,
                "status": source_task.status.value,
            },
        )

    task_options = dict((source_task.extra_params or {}).get("task_options", {}))
    new_task = CrawlTask(
        keyword=source_task.keyword,
        status=TaskStatus.PENDING,
        requested_video_limit=source_task.requested_video_limit,
        max_pages=source_task.max_pages,
        min_sleep_seconds=source_task.min_sleep_seconds,
        max_sleep_seconds=source_task.max_sleep_seconds,
        enable_proxy=source_task.enable_proxy,
        source_ip_strategy=source_task.source_ip_strategy,
        extra_params={
            "task_options": {
                "crawl_mode": task_options.get("crawl_mode", "keyword"),
                "search_scope": task_options.get("search_scope", "site"),
                "partition_tid": task_options.get("partition_tid"),
                "partition_name": task_options.get("partition_name"),
                "published_within_days": task_options.get("published_within_days"),
                "requested_video_limit": task_options.get(
                    "requested_video_limit",
                    source_task.requested_video_limit,
                ),
                "max_pages": task_options.get("max_pages", source_task.max_pages),
                "hot_author_total_count": task_options.get(
                    "hot_author_total_count",
                    0,
                ),
                "topic_hot_author_count": task_options.get(
                    "topic_hot_author_count",
                    0,
                ),
                "hot_author_video_limit": task_options.get(
                    "hot_author_video_limit",
                    10,
                ),
                "hot_author_summary_basis": task_options.get(
                    "hot_author_summary_basis",
                    "time",
                ),
                "enable_proxy": task_options.get(
                    "enable_proxy",
                    source_task.enable_proxy,
                ),
                "source_ip_strategy": task_options.get(
                    "source_ip_strategy",
                    source_task.source_ip_strategy,
                ),
            },
            "retry_context": {
                "retry_of_task_id": source_task.id,
                "retry_of_status": source_task.status.value,
            },
        },
    )
    session.add(new_task)
    session.flush()

    create_task_log(
        session,
        task=new_task,
        stage=TaskStage.TASK,
        message="Retry task created and waiting for queue dispatch.",
        payload={
            "keyword": new_task.keyword,
            "retry_of_task_id": source_task.id,
        },
    )
    dispatch_generation = _advance_dispatch_generation(new_task)
    transition_task_status(new_task, to_status=TaskStatus.QUEUED)
    session.commit()

    try:
        dispatch_result = enqueue_crawl_task(new_task.id, dispatch_generation)
    except Exception as exc:
        transition_task_status(
            new_task,
            to_status=TaskStatus.FAILED,
            error_message="Failed to enqueue retry crawl task.",
        )
        create_task_log(
            session,
            task=new_task,
            level=LogLevel.ERROR,
            stage=TaskStage.TASK,
            message="Failed to enqueue retry crawl task.",
            payload={
                "exception_type": type(exc).__name__,
                "detail": str(exc),
                "retry_of_task_id": source_task.id,
            },
        )
        session.commit()
        raise ServiceUnavailableError(
            message="Failed to enqueue retry crawl task.",
            details={
                "task_id": new_task.id,
                "retry_of_task_id": source_task.id,
                "exception_type": type(exc).__name__,
                "detail": str(exc),
            },
        ) from exc

    new_task.extra_params = _merge_dispatch_metadata(
        new_task.extra_params,
        {
            "celery_task_id": dispatch_result.celery_task_id,
            "task_name": dispatch_result.task_name,
            "dispatch_generation": dispatch_generation,
        },
    )
    create_task_log(
        session,
        task=new_task,
        stage=TaskStage.TASK,
        message="Retry task queued successfully.",
        payload={
            "celery_task_id": dispatch_result.celery_task_id,
            "task_name": dispatch_result.task_name,
            "retry_of_task_id": source_task.id,
        },
    )
    session.commit()

    detail = get_task_detail(session, new_task.id)
    dispatch = TaskDispatchRead(
        celery_task_id=dispatch_result.celery_task_id,
        task_name=dispatch_result.task_name,
    )
    return detail, dispatch


def pause_crawl_task(session: Session, task_id: str) -> TaskDetail:
    task = get_task_or_raise(session, task_id)
    task = reconcile_task_runtime_state(session, task)
    if task.status == TaskStatus.PAUSED:
        return get_task_detail(session, task.id)
    if task.status not in {TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.RUNNING}:
        raise ValidationError(
            message="Only pending, queued, or running tasks can be paused.",
            details={"task_id": task.id, "status": task.status.value},
        )

    _advance_dispatch_generation(task)
    task.extra_params = _merge_control_metadata(
        task.extra_params,
        {"requested_action": "pause", "requested_at": utc_now().isoformat()},
    )
    transition_task_status(task, to_status=TaskStatus.PAUSED)
    create_task_log(
        session,
        task=task,
        stage=TaskStage.TASK,
        message="Pause requested for the task.",
        payload={"requested_action": "pause"},
    )
    session.commit()
    return get_task_detail(session, task.id)


def cancel_crawl_task(session: Session, task_id: str) -> TaskDetail:
    task = get_task_or_raise(session, task_id)
    task = reconcile_task_runtime_state(session, task)
    if task.status not in {
        TaskStatus.PENDING,
        TaskStatus.QUEUED,
        TaskStatus.RUNNING,
        TaskStatus.PAUSED,
    }:
        raise ValidationError(
            message="Only pending, queued, running, or paused tasks can be cancelled.",
            details={"task_id": task.id, "status": task.status.value},
        )

    _advance_dispatch_generation(task)
    task.extra_params = _merge_control_metadata(
        task.extra_params,
        {"requested_action": "cancel", "requested_at": utc_now().isoformat()},
    )
    transition_task_status(
        task,
        to_status=TaskStatus.CANCELLED,
    )
    task.error_message = "Task was cancelled by user."
    create_task_log(
        session,
        task=task,
        stage=TaskStage.TASK,
        message="Cancellation requested for the task.",
        payload={"requested_action": "cancel"},
    )
    session.commit()
    return get_task_detail(session, task.id)


def resume_crawl_task(
    session: Session,
    task_id: str,
) -> tuple[TaskDetail, TaskDispatchRead]:
    task = get_task_or_raise(session, task_id)
    if task.status != TaskStatus.PAUSED:
        raise ValidationError(
            message="Only paused tasks can be resumed.",
            details={"task_id": task.id, "status": task.status.value},
        )

    dispatch_generation = _advance_dispatch_generation(task)
    task.extra_params = _clear_control_metadata(task.extra_params)
    transition_task_status(task, to_status=TaskStatus.QUEUED)
    create_task_log(
        session,
        task=task,
        stage=TaskStage.TASK,
        message="Paused task is being resumed and re-queued.",
        payload={"dispatch_generation": dispatch_generation},
    )
    session.commit()

    try:
        dispatch_result = enqueue_crawl_task(task.id, dispatch_generation)
    except Exception as exc:
        transition_task_status(
            task,
            to_status=TaskStatus.FAILED,
            error_message="Failed to enqueue resumed crawl task.",
        )
        create_task_log(
            session,
            task=task,
            level=LogLevel.ERROR,
            stage=TaskStage.TASK,
            message="Failed to enqueue resumed crawl task.",
            payload={
                "exception_type": type(exc).__name__,
                "detail": str(exc),
            },
        )
        session.commit()
        raise ServiceUnavailableError(
            message="Failed to enqueue resumed crawl task.",
            details={
                "task_id": task.id,
                "exception_type": type(exc).__name__,
                "detail": str(exc),
            },
        ) from exc

    task.extra_params = _merge_dispatch_metadata(
        task.extra_params,
        {
            "celery_task_id": dispatch_result.celery_task_id,
            "task_name": dispatch_result.task_name,
            "dispatch_generation": dispatch_generation,
        },
    )
    create_task_log(
        session,
        task=task,
        stage=TaskStage.TASK,
        message="Paused task queued successfully after resume.",
        payload={
            "celery_task_id": dispatch_result.celery_task_id,
            "task_name": dispatch_result.task_name,
            "dispatch_generation": dispatch_generation,
        },
    )
    session.commit()

    detail = get_task_detail(session, task.id)
    dispatch = TaskDispatchRead(
        celery_task_id=dispatch_result.celery_task_id,
        task_name=dispatch_result.task_name,
    )
    return detail, dispatch


def delete_crawl_task(session: Session, task_id: str) -> TaskDeletePayload:
    task = get_task_or_raise(session, task_id)
    task = reconcile_task_runtime_state(session, task)
    if task.status in ACTIVE_TASK_STATUSES or task.status == TaskStatus.PAUSED:
        _advance_dispatch_generation(task)
        task.extra_params = _merge_control_metadata(
            task.extra_params,
            {"requested_action": "cancel", "requested_at": utc_now().isoformat()},
        )
        transition_task_status(task, to_status=TaskStatus.CANCELLED)
        task.error_message = "Task was removed to trash by user."
        create_task_log(
            session,
            task=task,
            stage=TaskStage.TASK,
            message="Task moved to trash and cancelled.",
            payload={"requested_action": "trash"},
        )
    task.deleted_at = utc_now()
    session.commit()
    return TaskDeletePayload(task_id=task_id, deleted=True, deleted_at=task.deleted_at)


def delete_all_crawl_tasks(session: Session) -> TaskBulkDeletePayload:
    task_ids = list(
        session.scalars(
            select(CrawlTask.id)
            .where(CrawlTask.deleted_at.is_(None))
            .order_by(CrawlTask.created_at.desc(), CrawlTask.id.desc())
        ).all()
    )

    deleted_count = 0

    for task_id in task_ids:
        task = get_task_or_raise(session, task_id)
        task = reconcile_task_runtime_state(session, task)
        if task.status in ACTIVE_TASK_STATUSES or task.status == TaskStatus.PAUSED:
            _advance_dispatch_generation(task)
            task.extra_params = _merge_control_metadata(
                task.extra_params,
                {"requested_action": "cancel", "requested_at": utc_now().isoformat()},
            )
            transition_task_status(task, to_status=TaskStatus.CANCELLED)
            task.error_message = "Task was removed to trash by user."
        task.deleted_at = utc_now()
        deleted_count += 1

    session.commit()
    return TaskBulkDeletePayload(
        deleted_count=deleted_count,
        blocked_count=0,
    )


def restore_crawl_task(session: Session, task_id: str) -> TaskRestorePayload:
    task = get_trashed_task_or_raise(session, task_id)
    task.deleted_at = None
    session.commit()
    return TaskRestorePayload(task_id=task_id, restored=True)


def permanently_delete_crawl_task(session: Session, task_id: str) -> TaskDeletePayload:
    task = get_trashed_task_or_raise(session, task_id)
    session.delete(task)
    session.commit()
    return TaskDeletePayload(task_id=task_id, deleted=True)


def empty_task_trash(session: Session) -> TaskBulkDeletePayload:
    tasks = list(
        session.scalars(
            select(CrawlTask).where(CrawlTask.deleted_at.is_not(None))
        ).all()
    )

    for task in tasks:
        session.delete(task)

    session.commit()
    return TaskBulkDeletePayload(deleted_count=len(tasks))


def quantize_decimal(value: float | Decimal) -> Decimal:
    decimal_value = Decimal(str(value))
    return decimal_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_task_progress(task: CrawlTask) -> int:
    if task.status in {TaskStatus.SUCCESS, TaskStatus.PARTIAL_SUCCESS}:
        if _has_complete_terminal_artifacts(task):
            return 100
        if not _has_ready_analysis_snapshot(task):
            return 92
        if not _has_ready_report_snapshot(task):
            return 98
        return 100

    current_phase = _resolve_task_progress_phase(task)
    effective_total = _resolve_progress_target(task)
    processed_videos = min(_resolve_progress_processed_videos(task), effective_total)
    if current_phase == TaskStage.REPORT.value:
        return 98

    if current_phase == TaskStage.AUTHOR.value:
        return 92

    if current_phase == TaskStage.TOPIC.value:
        return 85

    if current_phase == TaskStage.AI.value:
        ai_total = _resolve_ai_target_count(task) or effective_total
        ai_processed = min(int(task.analyzed_videos), ai_total) if ai_total > 0 else 0
        if ai_total > 0 and ai_processed > 0:
            return min(60 + int((ai_processed / ai_total) * 20), 79)
        return 60

    if current_phase in {TaskStage.TEXT.value, TaskStage.SUBTITLE.value}:
        return 60

    if current_phase == TaskStage.DETAIL.value and effective_total > 0:
        if processed_videos > 0:
            return min(int((processed_videos / effective_total) * 100), 59)
        return 5

    if effective_total > 0 and processed_videos > 0:
        return min(int((processed_videos / effective_total) * 100), 59)

    if task.status == TaskStatus.RUNNING:
        if effective_total > 0 or _is_crawl_pipeline_in_progress(task):
            return 5
        return 1

    return 0


def _resolve_progress_target(task: CrawlTask) -> int:
    crawl_progress = _get_task_crawl_progress(task)
    selected_count = int(crawl_progress.get("selected_count") or 0)
    requested_video_limit = (
        task.requested_video_limit or selected_count or task.total_candidates
    )
    candidate_total = task.total_candidates or selected_count or requested_video_limit
    return min(candidate_total, requested_video_limit) if requested_video_limit else 0


def _resolve_progress_processed_videos(task: CrawlTask) -> int:
    crawl_progress = _get_task_crawl_progress(task)
    detail_processed_count = int(crawl_progress.get("detail_processed_count") or 0)
    return max(int(task.processed_videos), detail_processed_count)


def _is_crawl_pipeline_in_progress(task: CrawlTask) -> bool:
    current_phase = _resolve_task_progress_phase(task)
    return current_phase in {
        TaskStage.DETAIL.value,
        TaskStage.TEXT.value,
        TaskStage.SUBTITLE.value,
        TaskStage.AI.value,
        TaskStage.TOPIC.value,
        TaskStage.AUTHOR.value,
        TaskStage.REPORT.value,
        TaskStage.EXPORT.value,
    }


def _get_task_crawl_progress(task: CrawlTask) -> dict[str, Any]:
    extra_params = task.extra_params if isinstance(task.extra_params, dict) else {}
    crawl_progress = extra_params.get("crawl_progress")
    return crawl_progress if isinstance(crawl_progress, dict) else {}


def _get_task_pipeline_progress(task: CrawlTask) -> dict[str, Any]:
    extra_params = task.extra_params if isinstance(task.extra_params, dict) else {}
    pipeline_progress = extra_params.get("pipeline_progress")
    return pipeline_progress if isinstance(pipeline_progress, dict) else {}


def _resolve_task_progress_phase(task: CrawlTask) -> str:
    pipeline_progress = _get_task_pipeline_progress(task)
    pipeline_phase = str(pipeline_progress.get("current_phase") or "").strip().lower()
    if pipeline_phase:
        return pipeline_phase

    crawl_progress = _get_task_crawl_progress(task)
    crawl_phase = str(crawl_progress.get("current_phase") or "").strip().lower()
    if crawl_phase:
        return crawl_phase

    return ""


def _resolve_ai_target_count(task: CrawlTask) -> int:
    extra_params = task.extra_params if isinstance(task.extra_params, dict) else {}
    ai_stats = extra_params.get("ai_stats")
    if not isinstance(ai_stats, dict):
        return 0
    try:
        return int(ai_stats.get("target_video_count") or 0)
    except (TypeError, ValueError):
        return 0


def _resolve_display_stage(task: CrawlTask, latest_log) -> str:
    if task.status in {TaskStatus.SUCCESS, TaskStatus.PARTIAL_SUCCESS}:
        if not _has_ready_analysis_snapshot(task):
            return TaskStage.AUTHOR.value
        if not _has_ready_report_snapshot(task):
            return TaskStage.REPORT.value

    if latest_log is not None:
        return latest_log.stage.value

    phase = _resolve_task_progress_phase(task)
    if phase and phase != "completed":
        return phase

    return TaskStage.TASK.value


def _has_complete_terminal_artifacts(task: CrawlTask) -> bool:
    return _has_ready_analysis_snapshot(task) and _has_ready_report_snapshot(task)


def _has_ready_analysis_snapshot(task: CrawlTask) -> bool:
    snapshot = _get_task_snapshot(task, "analysis_snapshot")
    if snapshot is None:
        return False

    required_snapshot_keys = {"generated_at", "summary", "topics", "advanced", "top_videos"}
    if not required_snapshot_keys.issubset(snapshot):
        return False

    summary = snapshot.get("summary")
    topics = snapshot.get("topics")
    advanced = snapshot.get("advanced")
    top_videos = snapshot.get("top_videos")
    if not isinstance(summary, dict) or not isinstance(topics, list):
        return False
    if not isinstance(advanced, dict) or not isinstance(top_videos, list):
        return False

    required_advanced_keys = {
        "topic_insights",
        "video_insights",
        "recommendations",
        "popular_authors",
        "topic_hot_authors",
        "author_analysis_notes",
        "data_notes",
        "metric_definitions",
    }
    if not required_advanced_keys.issubset(advanced):
        return False

    return all(isinstance(advanced.get(key), list) for key in required_advanced_keys)


def _has_ready_report_snapshot(task: CrawlTask) -> bool:
    snapshot = _get_task_snapshot(task, "report_snapshot")
    if snapshot is None:
        return False

    required_snapshot_keys = {
        "generated_at",
        "sections",
        "ai_outputs",
        "featured_videos",
        "popular_authors",
        "topic_hot_authors",
        "report_markdown",
    }
    if not required_snapshot_keys.issubset(snapshot):
        return False

    if not isinstance(snapshot.get("sections"), list):
        return False
    if not isinstance(snapshot.get("ai_outputs"), list):
        return False
    if not isinstance(snapshot.get("featured_videos"), list):
        return False
    if not isinstance(snapshot.get("popular_authors"), list):
        return False
    if not isinstance(snapshot.get("topic_hot_authors"), list):
        return False

    report_markdown = snapshot.get("report_markdown")
    return isinstance(report_markdown, str) and bool(report_markdown.strip())


def _get_task_snapshot(task: CrawlTask, key: str) -> dict[str, Any] | None:
    extra_params = task.extra_params if isinstance(task.extra_params, dict) else {}
    snapshot = extra_params.get(key)
    return snapshot if isinstance(snapshot, dict) else None


def reconcile_task_list_runtime_states(
    session: Session,
    *,
    status: TaskStatus | None = None,
    task_ids: list[str] | None = None,
    runtime_state_resolver: RuntimeStateResolver | None = None,
) -> None:
    candidate_statuses = {TaskStatus.QUEUED, TaskStatus.RUNNING}
    if status is not None:
        if status not in candidate_statuses:
            return
        candidate_statuses = {status}

    statement = select(CrawlTask).where(
        CrawlTask.deleted_at.is_(None),
        CrawlTask.status.in_(candidate_statuses),
    )
    if task_ids:
        statement = statement.where(CrawlTask.id.in_(task_ids))

    tasks = list(session.scalars(statement).all())
    if not tasks:
        return

    resolver = runtime_state_resolver or _build_celery_runtime_state_resolver()
    for task in tasks:
        reconcile_task_runtime_state(
            session,
            task,
            runtime_state_resolver=resolver,
        )


def _ensure_task_is_deletable(task: CrawlTask) -> None:
    return


def _should_reconcile_running_task(task: CrawlTask) -> bool:
    return task.status in {TaskStatus.QUEUED, TaskStatus.RUNNING}


def _is_task_runtime_stale(task: CrawlTask) -> bool:
    updated_at = _normalize_task_timestamp(task.updated_at or task.started_at)
    if updated_at is None:
        return False
    stale_after = max(30, int(get_settings().worker_task_stale_after_seconds))
    return updated_at + timedelta(seconds=stale_after) < utc_now()


def _get_dispatched_celery_task_id(task: CrawlTask) -> str | None:
    extra_params = task.extra_params if isinstance(task.extra_params, dict) else {}
    dispatch = extra_params.get("dispatch")
    if not isinstance(dispatch, dict):
        return None
    celery_task_id = dispatch.get("celery_task_id")
    return str(celery_task_id).strip() if celery_task_id else None


def _get_celery_task_runtime_state(celery_task_id: str | None) -> str:
    return _build_celery_runtime_state_resolver()(celery_task_id)


def _build_celery_runtime_state_resolver() -> RuntimeStateResolver:
    active_ids: set[str] = set()
    reserved_ids: set[str] = set()
    scheduled_ids: set[str] = set()

    try:
        from app.worker import celery_app

        inspector = celery_app.control.inspect(timeout=0.2)
        active = inspector.active() or {}
        reserved = inspector.reserved() or {}
        scheduled = inspector.scheduled() or {}
    except Exception:
        fallback_state = _get_fallback_runtime_state()

        def _fallback_resolver(celery_task_id: str | None) -> str:
            if not celery_task_id:
                return "missing"
            return fallback_state

        return _fallback_resolver

    active_ids.update(_extract_celery_task_ids(active))
    reserved_ids.update(_extract_celery_task_ids(reserved))
    scheduled_ids.update(_extract_scheduled_celery_task_ids(scheduled))

    def _resolver(celery_task_id: str | None) -> str:
        if not celery_task_id:
            return "missing"
        if celery_task_id in active_ids:
            return "active"
        if celery_task_id in reserved_ids:
            return "reserved"
        if celery_task_id in scheduled_ids:
            return "scheduled"
        return "missing"

    return _resolver


def _get_cached_runtime_state_resolver() -> RuntimeStateResolver:
    global _runtime_state_resolver_cache

    now = utc_now()
    if _runtime_state_resolver_cache is not None:
        expires_at, resolver = _runtime_state_resolver_cache
        if expires_at > now:
            return resolver

    resolver = _build_celery_runtime_state_resolver()
    _runtime_state_resolver_cache = (
        now + timedelta(seconds=LIST_RUNTIME_STATE_CACHE_SECONDS),
        resolver,
    )
    return resolver


def _extract_celery_task_ids(payload: Any) -> set[str]:
    task_ids: set[str] = set()
    if not isinstance(payload, dict):
        return task_ids

    for tasks in payload.values():
        for item in tasks or []:
            if not isinstance(item, dict):
                continue
            task_id = str(item.get("id") or "").strip()
            if task_id:
                task_ids.add(task_id)
    return task_ids


def _extract_scheduled_celery_task_ids(payload: Any) -> set[str]:
    task_ids: set[str] = set()
    if not isinstance(payload, dict):
        return task_ids

    for tasks in payload.values():
        for item in tasks or []:
            if not isinstance(item, dict):
                continue
            request = item.get("request")
            if not isinstance(request, dict):
                continue
            task_id = str(request.get("id") or "").strip()
            if task_id:
                task_ids.add(task_id)
    return task_ids


def _get_fallback_runtime_state() -> str:
    try:
        snapshot = collect_monitoring_snapshot()
    except Exception:
        return "unknown"

    if snapshot.active_workers > 0:
        return "unknown"
    return "missing"


def _is_runtime_state_active_for_task(
    task: CrawlTask,
    runtime_state: str,
) -> bool:
    if task.status == TaskStatus.RUNNING:
        return runtime_state == "active"
    if task.status == TaskStatus.QUEUED:
        return runtime_state in {"active", "reserved", "scheduled"}
    return False


def _build_stale_task_error_message(task: CrawlTask) -> str:
    if task.status == TaskStatus.QUEUED:
        return (
            "Task stayed queued for too long because no worker accepted it. "
            "Please start a worker and retry the task."
        )

    return (
        "Task execution became stale because no worker is actively processing it. "
        "Please retry the task."
    )


def _build_stale_task_log_message(previous_status: str) -> str:
    if previous_status == TaskStatus.QUEUED.value:
        return "Marked queued task as failed after no worker accepted it in time."

    return "Marked task as failed after detecting a stale worker execution."


def _normalize_task_timestamp(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=utc_now().tzinfo)
    return value


def assert_task_execution_allowed(
    session: Session,
    task_id: str,
    *,
    expected_dispatch_generation: int | None = None,
) -> CrawlTask:
    task = get_any_task_or_raise(session, task_id)
    if task.deleted_at is not None:
        raise TaskControlSignal("cancel", "Task was deleted by user.")
    if expected_dispatch_generation is not None:
        current_generation = _get_dispatch_generation(task)
        if current_generation != expected_dispatch_generation:
            raise TaskControlSignal(
                "superseded",
                "Task dispatch has been superseded by a newer queue instruction.",
            )

    if task.status == TaskStatus.PAUSED:
        raise TaskControlSignal("pause", "Task was paused by user.")
    if task.status == TaskStatus.CANCELLED:
        raise TaskControlSignal("cancel", "Task was cancelled by user.")
    return task


def _advance_dispatch_generation(task: CrawlTask) -> int:
    next_generation = _get_dispatch_generation(task) + 1
    task.extra_params = _merge_dispatch_metadata(
        task.extra_params,
        {"dispatch_generation": next_generation},
    )
    return next_generation


def _get_dispatch_generation(task: CrawlTask) -> int:
    extra_params = task.extra_params if isinstance(task.extra_params, dict) else {}
    dispatch = extra_params.get("dispatch")
    if not isinstance(dispatch, dict):
        return 0
    value = dispatch.get("dispatch_generation")
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _merge_control_metadata(
    extra_params: dict[str, Any] | None,
    control_payload: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(extra_params or {})
    current_control = dict(merged.get("control", {}))
    current_control.update(control_payload)
    merged["control"] = current_control
    return merged


def _clear_control_metadata(
    extra_params: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(extra_params or {})
    if "control" in merged:
        merged.pop("control")
    return merged


def build_task_summary(task: CrawlTask) -> TaskSummary:
    return TaskSummary(
        id=task.id,
        keyword=task.keyword,
        status=task.status.value,
        requested_video_limit=task.requested_video_limit,
        max_pages=task.max_pages,
        min_sleep_seconds=float(task.min_sleep_seconds),
        max_sleep_seconds=float(task.max_sleep_seconds),
        enable_proxy=task.enable_proxy,
        source_ip_strategy=task.source_ip_strategy,
        total_candidates=task.total_candidates,
        processed_videos=task.processed_videos,
        analyzed_videos=task.analyzed_videos,
        clustered_topics=task.clustered_topics,
        started_at=task.started_at,
        finished_at=task.finished_at,
        error_message=task.error_message,
        created_at=task.created_at,
        updated_at=task.updated_at,
        deleted_at=task.deleted_at,
    )


def build_task_detail(
    task: CrawlTask,
    *,
    logs: list,
    log_total: int,
    logs_truncated: bool,
    current_stage: str,
) -> TaskDetail:
    summary = build_task_summary(task)
    latest_log = logs[-1] if logs else None
    return TaskDetail(
        **summary.model_dump(),
        extra_params=task.extra_params,
        current_stage=_resolve_display_stage(task, latest_log),
        progress_percent=calculate_task_progress(task),
        log_total=log_total,
        logs_truncated=logs_truncated,
        logs=[build_task_log_read(log) for log in logs],
    )


def build_task_log_read(log) -> TaskLogRead:
    return TaskLogRead(
        id=log.id,
        level=log.level.value,
        stage=log.stage.value,
        message=log.message,
        payload=log.payload,
        created_at=log.created_at,
    )


def _merge_dispatch_metadata(
    extra_params: dict[str, Any] | None,
    dispatch_payload: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(extra_params or {})
    current_dispatch = dict(merged.get("dispatch", {}))
    current_dispatch.update(dispatch_payload)
    merged["dispatch"] = current_dispatch
    return merged
