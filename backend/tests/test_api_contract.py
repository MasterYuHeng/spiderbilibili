from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.common import ComponentHealth, HealthIndicators, WorkerHealthRead


def test_root_endpoint_uses_unified_success_response() -> None:
    client = TestClient(app)

    response = client.get("/api/", headers={"X-Request-ID": "root-ok"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "root-ok"

    payload = response.json()
    assert payload["success"] is True
    assert payload["message"] == "ok"
    assert payload["error"] is None
    assert payload["request_id"] == "root-ok"
    assert payload["data"] == {"message": "spiderbilibili backend is running"}


def test_health_endpoint_returns_unified_success_response(monkeypatch) -> None:
    def mock_health_status() -> dict[str, object]:
        return {
            "status": "ok",
            "service_available": True,
            "components": ComponentHealth(
                api="ok",
                database="ok",
                redis="ok",
                worker="ok",
            ),
            "indicators": HealthIndicators(
                active_workers=1,
                expected_workers=1,
                celery_queue_depth=0,
                task_failure_ratio=0,
                ai_failure_ratio=0,
                task_counts={"success": 2},
            ),
            "workers": [
                WorkerHealthRead(
                    worker_name="celery",
                    hostname="worker-host",
                    pid=1234,
                    state="running",
                    last_seen_at=datetime(2026, 4, 7, 12, 0, tzinfo=UTC),
                    age_seconds=2.5,
                )
            ],
        }

    monkeypatch.setattr(
        "app.api.routes.system.get_health_status",
        mock_health_status,
    )

    client = TestClient(app)
    response = client.get("/api/health", headers={"X-Request-ID": "health-ok"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "health-ok"

    payload = response.json()
    assert payload["success"] is True
    assert payload["message"] == "ok"
    assert payload["request_id"] == "health-ok"
    assert payload["data"]["status"] == "ok"
    assert payload["data"]["components"] == {
        "api": "ok",
        "database": "ok",
        "redis": "ok",
        "worker": "ok",
    }
    assert payload["data"]["indicators"]["active_workers"] == 1
    assert payload["data"]["workers"][0]["worker_name"] == "celery"


def test_health_endpoint_allows_worker_warning_when_dependencies_are_available(
    monkeypatch,
) -> None:
    def mock_health_status() -> dict[str, object]:
        return {
            "status": "degraded",
            "service_available": True,
            "components": ComponentHealth(
                api="ok",
                database="ok",
                redis="ok",
                worker="warning",
            ),
            "indicators": HealthIndicators(
                active_workers=0,
                expected_workers=1,
                celery_queue_depth=1,
                task_failure_ratio=0,
                ai_failure_ratio=0,
                task_counts={"queued": 1},
            ),
            "workers": [],
        }

    monkeypatch.setattr(
        "app.api.routes.system.get_health_status",
        mock_health_status,
    )

    client = TestClient(app)
    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["status"] == "degraded"
    assert payload["data"]["components"]["worker"] == "warning"
