from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ServiceUnavailableError
from app.db.session import get_db_session
from app.schemas.common import ApiResponse, HealthPayload, MessagePayload
from app.schemas.system import (
    AiSettingsPayload,
    BilibiliAccountProfileRead,
    BilibiliBrowserImportRequest,
    BilibiliConfigRead,
    BilibiliConfigUpdateRequest,
    BrowserSourceRead,
    DeepSeekConfigRead,
    DeepSeekConfigUpdateRequest,
)
from app.services.bilibili_auth_service import (
    discover_bilibili_browser_sources,
    fetch_bilibili_account_profile,
    import_bilibili_auth_from_browser,
)
from app.services.health import HealthStatusSnapshot, get_health_status
from app.services.monitoring import PROMETHEUS_CONTENT_TYPE, render_metrics_payload
from app.services.system_config_service import (
    AI_RUNTIME_OVERRIDES_KEY,
    BILIBILI_RUNTIME_AUTH_KEY,
    get_system_config,
    resolve_ai_client_settings,
    resolve_bilibili_auth_settings,
    update_bilibili_runtime_auth_config,
    update_deepseek_runtime_config,
)
from app.utils.responses import success_response

router = APIRouter()
DbSession = Session
DbSessionDep = Annotated[DbSession, Depends(get_db_session)]
KeySource = Literal["runtime", "environment", "unset"]


@router.get("/", response_model=ApiResponse[MessagePayload], summary="Root endpoint")
def root(request: Request) -> ApiResponse[MessagePayload]:
    payload = MessagePayload(message="spiderbilibili backend is running")
    request_id = getattr(request.state, "request_id", None)
    return success_response(payload, request_id=request_id)


@router.get(
    "/ai-settings",
    response_model=ApiResponse[AiSettingsPayload],
    summary="Get runtime settings",
)
def get_ai_settings(
    request: Request,
    session: DbSessionDep,
) -> ApiResponse[AiSettingsPayload]:
    payload = AiSettingsPayload(
        deepseek=_build_deepseek_config_payload(session),
        bilibili=_build_bilibili_config_payload(session),
    )
    request_id = getattr(request.state, "request_id", None)
    return success_response(payload, request_id=request_id)


@router.put(
    "/ai-settings/deepseek",
    response_model=ApiResponse[DeepSeekConfigRead],
    summary="Update DeepSeek API key",
)
def update_deepseek_settings(
    payload: DeepSeekConfigUpdateRequest,
    request: Request,
    session: DbSessionDep,
) -> ApiResponse[DeepSeekConfigRead]:
    update_deepseek_runtime_config(session, api_key=payload.api_key)
    session.commit()
    response_payload = _build_deepseek_config_payload(session)
    request_id = getattr(request.state, "request_id", None)
    return success_response(response_payload, request_id=request_id)


@router.put(
    "/bilibili-settings",
    response_model=ApiResponse[BilibiliConfigRead],
    summary="Update Bilibili auth cookie",
)
def update_bilibili_settings(
    payload: BilibiliConfigUpdateRequest,
    request: Request,
    session: DbSessionDep,
) -> ApiResponse[BilibiliConfigRead]:
    account_profile, validation_message = fetch_bilibili_account_profile(payload.cookie)
    update_bilibili_runtime_auth_config(
        session,
        cookie=payload.cookie,
        account_profile=account_profile,
        import_source=None,
        validation_message=validation_message,
    )
    session.commit()
    response_payload = _build_bilibili_config_payload(session)
    request_id = getattr(request.state, "request_id", None)
    return success_response(response_payload, request_id=request_id)


@router.post(
    "/bilibili-settings/import-browser",
    response_model=ApiResponse[BilibiliConfigRead],
    summary="Import Bilibili auth from local browser",
)
def import_bilibili_settings_from_browser(
    payload: BilibiliBrowserImportRequest,
    request: Request,
    session: DbSessionDep,
) -> ApiResponse[BilibiliConfigRead]:
    import_result = import_bilibili_auth_from_browser(
        browser=payload.browser,
        profile_directory=payload.profile_directory,
        user_data_dir=payload.user_data_dir,
    )
    update_bilibili_runtime_auth_config(
        session,
        cookie=str(import_result["cookie"]),
        account_profile=import_result.get("account_profile"),
        import_source=import_result.get("import_source"),
        validation_message=import_result.get("validation_message"),
    )
    session.commit()
    response_payload = _build_bilibili_config_payload(session)
    request_id = getattr(request.state, "request_id", None)
    return success_response(response_payload, request_id=request_id)


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


