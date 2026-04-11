from __future__ import annotations

from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request

from app.core.logging import get_logger
from app.services.monitoring import record_http_request


def register_http_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        request.state.request_id = request_id
        logger = get_logger(__name__, request_id)

        started_at = perf_counter()
        logger.info("Started {} {}", request.method, request.url.path)
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((perf_counter() - started_at) * 1000, 2)
            duration_seconds = duration_ms / 1000
            route = request.scope.get("route")
            path = getattr(route, "path", request.url.path)
            record_http_request(
                request.method,
                path,
                500,
                duration_seconds,
            )
            logger.error(
                "Failed {} {} in {} ms",
                request.method,
                request.url.path,
                duration_ms,
            )
            raise

        duration_ms = round((perf_counter() - started_at) * 1000, 2)
        duration_seconds = duration_ms / 1000
        route = request.scope.get("route")
        path = getattr(route, "path", request.url.path)
        record_http_request(
            request.method,
            path,
            response.status_code,
            duration_seconds,
        )
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "Completed {} {} -> {} in {} ms",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response
