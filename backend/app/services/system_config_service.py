from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import (
    AI_PROVIDER_DEEPSEEK,
    AI_PROVIDER_OPENAI,
    AI_PROVIDER_PRESETS,
    Settings,
)
from app.crawler.auth import BILIBILI_COOKIE_FIELD_MAP
from app.models.analysis import SystemConfig
from app.models.base import utc_now

TOPIC_LIMIT_CAP = 10
AI_RUNTIME_OVERRIDES_KEY = "ai.runtime_overrides"
BILIBILI_RUNTIME_AUTH_KEY = "bilibili.runtime_auth"


def get_system_config(session: Session, config_key: str) -> SystemConfig | None:
    statement = select(SystemConfig).where(SystemConfig.config_key == config_key)
    return session.scalar(statement)


def get_system_config_value(session: Session, config_key: str) -> dict[str, Any] | None:
    config = get_system_config(session, config_key)
    if config is None or not config.is_active:
        return None
    return dict(config.config_value)


def upsert_system_config(
    session: Session,
    *,
    config_key: str,
    config_name: str,
    config_group: str,
    config_value: dict[str, Any],
    description: str,
    is_active: bool = True,
) -> SystemConfig:
    config = get_system_config(session, config_key)
    if config is None:
        config = SystemConfig(
            config_key=config_key,
            config_name=config_name,
            config_group=config_group,
            config_value=config_value,
            description=description,
            is_active=is_active,
        )
        session.add(config)
        session.flush()
        return config

    config.config_name = config_name
    config.config_group = config_group
    config.config_value = config_value
    config.description = description
    config.is_active = is_active
    config.updated_at = utc_now()
    session.flush()
    return config


def get_ai_runtime_overrides(session: Session) -> dict[str, Any]:
    return get_system_config_value(session, AI_RUNTIME_OVERRIDES_KEY) or {}


def update_deepseek_runtime_config(session: Session, *, api_key: str) -> SystemConfig:
    sanitized_key = api_key.strip()
    return upsert_system_config(
        session,
        config_key=AI_RUNTIME_OVERRIDES_KEY,
        config_name="AI runtime overrides",
        config_group="ai",
        config_value={
            "provider": AI_PROVIDER_DEEPSEEK if sanitized_key else "",
            "api_key": sanitized_key,
        },
        description="Runtime AI overrides managed from the frontend settings page.",
        is_active=True,
    )


def resolve_ai_client_settings(
    session: Session | None,
    settings: Settings,
) -> dict[str, Any]:
    runtime_overrides = get_ai_runtime_overrides(session) if session is not None else {}
    runtime_api_key = _first_non_empty(runtime_overrides.get("api_key", ""))

    resolved_provider = (
        AI_PROVIDER_DEEPSEEK if runtime_api_key else settings.normalized_ai_provider
    )
    preset = AI_PROVIDER_PRESETS[resolved_provider]

    if resolved_provider == AI_PROVIDER_DEEPSEEK:
        resolved_api_key = _first_non_empty(
            runtime_api_key,
            settings.ai_api_key,
            settings.deepseek_api_key,
        )
        resolved_base_url = _first_non_empty(
            settings.ai_base_url,
            settings.deepseek_base_url,
            preset["base_url"],
        )
        resolved_model = _first_non_empty(
            settings.ai_model,
            settings.deepseek_model,
            preset["model"],
        )
        resolved_fallback_model = (
            _first_non_empty(
                settings.ai_fallback_model,
                settings.deepseek_fallback_model,
                preset["fallback_model"],
            )
            or None
        )
        key_source = (
            "runtime" if runtime_api_key else "environment" if resolved_api_key else "unset"
        )
    elif resolved_provider == AI_PROVIDER_OPENAI:
        resolved_api_key = _first_non_empty(settings.ai_api_key, settings.openai_api_key)
        resolved_base_url = _first_non_empty(
            settings.ai_base_url,
            settings.openai_base_url,
            preset["base_url"],
        )
        resolved_model = _first_non_empty(
            settings.ai_model,
            settings.openai_model,
            preset["model"],
        )
        resolved_fallback_model = (
            _first_non_empty(
                settings.ai_fallback_model,
                settings.openai_fallback_model,
                preset["fallback_model"],
            )
            or None
        )
        key_source = "environment" if resolved_api_key else "unset"
    else:
        resolved_api_key = _first_non_empty(
            settings.ai_api_key,
            settings.openai_api_key,
            settings.deepseek_api_key,
        )
        resolved_base_url = _first_non_empty(
            settings.ai_base_url,
            settings.openai_base_url,
            settings.deepseek_base_url,
            preset["base_url"],
        )
        resolved_model = _first_non_empty(
            settings.ai_model,
            settings.openai_model,
            settings.deepseek_model,
            preset["model"],
        )
        resolved_fallback_model = (
            _first_non_empty(
                settings.ai_fallback_model,
                settings.openai_fallback_model,
                settings.deepseek_fallback_model,
                preset["fallback_model"],
            )
            or None
        )
        key_source = "environment" if resolved_api_key else "unset"

    resolved_timeout_seconds = (
        float(settings.ai_timeout_seconds)
        if settings.ai_timeout_seconds is not None
        else float(settings.openai_timeout_seconds)
        if settings.openai_timeout_seconds is not None
        else float(preset["timeout_seconds"])
    )
    resolved_max_retries = (
        int(settings.ai_max_retries)
        if settings.ai_max_retries is not None
        else int(settings.openai_max_retries)
        if settings.openai_max_retries is not None
        else int(preset["max_retries"])
    )

    return {
        "provider_name": resolved_provider,
        "api_key": resolved_api_key,
        "base_url": resolved_base_url,
        "default_model": resolved_model,
        "fallback_model": resolved_fallback_model,
        "timeout_seconds": resolved_timeout_seconds,
        "max_retries": resolved_max_retries,
        "key_source": key_source,
    }


