from __future__ import annotations

from collections import OrderedDict
from typing import Any

BILIBILI_COOKIE_FIELD_MAP = (
    ("SESSDATA", "bilibili_sessdata"),
    ("bili_jct", "bilibili_bili_jct"),
    ("DedeUserID", "bilibili_dedeuserid"),
    ("buvid3", "bilibili_buvid3"),
    ("buvid4", "bilibili_buvid4"),
)


def build_bilibili_cookie_pairs(settings: Any) -> list[tuple[str, str]]:
    cookies: OrderedDict[str, str] = OrderedDict()

    raw_cookie = str(getattr(settings, "bilibili_cookie", "") or "").strip()
    if raw_cookie:
        for chunk in raw_cookie.split(";"):
            item = chunk.strip()
            if not item or "=" not in item:
                continue
            name, value = item.split("=", 1)
            normalized_name = name.strip()
            normalized_value = value.strip()
            if not normalized_name or not normalized_value:
                continue
            cookies[normalized_name] = normalized_value

    for cookie_name, attr_name in BILIBILI_COOKIE_FIELD_MAP:
        value = str(getattr(settings, attr_name, "") or "").strip()
        if value:
            cookies[cookie_name] = value

    return list(cookies.items())


def build_bilibili_cookie_header(settings: Any) -> str:
    return "; ".join(
        f"{name}={value}" for name, value in build_bilibili_cookie_pairs(settings)
    )


def build_bilibili_playwright_cookies(settings: Any) -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "value": value,
            "domain": ".bilibili.com",
            "path": "/",
            "secure": True,
        }
        for name, value in build_bilibili_cookie_pairs(settings)
    ]
