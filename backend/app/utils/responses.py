from http import HTTPStatus
from typing import TypeVar

from app.schemas.common import ApiResponse

T = TypeVar("T")


def success_response(
    data: T,
    *,
    message: str = "ok",
    status_code: int = HTTPStatus.OK,
    request_id: str | None = None,
) -> ApiResponse[T]:
    return ApiResponse[T](
        success=True,
        message=message,
        data=data,
        request_id=request_id,
        status_code=status_code,
    )
