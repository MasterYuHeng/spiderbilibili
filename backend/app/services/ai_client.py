from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    OpenAI,
    RateLimitError,
)
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import get_settings
from app.core.exceptions import ServiceUnavailableError
from app.core.logging import get_logger
from app.schemas.analysis import VideoAiSummaryDraft

JSON_BLOCK_PATTERN = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


@dataclass(slots=True)
class AiPromptBundle:
    system_prompt: str
    user_prompt: str
    model: str
    fallback_model: str | None
    temperature: float


@dataclass(slots=True)
class AiStructuredResponse:
    payload: VideoAiSummaryDraft
    raw_content: str
    model_name: str | None


@dataclass(slots=True)
class AiJsonResponse:
    payload: dict[str, Any]
    raw_content: str
    model_name: str | None


class AiSummaryClient(Protocol):
    def is_available(self) -> bool:
        ...

    def generate_summary(self, prompt: AiPromptBundle) -> AiStructuredResponse:
        ...


class OpenAiChatCompletionsClient(Protocol):
    def create(self, **kwargs: Any) -> Any:
        ...


class OpenAiChatClient(Protocol):
    completions: OpenAiChatCompletionsClient


class OpenAiCompatibleClient(Protocol):
    chat: OpenAiChatClient


class OpenAICompatibleAiClient:
    def __init__(
        self,
        *,
        provider_name: str,
        api_key: str,
        base_url: str,
        default_model: str,
        fallback_model: str | None,
        timeout_seconds: float,
        max_retries: int,
        openai_client: Any | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.api_key = api_key
        self.base_url = base_url
        self.default_model = default_model
        self.fallback_model = fallback_model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(1, max_retries)
        self.logger = get_logger(__name__)
        self.client = openai_client or OpenAI(
            api_key=api_key or "missing-api-key",
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=0,
        )

    @classmethod
    def from_settings(cls) -> OpenAICompatibleAiClient:
        settings = get_settings()
        return cls(
            provider_name=settings.normalized_ai_provider,
            api_key=settings.resolved_ai_api_key,
            base_url=settings.resolved_ai_base_url,
            default_model=settings.resolved_ai_model,
            fallback_model=settings.resolved_ai_fallback_model,
            timeout_seconds=settings.resolved_ai_timeout_seconds,
            max_retries=settings.resolved_ai_max_retries,
        )

    def is_available(self) -> bool:
        return bool(self.api_key)

    def generate_json(self, prompt: AiPromptBundle) -> AiJsonResponse:
        if not self.is_available():
            raise ServiceUnavailableError(
                message="AI API key is not configured.",
                details={
                    "provider": self.provider_name,
                    "base_url": self.base_url,
                    "model": prompt.model,
                },
            )

        models_to_try: list[str] = []
        primary_model = prompt.model or self.default_model
        if primary_model:
            models_to_try.append(primary_model)

        fallback_model = prompt.fallback_model or self.fallback_model
        if fallback_model and fallback_model not in models_to_try:
            models_to_try.append(fallback_model)

        last_error: Exception | None = None
        for index, model_name in enumerate(models_to_try):
            try:
                self.logger.info(
                    "Calling AI json model {} via {} ({})",
                    model_name,
                    self.base_url,
                    self.provider_name,
                )
                response = self._request_completion(prompt, model_name=model_name)
                content = self._extract_message_content(response)
                payload = json.loads(self._extract_json_object(content))
                if not isinstance(payload, dict):
                    raise ValueError("AI response JSON payload must be an object.")
                resolved_model_name = getattr(response, "model", model_name)
                return AiJsonResponse(
                    payload=payload,
                    raw_content=content,
                    model_name=resolved_model_name,
                )
            except Exception as exc:
                last_error = exc
                if index == len(models_to_try) - 1:
                    raise
                self.logger.warning(
                    "Primary AI model {} failed, retrying with fallback model {}: {}",
                    model_name,
                    models_to_try[index + 1],
                    exc,
                )

        if last_error is not None:
            raise last_error
        raise RuntimeError("AI completion model selection exhausted unexpectedly.")

    def generate_summary(self, prompt: AiPromptBundle) -> AiStructuredResponse:
        response = self.generate_json(prompt)
        return AiStructuredResponse(
            payload=VideoAiSummaryDraft.model_validate(response.payload),
            raw_content=response.raw_content,
            model_name=response.model_name,
        )

    def _request_completion(self, prompt: AiPromptBundle, *, model_name: str) -> Any:
        retryer = Retrying(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type(
                (
                    APIConnectionError,
                    APIError,
                    APITimeoutError,
                    RateLimitError,
                    httpx.HTTPError,
                )
            ),
            reraise=True,
        )

        for attempt in retryer:
            with attempt:
                return self.client.chat.completions.create(
                    model=model_name,
                    temperature=prompt.temperature,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": prompt.system_prompt},
                        {"role": "user", "content": prompt.user_prompt},
                    ],
                )

        raise RuntimeError("AI completion retry loop exhausted unexpectedly.")

    @staticmethod
    def _extract_message_content(response: Any) -> str:
        choices = getattr(response, "choices", None) or []
        if not choices:
            raise ValueError("AI response did not contain any choices.")

        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None)
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            text_parts = []
            for item in content:
                text = getattr(item, "text", None)
                if text is None and isinstance(item, dict):
                    text = item.get("text")
                if text:
                    text_parts.append(str(text))
            merged = "\n".join(text_parts).strip()
            if merged:
                return merged

        raise ValueError("AI response message content was empty.")

    @staticmethod
    def _extract_json_object(content: str) -> str:
        if not content:
            raise ValueError("AI response content was empty.")

        fenced_match = JSON_BLOCK_PATTERN.search(content)
        if fenced_match:
            return fenced_match.group(1)

        stripped = content.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            json.loads(stripped)
            return stripped

        first_brace = stripped.find("{")
        last_brace = stripped.rfind("}")
        if first_brace != -1 and last_brace > first_brace:
            candidate = stripped[first_brace : last_brace + 1]
            json.loads(candidate)
            return candidate

        raise ValueError("AI response did not contain a valid JSON object.")
