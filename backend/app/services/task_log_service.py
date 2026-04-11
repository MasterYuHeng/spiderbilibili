from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.enums import LogLevel, TaskStage
from app.models.task import CrawlTask, CrawlTaskLog


def create_task_log(
    session: Session,
    *,
    task: CrawlTask | None = None,
    task_id: str | None = None,
    level: LogLevel = LogLevel.INFO,
    stage: TaskStage = TaskStage.TASK,
    message: str,
    payload: dict | list | str | None = None,
) -> CrawlTaskLog:
    resolved_task_id = task.id if task is not None else task_id
    if resolved_task_id is None:
        raise ValueError("A task or task_id is required to create a task log.")

    log = CrawlTaskLog(
        task_id=resolved_task_id,
        level=level,
        stage=stage,
        message=message,
        payload=payload,
    )
    session.add(log)
    session.flush()
    return log


def get_task_logs(
    session: Session,
    task_id: str,
    *,
    descending: bool = False,
    limit: int | None = None,
) -> list[CrawlTaskLog]:
    statement: Select[tuple[CrawlTaskLog]] = select(CrawlTaskLog).where(
        CrawlTaskLog.task_id == task_id
    )
    if descending:
        statement = statement.order_by(
            CrawlTaskLog.created_at.desc(),
            CrawlTaskLog.updated_at.desc(),
        )
    else:
        statement = statement.order_by(
            CrawlTaskLog.created_at.asc(),
            CrawlTaskLog.updated_at.asc(),
        )

    if limit is not None:
        statement = statement.limit(limit)

    return list(session.scalars(statement).all())


def get_task_log_count(session: Session, task_id: str) -> int:
    return int(
        session.scalar(
            select(func.count()).select_from(CrawlTaskLog).where(
                CrawlTaskLog.task_id == task_id
            )
        )
        or 0
    )


def get_latest_task_log(session: Session, task_id: str) -> CrawlTaskLog | None:
    logs = get_task_logs(session, task_id, descending=True, limit=1)
    return logs[0] if logs else None
