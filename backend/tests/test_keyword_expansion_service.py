from datetime import datetime
from types import SimpleNamespace

from app.services.ai_client import AiJsonResponse, AiPromptBundle
from app.services.keyword_expansion_service import KeywordExpansionService


class StubAiClient:
    def __init__(
        self,
        *,
        available: bool = True,
        response: AiJsonResponse | None = None,
        error: Exception | None = None,
        default_model: str = "gpt-test",
        fallback_model: str | None = "gpt-fallback",
    ) -> None:
        self.available = available
        self.response = response
        self.error = error
        self.default_model = default_model
        self.fallback_model = fallback_model
        self.prompts: list[AiPromptBundle] = []

    def is_available(self) -> bool:
        return self.available

    def generate_json(self, prompt: AiPromptBundle) -> AiJsonResponse:
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        if self.response is None:
            raise AssertionError("response was not configured")
        return self.response


def _build_settings() -> SimpleNamespace:
    return SimpleNamespace(
        resolved_ai_model="gpt-settings-default",
        resolved_ai_fallback_model="gpt-settings-fallback",
    )


def _assert_iso8601_timestamp(value: str | None) -> None:
    assert value is not None
    datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_expand_keyword_returns_skipped_payload_when_disabled() -> None:
    service = KeywordExpansionService(
        ai_client=StubAiClient(),
        settings=_build_settings(),
    )

    result = service.expand_keyword(
        source_keyword="和平精英",
        requested_synonym_count=1,
        enabled=False,
    )

    assert result == {
        "source_keyword": "和平精英",
        "enabled": False,
        "requested_synonym_count": None,
        "generated_synonyms": [],
        "expanded_keywords": ["和平精英"],
        "status": "skipped",
        "model_name": None,
        "error_message": None,
        "generated_at": None,
    }


def test_expand_keyword_returns_fallback_when_ai_is_unavailable() -> None:
    service = KeywordExpansionService(
        ai_client=StubAiClient(available=False),
        settings=_build_settings(),
    )

    result = service.expand_keyword(
        source_keyword="和平精英",
        requested_synonym_count=1,
        enabled=True,
    )

    assert result["status"] == "fallback"
    assert result["generated_synonyms"] == []
    assert result["expanded_keywords"] == ["和平精英"]
    assert result["model_name"] is None
    assert result["error_message"] == "AI keyword expansion is unavailable."
    _assert_iso8601_timestamp(result["generated_at"])


def test_expand_keyword_cleans_deduplicates_and_trims_synonyms() -> None:
    ai_client = StubAiClient(
        response=AiJsonResponse(
            payload={
                "synonyms": [
                    " 吃鸡 ",
                    "和平精英",
                    "吃鸡",
                    "大逃杀",
                    "",
                    None,
                    "手游吃鸡",
                ]
            },
            raw_content='{"synonyms":["吃鸡","和平精英","吃鸡","大逃杀"]}',
            model_name="gpt-4.1-mini",
        ),
    )
    service = KeywordExpansionService(
        ai_client=ai_client,
        settings=_build_settings(),
    )

    result = service.expand_keyword(
        source_keyword="和平精英",
        requested_synonym_count=2,
        enabled=True,
    )

    assert result["status"] == "success"
    assert result["generated_synonyms"] == ["吃鸡", "大逃杀"]
    assert result["expanded_keywords"] == ["和平精英", "吃鸡", "大逃杀"]
    assert result["model_name"] == "gpt-4.1-mini"
    assert result["error_message"] is None
    _assert_iso8601_timestamp(result["generated_at"])
    assert ai_client.prompts[0].model == "gpt-test"
    assert ai_client.prompts[0].fallback_model == "gpt-fallback"


def test_expand_keyword_returns_fallback_when_payload_shape_is_invalid() -> None:
    service = KeywordExpansionService(
        ai_client=StubAiClient(
            response=AiJsonResponse(
                payload={"keywords": ["吃鸡"]},
                raw_content='{"keywords":["吃鸡"]}',
                model_name="gpt-4o-mini",
            )
        ),
        settings=_build_settings(),
    )

    result = service.expand_keyword(
        source_keyword="和平精英",
        requested_synonym_count=1,
        enabled=True,
    )

    assert result["status"] == "fallback"
    assert result["generated_synonyms"] == []
    assert result["expanded_keywords"] == ["和平精英"]
    assert result["model_name"] == "gpt-4o-mini"
    assert "synonyms" in str(result["error_message"])
    _assert_iso8601_timestamp(result["generated_at"])


def test_expand_keyword_returns_fallback_when_cleaned_synonyms_are_empty() -> None:
    service = KeywordExpansionService(
        ai_client=StubAiClient(
            response=AiJsonResponse(
                payload={"synonyms": ["和平精英", " ", "和平精英"]},
                raw_content='{"synonyms":["和平精英"," ","和平精英"]}',
                model_name="gpt-4o-mini",
            )
        ),
        settings=_build_settings(),
    )

    result = service.expand_keyword(
        source_keyword="和平精英",
        requested_synonym_count=1,
        enabled=True,
    )

    assert result["status"] == "fallback"
    assert result["generated_synonyms"] == []
    assert result["expanded_keywords"] == ["和平精英"]
    assert (
        result["error_message"] == "AI keyword expansion returned no valid synonyms."
    )
    _assert_iso8601_timestamp(result["generated_at"])


def test_expand_keyword_returns_failed_when_unexpected_internal_error_occurs(
    monkeypatch,
) -> None:
    service = KeywordExpansionService(
        ai_client=StubAiClient(),
        settings=_build_settings(),
    )
    monkeypatch.setattr(
        service,
        "_expand_with_ai",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    result = service.expand_keyword(
        source_keyword="和平精英",
        requested_synonym_count=1,
        enabled=True,
    )

    assert result["status"] == "failed"
    assert result["generated_synonyms"] == []
    assert result["expanded_keywords"] == ["和平精英"]
    assert "boom" in str(result["error_message"])
    _assert_iso8601_timestamp(result["generated_at"])
