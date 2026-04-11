from dataclasses import dataclass

from app.schemas.common import ComponentHealth, HealthIndicators, WorkerHealthRead
from app.services.monitoring import collect_monitoring_snapshot


@dataclass(slots=True)
class HealthStatusSnapshot:
    status: str
    service_available: bool
    components: ComponentHealth
    indicators: HealthIndicators
    workers: list[WorkerHealthRead]


def get_health_status() -> HealthStatusSnapshot:
    snapshot = collect_monitoring_snapshot()

    return HealthStatusSnapshot(
        status=snapshot.overall_status,
        service_available=snapshot.service_available,
        components=ComponentHealth(
            api="ok",
            database="ok" if snapshot.database_ok else "error",
            redis="ok" if snapshot.redis_ok else "error",
            worker=snapshot.worker_status,
        ),
        indicators=HealthIndicators(
            active_workers=snapshot.active_workers,
            expected_workers=snapshot.expected_workers,
            celery_queue_depth=snapshot.celery_queue_depth,
            task_failure_ratio=snapshot.task_failure_ratio,
            ai_failure_ratio=snapshot.ai_failure_ratio,
            task_counts=snapshot.task_counts,
        ),
        workers=[
            WorkerHealthRead(
                worker_name=worker.worker_name,
                hostname=worker.hostname,
                pid=worker.pid,
                state=worker.state,
                last_seen_at=worker.last_seen_at,
                age_seconds=worker.age_seconds,
            )
            for worker in snapshot.workers
        ],
    )
