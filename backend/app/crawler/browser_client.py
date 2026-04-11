from __future__ import annotations

import json
from typing import Any

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Error,
    Playwright,
    sync_playwright,
)

from app.core.config import Settings, get_settings
from app.crawler.auth import build_bilibili_playwright_cookies
from app.crawler.exceptions import BilibiliParseError, BilibiliRequestError


class BilibiliBrowserClient:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        use_proxy: bool | None = None,
        proxy_url: str | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._auth_context: BrowserContext | None = None
        self._anonymous_context: BrowserContext | None = None
        self.proxy_url = self._resolve_proxy_url(
            use_proxy=use_proxy,
            explicit_proxy_url=proxy_url,
        )

    def close(self) -> None:
        if self._auth_context is not None:
            self._auth_context.close()
            self._auth_context = None
        if self._anonymous_context is not None:
            self._anonymous_context.close()
            self._anonymous_context = None
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    def __enter__(self) -> "BilibiliBrowserClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def fetch_api_json(
        self,
        url: str,
        *,
        referer: str = "https://www.bilibili.com/",
        include_auth_cookies: bool = True,
        include_credentials: bool = True,
    ) -> dict[str, Any]:
        page = self._get_context(include_auth_cookies=include_auth_cookies).new_page()
        try:
            try:
                page.goto(referer, wait_until="domcontentloaded")
                payload = page.evaluate(
                    """async (requestUrl) => {
                        const response = await fetch(requestUrl, {
                            credentials: __CREDENTIALS_MODE__,
                            headers: {
                                "Accept": "application/json, text/plain, */*"
                            }
                        });
                        return {
                            status: response.status,
                            text: await response.text()
                        };
                    }"""
                    .replace(
                        "__CREDENTIALS_MODE__",
                        '"include"' if include_credentials else '"omit"',
                    ),
                    url,
                )
            except Error as exc:
                raise BilibiliRequestError(
                    f"Browser fallback request failed for {url}"
                ) from exc
        finally:
            page.close()

        if payload["status"] >= 400:
            raise BilibiliRequestError(
                f"Browser fallback request failed with {payload['status']} for {url}"
            )
        try:
            return json.loads(payload["text"])
        except json.JSONDecodeError as exc:
            raise BilibiliParseError(
                f"Browser fallback returned non-JSON content for {url}"
            ) from exc

    def _get_context(self, *, include_auth_cookies: bool = True) -> BrowserContext:
        if include_auth_cookies and self._auth_context is not None:
            return self._auth_context
        if (not include_auth_cookies) and self._anonymous_context is not None:
            return self._anonymous_context

        if self._browser is None:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                **self._build_launch_kwargs()
            )

        context = self._browser.new_context(
            user_agent=self.settings.bilibili_user_agent,
            locale="zh-CN",
        )
        context.set_default_timeout(self.settings.playwright_timeout_seconds * 1000)

        if include_auth_cookies:
            context_cookies = build_bilibili_playwright_cookies(self.settings)
            if context_cookies:
                context.add_cookies(context_cookies)
            self._auth_context = context
        else:
            self._anonymous_context = context

        return context

    def _build_launch_kwargs(self) -> dict[str, Any]:
        launch_kwargs: dict[str, Any] = {
            "headless": self.settings.playwright_headless,
        }
        if self.proxy_url:
            launch_kwargs["proxy"] = {"server": self.proxy_url}
        return launch_kwargs

    def _resolve_proxy_url(
        self,
        *,
        use_proxy: bool | None,
        explicit_proxy_url: str | None,
    ) -> str | None:
        if use_proxy is False:
            return None
        if explicit_proxy_url:
            return explicit_proxy_url
        if use_proxy is True or use_proxy is None:
            return self.settings.https_proxy or self.settings.http_proxy or None
        return None
