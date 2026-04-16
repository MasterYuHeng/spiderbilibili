from __future__ import annotations

import json
import subprocess
import sys
from typing import TYPE_CHECKING, Any, cast

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.optional_dependencies import ensure_optional_dependency
from app.crawler.auth import build_bilibili_playwright_cookies
from app.crawler.exceptions import BilibiliParseError, BilibiliRequestError

if TYPE_CHECKING:
    from playwright.sync_api import Browser, BrowserContext, Error, Playwright
    from playwright.sync_api import sync_playwright as sync_playwright
else:
    Browser = BrowserContext = Playwright = Any
    Error = Exception
    sync_playwright = None

_sync_playwright = sync_playwright
_playwright_error_type = None


def _load_playwright_runtime() -> tuple[Any, type[Exception]]:
    global Error, _sync_playwright, _playwright_error_type, sync_playwright

    if sync_playwright is not None and _sync_playwright is not sync_playwright:
        _sync_playwright = sync_playwright

    if _sync_playwright is None:
        playwright_sync_api = ensure_optional_dependency(
            "playwright",
            "playwright.sync_api",
        )
        sync_playwright = playwright_sync_api.sync_playwright
        Error = playwright_sync_api.Error
        _sync_playwright = sync_playwright

    if _playwright_error_type is None:
        _playwright_error_type = Error

    return _sync_playwright, _playwright_error_type


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
                    }""".replace(
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
            sync_playwright, playwright_error_type = _load_playwright_runtime()
            self._playwright = sync_playwright().start()
            self._browser = self._launch_browser(playwright_error_type)

        context = self._browser.new_context(
            user_agent=self.settings.bilibili_user_agent,
            locale="zh-CN",
        )
        context.set_default_timeout(self.settings.playwright_timeout_seconds * 1000)

        if include_auth_cookies:
            context_cookies = build_bilibili_playwright_cookies(self.settings)
            if context_cookies:
                context.add_cookies(cast(Any, context_cookies))
            self._auth_context = context
        else:
            self._anonymous_context = context

        return context

    def _launch_browser(self, playwright_error_type: type[Exception]) -> Browser:
        if self._playwright is None:
            raise RuntimeError("Playwright runtime has not been initialized.")

        launch_kwargs = self._build_launch_kwargs()
        try:
            return self._playwright.chromium.launch(**launch_kwargs)
        except playwright_error_type as exc:
            if not self._is_missing_chromium_runtime_error(exc):
                raise

            self._install_chromium_runtime()
            return self._playwright.chromium.launch(**launch_kwargs)

    def _install_chromium_runtime(self) -> None:
        logger = get_logger(__name__)
        logger.info("Playwright Chromium runtime is missing, installing it on demand.")
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
        )

    @staticmethod
    def _is_missing_chromium_runtime_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return (
            "executable doesn't exist" in message
            or "please run the following command" in message
        )

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
