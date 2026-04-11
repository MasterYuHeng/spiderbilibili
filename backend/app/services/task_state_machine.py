from __future__ import annotations

from collections.abc import Iterable

from app.core.exceptions import ValidationError
from app.models.base import utc_now
from app.models.enums import TaskStatus
from app.models.task import CrawlTask

TERMINAL_TASK_STATUSES = {
    TaskStatus.PARTIAL_SUCCESS,
    TaskStatus.SUCCESS,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
}

ALLOWED_TASK_STATUS_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {
        TaskStatus.QUEUED,
        TaskStatus.PAUSED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.QUEUED: {
        TaskStatus.RUNNING,
        TaskStatus.PAUSED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.RUNNING: {
        TaskStatus.PAUSED,
        TaskStatus.PARTIAL_SUCCESS,
        TaskStatus.SUCCESS,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.PAUSED: {
        TaskStatus.QUEUED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.PARTIAL_SUCCESS: {
        TaskStatus.SUCCESS,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.SUCCESS: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.CANCELLED: set(),
}


def get_allowed_transitions(status: TaskStatus) -> set[TaskStatus]:
    return set(ALLOWED_TASK_STATUS_TRANSITIONS[status])


def is_terminal_status(status: TaskStatus) -> bool:
    return status in TERMINAL_TASK_STATUSES


def ensure_valid_task_status_transition(
    current_status: TaskStatus,
    new_status: TaskStatus,
) -> None:
    if current_status == new_status:
        return

    allowed = get_allowed_transitions(current_status)
    if new_status not in allowed:
        raise ValidationError(
            message="Invalid task status transition.",
            details={
                "from_status": current_status.value,
                "to_status": new_status.value,
                "allowed_statuses": _enum_values(allowed),
            },
        )


def transition_task_status(
    task: CrawlTask,
    *,
    to_status: TaskStatus,
    error_message: str | None = None,
    clear_error: bool = True,
) -> CrawlTask:
    ensure_valid_task_status_transition(task.status, to_status)

    if to_status == TaskStatus.RUNNING and task.started_at is None:
        task.started_at = utc_now()

    if is_terminal_status(to_status):
        task.finished_at = utc_now()

    if to_status == TaskStatus.FAILED:
        task.error_message = error_message
    elif clear_error:
        task.error_message = None

    task.status = to_status
    task.updated_at = utc_now()
    return task


def _enum_values(statuses: Iterable[TaskStatus]) -> list[str]:
    return sorted(status.value for status in statuses)
