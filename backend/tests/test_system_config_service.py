from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.analysis import SystemConfig
from app.services.system_config_service import (
    build_bilibili_runtime_settings,
    get_ai_batch_defaults,
    get_ai_quality_control_defaults,
    get_ai_runtime_overrides,
    get_ai_summary_defaults,
    get_statistics_defaults,
    get_system_config_value,
    get_task_creation_defaults,
    get_topic_clustering_defaults,
    resolve_ai_client_settings,
    resolve_bilibili_auth_settings,
    update_bilibili_runtime_auth_config,
    update_deepseek_runtime_config,
)


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return factory()


def build_settings() -> SimpleNamespace:
    return SimpleNamespace(
        ai_provider="openai",
        ai_api_key="",
        ai_base_url="",
        ai_model="",
        ai_fallback_model="",
        ai_timeout_seconds=None,
        ai_max_retries=None,
        crawler_max_videos=80,
        crawler_max_pages=8,
        crawler_min_sleep=0.5,
        crawler_max_sleep=3.5,
        deepseek_api_key="",
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-chat",
        deepseek_fallback_model="",
        openai_model="gpt-5.4-mini",
        openai_api_key="openai-env-key",
        openai_base_url="https://api.openai.com/v1",
        openai_fallback_model="gpt-4.1-mini",
        openai_timeout_seconds=None,
        openai_max_retries=None,
        normalized_ai_provider="openai",
        bilibili_cookie="SESSDATA=env-sess; bili_jct=env-jct; DedeUserID=10001",
        bilibili_sessdata="",
        bilibili_bili_jct="",
        bilibili_dedeuserid="",
        bilibili_buvid3="",
        bilibili_buvid4="",
        bilibili_user_agent="Mozilla/5.0 test",
        http_timeout_seconds=20.0,
        http_max_retries=3,
        https_proxy="",
        http_proxy="",
        playwright_timeout_seconds=30.0,
        playwright_headless=True,
    )


def build_system_config(
    *,
    key: str,
    value: dict[str, Any],
    is_active: bool = True,
    name: str | None = None,
    group: str = "test",
) -> SystemConfig:
    return SystemConfig(
        config_key=key,
        config_name=name or key,
        config_group=group,
        config_value=value,
        is_active=is_active,
    )


def test_get_system_config_value_returns_only_active_payloads() -> None:
    with build_session() as session:
        config = build_system_config(
            key="crawl.default_limits",
            value={"requested_video_limit": 20},
            is_active=False,
        )
        session.add(config)
        session.commit()

        assert get_system_config_value(session, "crawl.default_limits") is None

        config.is_active = True
        config.config_value = {"requested_video_limit": 30}
        session.commit()

        value = get_system_config_value(session, "crawl.default_limits")

    assert value == {"requested_video_limit": 30}


def test_task_creation_defaults_merge_database_values_with_settings() -> None:
    with build_session() as session:
        session.add_all(
            [
                build_system_config(
                    key="crawl.default_limits",
                    value={
                        "requested_video_limit": 25,
                        "max_pages": 6,
                        "min_sleep_seconds": 1.25,
                        "max_sleep_seconds": 2.5,
                    },
                ),
                build_system_config(
                    key="crawl.ip_strategy",
                    value={"enable_proxy": True, "mode": "proxy_pool"},
                ),
            ]
        )
        session.commit()

        defaults = get_task_creation_defaults(session, build_settings())

    assert defaults == {
        "requested_video_limit": 25,
        "max_pages": 6,
        "min_sleep_seconds": 1.25,
        "max_sleep_seconds": 2.5,
        "enable_proxy": True,
        "source_ip_strategy": "proxy_pool",
    }


def test_ai_defaults_and_statistics_use_fallbacks_when_configs_are_missing() -> None:
    with build_session() as session:
        ai_summary_defaults = get_ai_summary_defaults(session, build_settings())
        ai_batch_defaults = get_ai_batch_defaults(session)
        quality_defaults = get_ai_quality_control_defaults(session)
        clustering_defaults = get_topic_clustering_defaults(session)
        statistics_defaults = get_statistics_defaults(session)

    assert ai_summary_defaults["model"] == "gpt-5.4-mini"
    assert ai_summary_defaults["fallback_model"] == "gpt-4.1-mini"
    assert ai_summary_defaults["provider"] == "openai"
    assert ai_summary_defaults["topic_count"] == 5
    assert ai_batch_defaults == {
        "batch_size": 10,
        "max_retries": 2,
        "fallback_enabled": True,
        "reuse_existing_results": True,
    }
    assert quality_defaults["fallback_primary_topic"] == "视频主题"
    assert clustering_defaults["topic_aliases"] == {}
    assert clustering_defaults["max_cluster_count"] == 10
    assert statistics_defaults["top_topic_limit"] == 10


