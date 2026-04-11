from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class VideoAiSummaryDraft(BaseModel):
    summary: str
    topics: list[str] = Field(default_factory=list)
    primary_topic: str | None = None
    tone: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("summary cannot be empty")
        return normalized

    @field_validator("topics")
    @classmethod
    def validate_topics(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()

        for value in values:
            topic = " ".join(value.split()).strip()
            if not topic:
                continue
            topic_key = topic.casefold()
            if topic_key in seen:
                continue
            normalized.append(topic)
            seen.add(topic_key)

        return normalized

    @field_validator("primary_topic", "tone")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split()).strip()
        return normalized or None