def get_bilibili_runtime_auth(session: Session) -> dict[str, Any]:
    return get_system_config_value(session, BILIBILI_RUNTIME_AUTH_KEY) or {}


def update_bilibili_runtime_auth_config(
    session: Session,
    *,
    cookie: str,
    account_profile: dict[str, Any] | None = None,
    import_source: dict[str, Any] | None = None,
    validation_message: str | None = None,
) -> SystemConfig:
    normalized_payload = _normalize_bilibili_runtime_payload(
        cookie=cookie,
        account_profile=account_profile,
        import_source=import_source,
        validation_message=validation_message,
    )
    return upsert_system_config(
        session,
        config_key=BILIBILI_RUNTIME_AUTH_KEY,
        config_name="Bilibili runtime auth",
        config_group="crawler",
        config_value=normalized_payload,
        description="Runtime Bilibili authentication settings managed from the frontend.",
        is_active=True,
    )


def resolve_bilibili_auth_settings(
    session: Session | None,
    settings: Settings,
) -> dict[str, Any]:
    runtime_payload = get_bilibili_runtime_auth(session) if session is not None else {}
    runtime_cookie = _first_non_empty(runtime_payload.get("bilibili_cookie", ""))
    runtime_cookie_pairs = _parse_cookie_string(runtime_cookie)
    runtime_values = {
        attr_name: _first_non_empty(
            runtime_payload.get(attr_name, ""),
            runtime_cookie_pairs.get(cookie_name, ""),
        )
        for cookie_name, attr_name in BILIBILI_COOKIE_FIELD_MAP
    }

    environment_cookie = _first_non_empty(settings.bilibili_cookie)
    environment_cookie_pairs = _parse_cookie_string(environment_cookie)
    environment_values = {
        attr_name: _first_non_empty(
            getattr(settings, attr_name, ""),
            environment_cookie_pairs.get(cookie_name, ""),
        )
        for cookie_name, attr_name in BILIBILI_COOKIE_FIELD_MAP
    }

    has_runtime_auth = bool(runtime_cookie) or any(runtime_values.values())
    has_environment_auth = bool(environment_cookie) or any(environment_values.values())
    resolved_values = {
        attr_name: runtime_values.get(attr_name) or environment_values.get(attr_name, "")
        for _cookie_name, attr_name in BILIBILI_COOKIE_FIELD_MAP
    }
    resolved_cookie = _compose_bilibili_cookie_string(resolved_values)
    account_profile = (
        runtime_payload.get("account_profile")
        if has_runtime_auth and isinstance(runtime_payload.get("account_profile"), dict)
        else None
    )
    import_source = (
        runtime_payload.get("import_source")
        if has_runtime_auth and isinstance(runtime_payload.get("import_source"), dict)
        else None
    )
    validation_message = (
        str(runtime_payload.get("validation_message") or "").strip() or None
        if has_runtime_auth
        else None
    )

    return {
        "cookie": resolved_cookie,
        "bilibili_sessdata": resolved_values.get("bilibili_sessdata", ""),
        "bilibili_bili_jct": resolved_values.get("bilibili_bili_jct", ""),
        "bilibili_dedeuserid": resolved_values.get("bilibili_dedeuserid", ""),
        "bilibili_buvid3": resolved_values.get("bilibili_buvid3", ""),
        "bilibili_buvid4": resolved_values.get("bilibili_buvid4", ""),
        "cookie_configured": bool(resolved_cookie),
        "key_source": (
            "runtime" if has_runtime_auth else "environment" if has_environment_auth else "unset"
        ),
        "account_profile": account_profile,
        "import_source": import_source,
        "validation_message": validation_message,
    }


