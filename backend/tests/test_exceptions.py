from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.exceptions import NotFoundError
from app.core.handlers import register_exception_handlers
from app.core.middleware import register_http_middleware
from app.main import app as main_app
from app.schemas.common import ComponentHealth, HealthIndicators, WorkerHealthRead


def create_test_app() -> FastAPI:
    app = FastAPI()
    register_http_middleware(app)
    register_exception_handlers(app)

    @app.get("/not-found")
    def not_found() -> None:
        raise NotFoundError(
            message="Task not found.",
            details={"task_id": "missing-task"},
        )

    @app.get("/unexpected")
    def unexpected() -> None:
        raise RuntimeError("boom")

    @app.get("/items/{item_id}")
    def read_item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    return app


def test_service_unavailable_error_uses_unified_error_response(monkeypatch) -> None:
    def mock_health_status() -> dict[str, object]:
        return {
            "status": "degraded",
            "service_available": False,
            "components": ComponentHealth(
                api="ok",
                database="error",
                redis="ok",
                worker="warning",
            ),
            "indicators": HealthIndicators(
                active_workers=0,
                expected_workers=1,
                celery_queue_depth=2,
                task_failure_ratio=0.5,
                ai_failure_ratio=0.25,
                task_counts={"failed": 1},
            ),
            "workers": [
                WorkerHealthRead(
                    worker_name="celery",
                    hostname="worker-host",
                    pid=1234,
                    state="running",
                    last_seen_at=datetime(2026, 4, 7, 12, 0, tzinfo=UTC),
                    age_seconds=180.0,
                )
            ],
        }

    monkeypatch.setattr(
        "app.api.routes.system.get_health_status",
        mock_health_status,
    )

    client = TestClient(main_app)
    response = client.get("/api/health", headers={"X-Request-ID": "health-degraded"})

    assert response.status_code == 503
    assert response.headers["X-Request-ID"] == "health-degraded"

    payload = response.json()
    assert payload["success"] is False
    assert payload["message"] == "One or more backend dependencies are unavailable."
    assert payload["error"]["code"] == "service_unavailable"
    assert payload["error"]["details"]["status"] == "degraded"


def test_app_error_uses_unified_error_response() -> None:
    client = TestClient(create_test_app())

    response = client.get("/not-found", headers={"X-Request-ID": "app-error"})

    assert response.status_code == 404
    assert response.headers["X-Request-ID"] == "app-error"

    payload = response.json()
    assert payload["success"] is False
    assert payload["message"] == "Task not found."
    assert payload["error"]["code"] == "not_found"
    assert payload["error"]["details"] == {"task_id": "missing-task"}
    assert payload["request_id"] == "app-error"


def test_request_validation_uses_unified_error_response() -> None:
    client = TestClient(create_test_app())

    response = client.get("/items/not-an-int", headers={"X-Request-ID": "validation"})

    assert response.status_code == 422
    assert response.headers["X-Request-ID"] == "validation"

    payload = response.json()
    assert payload["success"] is False
    assert payload["message"] == "Request validation failed."
    assert payload["error"]["code"] == "request_validation_error"
    assert payload["request_id"] == "validation"


def test_unexpected_error_uses_unified_error_response() -> None:
    client = TestClient(create_test_app(), raise_server_exceptions=False)

    response = client.get("/unexpected", headers={"X-Request-ID": "internal-error"})

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "internal-error"

    payload = response.json()
    assert payload["success"] is False
    assert payload["message"] == "Internal server error."
    assert payload["error"]["code"] == "internal_server_error"
    assert payload["request_id"] == "internal-error"
