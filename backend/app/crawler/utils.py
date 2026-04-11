from __future__ import annotations

import hashlib
import html
import math
import re
from datetime import datetime, timezone
from pathlib import Path

HTML_TAG_PATTERN = re.compile(r"<[^>]+>")


def strip_html_tags(value: str | None) -> str:
    if not value:
        return ""
    return HTML_TAG_PATTERN.sub("", html.unescape(value)).strip()


def ensure_https_url(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith("//"):
        return f"https:{value}"
    return value


def parse_duration_text(value: str | int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value

    parts = [segment for segment in str(value).split(":") if segment]
    if not parts:
        return None

    try:
        numbers = [int(part) for part in parts]
    except ValueError:
        return None

    seconds = 0
    for number in numbers:
        seconds = (seconds * 60) + number
    return seconds


def parse_count_text(value: int | float | str | None) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            return 0
        return int(value)

    normalized = str(value).strip().replace(",", "")
    if not normalized:
        return 0

    multiplier = 1
    if normalized.endswith("\u4e07"):
        multiplier = 10_000
        normalized = normalized[:-1]
    elif normalized.endswith("\u4ebf"):
        multiplier = 100_000_000
        normalized = normalized[:-1]

    try:
        return int(float(normalized) * multiplier)
    except ValueError:
        digits = re.sub(r"[^\d]", "", normalized)
        return int(digits or 0)


def datetime_from_timestamp(value: int | float | str | None) -> datetime | None:
    if value in (None, ""):
        return None
    if not isinstance(value, (int, float, str)):
        return None
    try:
        timestamp = int(float(value))
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def stable_text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sanitize_filename(value: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9._-]+", "_", value)
    return sanitized.strip("._") or "payload"


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
