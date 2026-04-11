from __future__ import annotations

import json
from typing import Any

from app.crawler.browser_client import BilibiliBrowserClient
from app.crawler.client import BilibiliHttpClient
from app.crawler.exceptions import BilibiliCrawlerError, BilibiliParseError
from app.crawler.models import SubtitleData, SubtitleSegmentData
from app.crawler.raw_archive import RawArchiveStore
from app.crawler.utils import ensure_https_url, strip_html_tags


class BilibiliSubtitleSpider:
    endpoint = "/x/player/wbi/v2"
    preferred_languages = ("zh-CN", "zh-Hans", "ai-zh", "en-US", "en")

    def __init__(
        self,
        http_client: BilibiliHttpClient,
        *,
        browser_client: BilibiliBrowserClient | None = None,
        raw_archive: RawArchiveStore | None = None,
    ) -> None:
        self.http_client = http_client
        self.browser_client = browser_client
        self.raw_archive = raw_archive

    def fetch_best_subtitle(self, bvid: str, cid: int | None) -> SubtitleData | None:
        if cid is None:
            return None

        params = {"bvid": bvid, "cid": cid}
        try:
            payload = self.http_client.get_api_json(
                self.endpoint,
                params=params,
                referer=f"{self.http_client.site_origin}/video/{bvid}",
            )
        except BilibiliCrawlerError:
            if self.browser_client is None:
                raise
            url = self.http_client.build_url(self.endpoint, params=params)
            payload = self.browser_client.fetch_api_json(
                url,
                referer=f"{self.http_client.site_origin}/video/{bvid}",
            )

        if self.raw_archive is not None:
            self.raw_archive.save_json("subtitle_meta", f"{bvid}_{cid}", payload)

        subtitle_meta = self._pick_best_subtitle_meta(payload)
        if subtitle_meta is None:
            return None

        subtitle_url = ensure_https_url(subtitle_meta.get("subtitle_url"))
        if subtitle_url is None:
            return None

        subtitle_payload = self._fetch_subtitle_body(subtitle_url, bvid=bvid)
        if self.raw_archive is not None:
            self.raw_archive.save_json(
                "subtitle_body",
                f"{bvid}_{cid}",
                subtitle_payload,
            )

        return self.parse_subtitle_payload(
            subtitle_meta=subtitle_meta,
            subtitle_payload=subtitle_payload,
        )

    def _fetch_subtitle_body(self, subtitle_url: str, *, bvid: str) -> dict[str, Any]:
        try:
            response = self.http_client.get_text(
                subtitle_url,
                referer=f"{self.http_client.site_origin}/video/{bvid}",
                skip_throttle=True,
            )
            return json.loads(response)
        except BilibiliCrawlerError:
            if self.browser_client is None:
                raise
            return self.browser_client.fetch_api_json(
                subtitle_url,
                referer=f"{self.http_client.site_origin}/video/{bvid}",
            )

    def _pick_best_subtitle_meta(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        subtitles = ((payload.get("data") or {}).get("subtitle") or {}).get(
            "subtitles"
        ) or []
        if not subtitles:
            return None

        def sort_key(item: dict[str, Any]) -> tuple[int, str]:
            language = str(item.get("lan") or "")
            try:
                priority = self.preferred_languages.index(language)
            except ValueError:
                priority = len(self.preferred_languages)
            return (priority, language)

        return sorted(subtitles, key=sort_key)[0]

    @staticmethod
    def parse_subtitle_payload(
        *,
        subtitle_meta: dict[str, Any],
        subtitle_payload: dict[str, Any],
    ) -> SubtitleData:
        body = subtitle_payload.get("body")
        if body is None:
            raise BilibiliParseError("Subtitle payload is missing body segments.")

        segments = [
            SubtitleSegmentData(
                segment_index=index,
                start_seconds=(
                    float(item.get("from")) if item.get("from") is not None else None
                ),
                end_seconds=(
                    float(item.get("to")) if item.get("to") is not None else None
                ),
                content=strip_html_tags(str(item.get("content") or "")),
            )
            for index, item in enumerate(body)
            if strip_html_tags(str(item.get("content") or ""))
        ]

        return SubtitleData(
            subtitle_url=ensure_https_url(subtitle_meta.get("subtitle_url")) or "",
            language_code=str(subtitle_meta.get("lan") or ""),
            language_name=strip_html_tags(str(subtitle_meta.get("lan_doc") or "")),
            segments=segments,
            raw_payload=subtitle_payload,
        )
