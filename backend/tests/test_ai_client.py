from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.core.exceptions import ServiceUnavailableError
from app.services.ai_client import AiPromptBundle, OpenAICompatibleAiClient


class FakeChatCompletions:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if callable(self.response):
            return self.response(**kwargs)
        return self.response


class FakeOpenAIClient:
    def __init__(self, response):
        self.chat = SimpleNamespace(completions=FakeChatCompletions(response))


def build_response(content: str, *, model: str = "gpt-test"):
    return SimpleNamespace(
        model=model,
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
            )
        ],
    )


def set_required_runtime_env(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/1")
    monkeypatch.setenv("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/2")


def test_openai_compatible_client_parses_json_response() -> None:
    response = build_response(
        '{"summary":"AI视频总结","topics":["AI","产品"],'
        '"primary_topic":"AI","tone":"neutral","confidence":0.91}'
    )
    fake_client = FakeOpenAIClient(response)
    client = OpenAICompatibleAiClient(
        provider_name="openai",
        api_key="test-key",
        base_url="https://example.com/v1",
        default_model="gpt-test",
        fallback_model="gpt-fallback",
        timeout_seconds=10,
        max_retries=2,
        openai_client=fake_client,
    )

    result = client.generate_summary(
        AiPromptBundle(
            system_prompt="system",
            user_prompt="user",
            model="gpt-4o-mini",
            fallback_model="gpt-4.1-mini",
            temperature=0.2,
        )
    )

    assert result.payload.summary == "AI视频总结"
    assert result.payload.topics == ["AI", "产品"]
    assert result.model_name == "gpt-test"
    assert fake_client.chat.completions.calls[0]["model"] == "gpt-4o-mini"


def test_openai_compatible_client_requires_api_key() -> None:
    client = OpenAICompatibleAiClient(
        provider_name="openai",
        api_key="",
        base_url="https://example.com/v1",
        default_model="gpt-test",
        fallback_model="gpt-fallback",
        timeout_seconds=10,
        max_retries=2,
        openai_client=FakeOpenAIClient(build_response("{}")),
    )

    with pytest.raises(ServiceUnavailableError):
        client.generate_summary(
            AiPromptBundle(
                system_prompt="system",
                user_prompt="user",
                model="gpt-4o-mini",
                fallback_model="gpt-4.1-mini",
                temperature=0.2,
            )
        )


def test_openai_compatible_client_falls_back_to_secondary_model() -> None:
    def response_factory(**kwargs):
        if kwargs["model"] == "gpt-4o-mini":
            raise ValueError("primary model returned invalid payload")
        return build_response(
            '{"summary":"降级模型摘要","topics":["AI","成本"],'
            '"primary_topic":"AI","tone":"neutral","confidence":0.77}',
            model=kwargs["model"],
        )

    fake_client = FakeOpenAIClient(response_factory)
    client = OpenAICompatibleAiClient(
        provider_name="openai",
        api_key="test-key",
        base_url="https://example.com/v1",
        default_model="gpt-test",
        fallback_model="gpt-fallback",
        timeout_seconds=10,
        max_retries=1,
        openai_client=fake_client,
    )

    result = client.generate_summary(
        AiPromptBundle(
            system_prompt="system",
            user_prompt="user",
            model="gpt-4o-mini",
            fallback_model="gpt-4.1-mini",
            temperature=0.2,
        )
    )

    assert result.payload.summary == "降级模型摘要"
    assert [call["model"] for call in fake_client.chat.completions.calls] == [
        "gpt-4o-mini",
        "gpt-4.1-mini",
    ]


def test_openai_compatible_client_generate_json_returns_object_payload() -> None:
    response = build_response(
        '{"outputs":[{"key":"melon_reader","content":"热点结果"}]}'
    )
    fake_client = FakeOpenAIClient(response)
    client = OpenAICompatibleAiClient(
        provider_name="openai",
        api_key="test-key",
        base_url="https://example.com/v1",
        default_model="gpt-test",
        fallback_model="gpt-fallback",
        timeout_seconds=10,
        max_retries=2,
        openai_client=fake_client,
    )

    result = client.generate_json(
        AiPromptBundle(
            system_prompt="system",
            user_prompt="user",
            model="gpt-4o-mini",
            fallback_model="gpt-4.1-mini",
            temperature=0.2,
        )
    )

    assert result.payload["outputs"][0]["key"] == "melon_reader"
    assert result.model_name == "gpt-test"


def test_settings_resolve_deepseek_provider_defaults(monkeypatch) -> None:
    set_required_runtime_env(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "deepseek")
    monkeypatch.setenv("AI_API_KEY", "deepseek-key")

    settings = Settings(_env_file=None)

    assert settings.normalized_ai_provider == "deepseek"
    assert settings.resolved_ai_api_key == "deepseek-key"
    assert settings.resolved_ai_base_url == "https://api.deepseek.com"
    assert settings.resolved_ai_model == "deepseek-chat"
    assert settings.resolved_ai_fallback_model is None


def test_settings_keep_legacy_openai_configuration_available(monkeypatch) -> None:
    set_required_runtime_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "legacy-openai-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://legacy.example.com/v1")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-legacy")
    monkeypatch.setenv("OPENAI_FALLBACK_MODEL", "gpt-legacy-fallback")

    settings = Settings(_env_file=None)

    assert settings.normalized_ai_provider == "openai"
    assert settings.resolved_ai_api_key == "legacy-openai-key"
    assert settings.resolved_ai_base_url == "https://legacy.example.com/v1"
    assert settings.resolved_ai_model == "gpt-legacy"
    assert settings.resolved_ai_fallback_model == "gpt-legacy-fallback"
