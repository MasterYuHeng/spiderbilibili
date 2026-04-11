from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.base import utc_now
from app.models.enums import TaskStatus
from app.models.task import CrawlTask
from app.services.task_concurrency_service import TaskExecutionGate


class FakeRedisPipeline:
    def __init__(self, redis: "FakeRedis") -> None:
        self.redis = redis
        self.pending_add: tuple[str, float] | None = None
        self.pending_expire: int | None = None

    def __enter__(self) -> "FakeRedisPipeline":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def watch(self, key: str) -> None:
        self.redis.last_key = key

    def zremrangebyscore(self, key: str, minimum: str, maximum: float) -> None:
        self.redis.data = {
            member: score
            for member, score in self.redis.data.items()
            if score > maximum
        }

    def zcard(self, key: str) -> int:
        return len(self.redis.data)

    def zscore(self, key: str, owner_id: str) -> float | None:
        return self.redis.data.get(owner_id)

    def multi(self) -> None:
        return None

    def zadd(self, key: str, mapping: dict[str, float]) -> None:
        self.pending_add = next(iter(mapping.items()))

    def expire(self, key: str, seconds: int) -> None:
        self.pending_expire = seconds

    def execute(self) -> None:
        if self.pending_add is not None:
            owner_id, score = self.pending_add
            self.redis.data[owner_id] = score
        if self.pending_expire is not None:
            self.redis.expire_seconds = self.pending_expire

    def unwatch(self) -> None:
        return None


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, float] = {}
        self.expire_seconds: int | None = None
        self.last_key: str | None = None

    def pipeline(self) -> FakeRedisPipeline:
        return FakeRedisPipeline(self)

    def zrem(self, key: str, owner_id: str) -> None:
        self.data.pop(owner_id, None)

    def zrange(
        self,
        key: str,
        start: int,
        stop: int,
        withscores: bool = False,
    ) -> list:
        items = sorted(self.data.items(), key=lambda item: item[1])
        if stop == -1:
            selected = items[start:]
        else:
            selected = items[start : stop + 1]
        if withscores:
            return [(member.encode("utf-8"), score) for member, score in selected]
        return [member.encode("utf-8") for member, _ in selected]


def build_settings(**overrides):
    defaults = {
        "redis_url": "redis://localhost:6379/0",
        "worker_global_task_concurrency": 2,
        "worker_task_concurrency_wait_seconds": 1.0,
        "worker_task_concurrency_poll_seconds": 0.1,
        "worker_task_concurrency_lease_seconds": 3600,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_task_execution_gate_acquires_and_releases_slots() -> None:
    redis_client = FakeRedis()
    gate = TaskExecutionGate(
        settings=build_settings(worker_global_task_concurrency=1),
        redis_client=redis_client,
    )

    lease = gate.acquire("task-1")
    assert redis_client.data["task-1"] > 0

    lease.release()
    assert redis_client.data == {}


def test_task_execution_gate_raises_when_global_slots_are_full() -> None:
    redis_client = FakeRedis()
    redis_client.data["task-1"] = 99999.0
    sleep_calls: list[float] = []
    current_time = {"value": 100.0}
    gate = TaskExecutionGate(
        settings=build_settings(
            worker_global_task_concurrency=1,
            worker_task_concurrency_wait_seconds=0.2,
            worker_task_concurrency_poll_seconds=0.1,
        ),
        redis_client=redis_client,
        sleep_func=lambda seconds: record_sleep(seconds, sleep_calls, current_time),
        time_func=lambda: current_time["value"],
    )

    with pytest.raises(RuntimeError, match="Global task concurrency throttle"):
        gate.acquire("task-2")

    assert sleep_calls == [0.1, 0.1, 0.1]


def test_task_execution_gate_cleans_terminal_task_leases_before_counting() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with factory() as session:
        stale_task = CrawlTask(
            keyword="stale-task",
            status=TaskStatus.FAILED,
            requested_video_limit=5,
            max_pages=2,
            min_sleep_seconds=1.0,
            max_sleep_seconds=1.0,
            enable_proxy=False,
            source_ip_strategy="local_sleep",
        )
        session.add(stale_task)
        session.commit()
        stale_task_id = stale_task.id

    redis_client = FakeRedis()
    redis_client.data[stale_task_id] = (
        utc_now().timestamp() + timedelta(hours=1).total_seconds()
    )

    gate = TaskExecutionGate(
        settings=build_settings(worker_global_task_concurrency=1),
        redis_client=redis_client,
        session_factory=factory,
    )

    lease = gate.acquire("task-2")

    assert stale_task_id not in redis_client.data
    assert "task-2" in redis_client.data

    lease.release()


def record_sleep(
    seconds: float,
    sleep_calls: list[float],
    current_time: dict[str, float],
) -> None:
    sleep_calls.append(seconds)
    current_time["value"] += seconds
