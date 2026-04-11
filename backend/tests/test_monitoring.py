import json
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
from app.services.monitoring import (
    MonitoringSnapshot,
    WorkerHeartbeat,
    get_worker_heartbeats,
)


def test_metrics_endpoint_returns_prometheus_payload(monkeypatch) -> None:
    def fake_snapshot() -> MonitoringSnapshot:
        return MonitoringSnapshot(
            overall_status="ok",
            service_available=True,
            database_ok=True,
            redis_ok=True,
            worker_status="ok",
            workers=[
                WorkerHeartbeat(
                    worker_name="celery",
                    hostname="worker-host",
                    pid=1234,
                    state="running",
                    last_seen_at=datetime(2026, 4, 7, 12, 0, tzinfo=UTC),
                    age_seconds=1.25,
                )
            ],
            active_workers=1,
            expected_workers=1,
            celery_queue_depth=3,
            task_counts={"queued": 2, "success": 4},
            task_terminal_counts={"success": 4, "failed": 1},
            task_stage_failure_counts={"task": 1.0, "ai": 2.0},
            ai_outcome_counts={"total": 10, "success": 8, "failure": 2},
            task_failure_ratio=0.2,
            ai_failure_ratio=0.2,
        )

    monkeypatch.setattr(
        "app.services.monitoring.collect_monitoring_snapshot",
        fake_snapshot,
    )

    client = TestClient(app)
    response = client.get("/api/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "spiderbilibili_component_health_status" in response.text
    assert "spiderbilibili_runtime_health" in response.text
    assert "spiderbilibili_celery_queue_depth" in response.text
    assert "spiderbilibili_task_terminal_total" in response.text


def test_get_worker_heartbeats_uses_batch_reads(monkeypatch) -> None:
    payloads = {
        "prefix:worker:celery:worker-a:1": {
            "worker_name": "celery",
            "hostname": "worker-a",
            "pid": 1,
            "state": "running",
            "last_seen_at": "2026-04-07T12:00:00+00:00",
        },
        "prefix:worker:celery:worker-b:2": {
            "worker_name": "celery",
            "hostname": "worker-b",
            "pid": 2,
            "state": "running",
            "last_seen_at": "2026-04-07T12:00:05+00:00",
        },
    }

    class FakeRedis:
        def __init__(self) -> None:
            self.mget_calls: list[list[str]] = []

        def scan_iter(self, *, match: str):
            assert match == "prefix:worker:*"
            return iter(payloads.keys())

        def mget(self, keys: list[str]) -> list[str]:
            self.mget_calls.append(keys)
            return [json.dumps(payloads[key]) for key in keys]

        def get(self, key: str) -> str:
            raise AssertionError(f"Unexpected single-key fetch for {key}")

    fake_redis = FakeRedis()
    monkeypatch.setattr(
        "app.services.monitoring.get_monitoring_redis_client",
        lambda: fake_redis,
    )
    monkeypatch.setattr(
        "app.services.monitoring.get_settings",
        lambda: SimpleNamespace(monitoring_redis_prefix="prefix"),
    )
    monkeypatch.setattr(
        "app.services.monitoring.utc_now",
        lambda: datetime(2026, 4, 7, 12, 0, 10, tzinfo=UTC),
    )

    heartbeats = get_worker_heartbeats()

    assert len(heartbeats) == 2
    assert fake_redis.mget_calls == [list(payloads.keys())]
    assert heartbeats[0].hostname == "worker-b"
    assert heartbeats[0].age_seconds == 5.0
