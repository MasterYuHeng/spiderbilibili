from __future__ import annotations

from pathlib import Path
from typing import Any

import orjson

from app.core.config import Settings, get_settings
from app.crawler.utils import ensure_directory, sanitize_filename


class RawArchiveStore:
    def __init__(
        self,
        task_id: str,
        *,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.enabled = self.settings.crawler_save_raw_payloads
        self.root_dir = (
            ensure_directory(
                Path(self.settings.crawler_raw_data_dir) / sanitize_filename(task_id)
            )
            if self.enabled
            else None
        )

    def save_json(self, category: str, name: str, payload: Any) -> Path | None:
        if not self.enabled:
            return None
        target = self._build_path(category, name, ".json")
        target.write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2))
        return target

    def save_text(self, category: str, name: str, payload: str) -> Path | None:
        if not self.enabled:
            return None
        target = self._build_path(category, name, ".txt")
        target.write_text(payload, encoding="utf-8")
        return target

    def _build_path(self, category: str, name: str, suffix: str) -> Path:
        if self.root_dir is None:
            raise RuntimeError("Raw archive storage is disabled.")
        category_dir = ensure_directory(self.root_dir / sanitize_filename(category))
        filename = f"{sanitize_filename(name)}{suffix}"
        return category_dir / filename
