from fastapi import APIRouter, Request, Response, status

from app.core.config import get_settings
from app.core.exceptions import ServiceUnavailableError
from app.schemas.common import ApiResponse, HealthPayload, MessagePayload
from app.services.health import HealthStatusSnapshot, get_health_status
from app.services.monitoring import PROMETHEUS_CONTENT_TYPE, render_metrics_payload
from app.utils.responses import success_response

router = APIRouter()


@router.get("/", response_model=ApiResponse[MessagePayload], summary="Root endpoint")
def root(request: Request) -> ApiResponse[MessagePayload]:
    payload = MessagePayload(message="spiderbilibili backend is running")
    request_id = getattr(request.state, "request_id", None)
    return success_response(payload, request_id=request_id)


@router.get(
    "/health",
    response_model=ApiResponse[HealthPayload],
    summary="Health check",
)
def healthcheck(request: Request) -> ApiResponse[HealthPayload]:
    settings = get_settings()
    status_payload = _coerce_health_status_snapshot(get_health_status())
    payload = HealthPayload(
        app=settings.app_name,
        env=settings.app_env,
        status=status_payload.status,
        components=status_payload.components,
        indicators=status_payload.indicators,
        workers=status_payload.workers,
    )

    if not status_payload.service_available:
        raise ServiceUnavailableError(
            message="One or more backend dependencies are unavailable.",
            details=payload.model_dump(),
        )

    request_id = getattr(request.state, "request_id", None)
    return success_response(
        payload,
        status_code=status.HTTP_200_OK,
        request_id=request_id,
    )


def _coerce_health_status_snapshot(payload: object) -> HealthStatusSnapshot:
    if isinstance(payload, HealthStatusSnapshot):
        return payload
    if isinstance(payload, dict):
        return HealthStatusSnapshot(
            status=str(payload["status"]),
            service_available=bool(payload["service_available"]),
            components=payload["components"],
            indicators=payload["indicators"],
            workers=list(payload["workers"]),
        )
    raise TypeError("Unsupported health status payload.")


@router.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(
        content=render_metrics_payload(),
        media_type=PROMETHEUS_CONTENT_TYPE,
    )
