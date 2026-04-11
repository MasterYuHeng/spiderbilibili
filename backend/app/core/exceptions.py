from __future__ import annotations

from http import HTTPStatus


class AppError(Exception):
    def __init__(
        self,
        *,
        message: str,
        code: str = "app_error",
        status_code: int = HTTPStatus.BAD_REQUEST,
        details: dict | list | str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = int(status_code)
        self.details = details


class ValidationError(AppError):
    def __init__(
        self,
        *,
        message: str,
        details: dict | list | str | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="validation_error",
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            details=details,
        )


class NotFoundError(AppError):
    def __init__(
        self,
        *,
        message: str,
        details: dict | list | str | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="not_found",
            status_code=HTTPStatus.NOT_FOUND,
            details=details,
        )


class ServiceUnavailableError(AppError):
    def __init__(
        self,
        *,
        message: str,
        details: dict | list | str | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="service_unavailable",
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            details=details,
        )
