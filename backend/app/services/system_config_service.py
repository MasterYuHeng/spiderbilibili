from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.analysis import SystemConfig

TOPIC_LIMIT_CAP = 10


def get_system_config_value(session: Session, config_key: str) -> dict[str, Any] | None:
    statement = select(SystemConfig).where(
        SystemConfig.config_key == config_key,
        SystemConfig.is_active.is_(True),
    )
    config = session.scalar(statement)
    if config is None:
        return None
    return dict(config.config_value)


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
            min(
                int(summary_defaults.get("topic_count", max_topic_count)),
                max_topic_count,
            ),
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
            min(
                int(clustering_defaults.get("max_cluster_count", TOPIC_LIMIT_CAP)),
                TOPIC_LIMIT_CAP,
            ),
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


def _get_setting(settings: Settings, *names: str, default: Any = None) -> Any:
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


def _get_optional_setting(settings: Settings, *names: str) -> str | None:
    value = _get_setting(settings, *names, default="")
    normalized = str(value).strip()
    return normalized or None
