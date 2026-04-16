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


class BilibiliSearchSpider:
    endpoint = "/x/web-interface/search/type"

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

    def search_keyword(
        self,
        keyword: str,
        *,
        max_pages: int,
        limit: int,
        tids: int | None = None,
    ) -> list[SearchVideoCandidate]:
        candidates: list[SearchVideoCandidate] = []
        unique_bvids: set[str] = set()
        for page in range(1, max_pages + 1):
            page_kwargs = {"page": page}
            if tids is not None:
                page_kwargs["tids"] = tids
            page_data = self.search_page(keyword, **page_kwargs)
            candidates.extend(page_data.candidates)
            unique_bvids.update(
                candidate.bvid for candidate in page_data.candidates if candidate.bvid
            )
            if len(unique_bvids) >= limit or page >= page_data.total_pages:
                break
        return candidates

    def search_page(
        self,
        keyword: str,
        *,
        page: int,
        tids: int | None = None,
    ) -> SearchPageData:
        params = {
            "search_type": "video",
            "keyword": keyword,
            "page": page,
        }
        if tids is not None:
            params["tids"] = tids
        try:
            payload = self.http_client.get_api_json(
                self.endpoint,
                params=params,
                referer=self.http_client.search_origin,
                include_auth=False,
            )
        except BilibiliCrawlerError:
            if self.browser_client is None:
                raise
            url = self.http_client.build_url(
                self.endpoint,
                params=params,
                use_wbi=False,
            )
            payload = self.browser_client.fetch_api_json(
                url,
                referer=f"{self.http_client.search_origin}/all?keyword={keyword}",
                include_auth_cookies=False,
                include_credentials=False,
            )

        if self.raw_archive is not None:
            archive_suffix = f"{keyword}_tids_{tids}" if tids is not None else keyword
            self.raw_archive.save_json(
                "search", f"page_{page}_{archive_suffix}", payload
            )

        return self.parse_search_page_data(payload, keyword=keyword, page=page)

    @staticmethod
    def parse_search_page_data(
        payload: dict[str, Any],
        *,
        keyword: str,
        page: int,
    ) -> SearchPageData:
        data = payload.get("data") or {}
        raw_results = data.get("result") or []
        page_size = int(data.get("pagesize") or len(raw_results) or 20)
        candidates = [
            BilibiliSearchSpider.parse_search_result_item(
                item,
                keyword=keyword,
                page=page,
                page_size=page_size,
            )
            for item in raw_results
        ]
        return SearchPageData(
            keyword=keyword,
            page=page,
            page_size=page_size,
            total_results=int(data.get("numResults") or 0),
            total_pages=int(data.get("numPages") or 0),
            candidates=candidates,
            raw_payload=payload,
        )

    @staticmethod
    def parse_search_result_item(
        payload: dict[str, Any],
        *,
        keyword: str,
        page: int,
        page_size: int,
    ) -> SearchVideoCandidate:
        rank_index = int(payload.get("rank_index") or payload.get("rank_offset") or 1)
        search_rank = ((page - 1) * page_size) + rank_index
        bvid = str(payload.get("bvid") or "")
        aid = payload.get("aid")
        return SearchVideoCandidate(
            keyword=keyword,
            bvid=bvid,
            aid=int(aid) if aid is not None else None,
            title=strip_html_tags(str(payload.get("title") or "")),
            description=strip_html_tags(str(payload.get("description") or "")),
            author_name=strip_html_tags(str(payload.get("author") or "")) or None,
            author_mid=str(payload.get("mid") or "") or None,
            url=payload.get("arcurl")
            or f"{BilibiliHttpClient.site_origin}/video/{bvid}",
            cover_url=ensure_https_url(payload.get("pic") or payload.get("cover")),
            published_at=datetime_from_timestamp(
                payload.get("pubdate") or payload.get("senddate")
            ),
            duration_seconds=parse_duration_text(payload.get("duration")),
            search_rank=search_rank,
            play_count=parse_count_text(payload.get("play")),
            like_count=parse_count_text(payload.get("like")),
            favorite_count=parse_count_text(payload.get("favorites")),
            comment_count=parse_count_text(payload.get("review")),
            danmaku_count=parse_count_text(
                payload.get("video_review") or payload.get("danmaku")
            ),
            tag_names=[
                strip_html_tags(tag)
                for tag in str(payload.get("tag") or "").split(",")
                if strip_html_tags(tag)
            ],
            hit_columns=[str(item) for item in payload.get("hit_columns") or []],
            raw_payload=payload,
        )
