from functools import lru_cache
from pathlib import Path
from typing import Literal, TypedDict

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]
AiProviderName = Literal["openai", "deepseek", "openai_compatible"]


class AiProviderPreset(TypedDict):
    base_url: str
    model: str
    fallback_model: str
    timeout_seconds: float
    max_retries: int


AI_PROVIDER_OPENAI: AiProviderName = "openai"
AI_PROVIDER_DEEPSEEK: AiProviderName = "deepseek"
AI_PROVIDER_OPENAI_COMPATIBLE: AiProviderName = "openai_compatible"
AI_PROVIDER_PRESETS: dict[AiProviderName, AiProviderPreset] = {
    AI_PROVIDER_OPENAI: {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "fallback_model": "gpt-4.1-mini",
        "timeout_seconds": 30.0,
        "max_retries": 3,
    },
    AI_PROVIDER_DEEPSEEK: {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "fallback_model": "",
        "timeout_seconds": 30.0,
        "max_retries": 3,
    },
    AI_PROVIDER_OPENAI_COMPATIBLE: {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "fallback_model": "",
        "timeout_seconds": 30.0,
        "max_retries": 3,
    },
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="spiderbilibili", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_debug: bool = Field(default=True, alias="APP_DEBUG")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    app_api_prefix: str = Field(default="/api", alias="APP_API_PREFIX")
    app_cors_origins: str = Field(
        default="http://127.0.0.1:5173,http://localhost:5173",
        alias="APP_CORS_ORIGINS",
    )

    database_url: str = Field(alias="DATABASE_URL")
    redis_url: str = Field(alias="REDIS_URL")
    celery_broker_url: str = Field(alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field(alias="CELERY_RESULT_BACKEND")

    ai_provider: str = Field(default="", alias="AI_PROVIDER")
    ai_api_key: str = Field(default="", alias="AI_API_KEY")
    ai_base_url: str = Field(default="", alias="AI_BASE_URL")
    ai_model: str = Field(default="", alias="AI_MODEL")
    ai_fallback_model: str = Field(default="", alias="AI_FALLBACK_MODEL")
    ai_timeout_seconds: float | None = Field(
        default=None,
        alias="AI_TIMEOUT_SECONDS",
    )
    ai_max_retries: int | None = Field(default=None, alias="AI_MAX_RETRIES")

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="", alias="OPENAI_BASE_URL")
    openai_model: str = Field(default="", alias="OPENAI_MODEL")
    openai_fallback_model: str = Field(default="", alias="OPENAI_FALLBACK_MODEL")
    openai_timeout_seconds: float | None = Field(
        default=None,
        alias="OPENAI_TIMEOUT_SECONDS",
    )
    openai_max_retries: int | None = Field(
        default=None,
        alias="OPENAI_MAX_RETRIES",
    )
    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(default="", alias="DEEPSEEK_BASE_URL")
    deepseek_model: str = Field(default="", alias="DEEPSEEK_MODEL")
    deepseek_fallback_model: str = Field(
        default="",
        alias="DEEPSEEK_FALLBACK_MODEL",
    )

    http_timeout_seconds: float = Field(default=20.0, alias="HTTP_TIMEOUT_SECONDS")
    http_max_retries: int = Field(default=3, alias="HTTP_MAX_RETRIES")

    proxy_provider: str = Field(default="", alias="PROXY_PROVIDER")
    http_proxy: str = Field(default="", alias="HTTP_PROXY")
    https_proxy: str = Field(default="", alias="HTTPS_PROXY")

    bilibili_user_agent: str = Field(
        default=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
        ),
        alias="BILIBILI_USER_AGENT",
    )
    bilibili_cookie: str = Field(default="", alias="BILIBILI_COOKIE")
    bilibili_sessdata: str = Field(default="", alias="BILIBILI_SESSDATA")
    bilibili_bili_jct: str = Field(default="", alias="BILIBILI_BILI_JCT")
    bilibili_dedeuserid: str = Field(default="", alias="BILIBILI_DEDEUSERID")
    bilibili_buvid3: str = Field(default="", alias="BILIBILI_BUVID3")
    bilibili_buvid4: str = Field(default="", alias="BILIBILI_BUVID4")
    crawler_min_sleep: float = Field(default=1.5, alias="CRAWLER_MIN_SLEEP")
    crawler_max_sleep: float = Field(default=5.0, alias="CRAWLER_MAX_SLEEP")
    crawler_max_pages: int = Field(default=5, alias="CRAWLER_MAX_PAGES")
    crawler_max_videos: int = Field(default=100, alias="CRAWLER_MAX_VIDEOS")
    crawler_concurrency: int = Field(default=1, alias="CRAWLER_CONCURRENCY")
    crawler_backoff_base_seconds: float = Field(
        default=1.0, alias="CRAWLER_BACKOFF_BASE_SECONDS"
    )
    crawler_backoff_max_seconds: float = Field(
        default=20.0, alias="CRAWLER_BACKOFF_MAX_SECONDS"
    )
    crawler_backoff_jitter_seconds: float = Field(
        default=0.5, alias="CRAWLER_BACKOFF_JITTER_SECONDS"
    )
    crawler_circuit_breaker_failure_threshold: int = Field(
        default=4, alias="CRAWLER_CIRCUIT_BREAKER_FAILURE_THRESHOLD"
    )
    crawler_circuit_breaker_recovery_seconds: float = Field(
        default=60.0, alias="CRAWLER_CIRCUIT_BREAKER_RECOVERY_SECONDS"
    )
    crawler_enable_proxy: bool = Field(default=False, alias="CRAWLER_ENABLE_PROXY")
    crawler_rate_limit_per_minute: int = Field(
        default=20, alias="CRAWLER_RATE_LIMIT_PER_MINUTE"
    )
    crawler_save_raw_payloads: bool = Field(
        default=True, alias="CRAWLER_SAVE_RAW_PAYLOADS"
    )
    crawler_raw_data_dir: str = Field(
        default=str(BASE_DIR / "data" / "raw"),
        alias="CRAWLER_RAW_DATA_DIR",
    )
    playwright_headless: bool = Field(default=True, alias="PLAYWRIGHT_HEADLESS")
    playwright_timeout_seconds: float = Field(
        default=30.0,
        alias="PLAYWRIGHT_TIMEOUT_SECONDS",
    )

    pagination_default_page_size: int = Field(
        default=20, alias="PAGINATION_DEFAULT_PAGE_SIZE"
    )
    pagination_max_page_size: int = Field(default=100, alias="PAGINATION_MAX_PAGE_SIZE")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_dir: str = Field(default=str(BASE_DIR / "logs"), alias="LOG_DIR")
    log_rotation: str = Field(default="10 MB", alias="LOG_ROTATION")
    log_retention: str = Field(default="7 days", alias="LOG_RETENTION")

    worker_global_task_concurrency: int = Field(
        default=2, alias="WORKER_GLOBAL_TASK_CONCURRENCY"
    )
    worker_task_concurrency_wait_seconds: float = Field(
        default=60.0, alias="WORKER_TASK_CONCURRENCY_WAIT_SECONDS"
    )
    worker_task_concurrency_poll_seconds: float = Field(
        default=1.0, alias="WORKER_TASK_CONCURRENCY_POLL_SECONDS"
    )
    worker_task_concurrency_lease_seconds: int = Field(
        default=21600, alias="WORKER_TASK_CONCURRENCY_LEASE_SECONDS"
    )
    worker_task_stale_after_seconds: int = Field(
        default=180,
        alias="WORKER_TASK_STALE_AFTER_SECONDS",
    )

    ai_input_char_limit: int = Field(default=2400, alias="AI_INPUT_CHAR_LIMIT")
    ai_reuse_existing_results: bool = Field(
        default=True, alias="AI_REUSE_EXISTING_RESULTS"
    )
    monitoring_enabled: bool = Field(default=True, alias="MONITORING_ENABLED")
    monitoring_redis_prefix: str = Field(
        default="spiderbilibili:monitoring",
        alias="MONITORING_REDIS_PREFIX",
    )
    monitoring_celery_queue_name: str = Field(
        default="celery",
        alias="MONITORING_CELERY_QUEUE_NAME",
    )
    monitoring_worker_heartbeat_ttl_seconds: int = Field(
        default=150,
        alias="MONITORING_WORKER_HEARTBEAT_TTL_SECONDS",
    )
    monitoring_worker_expected_count: int = Field(
        default=1,
        alias="MONITORING_WORKER_EXPECTED_COUNT",
    )

    alerting_enabled: bool = Field(default=False, alias="ALERTING_ENABLED")
    alerting_dedupe_window_seconds: int = Field(
        default=900,
        alias="ALERTING_DEDUPE_WINDOW_SECONDS",
    )
    alerting_request_timeout_seconds: float = Field(
        default=8.0,
        alias="ALERTING_REQUEST_TIMEOUT_SECONDS",
    )
    alerting_wechat_webhook: str = Field(
        default="",
        alias="ALERTING_WECHAT_WEBHOOK",
    )
    alerting_dingtalk_webhook: str = Field(
        default="",
        alias="ALERTING_DINGTALK_WEBHOOK",
    )
    alerting_email_enabled: bool = Field(
        default=False,
        alias="ALERTING_EMAIL_ENABLED",
    )
    alerting_email_smtp_host: str = Field(
        default="",
        alias="ALERTING_EMAIL_SMTP_HOST",
    )
    alerting_email_smtp_port: int = Field(
        default=587,
        alias="ALERTING_EMAIL_SMTP_PORT",
    )
    alerting_email_username: str = Field(
        default="",
        alias="ALERTING_EMAIL_USERNAME",
    )
    alerting_email_password: str = Field(
        default="",
        alias="ALERTING_EMAIL_PASSWORD",
    )
    alerting_email_from: str = Field(
        default="",
        alias="ALERTING_EMAIL_FROM",
    )
    alerting_email_to: str = Field(
        default="",
        alias="ALERTING_EMAIL_TO",
    )
    alerting_email_use_tls: bool = Field(
        default=True,
        alias="ALERTING_EMAIL_USE_TLS",
    )
    app_public_base_url: str = Field(default="", alias="APP_PUBLIC_BASE_URL")

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.app_cors_origins.split(",")
            if origin.strip()
        ]

    @property
    def proxy_mapping(self) -> dict[str, str]:
        proxies: dict[str, str] = {}
        if self.http_proxy:
            proxies["http://"] = self.http_proxy
        if self.https_proxy:
            proxies["https://"] = self.https_proxy
        return proxies

    @property
    def alert_email_recipients(self) -> list[str]:
        return [
            recipient.strip()
            for recipient in self.alerting_email_to.split(",")
            if recipient.strip()
        ]

    @property
    def normalized_ai_provider(self) -> AiProviderName:
        provider = self.ai_provider.strip().casefold().replace("-", "_")
        if not provider:
            if any(
                (
                    self.deepseek_api_key,
                    self.deepseek_base_url,
                    self.deepseek_model,
                )
            ):
                return AI_PROVIDER_DEEPSEEK
            return AI_PROVIDER_OPENAI

        if provider in {"custom", "compatible"}:
            return AI_PROVIDER_OPENAI_COMPATIBLE
        if provider not in AI_PROVIDER_PRESETS:
            return AI_PROVIDER_OPENAI_COMPATIBLE
        return provider

    @property
    def resolved_ai_api_key(self) -> str:
        provider = self.normalized_ai_provider
        if provider == AI_PROVIDER_DEEPSEEK:
            return self._first_non_empty(self.ai_api_key, self.deepseek_api_key)
        if provider == AI_PROVIDER_OPENAI:
            return self._first_non_empty(self.ai_api_key, self.openai_api_key)
        return self._first_non_empty(
            self.ai_api_key,
            self.openai_api_key,
            self.deepseek_api_key,
        )

    @property
    def resolved_ai_base_url(self) -> str:
        provider = self.normalized_ai_provider
        preset_base_url = AI_PROVIDER_PRESETS[provider]["base_url"]
        if provider == AI_PROVIDER_DEEPSEEK:
            return self._first_non_empty(
                self.ai_base_url,
                self.deepseek_base_url,
                preset_base_url,
            )
        if provider == AI_PROVIDER_OPENAI:
            return self._first_non_empty(
                self.ai_base_url,
                self.openai_base_url,
                preset_base_url,
            )
        return self._first_non_empty(
            self.ai_base_url,
            self.openai_base_url,
            self.deepseek_base_url,
            preset_base_url,
        )

    @property
    def resolved_ai_model(self) -> str:
        provider = self.normalized_ai_provider
        preset_model = AI_PROVIDER_PRESETS[provider]["model"]
        if provider == AI_PROVIDER_DEEPSEEK:
            return self._first_non_empty(
                self.ai_model,
                self.deepseek_model,
                preset_model,
            )
        if provider == AI_PROVIDER_OPENAI:
            return self._first_non_empty(
                self.ai_model,
                self.openai_model,
                preset_model,
            )
        return self._first_non_empty(
            self.ai_model,
            self.openai_model,
            self.deepseek_model,
            preset_model,
        )

    @property
    def resolved_ai_fallback_model(self) -> str | None:
        provider = self.normalized_ai_provider
        preset_fallback_model = AI_PROVIDER_PRESETS[provider]["fallback_model"]
        if provider == AI_PROVIDER_DEEPSEEK:
            resolved = self._first_non_empty(
                self.ai_fallback_model,
                self.deepseek_fallback_model,
                preset_fallback_model,
            )
        elif provider == AI_PROVIDER_OPENAI:
            resolved = self._first_non_empty(
                self.ai_fallback_model,
                self.openai_fallback_model,
                preset_fallback_model,
            )
        else:
            resolved = self._first_non_empty(
                self.ai_fallback_model,
                self.openai_fallback_model,
                self.deepseek_fallback_model,
                preset_fallback_model,
            )
        return resolved or None

    @property
    def resolved_ai_timeout_seconds(self) -> float:
        provider = self.normalized_ai_provider
        preset_timeout = AI_PROVIDER_PRESETS[provider]["timeout_seconds"]
        if self.ai_timeout_seconds is not None:
            return float(self.ai_timeout_seconds)
        if self.openai_timeout_seconds is not None:
            return float(self.openai_timeout_seconds)
        return preset_timeout

    @property
    def resolved_ai_max_retries(self) -> int:
        provider = self.normalized_ai_provider
        preset_max_retries = AI_PROVIDER_PRESETS[provider]["max_retries"]
        if self.ai_max_retries is not None:
            return int(self.ai_max_retries)
        if self.openai_max_retries is not None:
            return int(self.openai_max_retries)
        return preset_max_retries

    @staticmethod
    def _first_non_empty(*values: str) -> str:
        for value in values:
            normalized = value.strip()
            if normalized:
                return normalized
        return ""


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
