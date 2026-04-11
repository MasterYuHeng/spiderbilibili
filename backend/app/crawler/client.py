from __future__ import annotations

import json
import random
import time
from collections import deque
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import Settings, get_settings
from app.crawler.auth import build_bilibili_cookie_header
from app.crawler.exceptions import (
    BilibiliAntiCrawlerError,
    BilibiliApiError,
    BilibiliParseError,
    BilibiliRequestError,
)
from app.crawler.wbi import sign_wbi_params


class BilibiliHttpClient:
    api_origin = "https://api.bilibili.com"
    site_origin = "https://www.bilibili.com"
    search_origin = "https://search.bilibili.com"

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        min_sleep_seconds: float | None = None,
        max_sleep_seconds: float | None = None,
        use_proxy: bool | None = None,
        proxy_url: str | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep_func=time.sleep,
        random_func=random.uniform,
    ) -> None:
        self.settings = settings or get_settings()
        self.min_sleep_seconds = (
            float(min_sleep_seconds)
            if min_sleep_seconds is not None
            else self.settings.crawler_min_sleep
        )
        self.max_sleep_seconds = (
            float(max_sleep_seconds)
            if max_sleep_seconds is not None
            else self.settings.crawler_max_sleep
        )
        self.sleep_func = sleep_func
        self.random_func = random_func
        self._last_request_at: float | None = None
        self._request_timestamps: deque[float] = deque()
        self._state_lock = Lock()
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0
        self._wbi_keys: tuple[str, str] | None = None

        base_headers = {
            "User-Agent": self.settings.bilibili_user_agent,
            "Accept": "application/json, text/plain, */*",
        }
        auth_headers = dict(base_headers)
        cookie_header = build_bilibili_cookie_header(self.settings)
        if cookie_header:
            auth_headers["Cookie"] = cookie_header
        self.proxy_url = self._resolve_proxy_url(
            use_proxy=use_proxy,
            explicit_proxy_url=proxy_url,
        )
        client_kwargs = dict(
            timeout=self.settings.http_timeout_seconds,
            transport=transport,
            follow_redirects=True,
            proxy=self.proxy_url,
        )
        self.client = httpx.Client(
            headers=auth_headers,
            **client_kwargs,
        )
        self.public_client = httpx.Client(
            headers=base_headers,
            **client_kwargs,
        )

    def close(self) -> None:
        self.client.close()
        self.public_client.close()

    def __enter__(self) -> "BilibiliHttpClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def get_api_json(
        self,
        path_or_url: str,
        *,
        params: dict[str, Any] | None = None,
        referer: str | None = None,
        use_wbi: bool = False,
        skip_throttle: bool = False,
        include_auth: bool = True,
    ) -> dict[str, Any]:
        url, query_params = self._build_request(
            path_or_url,
            params or {},
            use_wbi=use_wbi,
        )
        response = self._send_request(
            url,
            query_params,
            referer=referer,
            skip_throttle=skip_throttle,
            include_auth=include_auth,
        )
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise BilibiliParseError("Expected a JSON response from Bilibili.") from exc

        code = payload.get("code")
        if code in {-412, 412}:
            raise BilibiliAntiCrawlerError(
                f"Bilibili anti-crawler blocked the request: {url}"
            )
        if code not in (0, None, -101):
            raise BilibiliApiError(
                f"Bilibili API returned code {code}: {payload.get('message')}"
            )
        return payload

    def get_text(
        self,
        path_or_url: str,
        *,
        params: dict[str, Any] | None = None,
        referer: str | None = None,
        skip_throttle: bool = False,
        include_auth: bool = True,
    ) -> str:
        url, query_params = self._build_request(
            path_or_url,
            params or {},
            use_wbi=False,
        )
        response = self._send_request(
            url,
            query_params,
            referer=referer,
            skip_throttle=skip_throttle,
            include_auth=include_auth,
        )
        return response.text

    def build_url(
        self,
        path_or_url: str,
        *,
        params: dict[str, Any] | None = None,
        use_wbi: bool = False,
    ) -> str:
        url, query_params = self._build_request(
            path_or_url,
            params or {},
            use_wbi=use_wbi,
        )
        if not query_params:
            return url
        return f"{url}?{urlencode(query_params)}"

    def _build_request(
        self,
        path_or_url: str,
        params: dict[str, Any],
        *,
        use_wbi: bool,
    ) -> tuple[str, dict[str, Any]]:
        url = (
            path_or_url
            if path_or_url.startswith("http://") or path_or_url.startswith("https://")
            else f"{self.api_origin}{path_or_url}"
        )
        query_params = dict(params)
        if use_wbi:
            img_key, sub_key = self._get_wbi_keys()
            query_params = sign_wbi_params(
                query_params,
                img_key=img_key,
                sub_key=sub_key,
            )
        return url, query_params

    def _send_request(
        self,
        url: str,
        query_params: dict[str, Any] | None,
        *,
        referer: str | None = None,
        skip_throttle: bool = False,
        include_auth: bool = True,
    ) -> httpx.Response:
        last_error: Exception | None = None
        selected_client = self.client if include_auth else self.public_client
        for attempt in range(self.settings.http_max_retries + 1):
            self._ensure_circuit_closed(url)
            if not skip_throttle:
                self._wait_before_request()
            try:
                response = selected_client.get(
                    url,
                    params=query_params or None,
                    headers={"Referer": referer or self.site_origin},
                )
            except httpx.RequestError as exc:
                last_error = exc
                self._record_failure()
                if attempt >= self.settings.http_max_retries:
                    raise BilibiliRequestError(f"Failed to request {url}") from exc
                self._sleep_backoff(attempt)
                continue

            if response.status_code in {412, 429}:
                last_error = BilibiliAntiCrawlerError(
                    f"Bilibili anti-crawler responded with {response.status_code}."
                )
                self._record_failure(anti_crawler=True)
                if attempt >= self.settings.http_max_retries:
                    raise last_error
                self._sleep_backoff(attempt, anti_crawler=True)
                continue

            if response.status_code >= 500:
                last_error = BilibiliRequestError(
                    f"Upstream server error {response.status_code} for {url}"
                )
                self._record_failure()
                if attempt >= self.settings.http_max_retries:
                    raise last_error
                self._sleep_backoff(attempt)
                continue

            if response.status_code >= 400:
                self._record_failure()
                raise BilibiliRequestError(
                    f"Unexpected status {response.status_code} for {url}"
                )

            self._record_success()
            return response

        if last_error is None:
            raise BilibiliRequestError(f"Failed to request {url}")
        raise last_error

    def _wait_before_request(self) -> None:
        while True:
            sleep_seconds = 0.0
            with self._state_lock:
                now = time.monotonic()
                rate_limit = max(0, int(self.settings.crawler_rate_limit_per_minute))
                while (
                    self._request_timestamps and now - self._request_timestamps[0] >= 60
                ):
                    self._request_timestamps.popleft()

                if rate_limit > 0 and len(self._request_timestamps) >= rate_limit:
                    sleep_seconds = max(
                        sleep_seconds,
                        60 - (now - self._request_timestamps[0]),
                    )

                min_interval = 0.0
                if rate_limit > 0:
                    min_interval = 60 / rate_limit

                random_sleep = 0.0
                if self.max_sleep_seconds > 0:
                    low = max(self.min_sleep_seconds, 0.0)
                    high = max(self.max_sleep_seconds, low)
                    random_sleep = self.random_func(low, high)

                elapsed = (
                    now - self._last_request_at
                    if self._last_request_at is not None
                    else None
                )
                target_sleep = max(min_interval, random_sleep)
                if elapsed is not None and elapsed < target_sleep:
                    sleep_seconds = max(sleep_seconds, target_sleep - elapsed)

                if sleep_seconds <= 0:
                    reserved_at = time.monotonic()
                    self._last_request_at = reserved_at
                    self._request_timestamps.append(reserved_at)
                    return

            self.sleep_func(sleep_seconds)

    def _sleep_backoff(self, attempt: int, *, anti_crawler: bool = False) -> None:
        base = float(getattr(self.settings, "crawler_backoff_base_seconds", 1.0))
        maximum = float(getattr(self.settings, "crawler_backoff_max_seconds", 20.0))
        jitter = max(
            0.0,
            float(getattr(self.settings, "crawler_backoff_jitter_seconds", 0.5)),
        )
        multiplier = 2.0 if anti_crawler else 1.0
        backoff = min(maximum, base * multiplier * (2**attempt))
        if jitter > 0:
            backoff += self.random_func(0.0, jitter)
        self.sleep_func(backoff)

    def _ensure_circuit_closed(self, url: str) -> None:
        with self._state_lock:
            if self._circuit_open_until <= 0:
                return
            remaining = self._circuit_open_until - time.monotonic()
            if remaining <= 0:
                self._circuit_open_until = 0.0
                self._consecutive_failures = 0
                return
        raise BilibiliAntiCrawlerError(
            "Bilibili request circuit breaker is open for "
            f"{url}. Retry after {remaining:.1f}s."
        )

    def _record_success(self) -> None:
        with self._state_lock:
            self._consecutive_failures = 0
            self._circuit_open_until = 0.0

    def _record_failure(self, *, anti_crawler: bool = False) -> None:
        threshold = max(
            1,
            int(
                getattr(
                    self.settings,
                    "crawler_circuit_breaker_failure_threshold",
                    4,
                )
            ),
        )
        recovery_seconds = max(
            1.0,
            float(
                getattr(
                    self.settings,
                    "crawler_circuit_breaker_recovery_seconds",
                    60.0,
                )
            ),
        )
        with self._state_lock:
            self._consecutive_failures += 2 if anti_crawler else 1
            if self._consecutive_failures >= threshold:
                self._circuit_open_until = max(
                    self._circuit_open_until,
                    time.monotonic() + recovery_seconds,
                )

    def _get_wbi_keys(self) -> tuple[str, str]:
        if self._wbi_keys is not None:
            return self._wbi_keys

        payload = self.get_api_json("/x/web-interface/nav", referer=self.site_origin)
        data = payload.get("data") or {}
        wbi_img = data.get("wbi_img") or {}
        img_url = wbi_img.get("img_url")
        sub_url = wbi_img.get("sub_url")
        if not img_url or not sub_url:
            raise BilibiliParseError("Failed to retrieve WBI keys from nav response.")

        img_key = Path(img_url).stem
        sub_key = Path(sub_url).stem
        self._wbi_keys = (img_key, sub_key)
        return self._wbi_keys

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