def build_bilibili_runtime_settings(
    session: Session | None,
    settings: Settings | Any,
) -> Any:
    base_values = _settings_to_dict(settings)
    resolved = resolve_bilibili_auth_settings(session, settings)
    base_values.update(
        {
            "bilibili_cookie": resolved["cookie"],
            "bilibili_sessdata": resolved["bilibili_sessdata"],
            "bilibili_bili_jct": resolved["bilibili_bili_jct"],
            "bilibili_dedeuserid": resolved["bilibili_dedeuserid"],
            "bilibili_buvid3": resolved["bilibili_buvid3"],
            "bilibili_buvid4": resolved["bilibili_buvid4"],
        }
    )
    return SimpleNamespace(**base_values)


def get_task_creation_defaults(
    session: Session,
    settings: Settings,
) -> dict[str, Any]:
    crawl_defaults = get_system_config_value(session, "crawl.default_limits") or {}
    ip_defaults = get_system_config_value(session, "crawl.ip_strategy") or {}

    enable_proxy = bool(ip_defaults.get("enable_proxy", False))
    source_ip_strategy = str(
        ip_defaults.get("mode", "proxy_pool" if enable_proxy else "local_sleep")
    )

    return {
        "requested_video_limit": int(
            crawl_defaults.get("requested_video_limit", settings.crawler_max_videos)
        ),
        "max_pages": int(crawl_defaults.get("max_pages", settings.crawler_max_pages)),
        "min_sleep_seconds": float(
            crawl_defaults.get("min_sleep_seconds", settings.crawler_min_sleep)
        ),
        "max_sleep_seconds": float(
            crawl_defaults.get("max_sleep_seconds", settings.crawler_max_sleep)
        ),
        "enable_proxy": enable_proxy,
        "source_ip_strategy": source_ip_strategy,
    }


def get_ai_summary_defaults(
    session: Session,
    settings: Settings,
) -> dict[str, Any]:
    summary_defaults = get_system_config_value(session, "ai.summary_defaults") or {}
    quality_defaults = get_system_config_value(session, "ai.quality_control") or {}
    env_model = _get_optional_setting(settings, "ai_model")
    env_fallback_model = _get_optional_setting(settings, "ai_fallback_model")

    if hasattr(settings, "resolved_ai_model"):
        default_model = str(settings.resolved_ai_model or "gpt-4o-mini")
    else:
        default_model = _get_setting(
            settings,
            "ai_model",
            "openai_model",
            default="gpt-4o-mini",
        )

    if hasattr(settings, "resolved_ai_fallback_model"):
        default_fallback_model = settings.resolved_ai_fallback_model
    else:
        default_fallback_model = _get_optional_setting(
            settings,
            "ai_fallback_model",
            "openai_fallback_model",
        )

    max_topic_count = int(
        quality_defaults.get(
            "max_topic_count",
            summary_defaults.get("topic_count", 5),
        )
    )
    max_topic_count = max(1, min(max_topic_count, TOPIC_LIMIT_CAP))

    resolved_provider = _get_setting(
        settings,
        "normalized_ai_provider",
        "ai_provider",
        default="openai",
    )
    resolved_model = str(env_model or summary_defaults.get("model") or default_model)
    if env_model is not None:
        resolved_fallback_model = env_fallback_model or default_fallback_model
    else:
        resolved_fallback_model = (
            env_fallback_model
            or summary_defaults.get("fallback_model")
            or default_fallback_model
        )

    return {
        "provider": resolved_provider,
        "model": resolved_model,
        "fallback_model": str(resolved_fallback_model or "") or None,
        "summary_max_length": int(summary_defaults.get("summary_max_length", 200)),
        "topic_count": max(
            1,
            min(int(summary_defaults.get("topic_count", max_topic_count)), max_topic_count),
        ),
        "prompt_version": str(summary_defaults.get("prompt_version", "v1")),
        "temperature": float(summary_defaults.get("temperature", 0.2)),
    }


def get_ai_batch_defaults(session: Session) -> dict[str, Any]:
    batch_defaults = get_system_config_value(session, "ai.batch_defaults") or {}
    return {
        "batch_size": int(batch_defaults.get("batch_size", 10)),
        "max_retries": int(batch_defaults.get("max_retries", 2)),
        "fallback_enabled": bool(batch_defaults.get("fallback_enabled", True)),
        "reuse_existing_results": bool(
            batch_defaults.get("reuse_existing_results", True)
        ),
    }


