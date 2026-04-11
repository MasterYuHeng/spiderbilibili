from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_session_factory
from app.models.analysis import SystemConfig

DEFAULT_SYSTEM_CONFIGS = [
    {
        "config_key": "crawl.default_limits",
        "config_name": "Default crawl limits",
        "config_group": "crawl",
        "config_value": {
            "requested_video_limit": 100,
            "max_pages": 5,
            "min_sleep_seconds": 1.5,
            "max_sleep_seconds": 5.0,
        },
        "description": "Default limits for keyword-based crawl tasks.",
    },
    {
        "config_key": "crawl.ip_strategy",
        "config_name": "Default IP strategy",
        "config_group": "crawl",
        "config_value": {
            "mode": "local_sleep",
            "enable_proxy": False,
            "proxy_provider": None,
        },
        "description": "Use local IP with sleep throttling as the default strategy.",
    },
    {
        "config_key": "analysis.scoring_weights",
        "config_name": "Composite score weights",
        "config_group": "analysis",
        "config_value": {
            "relevance_weight": 0.4,
            "heat_weight": 0.6,
            "heat_dimensions": [
                "view_count",
                "like_count",
                "coin_count",
                "favorite_count",
                "reply_count",
                "danmaku_count",
            ],
        },
        "description": "Default weights for relevance and popularity scoring.",
    },
    {
        "config_key": "analysis.topic_clustering",
        "config_name": "Topic clustering defaults",
        "config_group": "analysis",
        "config_value": {
            "max_topic_keywords": 5,
            "min_cluster_size": 2,
            "max_cluster_count": 10,
            "fallback_primary_topic": "视频主题",
            "stop_topics": [
                "视频",
                "内容",
                "总结",
                "教程",
                "分享",
            ],
            "topic_aliases": {
                "ai": ["人工智能", "a.i.", "AI"],
                "机器人": ["robotics", "robot"],
                "产品": ["product", "产品趋势"],
                "教程": ["教学", "入门教程"],
            },
        },
        "description": "Default settings for topic grouping and normalization.",
    },
    {
        "config_key": "analysis.statistics_defaults",
        "config_name": "Statistics defaults",
        "config_group": "analysis",
        "config_value": {
            "top_topic_limit": 10,
            "cooccurrence_limit": 10,
            "distribution_bucket_limit": 30,
        },
        "description": "Default limits for topic and analysis statistics outputs.",
    },
    {
        "config_key": "ai.batch_defaults",
        "config_name": "AI batch defaults",
        "config_group": "ai",
        "config_value": {
            "batch_size": 10,
            "max_retries": 2,
            "fallback_enabled": True,
            "reuse_existing_results": True,
        },
        "description": "Default batch size and retry behavior for AI analysis.",
    },
    {
        "config_key": "ai.quality_control",
        "config_name": "AI quality control defaults",
        "config_group": "ai",
        "config_value": {
            "min_summary_length": 40,
            "max_summary_length": 200,
            "min_topic_count": 3,
            "max_topic_count": 10,
            "fallback_primary_topic": "视频主题",
            "fallback_tone": "neutral",
        },
        "description": "Validation and fallback rules for AI-generated summaries.",
    },
    {
        "config_key": "ai.summary_defaults",
        "config_name": "AI summary defaults",
        "config_group": "ai",
        "config_value": {
            "provider": None,
            "model": None,
            "fallback_model": None,
            "summary_max_length": 200,
            "topic_count": 10,
            "prompt_version": "v1",
            "temperature": 0.2,
        },
        "description": (
            "Default settings for per-video AI summaries and topic extraction."
        ),
    },
]


def bootstrap_system_configs(session: Session, *, commit: bool = True) -> int:
    inserted_or_updated = 0

    for payload in DEFAULT_SYSTEM_CONFIGS:
        statement = select(SystemConfig).where(
            SystemConfig.config_key == payload["config_key"]
        )
        current = session.scalar(statement)

        if current is None:
            session.add(SystemConfig(**payload))
            inserted_or_updated += 1
            continue

        current.config_name = payload["config_name"]
        current.config_group = payload["config_group"]
        current.config_value = payload["config_value"]
        current.description = payload["description"]
        current.is_active = True
        inserted_or_updated += 1

    if commit:
        session.commit()
    else:
        session.flush()

    return inserted_or_updated


def main() -> None:
    session_factory = get_session_factory()
    with session_factory() as session:
        affected_rows = bootstrap_system_configs(session, commit=True)
        print(f"Bootstrapped {affected_rows} system config records.")


if __name__ == "__main__":
    main()
