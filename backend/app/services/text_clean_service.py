from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from app.crawler.models import SubtitleData
from app.crawler.utils import stable_text_hash

WHITESPACE_PATTERN = re.compile(r"[^\S\r\n]+")
BLANK_LINE_PATTERN = re.compile(r"\n{3,}")


@dataclass(slots=True)
class CleanedSubtitleSegment:
    segment_index: int
    start_seconds: Decimal | None
    end_seconds: Decimal | None
    content: str


@dataclass(slots=True)
class CleanedVideoText:
    has_description: bool
    has_subtitle: bool
    description_text: str | None
    subtitle_text: str | None
    combined_text: str
    combined_text_hash: str | None
    language_code: str
    subtitle_segments: list[CleanedSubtitleSegment]


class TextCleanService:
    def __init__(self, *, max_combined_length: int = 20_000) -> None:
        self.max_combined_length = max_combined_length

    def build_cleaned_text(
        self,
        *,
        title: str,
        description: str | None,
        search_summary: str | None = None,
        subtitle: SubtitleData | None,
    ) -> CleanedVideoText:
        cleaned_description = self._normalize_text(description)
        cleaned_search_summary = self._normalize_text(search_summary)
        cleaned_segments = self._clean_subtitle_segments(subtitle)
        subtitle_text = "\n".join(segment.content for segment in cleaned_segments)
        subtitle_text = self._normalize_text(subtitle_text)
        description_parts = self._merge_unique_texts(
            cleaned_description,
            cleaned_search_summary,
        )
        description_text = "\n\n".join(description_parts)
        has_description = bool(description_text)
        has_subtitle = bool(subtitle_text)
        language_code = (
            subtitle.language_code
            if subtitle and subtitle.language_code
            else "zh-CN"
        )

        combined_sections = []
        if cleaned_description:
            combined_sections.append(f"Video Description:\n{cleaned_description}")
        if (
            cleaned_search_summary
            and cleaned_search_summary.casefold() != cleaned_description.casefold()
        ):
            combined_sections.append(
                f"Video Search Summary:\n{cleaned_search_summary}"
            )
        if subtitle_text:
            combined_sections.append(f"Video Subtitle:\n{subtitle_text}")
        if not combined_sections:
            fallback_title = self._normalize_text(title)
            fallback_value = fallback_title or "Untitled Video"
            combined_sections.append(f"Video Title:\n{fallback_value}")

        combined_text = "\n\n".join(combined_sections)
        combined_text = self._truncate_text(combined_text)
        combined_text_hash = stable_text_hash(combined_text) if combined_text else None

        return CleanedVideoText(
            has_description=has_description,
            has_subtitle=has_subtitle,
            description_text=description_text or None,
            subtitle_text=subtitle_text or None,
            combined_text=combined_text,
            combined_text_hash=combined_text_hash,
            language_code=language_code,
            subtitle_segments=cleaned_segments,
        )

    def _clean_subtitle_segments(
        self,
        subtitle: SubtitleData | None,
    ) -> list[CleanedSubtitleSegment]:
        if subtitle is None:
            return []

        cleaned_segments: list[CleanedSubtitleSegment] = []
        for segment in subtitle.segments:
            content = self._normalize_text(segment.content)
            if not content:
                continue
            cleaned_segments.append(
                CleanedSubtitleSegment(
                    segment_index=segment.segment_index,
                    start_seconds=self._to_decimal(segment.start_seconds),
                    end_seconds=self._to_decimal(segment.end_seconds),
                    content=content,
                )
            )
        return cleaned_segments

    @staticmethod
    def _normalize_text(value: str | None) -> str:
        if not value:
            return ""

        normalized = value.replace("\r\n", "\n").replace("\r", "\n")
        normalized_lines = []
        for line in normalized.split("\n"):
            compact_line = WHITESPACE_PATTERN.sub(" ", line).strip()
            normalized_lines.append(compact_line)
        normalized = "\n".join(normalized_lines).strip()
        normalized = BLANK_LINE_PATTERN.sub("\n\n", normalized)
        return normalized

    def _truncate_text(self, value: str) -> str:
        if self.max_combined_length <= 0 or len(value) <= self.max_combined_length:
            return value
        truncated = value[: self.max_combined_length].rstrip()
        return f"{truncated}\n\n[TRUNCATED]"

    @staticmethod
    def _merge_unique_texts(*values: str) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for value in values:
            if not value:
                continue
            normalized_key = value.casefold()
            if normalized_key in seen:
                continue
            merged.append(value)
            seen.add(normalized_key)
        return merged

    @staticmethod
    def _to_decimal(value: float | None) -> Decimal | None:
        if value is None:
            return None
        return Decimal(str(value))