def get_ai_quality_control_defaults(session: Session) -> dict[str, Any]:
    quality_defaults = get_system_config_value(session, "ai.quality_control") or {}
    max_topic_count = max(
        1,
        min(int(quality_defaults.get("max_topic_count", 5)), TOPIC_LIMIT_CAP),
    )
    min_topic_count = max(
        1,
        min(int(quality_defaults.get("min_topic_count", 3)), max_topic_count),
    )
    return {
        "min_summary_length": int(quality_defaults.get("min_summary_length", 40)),
        "max_summary_length": int(quality_defaults.get("max_summary_length", 200)),
        "min_topic_count": min_topic_count,
        "max_topic_count": max_topic_count,
        "fallback_primary_topic": str(
            quality_defaults.get("fallback_primary_topic", "视频主题")
        ),
        "fallback_tone": str(quality_defaults.get("fallback_tone", "neutral")),
    }


def get_topic_clustering_defaults(session: Session) -> dict[str, Any]:
    clustering_defaults = (
        get_system_config_value(session, "analysis.topic_clustering") or {}
    )
    topic_aliases = clustering_defaults.get("topic_aliases", {})
    normalized_aliases = {
        str(canonical): [str(item) for item in aliases]
        for canonical, aliases in topic_aliases.items()
        if isinstance(aliases, list)
    }

    return {
        "max_topic_keywords": int(clustering_defaults.get("max_topic_keywords", 5)),
        "min_cluster_size": int(clustering_defaults.get("min_cluster_size", 2)),
        "max_cluster_count": max(
            1,
            min(int(clustering_defaults.get("max_cluster_count", TOPIC_LIMIT_CAP)), TOPIC_LIMIT_CAP),
        ),
        "fallback_primary_topic": str(
            clustering_defaults.get("fallback_primary_topic", "视频主题")
        ),
        "stop_topics": [
            str(topic)
            for topic in clustering_defaults.get("stop_topics", [])
            if str(topic).strip()
        ],
        "topic_aliases": normalized_aliases,
    }


def get_statistics_defaults(session: Session) -> dict[str, Any]:
    statistics_defaults = (
        get_system_config_value(session, "analysis.statistics_defaults") or {}
    )
    return {
        "top_topic_limit": int(statistics_defaults.get("top_topic_limit", 10)),
        "cooccurrence_limit": int(statistics_defaults.get("cooccurrence_limit", 10)),
        "distribution_bucket_limit": int(
            statistics_defaults.get("distribution_bucket_limit", 30)
        ),
    }


def _settings_to_dict(settings: Settings | Any) -> dict[str, Any]:
    if hasattr(settings, "model_dump"):
        return dict(settings.model_dump())
    return dict(vars(settings))


def _normalize_bilibili_runtime_payload(
    *,
    cookie: str,
    account_profile: dict[str, Any] | None,
    import_source: dict[str, Any] | None,
    validation_message: str | None,
) -> dict[str, Any]:
    cookie_pairs = _parse_cookie_string(cookie)
    field_values = {
        attr_name: cookie_pairs.get(cookie_name, "")
        for cookie_name, attr_name in BILIBILI_COOKIE_FIELD_MAP
    }
    composed_cookie = _compose_bilibili_cookie_string(field_values)
    payload: dict[str, Any] = {
        "bilibili_cookie": composed_cookie,
        **field_values,
        "account_profile": account_profile or {},
        "import_source": import_source or {},
        "validation_message": (validation_message or "").strip(),
    }
    return payload


def _parse_cookie_string(raw_cookie: str) -> dict[str, str]:
    cookie_map: dict[str, str] = {}
    for chunk in str(raw_cookie or "").split(";"):
        item = chunk.strip()
        if not item or "=" not in item:
            continue
        name, value = item.split("=", 1)
        normalized_name = name.strip()
        normalized_value = value.strip()
        if normalized_name and normalized_value:
            cookie_map[normalized_name] = normalized_value
    return cookie_map


def _compose_bilibili_cookie_string(values: dict[str, str]) -> str:
    parts: list[str] = []
    for cookie_name, attr_name in BILIBILI_COOKIE_FIELD_MAP:
        value = _first_non_empty(values.get(attr_name, ""))
        if value:
            parts.append(f"{cookie_name}={value}")
    return "; ".join(parts)


def _get_setting(settings: Settings | Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if not hasattr(settings, name):
            continue
        value = getattr(settings, name)
        if value is None:
            continue
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                continue
            return normalized
        return value
    return default


def _get_optional_setting(settings: Settings | Any, *names: str) -> str | None:
    value = _get_setting(settings, *names, default="")
    normalized = str(value).strip()
    return normalized or None


def _first_non_empty(*values: object) -> str:
    for value in values:
        normalized = str(value or "").strip()
        if normalized:
            return normalized
    return ""
