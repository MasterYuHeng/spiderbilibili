from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.base import utc_now
from app.schemas.task import ALLOWED_KEYWORD_SYNONYM_COUNTS
from app.services.ai_client import AiPromptBundle, AiJsonResponse, OpenAICompatibleAiClient

KEYWORD_EXPANSION_SUCCESS = "success"
KEYWORD_EXPANSION_FALLBACK = "fallback"
KEYWORD_EXPANSION_FAILED = "failed"
KEYWORD_EXPANSION_SKIPPED = "skipped"
KEYWORD_EXPANSION_PENDING = "pending"
KEYWORD_EXPANSION_ALLOWED_STATUSES = {
    KEYWORD_EXPANSION_SKIPPED,
    KEYWORD_EXPANSION_PENDING,
    KEYWORD_EXPANSION_SUCCESS,
    KEYWORD_EXPANSION_FALLBACK,
    KEYWORD_EXPANSION_FAILED,
}
WHITESPACE_PATTERN = re.compile(r"\s+")
TRIMMABLE_QUOTES = " \t\r\n\"'"


class KeywordExpansionService:
    def __init__(
        self,
        session: Session | None = None,
        *,
        ai_client: OpenAICompatibleAiClient | Any | None = None,
        settings: Any | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.ai_client = ai_client or OpenAICompatibleAiClient.from_runtime(
            session=self.session,
            settings=self.settings,
        )
        self.logger = get_logger(__name__)

    def expand_keyword(
        self,
        *,
        source_keyword: str,
        requested_synonym_count: int | None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        normalized_source_keyword = self._normalize_keyword(source_keyword)
        normalized_requested_count = self._normalize_requested_synonym_count(
            requested_synonym_count
        )

        if not enabled:
            return self._build_payload(
                source_keyword=normalized_source_keyword,
                enabled=False,
                requested_synonym_count=None,
                status=KEYWORD_EXPANSION_SKIPPED,
            )

        if not normalized_source_keyword:
            return self._build_payload(
                source_keyword=normalized_source_keyword,
                enabled=True,
                requested_synonym_count=normalized_requested_count,
                status=KEYWORD_EXPANSION_FAILED,
                error_message="Source keyword was empty.",
                generated_at=self._build_timestamp(),
            )

        if normalized_requested_count is None:
            return self._build_payload(
                source_keyword=normalized_source_keyword,
                enabled=True,
                requested_synonym_count=None,
                status=KEYWORD_EXPANSION_FAILED,
                error_message="Requested synonym count was invalid.",
                generated_at=self._build_timestamp(),
            )

        try:
            return self._expand_with_ai(
                source_keyword=normalized_source_keyword,
                requested_synonym_count=normalized_requested_count,
            )
        except Exception as exc:
            self.logger.exception(
                "Keyword expansion failed unexpectedly for keyword {}: {}",
                normalized_source_keyword,
                exc,
            )
            return self._build_payload(
                source_keyword=normalized_source_keyword,
                enabled=True,
                requested_synonym_count=normalized_requested_count,
                status=KEYWORD_EXPANSION_FAILED,
                error_message=f"Keyword expansion failed unexpectedly: {exc}",
                generated_at=self._build_timestamp(),
            )

    def _expand_with_ai(
        self,
        *,
        source_keyword: str,
        requested_synonym_count: int,
    ) -> dict[str, Any]:
        generated_at = self._build_timestamp()

        if not hasattr(self.ai_client, "is_available") or not self.ai_client.is_available():
            return self._build_payload(
                source_keyword=source_keyword,
                enabled=True,
                requested_synonym_count=requested_synonym_count,
                status=KEYWORD_EXPANSION_FALLBACK,
                error_message="AI keyword expansion is unavailable.",
                generated_at=generated_at,
            )

        prompt = self._build_prompt(
            source_keyword=source_keyword,
            requested_synonym_count=requested_synonym_count,
        )

        try:
            response = self.ai_client.generate_json(prompt)
        except Exception as exc:
            return self._build_payload(
                source_keyword=source_keyword,
                enabled=True,
                requested_synonym_count=requested_synonym_count,
                status=KEYWORD_EXPANSION_FALLBACK,
                error_message=f"AI keyword expansion request failed: {exc}",
                generated_at=generated_at,
            )

        synonyms_or_error = self._extract_synonyms(response)
        if isinstance(synonyms_or_error, str):
            return self._build_payload(
                source_keyword=source_keyword,
                enabled=True,
                requested_synonym_count=requested_synonym_count,
                status=KEYWORD_EXPANSION_FALLBACK,
                model_name=response.model_name,
                error_message=synonyms_or_error,
                generated_at=generated_at,
            )

        cleaned_synonyms = self._clean_synonyms(
            synonyms_or_error,
            source_keyword=source_keyword,
            requested_synonym_count=requested_synonym_count,
        )
        if not cleaned_synonyms:
            return self._build_payload(
                source_keyword=source_keyword,
                enabled=True,
                requested_synonym_count=requested_synonym_count,
                status=KEYWORD_EXPANSION_FALLBACK,
                model_name=response.model_name,
                error_message="AI keyword expansion returned no valid synonyms.",
                generated_at=generated_at,
            )

        return self._build_payload(
            source_keyword=source_keyword,
            enabled=True,
            requested_synonym_count=requested_synonym_count,
            status=KEYWORD_EXPANSION_SUCCESS,
            generated_synonyms=cleaned_synonyms,
            model_name=response.model_name,
            generated_at=generated_at,
        )

    def _build_prompt(
        self,
        *,
        source_keyword: str,
        requested_synonym_count: int,
    ) -> AiPromptBundle:
        return AiPromptBundle(
            system_prompt=(
                "你是一个负责 B 站搜索召回增强的中文关键词扩展助手。"
                "请只输出 JSON 对象，不要输出额外解释。"
                'JSON 结构必须为 {"synonyms":["词1","词2"]}。'
                "synonyms 只返回与原关键词在 B 站语境下常见的同义词、简称、代称或流行说法。"
                "不要返回原关键词本身，不要返回解释句，不要返回无关长句。"
                "优先保留真正能提升视频搜索召回的表达。"
            ),
            user_prompt=(
                f"原关键词：{source_keyword}\n"
                f"需要补充数量：{requested_synonym_count}\n"
                "请返回不超过指定数量的候选同义词，结果按相关性从高到低排序。"
            ),
            model=self._resolve_prompt_model_name(),
            fallback_model=self._resolve_prompt_fallback_model_name(),
            temperature=0.2,
        )

    @staticmethod
    def _extract_synonyms(response: AiJsonResponse) -> list[Any] | str:
        payload = response.payload
        if not isinstance(payload, dict):
            return "AI keyword expansion payload must be a JSON object."
        if "synonyms" not in payload:
            return "AI keyword expansion payload did not contain a synonyms field."
        synonyms = payload.get("synonyms")
        if not isinstance(synonyms, list):
            return "AI keyword expansion payload field 'synonyms' must be an array."
        return synonyms

    def _clean_synonyms(
        self,
        values: list[Any],
        *,
        source_keyword: str,
        requested_synonym_count: int,
    ) -> list[str]:
        normalized_source_keyword = self._normalize_keyword(source_keyword)
        normalized_source_casefold = normalized_source_keyword.casefold()
        cleaned_values: list[str] = []
        seen: set[str] = set()

        for item in values:
            if not isinstance(item, str):
                continue
            normalized_item = self._normalize_keyword(item)
            if not normalized_item:
                continue
            normalized_item_casefold = normalized_item.casefold()
            if normalized_item_casefold == normalized_source_casefold:
                continue
            if normalized_item_casefold in seen:
                continue
            cleaned_values.append(normalized_item)
            seen.add(normalized_item_casefold)
            if len(cleaned_values) >= requested_synonym_count:
                break

        return cleaned_values

    @staticmethod
    def _normalize_requested_synonym_count(value: Any) -> int | None:
        try:
            normalized_value = int(value)
        except (TypeError, ValueError):
            return None
        if normalized_value not in ALLOWED_KEYWORD_SYNONYM_COUNTS:
            return None
        return normalized_value

    @staticmethod
    def _normalize_keyword(value: Any) -> str:
        if value is None:
            return ""
        normalized = WHITESPACE_PATTERN.sub(" ", str(value)).strip(TRIMMABLE_QUOTES)
        return normalized.strip()

    @staticmethod
    def _build_timestamp() -> str:
        return utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _resolve_prompt_model_name(self) -> str:
        model_name = getattr(self.ai_client, "default_model", None) or getattr(
            self.settings,
            "resolved_ai_model",
            "",
        )
        return str(model_name or "")

    def _resolve_prompt_fallback_model_name(self) -> str | None:
        fallback_model = getattr(self.ai_client, "fallback_model", None)
        if fallback_model:
            return str(fallback_model)
        settings_fallback_model = getattr(
            self.settings,
            "resolved_ai_fallback_model",
            None,
        )
        return str(settings_fallback_model) if settings_fallback_model else None

    @staticmethod
    def _build_payload(
        *,
        source_keyword: str,
        enabled: bool,
        requested_synonym_count: int | None,
        status: str,
        generated_synonyms: list[str] | None = None,
        model_name: str | None = None,
        error_message: str | None = None,
        generated_at: str | None = None,
    ) -> dict[str, Any]:
        normalized_source_keyword = KeywordExpansionService._normalize_keyword(
            source_keyword
        )
        normalized_status = str(status).strip().lower()
        if normalized_status not in KEYWORD_EXPANSION_ALLOWED_STATUSES:
            normalized_status = (
                KEYWORD_EXPANSION_PENDING if enabled else KEYWORD_EXPANSION_SKIPPED
            )

        normalized_generated_synonyms = (
            generated_synonyms if normalized_status == KEYWORD_EXPANSION_SUCCESS else []
        )
        expanded_keywords = [normalized_source_keyword]
        expanded_keywords.extend(
            item
            for item in normalized_generated_synonyms
            if item != normalized_source_keyword
        )

        return {
            "source_keyword": normalized_source_keyword,
            "enabled": bool(enabled),
            "requested_synonym_count": requested_synonym_count if enabled else None,
            "generated_synonyms": normalized_generated_synonyms,
            "expanded_keywords": expanded_keywords,
            "status": normalized_status,
            "model_name": (
                model_name
                if normalized_status
                in {
                    KEYWORD_EXPANSION_SUCCESS,
                    KEYWORD_EXPANSION_FALLBACK,
                    KEYWORD_EXPANSION_FAILED,
                }
                else None
            ),
            "error_message": (
                error_message
                if normalized_status
                in {
                    KEYWORD_EXPANSION_SUCCESS,
                    KEYWORD_EXPANSION_FALLBACK,
                    KEYWORD_EXPANSION_FAILED,
                }
                else None
            ),
            "generated_at": (
                generated_at
                if normalized_status
                in {
                    KEYWORD_EXPANSION_SUCCESS,
                    KEYWORD_EXPANSION_FALLBACK,
                    KEYWORD_EXPANSION_FAILED,
                }
                else None
            ),
        }