def test_topic_clustering_defaults_normalize_alias_lists() -> None:
    with build_session() as session:
        session.add(
            build_system_config(
                key="analysis.topic_clustering",
                value={
                    "max_topic_keywords": 7,
                    "min_cluster_size": 3,
                    "max_cluster_count": 9,
                    "stop_topics": ["hotspot", "", "  ", "recommend"],
                    "topic_aliases": {
                        "ai": ["artificial intelligence", "AIGC"],
                        "invalid": "should-be-ignored",
                    },
                },
            )
        )
        session.commit()

        defaults = get_topic_clustering_defaults(session)

    assert defaults["max_topic_keywords"] == 7
    assert defaults["min_cluster_size"] == 3
    assert defaults["max_cluster_count"] == 9
    assert defaults["stop_topics"] == ["hotspot", "recommend"]
    assert defaults["topic_aliases"] == {"ai": ["artificial intelligence", "AIGC"]}


def test_ai_summary_defaults_allow_environment_override_to_switch_provider() -> None:
    with build_session() as session:
        session.add(
            build_system_config(
                key="ai.summary_defaults",
                value={
                    "model": "gpt-4o-mini",
                    "fallback_model": "gpt-4.1-mini",
                    "topic_count": 4,
                },
                group="ai",
            )
        )
        session.commit()

        settings = SimpleNamespace(
            ai_provider="deepseek",
            ai_model="deepseek-chat",
            ai_fallback_model="",
            openai_model="gpt-4o-mini",
            openai_fallback_model="gpt-4.1-mini",
            resolved_ai_model="deepseek-chat",
            resolved_ai_fallback_model=None,
            normalized_ai_provider="deepseek",
        )
        defaults = get_ai_summary_defaults(session, settings)

    assert defaults["provider"] == "deepseek"
    assert defaults["model"] == "deepseek-chat"
    assert defaults["fallback_model"] is None
    assert defaults["topic_count"] == 4


def test_update_deepseek_runtime_config_persists_frontend_managed_key() -> None:
    with build_session() as session:
        record = update_deepseek_runtime_config(session, api_key="deepseek-runtime-key")
        session.commit()
        stored = get_ai_runtime_overrides(session)

    assert record.config_key == "ai.runtime_overrides"
    assert stored == {
        "provider": "deepseek",
        "api_key": "deepseek-runtime-key",
    }


def test_resolve_ai_client_settings_prefers_runtime_deepseek_key() -> None:
    with build_session() as session:
        update_deepseek_runtime_config(session, api_key="deepseek-runtime-key")
        session.commit()
        settings = build_settings()
        resolved = resolve_ai_client_settings(session, settings)

    assert resolved["provider_name"] == "deepseek"
    assert resolved["api_key"] == "deepseek-runtime-key"
    assert resolved["base_url"] == "https://api.deepseek.com"
    assert resolved["default_model"] == "deepseek-chat"
    assert resolved["key_source"] == "runtime"


def test_update_bilibili_runtime_config_parses_cookie_and_stores_account_profile() -> (
    None
):
    with build_session() as session:
        update_bilibili_runtime_auth_config(
            session,
            cookie=(
                "SESSDATA=runtime-sess; bili_jct=runtime-jct; "
                "DedeUserID=2233; buvid3=aaa"
            ),
            account_profile={"is_login": True, "mid": "2233", "username": "测试账号"},
            import_source={"label": "Microsoft Edge / Default"},
            validation_message=None,
        )
        session.commit()
        resolved = resolve_bilibili_auth_settings(session, build_settings())

    assert resolved["key_source"] == "runtime"
    assert (
        resolved["cookie"]
        == "SESSDATA=runtime-sess; bili_jct=runtime-jct; DedeUserID=2233; buvid3=aaa"
    )
    assert resolved["bilibili_sessdata"] == "runtime-sess"
    assert resolved["bilibili_bili_jct"] == "runtime-jct"
    assert resolved["bilibili_dedeuserid"] == "2233"
    assert resolved["account_profile"] == {
        "is_login": True,
        "mid": "2233",
        "username": "测试账号",
    }


def test_build_bilibili_runtime_settings_overrides_environment_values() -> None:
    with build_session() as session:
        update_bilibili_runtime_auth_config(
            session,
            cookie="SESSDATA=runtime-sess; bili_jct=runtime-jct; DedeUserID=2233",
            account_profile=None,
            import_source=None,
            validation_message="",
        )
        session.commit()
        runtime_settings = build_bilibili_runtime_settings(session, build_settings())

    assert (
        runtime_settings.bilibili_cookie
        == "SESSDATA=runtime-sess; bili_jct=runtime-jct; DedeUserID=2233"
    )
    assert runtime_settings.bilibili_sessdata == "runtime-sess"
    assert runtime_settings.bilibili_bili_jct == "runtime-jct"
    assert runtime_settings.bilibili_dedeuserid == "2233"
