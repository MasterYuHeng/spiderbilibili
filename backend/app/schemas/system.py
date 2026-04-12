from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DeepSeekConfigRead(BaseModel):
    provider: Literal["deepseek"] = "deepseek"
    effective_provider: str
    api_key: str = ""
    api_key_configured: bool
    key_source: Literal["runtime", "environment", "unset"]
    base_url: str
    model: str
    fallback_model: str | None = None
    timeout_seconds: float
    max_retries: int
    updated_at: datetime | None = None


class BilibiliAccountProfileRead(BaseModel):
    is_login: bool = False
    mid: str | None = None
    username: str | None = None
    level: int | None = None
    avatar_url: str | None = None


class BrowserProfileRead(BaseModel):
    id: str
    label: str
    directory_name: str
    cookie_db_exists: bool


class BrowserSourceRead(BaseModel):
    browser: str
    label: str
    user_data_dir: str
    default_profile_id: str | None = None
    profiles: list[BrowserProfileRead] = Field(default_factory=list)


class BilibiliConfigRead(BaseModel):
    provider: Literal["bilibili"] = "bilibili"
    cookie: str = ""
    cookie_configured: bool
    key_source: Literal["runtime", "environment", "unset"]
    sessdata: str = ""
    bili_jct: str = ""
    dede_user_id: str = ""
    buvid3: str = ""
    buvid4: str = ""
    account_profile: BilibiliAccountProfileRead | None = None
    import_summary: str | None = None
    validation_message: str | None = None
    browser_sources: list[BrowserSourceRead] = Field(default_factory=list)
    updated_at: datetime | None = None


class AiSettingsPayload(BaseModel):
    deepseek: DeepSeekConfigRead
    bilibili: BilibiliConfigRead


class DeepSeekConfigUpdateRequest(BaseModel):
    api_key: str = Field(default="", max_length=512)


class BilibiliConfigUpdateRequest(BaseModel):
    cookie: str = Field(default="", max_length=16384)


class BilibiliBrowserImportRequest(BaseModel):
    browser: str | None = Field(default=None, max_length=64)
    profile_directory: str | None = Field(default=None, max_length=255)
    user_data_dir: str | None = Field(default=None, max_length=1024)
