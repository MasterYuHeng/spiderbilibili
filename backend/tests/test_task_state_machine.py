from app.core.exceptions import ValidationError
from app.models.enums import TaskStatus
from app.models.task import CrawlTask
from app.services.task_service import calculate_task_progress
from app.services.task_state_machine import transition_task_status


def test_task_state_machine_sets_started_and_finished_timestamps() -> None:
    task = CrawlTask(keyword="ai", status=TaskStatus.PENDING)

    transition_task_status(task, to_status=TaskStatus.QUEUED)
    transition_task_status(task, to_status=TaskStatus.RUNNING)
    transition_task_status(task, to_status=TaskStatus.SUCCESS)

    assert task.started_at is not None
    assert task.finished_at is not None
    assert task.status == TaskStatus.SUCCESS


def test_task_state_machine_allows_pausing_and_requeueing() -> None:
    task = CrawlTask(keyword="ai", status=TaskStatus.PENDING)

    transition_task_status(task, to_status=TaskStatus.QUEUED)
    transition_task_status(task, to_status=TaskStatus.RUNNING)
    transition_task_status(task, to_status=TaskStatus.PAUSED)
    transition_task_status(task, to_status=TaskStatus.QUEUED)

    assert task.started_at is not None
    assert task.finished_at is None
    assert task.status == TaskStatus.QUEUED


def test_task_state_machine_rejects_invalid_transition() -> None:
    task = CrawlTask(keyword="ai", status=TaskStatus.PENDING)

    try:
        transition_task_status(task, to_status=TaskStatus.SUCCESS)
    except ValidationError as exc:
        assert exc.code == "validation_error"
        assert exc.details["from_status"] == "pending"
        assert exc.details["to_status"] == "success"
    else:
        raise AssertionError("Expected invalid task status transition to fail.")


def test_failed_task_progress_keeps_actual_completion_ratio() -> None:
    task = CrawlTask(
        keyword="ai",
        status=TaskStatus.FAILED,
        total_candidates=10,
        processed_videos=4,
    )

    assert calculate_task_progress(task) == 40
