from __future__ import annotations

import json
import os
import socket
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any, Protocol, TypedDict, cast

import redis
from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily, Metric
from prometheus_client.gc_collector import GCCollector
from prometheus_client.platform_collector import PlatformCollector
from prometheus_client.process_collector import ProcessCollector
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.session import check_database_connection, get_session_factory
from app.models.base import utc_now
from app.models.task import CrawlTask

PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


@dataclass(slots=True)
class WorkerHeartbeat:
    worker_name: str
    hostname: str
    pid: int
    state: str
    last_seen_at: datetime
    age_seconds: float


@dataclass(slots=True)
class MonitoringSnapshot:
    overall_status: str
    service_available: bool
    database_ok: bool
    redis_ok: bool
    worker_status: str
    workers: list[WorkerHeartbeat]
    active_workers: int
    expected_workers: int
    celery_queue_depth: int
    task_counts: dict[str, int]
    task_terminal_counts: dict[str, float]
    task_stage_failure_counts: dict[str, float]
    ai_outcome_counts: dict[str, float]
    task_failure_ratio: float
    ai_failure_ratio: float


class MonitoringRedisClient(Protocol):
    def set(self, name: str, value: str, *, nx: bool, ex: int) -> object:
        ...

    def delete(self, *names: str) -> object:
        ...

    def setex(self, name: str, time: int, value: str) -> object:
        ...

    def scan_iter(self, *, match: str) -> Iterable[str]:
        ...

    def mget(self, keys: list[str]) -> list[str | None]:
        ...

    def llen(self, name: str) -> object:
        ...

    def hgetall(self, name: str) -> Mapping[str, str]:
        ...

    def hincrby(self, name: str, key: str, amount: int) -> object:
        ...

    def ping(self) -> object:
        ...


class WorkerHeartbeatPayload(TypedDict):
    worker_name: str
    hostname: str
    pid: int
    state: str
    last_seen_at: str


@lru_cache
def get_monitoring_redis_client() -> MonitoringRedisClient:
    settings = get_settings()
    return cast(
        MonitoringRedisClient,
        redis.Redis.from_url(settings.redis_url, decode_responses=True),
    )


