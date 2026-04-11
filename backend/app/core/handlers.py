from __future__ import annotations

from http import HTTPStatus
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.schemas.common import ApiErrorPayload, ApiResponse


def _build_error_response(
    *,
    request_id: str | None,
    status_code: int,
    code: str,
    message: str,
    details: dict | list | str | None = None,
) -> JSONResponse:
    payload = ApiResponse[None](
        success=False,
        message=message,
        error=ApiErrorPayload(code=code, details=details),
        request_id=request_id,
        status_code=status_code,
    )
    headers = {"X-Request-ID": request_id} if request_id else None
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(
            payload.model_dump(exclude_none=True),
            custom_encoder={Exception: lambda exc: str(exc)},
        ),
        headers=headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        get_logger(__name__, request_id).warning(
            "Handled application error: {}", exc.message
        )
        return _build_error_response(
            request_id=request_id,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        get_logger(__name__, request_id).warning("Request validation failed")
        return _build_error_response(
            request_id=request_id,
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="request_validation_error",
            message="Request validation failed.",
            details=list(exc.errors()),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", str(uuid4()))
        get_logger(__name__, request_id).exception("Unhandled exception: {}", exc)
        return _build_error_response(
            request_id=request_id,
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            code="internal_server_error",
            message="Internal server error.",
        )
