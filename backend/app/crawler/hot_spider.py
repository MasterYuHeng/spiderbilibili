from __future__ import annotations

from typing import Any

from app.crawler.browser_client import BilibiliBrowserClient
from app.crawler.client import BilibiliHttpClient
from app.crawler.exceptions import BilibiliCrawlerError
from app.crawler.models import SearchPageData, SearchVideoCandidate
from app.crawler.raw_archive import RawArchiveStore
from app.crawler.utils import (
    datetime_from_timestamp,
    ensure_https_url,
    parse_count_text,
    parse_duration_text,
    strip_html_tags,
)


class BilibiliHotSpider:
    popular_endpoint = "/x/web-interface/popular"
    ranking_endpoint = "/x/web-interface/ranking/v2"

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

    def fetch_sitewide_hot(
        self,
        *,
        max_pages: int,
        limit: int,
        page_size: int = 20,
    ) -> list[SearchVideoCandidate]:
        candidates: list[SearchVideoCandidate] = []
        for page in range(1, max_pages + 1):
            page_data = self.fetch_popular_page(page=page, page_size=page_size)
            candidates.extend(page_data.candidates)
            if len(candidates) >= limit or page >= page_data.total_pages:
                break
        return candidates[:limit]

    def fetch_partition_hot(
        self,
        partition_tid: int,
        *,
        limit: int,
    ) -> list[SearchVideoCandidate]:
        page_data = self.fetch_partition_ranking(partition_tid)
        return page_data.candidates[:limit]

    def fetch_popular_page(
        self,
        *,
        page: int,
        page_size: int = 20,
    ) -> SearchPageData:
        params = {"pn": page, "ps": page_size}
        payload = self._fetch_payload(
            self.popular_endpoint,
            params=params,
            referer=self.http_client.site_origin,
        )
        if self.raw_archive is not None:
            self.raw_archive.save_json("hot", f"popular_page_{page}", payload)
        return self.parse_popular_page_data(payload, page=page, page_size=page_size)

    def fetch_partition_ranking(
        self,
        partition_tid: int,
    ) -> SearchPageData:
        params = {"rid": partition_tid, "type": "all"}
        payload = self._fetch_payload(
            self.ranking_endpoint,
            params=params,
            referer=self.http_client.site_origin,
        )
        if self.raw_archive is not None:
            self.raw_archive.save_json("hot", f"ranking_partition_{partition_tid}", payload)
        return self.parse_partition_ranking_data(payload, partition_tid=partition_tid)

    def _fetch_payload(
        self,
        path: str,
        *,
        params: dict[str, Any],
        referer: str,
    ) -> dict[str, Any]:
        try:
            return self.http_client.get_api_json(
                path,
                params=params,
                referer=referer,
            )
        except BilibiliCrawlerError:
            if self.browser_client is None:
                raise
            url = self.http_client.build_url(path, params=params, use_wbi=False)
            return self.browser_client.fetch_api_json(url, referer=referer)

    @classmethod
    def parse_popular_page_data(
        cls,
        payload: dict[str, Any],
        *,
        page: int,
        page_size: int,
    ) -> SearchPageData:
        data = payload.get("data") or {}
        raw_results = data.get("list") or []
        no_more = bool(data.get("no_more"))
        candidates = [
            cls.parse_hot_video_item(
                item,
                ranking_position=((page - 1) * page_size) + index,
            )
            for index, item in enumerate(raw_results, start=1)
        ]
        return SearchPageData(
            keyword="",
            page=page,
            page_size=page_size,
            total_results=(page * page_size)
            if no_more
            else max(page * page_size, len(raw_results)),
            total_pages=page if no_more else page + 1,
            candidates=candidates,
            raw_payload=payload,
        )

    @classmethod
    def parse_partition_ranking_data(
        cls,
        payload: dict[str, Any],
        *,
        partition_tid: int,
    ) -> SearchPageData:
        data = payload.get("data") or {}
        raw_results = data.get("list") or []
        candidates = [
            cls.parse_hot_video_item(item, ranking_position=index)
            for index, item in enumerate(raw_results, start=1)
        ]
        return SearchPageData(
            keyword="",
            page=1,
            page_size=len(raw_results) or 100,
            total_results=len(raw_results),
            total_pages=1,
            candidates=candidates,
            raw_payload={**payload, "partition_tid": partition_tid},
        )

    @staticmethod
    def parse_hot_video_item(
        payload: dict[str, Any],
        *,
        ranking_position: int,
    ) -> SearchVideoCandidate:
        stat = payload.get("stat") or {}
        owner = payload.get("owner") or {}
        bvid = str(payload.get("bvid") or "")
        aid = payload.get("aid")
        primary_tag = strip_html_tags(str(payload.get("tname") or ""))
        secondary_tag = strip_html_tags(str(payload.get("tnamev2") or ""))
        tags: list[str] = []
        for tag in (primary_tag, secondary_tag):
            if tag and tag not in tags:
                tags.append(tag)
        duration_value = payload.get("duration")
        duration_seconds = (
            int(duration_value)
            if isinstance(duration_value, int)
            else parse_duration_text(duration_value)
        )

        return SearchVideoCandidate(
            keyword="",
            bvid=bvid,
            aid=int(aid) if aid is not None else None,
            title=strip_html_tags(str(payload.get("title") or "")),
            description=strip_html_tags(
                str(payload.get("desc") or payload.get("dynamic") or "")
            ),
            author_name=strip_html_tags(str(owner.get("name") or "")) or None,
            author_mid=str(owner.get("mid") or "") or None,
            url=payload.get("short_link_v2")
            or f"{BilibiliHttpClient.site_origin}/video/{bvid}",
            cover_url=ensure_https_url(payload.get("pic")),
            published_at=datetime_from_timestamp(
                payload.get("pubdate") or payload.get("ctime")
            ),
            duration_seconds=duration_seconds,
            search_rank=ranking_position,
            play_count=parse_count_text(stat.get("view")),
            like_count=parse_count_text(stat.get("like")),
            favorite_count=parse_count_text(stat.get("favorite")),
            comment_count=parse_count_text(stat.get("reply")),
            danmaku_count=parse_count_text(stat.get("danmaku")),
            tag_names=tags,
            hit_columns=[],
            raw_payload=payload,
        )
