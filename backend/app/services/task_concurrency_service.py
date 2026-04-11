from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from redis import Redis
from redis.exceptions import RedisError, WatchError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.models.enums import TaskStatus
from app.models.task import CrawlTask


@dataclass(slots=True)
class TaskExecutionLease:
    gate: "TaskExecutionGate"
    owner_id: str
    acquired: bool = True

    def release(self) -> None:
        if not self.acquired:
            return
        self.gate.release(self.owner_id)
        self.acquired = False

    def __enter__(self) -> "TaskExecutionLease":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


class RedisPipelineProtocol(Protocol):
    def __enter__(self) -> "RedisPipelineProtocol": ...

    def __exit__(self, exc_type, exc, tb) -> None: ...

    def watch(self, key: str) -> object: ...

    def zremrangebyscore(self, key: str, minimum: str, maximum: float) -> object: ...

    def zcard(self, key: str) -> object: ...

    def zscore(self, key: str, owner_id: str) -> object: ...

    def multi(self) -> object: ...

    def zadd(self, key: str, mapping: dict[str, float]) -> object: ...

    def expire(self, key: str, seconds: int) -> object: ...

    def execute(self) -> object: ...

    def unwatch(self) -> object: ...


class RedisGateClient(Protocol):
    def pipeline(self) -> RedisPipelineProtocol: ...

    def zrem(self, key: str, owner_id: str) -> object: ...


class TaskExecutionGate:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        redis_client: RedisGateClient | None = None,
        session_factory: Callable[[], Session] | None = None,
        sleep_func=time.sleep,
        time_func=time.time,
    ) -> None:
        self.settings = settings or get_settings()
        self.redis = redis_client or Redis.from_url(self.settings.redis_url)
        self.session_factory = session_factory or _resolve_session_factory(
            self.settings
        )
        self.sleep_func = sleep_func
        self.time_func = time_func
        self.logger = get_logger(__name__)
        self._active_key = "spiderbilibili:worker:active_tasks"

    def acquire(self, owner_id: str) -> TaskExecutionLease:
        concurrency_limit = max(0, int(self.settings.worker_global_task_concurrency))
        if concurrency_limit <= 0:
            return TaskExecutionLease(gate=self, owner_id=owner_id)

        wait_seconds = max(
            0.0,
            float(self.settings.worker_task_concurrency_wait_seconds),
        )
        poll_seconds = max(
            0.1,
            float(self.settings.worker_task_concurrency_poll_seconds),
        )
        lease_seconds = max(
            60,
            int(self.settings.worker_task_concurrency_lease_seconds),
        )
        deadline = self.time_func() + wait_seconds

        while True:
            self._cleanup_stale_leases()
            try:
                with self.redis.pipeline() as pipeline:
                    now = self.time_func()
                    pipeline.watch(self._active_key)
                    pipeline.zremrangebyscore(self._active_key, "-inf", now)
                    active_count = _coerce_int(pipeline.zcard(self._active_key))
                    existing_score = _coerce_float(
                        pipeline.zscore(self._active_key, owner_id)
                    )

                    if existing_score is not None or active_count < concurrency_limit:
                        pipeline.multi()
                        pipeline.zadd(
                            self._active_key,
                            {owner_id: now + lease_seconds},
                        )
                        pipeline.expire(self._active_key, lease_seconds + 60)
                        pipeline.execute()
                        return TaskExecutionLease(gate=self, owner_id=owner_id)

                    pipeline.unwatch()
            except WatchError:
                continue
            except RedisError as exc:
                self.logger.warning(
                    "Redis task execution gate is unavailable, skipping throttle: {}",
                    exc,
                )
                return TaskExecutionLease(gate=self, owner_id=owner_id)

            if self.time_func() >= deadline:
                raise RuntimeError(
                    "Global task concurrency throttle is saturated. "
                    "Please retry after active tasks finish."
                )
            self.sleep_func(poll_seconds)

    def release(self, owner_id: str) -> None:
        concurrency_limit = max(0, int(self.settings.worker_global_task_concurrency))
        if concurrency_limit <= 0:
            return
        try:
            self.redis.zrem(self._active_key, owner_id)
        except RedisError as exc:
            self.logger.warning(
                "Failed to release Redis task execution slot for {}: {}",
                owner_id,
                exc,
            )

    def _cleanup_stale_leases(self) -> None:
        if self.session_factory is None:
            return

        try:
            owner_ids = [
                (
                    owner_id.decode("utf-8")
                    if isinstance(owner_id, bytes)
                    else str(owner_id)
                )
                for owner_id in self.redis.zrange(self._active_key, 0, -1)
            ]
        except RedisError as exc:
            self.logger.warning(
                "Failed to inspect Redis task execution slots before acquire: {}",
                exc,
            )
            return

        if not owner_ids:
            return

        stale_owner_ids = self._find_stale_owner_ids(owner_ids)
        if not stale_owner_ids:
            return

        for owner_id in stale_owner_ids:
            try:
                self.redis.zrem(self._active_key, owner_id)
            except RedisError as exc:
                self.logger.warning(
                    "Failed to clean stale Redis task execution slot for {}: {}",
                    owner_id,
                    exc,
                )

    def _find_stale_owner_ids(self, owner_ids: list[str]) -> list[str]:
        if self.session_factory is None or not owner_ids:
            return []

        from app.services.task_service import (
            _get_celery_task_runtime_state,
            _get_dispatched_celery_task_id,
            _is_runtime_state_active_for_task,
            _is_task_runtime_stale,
            reconcile_task_runtime_state,
        )

        stale_owner_ids: list[str] = []
        with self.session_factory() as session:
            tasks = {
                task.id: task
                for task in session.scalars(
                    select(CrawlTask).where(CrawlTask.id.in_(owner_ids))
                ).all()
            }

            for owner_id in owner_ids:
                task = tasks.get(owner_id)
                if task is None:
                    stale_owner_ids.append(owner_id)
                    continue

                if task.status not in {TaskStatus.QUEUED, TaskStatus.RUNNING}:
                    stale_owner_ids.append(owner_id)
                    continue

                if not _is_task_runtime_stale(task):
                    continue

                celery_task_id = _get_dispatched_celery_task_id(task)
                runtime_state = _get_celery_task_runtime_state(celery_task_id)
                if runtime_state == "unknown":
                    continue
                if _is_runtime_state_active_for_task(task, runtime_state):
                    continue

                task = reconcile_task_runtime_state(session, task)
                if task.status not in {TaskStatus.QUEUED, TaskStatus.RUNNING}:
                    stale_owner_ids.append(owner_id)

        return stale_owner_ids


def _coerce_int(value: object, *, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _coerce_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _resolve_session_factory(
    settings: Settings,
) -> Callable[[], Session] | None:
    if not getattr(settings, "database_url", None):
        return None

    from app.db.session import get_session_factory

    return get_session_factory()