def _build_deepseek_config_payload(session: Session) -> DeepSeekConfigRead:
    settings = get_settings()
    resolved = resolve_ai_client_settings(session, settings)
    runtime_record = get_system_config(session, AI_RUNTIME_OVERRIDES_KEY)
    runtime_api_key = ""
    if (
        runtime_record
        and runtime_record.is_active
        and isinstance(runtime_record.config_value, dict)
    ):
        runtime_api_key = _first_non_empty(
            runtime_record.config_value.get("api_key", "")
        )
    environment_api_key = _first_non_empty(
        settings.deepseek_api_key,
        settings.ai_api_key if settings.normalized_ai_provider == "deepseek" else "",
    )
    effective_api_key = runtime_api_key or environment_api_key
    key_source: KeySource = (
        "runtime"
        if runtime_api_key
        else "environment" if environment_api_key else "unset"
    )
    deepseek_base_url = _first_non_empty(
        settings.ai_base_url,
        settings.deepseek_base_url,
        "https://api.deepseek.com",
    )
    deepseek_model = _first_non_empty(
        settings.ai_model,
        settings.deepseek_model,
        "deepseek-chat",
    )
    deepseek_fallback_model = (
        _first_non_empty(
            settings.ai_fallback_model,
            settings.deepseek_fallback_model,
        )
        or None
    )
    return DeepSeekConfigRead(
        effective_provider=resolved["provider_name"],
        api_key=effective_api_key,
        api_key_configured=bool(effective_api_key),
        key_source=key_source,
        base_url=deepseek_base_url,
        model=deepseek_model,
        fallback_model=deepseek_fallback_model,
        timeout_seconds=float(resolved["timeout_seconds"]),
        max_retries=int(resolved["max_retries"]),
        updated_at=(
            runtime_record.updated_at
            if runtime_record and runtime_record.is_active
            else None
        ),
    )


def _build_bilibili_config_payload(session: Session) -> BilibiliConfigRead:
    settings = get_settings()
    resolved = resolve_bilibili_auth_settings(session, settings)
    runtime_record = get_system_config(session, BILIBILI_RUNTIME_AUTH_KEY)
    import_source = resolved.get("import_source")
    import_summary = None
    if isinstance(import_source, dict):
        import_summary = _first_non_empty(import_source.get("label", ""))

    account_profile = resolved.get("account_profile")
    normalized_account_profile = (
        BilibiliAccountProfileRead.model_validate(account_profile)
        if isinstance(account_profile, dict)
        else None
    )
    browser_sources = [
        BrowserSourceRead.model_validate(item)
        for item in discover_bilibili_browser_sources()
    ]
    return BilibiliConfigRead(
        cookie=str(resolved["cookie"]),
        cookie_configured=bool(resolved["cookie_configured"]),
        key_source=cast(KeySource, str(resolved["key_source"])),
        sessdata=str(resolved["bilibili_sessdata"]),
        bili_jct=str(resolved["bilibili_bili_jct"]),
        dede_user_id=str(resolved["bilibili_dedeuserid"]),
        buvid3=str(resolved["bilibili_buvid3"]),
        buvid4=str(resolved["bilibili_buvid4"]),
        account_profile=normalized_account_profile,
        import_summary=import_summary,
        validation_message=(
            str(resolved.get("validation_message") or "").strip() or None
        ),
        browser_sources=browser_sources,
        updated_at=(
            runtime_record.updated_at
            if runtime_record and runtime_record.is_active
            else None
        ),
    )


def _first_non_empty(*values: object) -> str:
    for value in values:
        normalized = str(value or "").strip()
        if normalized:
            return normalized
    return ""
