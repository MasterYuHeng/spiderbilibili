from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ApiErrorPayload(BaseModel):
    code: str
    details: dict | list | str | None = None


class ApiResponse(BaseModel, Generic[T]):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    success: bool = True
    message: str = "ok"
    data: T | None = None
    error: ApiErrorPayload | None = None
    request_id: str | None = None
    status_code: int = Field(default=200, exclude=True)


class MessagePayload(BaseModel):
    message: str


class ComponentHealth(BaseModel):
    api: str
    database: str
    redis: str
    worker: str = "unknown"


class WorkerHealthRead(BaseModel):
    worker_name: str
    hostname: str
    pid: int
    state: str
    last_seen_at: datetime
    age_seconds: float


class HealthIndicators(BaseModel):
    active_workers: int = 0
    expected_workers: int = 0
    celery_queue_depth: int = 0
    task_failure_ratio: float = 0
    ai_failure_ratio: float = 0
    task_counts: dict[str, int] = Field(default_factory=dict)


class HealthPayload(BaseModel):
    app: str
    env: str
    status: str
    components: ComponentHealth
    indicators: HealthIndicators
    workers: list[WorkerHealthRead] = Field(default_factory=list)