def record_http_request(
    method: str,
    path: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    settings = get_settings()
    if not settings.monitoring_enabled:
        return

    if path.endswith("/metrics"):
        return

    HTTP_REQUESTS_TOTAL.labels(
        method=method.upper(),
        path=path,
        status_code=str(status_code),
    ).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(
        method=method.upper(),
        path=path,
    ).observe(duration_seconds)


def record_task_terminal_status(status: str) -> None:
    _increment_hash_counter("task_terminal_status", status)


def record_task_stage_failure(stage: str) -> None:
    _increment_hash_counter("task_stage_failures", stage)


def record_ai_batch_outcomes(
    *,
    total_count: int,
    success_count: int,
    failure_count: int,
    fallback_count: int = 0,
    cached_count: int = 0,
) -> None:
    increments = {
        "total": total_count,
        "success": success_count,
        "failure": failure_count,
        "fallback": fallback_count,
        "cached": cached_count,
    }
    for outcome, increment in increments.items():
        if increment > 0:
            _increment_hash_counter("ai_outcomes", outcome, increment=increment)


def record_worker_heartbeat(
    *,
    worker_name: str = "celery",
    state: str = "running",
) -> None:
    settings = get_settings()
    if not settings.monitoring_enabled:
        return

    payload: WorkerHeartbeatPayload = {
        "worker_name": worker_name,
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
        "state": state,
        "last_seen_at": utc_now().isoformat(),
    }
    try:
        client = get_monitoring_redis_client()
        client.setex(
            _worker_key(
                worker_name=payload["worker_name"],
                hostname=payload["hostname"],
                pid=payload["pid"],
            ),
            settings.monitoring_worker_heartbeat_ttl_seconds,
            json.dumps(payload),
        )
    except Exception:
        return


def collect_monitoring_snapshot() -> MonitoringSnapshot:
    settings = get_settings()
    database_ok = _safe_database_check()
    redis_ok = _safe_redis_check()
    worker_status = "unknown"
    workers: list[WorkerHeartbeat] = []
    queue_depth = 0
    terminal_counts: dict[str, float] = {}
    stage_failure_counts: dict[str, float] = {}
    ai_outcomes: dict[str, float] = {}

    if redis_ok:
        client = get_monitoring_redis_client()
        workers = get_worker_heartbeats(client=client, settings=settings)
        worker_status = _resolve_worker_status(
            active_workers=len(workers),
            expected_workers=settings.monitoring_worker_expected_count,
        )
        queue_depth = get_celery_queue_depth(client=client, settings=settings)
        terminal_counts = get_hash_counter_snapshot(
            "task_terminal_status",
            client=client,
            settings=settings,
        )
        stage_failure_counts = get_hash_counter_snapshot(
            "task_stage_failures",
            client=client,
            settings=settings,
        )
        ai_outcomes = get_hash_counter_snapshot(
            "ai_outcomes",
            client=client,
            settings=settings,
        )

    task_counts = get_task_counts_by_status() if database_ok else {}
    total_terminal = sum(terminal_counts.values())
    failed_terminal = float(terminal_counts.get("failed", 0))
    ai_total = float(ai_outcomes.get("total", 0))
    ai_failed = float(ai_outcomes.get("failure", 0))
    service_available = database_ok and redis_ok

    return MonitoringSnapshot(
        overall_status=(
            "ok"
            if service_available and worker_status in {"ok", "unknown"}
            else "degraded"
        ),
        service_available=service_available,
        database_ok=database_ok,
        redis_ok=redis_ok,
        worker_status=worker_status,
        workers=workers,
        active_workers=len(workers),
        expected_workers=settings.monitoring_worker_expected_count,
        celery_queue_depth=queue_depth,
        task_counts=task_counts,
        task_terminal_counts=terminal_counts,
        task_stage_failure_counts=stage_failure_counts,
        ai_outcome_counts=ai_outcomes,
        task_failure_ratio=round(failed_terminal / total_terminal, 4)
        if total_terminal
        else 0.0,
        ai_failure_ratio=round(ai_failed / ai_total, 4) if ai_total else 0.0,
    )


def get_worker_heartbeats(
    *,
    client: MonitoringRedisClient | None = None,
    settings=None,
) -> list[WorkerHeartbeat]:
    settings = settings or get_settings()
    client = client or get_monitoring_redis_client()
    heartbeats: list[WorkerHeartbeat] = []

    keys = list(client.scan_iter(match=f"{settings.monitoring_redis_prefix}:worker:*"))
    if not keys:
        return heartbeats

    raw_payloads = client.mget(keys)
    for raw_payload in raw_payloads:
        if not raw_payload:
            continue

        heartbeat = _parse_worker_heartbeat(raw_payload)
        if heartbeat is not None:
            heartbeats.append(heartbeat)

    heartbeats.sort(key=lambda item: item.last_seen_at, reverse=True)
    return heartbeats


def get_celery_queue_depth(
    *,
    client: MonitoringRedisClient | None = None,
    settings=None,
) -> int:
    settings = settings or get_settings()
    client = client or get_monitoring_redis_client()
    try:
        return _coerce_int(client.llen(settings.monitoring_celery_queue_name))
    except Exception:
        return 0


def get_task_counts_by_status() -> dict[str, int]:
    session_factory = get_session_factory()
    with session_factory() as session:
        rows = session.execute(
            select(CrawlTask.status, func.count())
            .where(CrawlTask.deleted_at.is_(None))
            .group_by(CrawlTask.status)
        ).all()
    return {status.value: int(count) for status, count in rows}


def get_hash_counter_snapshot(
    metric_name: str,
    *,
    client: MonitoringRedisClient | None = None,
    settings=None,
) -> dict[str, float]:
    settings = settings or get_settings()
    try:
        client = client or get_monitoring_redis_client()
        raw_items = dict(client.hgetall(_hash_key(metric_name, settings=settings)))
    except Exception:
        return {}
    return {key: float(value) for key, value in raw_items.items()}


def render_metrics_payload() -> bytes:
    return generate_latest(METRICS_REGISTRY)


class SpiderBilibiliRuntimeCollector:
    def describe(self) -> list[Metric]:
        return []

    def collect(self) -> Iterator[Metric]:
        snapshot = collect_monitoring_snapshot()

        component_health = GaugeMetricFamily(
            "spiderbilibili_component_health_status",
            "Health status for core components.",
            labels=["component"],
        )
        component_health.add_metric(["api"], 1)
        component_health.add_metric(["database"], 1 if snapshot.database_ok else 0)
        component_health.add_metric(["redis"], 1 if snapshot.redis_ok else 0)
        component_health.add_metric(
            ["worker"],
            1 if snapshot.worker_status == "ok" else 0,
        )
        yield component_health

        worker_active = GaugeMetricFamily(
            "spiderbilibili_worker_active",
            "Worker heartbeat presence by worker process.",
            labels=["worker_name", "hostname", "pid", "state"],
        )
        worker_age = GaugeMetricFamily(
            "spiderbilibili_worker_heartbeat_age_seconds",
            "Seconds since the latest worker heartbeat.",
            labels=["worker_name", "hostname", "pid"],
        )
        for worker in snapshot.workers:
            labels = [
                worker.worker_name,
                worker.hostname,
                str(worker.pid),
                worker.state,
            ]
            worker_active.add_metric(labels, 1)
            worker_age.add_metric(
                [worker.worker_name, worker.hostname, str(worker.pid)],
                worker.age_seconds,
            )
        yield worker_active
        yield worker_age

        queue_depth = GaugeMetricFamily(
            "spiderbilibili_celery_queue_depth",
            "Current Redis-backed Celery queue depth.",
            labels=["queue"],
        )
        queue_depth.add_metric(
            [get_settings().monitoring_celery_queue_name],
            snapshot.celery_queue_depth,
        )
        yield queue_depth

        task_records = GaugeMetricFamily(
            "spiderbilibili_task_records",
            "Current persisted task records grouped by status.",
            labels=["status"],
        )
        for status, task_count in sorted(snapshot.task_counts.items()):
            task_records.add_metric([status], task_count)
        yield task_records

        task_terminal_total = CounterMetricFamily(
            "spiderbilibili_task_terminal_total",
            "Observed terminal task outcomes.",
            labels=["status"],
        )
        for status, terminal_count in sorted(snapshot.task_terminal_counts.items()):
            task_terminal_total.add_metric([status], terminal_count)
        yield task_terminal_total

        task_stage_failures = CounterMetricFamily(
            "spiderbilibili_task_stage_failures_total",
            "Observed task stage failures.",
            labels=["stage"],
        )
        for stage, stage_count in sorted(snapshot.task_stage_failure_counts.items()):
            task_stage_failures.add_metric([stage], stage_count)
        yield task_stage_failures

        ai_outcomes = CounterMetricFamily(
            "spiderbilibili_ai_video_analyses_total",
            "Observed AI analysis outcomes.",
            labels=["outcome"],
        )
        for outcome, outcome_count in sorted(snapshot.ai_outcome_counts.items()):
            ai_outcomes.add_metric([outcome], outcome_count)
        yield ai_outcomes

        runtime_health = GaugeMetricFamily(
            "spiderbilibili_runtime_health",
            "Runtime health indicators for observability.",
            labels=["indicator"],
        )
        runtime_health.add_metric(["active_workers"], snapshot.active_workers)
        runtime_health.add_metric(["expected_workers"], snapshot.expected_workers)
        runtime_health.add_metric(["task_failure_ratio"], snapshot.task_failure_ratio)
        runtime_health.add_metric(["ai_failure_ratio"], snapshot.ai_failure_ratio)
        yield runtime_health


def _increment_hash_counter(
    metric_name: str,
    field_name: str,
    *,
    increment: int = 1,
) -> None:
    settings = get_settings()
    if not settings.monitoring_enabled or increment <= 0:
        return

    try:
        client = get_monitoring_redis_client()
        client.hincrby(_hash_key(metric_name, settings=settings), field_name, increment)
    except Exception:
        return


def _hash_key(metric_name: str, *, settings=None) -> str:
    settings = settings or get_settings()
    return f"{settings.monitoring_redis_prefix}:hash:{metric_name}"


def _worker_key(*, worker_name: str, hostname: str, pid: int) -> str:
    settings = get_settings()
    return (
        f"{settings.monitoring_redis_prefix}:worker:"
        f"{worker_name}:{hostname}:{pid}"
    )


def _safe_database_check() -> bool:
    try:
        return check_database_connection()
    except Exception:
        return False


def _safe_redis_check() -> bool:
    try:
        return bool(get_monitoring_redis_client().ping())
    except Exception:
        return False


def _resolve_worker_status(*, active_workers: int, expected_workers: int) -> str:
    if expected_workers <= 0:
        return "ok"
    if active_workers >= expected_workers:
        return "ok"
    return "warning"


def _parse_worker_heartbeat(raw_payload: str) -> WorkerHeartbeat | None:
    try:
        payload = cast(WorkerHeartbeatPayload, json.loads(raw_payload))
        last_seen_at = datetime.fromisoformat(payload["last_seen_at"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None

    age_seconds = max((utc_now() - last_seen_at).total_seconds(), 0.0)
    return WorkerHeartbeat(
        worker_name=payload["worker_name"],
        hostname=payload["hostname"],
        pid=payload["pid"],
        state=payload.get("state", "running"),
        last_seen_at=last_seen_at,
        age_seconds=round(age_seconds, 2),
    )


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


METRICS_REGISTRY = CollectorRegistry(auto_describe=False)
GCCollector(registry=METRICS_REGISTRY)
PlatformCollector(registry=METRICS_REGISTRY)
ProcessCollector(registry=METRICS_REGISTRY)

HTTP_REQUESTS_TOTAL = Counter(
    "spiderbilibili_http_requests_total",
    "Total API requests.",
    labelnames=("method", "path", "status_code"),
    registry=METRICS_REGISTRY,
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "spiderbilibili_http_request_duration_seconds",
    "API request latency in seconds.",
    labelnames=("method", "path"),
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
    registry=METRICS_REGISTRY,
)
METRICS_REGISTRY.register(cast(Any, SpiderBilibiliRuntimeCollector()))
