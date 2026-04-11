from __future__ import annotations

from typing import Any

from app.crawler.browser_client import BilibiliBrowserClient
from app.crawler.client import BilibiliHttpClient
from app.crawler.exceptions import BilibiliCrawlerError, BilibiliParseError
from app.crawler.models import SearchPageData, SearchVideoCandidate
from app.crawler.raw_archive import RawArchiveStore
from app.crawler.utils import (
    datetime_from_timestamp,
    ensure_https_url,
    parse_count_text,
    parse_duration_text,
    strip_html_tags,
)


class BilibiliUploaderSpider:
    endpoint = "/x/space/wbi/arc/search"

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

    def fetch_uploader_videos(
        self,
        author_mid: str,
        *,
        limit: int,
        order: str = "pubdate",
        page_size: int = 30,
    ) -> list[SearchVideoCandidate]:
        candidates: list[SearchVideoCandidate] = []
        total_pages = 1
        page = 1
        while page <= total_pages and len(candidates) < limit:
            page_data = self.fetch_page(
                author_mid,
                page=page,
                page_size=page_size,
                order=order,
            )
            candidates.extend(page_data.candidates)
            total_pages = max(page_data.total_pages, 1)
            page += 1
        return candidates[:limit]

    def fetch_page(
        self,
        author_mid: str,
        *,
        page: int,
        page_size: int = 30,
        order: str = "pubdate",
    ) -> SearchPageData:
        params = {
            "mid": author_mid,
            "pn": page,
            "ps": page_size,
            "order": order,
        }
        try:
            payload = self.http_client.get_api_json(
                self.endpoint,
                params=params,
                referer=f"{self.http_client.site_origin}/",
                use_wbi=True,
            )
        except BilibiliCrawlerError:
            if self.browser_client is None:
                raise
            url = self.http_client.build_url(
                self.endpoint,
                params=params,
                use_wbi=True,
            )
            payload = self.browser_client.fetch_api_json(
                url,
                referer=f"{self.http_client.site_origin}/",
            )

        if self.raw_archive is not None:
            self.raw_archive.save_json(
                "uploader",
                f"mid_{author_mid}_page_{page}_{order}",
                payload,
            )

        return self.parse_uploader_page_data(
            payload,
            author_mid=author_mid,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    def parse_uploader_page_data(
        payload: dict[str, Any],
        *,
        author_mid: str,
        page: int,
        page_size: int,
    ) -> SearchPageData:
        data = payload.get("data") or {}
        page_info = data.get("page") or {}
        list_payload = data.get("list") or {}
        raw_results = list_payload.get("vlist") or []
        if not isinstance(raw_results, list):
            raise BilibiliParseError("Uploader page payload is missing list.vlist.")

        resolved_page_size = int(page_info.get("ps") or page_size or len(raw_results) or 30)
        total_results = int(page_info.get("count") or len(raw_results))
        total_pages = int(page_info.get("count") or 0)
        if resolved_page_size > 0:
            total_pages = max(1, (total_results + resolved_page_size - 1) // resolved_page_size)
        else:
            total_pages = 1

        candidates = [
            BilibiliUploaderSpider.parse_uploader_video_item(
                item,
                author_mid=author_mid,
                page=page,
                page_size=resolved_page_size,
                index=index,
            )
            for index, item in enumerate(raw_results, start=1)
        ]
        return SearchPageData(
            keyword="",
            page=page,
            page_size=resolved_page_size,
            total_results=total_results,
            total_pages=total_pages,
            candidates=candidates,
            raw_payload=payload,
        )

    @staticmethod
    def parse_uploader_video_item(
        payload: dict[str, Any],
        *,
        author_mid: str,
        page: int,
        page_size: int,
        index: int,
    ) -> SearchVideoCandidate:
        bvid = str(payload.get("bvid") or "")
        aid = payload.get("aid")
        title = strip_html_tags(str(payload.get("title") or ""))
        description = strip_html_tags(
            str(payload.get("description") or payload.get("desc") or "")
        )
        author_name = strip_html_tags(
            str(payload.get("author") or payload.get("name") or "")
        ) or None
        cover_value = payload.get("pic") or payload.get("cover")
        if isinstance(cover_value, str) and cover_value.startswith("http://i0.hdslb.com"):
            cover_value = cover_value.replace("http://", "https://", 1)

        return SearchVideoCandidate(
            keyword="",
            bvid=bvid,
            aid=int(aid) if aid is not None else None,
            title=title,
            description=description,
            author_name=author_name,
            author_mid=str(payload.get("mid") or author_mid or "") or None,
            url=payload.get("arcurl")
            or f"{BilibiliHttpClient.site_origin}/video/{bvid}",
            cover_url=ensure_https_url(cover_value),
            published_at=datetime_from_timestamp(
                payload.get("created") or payload.get("pubdate")
            ),
            duration_seconds=parse_duration_text(
                payload.get("length") or payload.get("duration")
            ),
            search_rank=((page - 1) * page_size) + index,
            play_count=parse_count_text(payload.get("play") or payload.get("view")),
            like_count=parse_count_text(payload.get("like")),
            favorite_count=parse_count_text(
                payload.get("favorites") or payload.get("favorite")
            ),
            comment_count=parse_count_text(payload.get("comment") or payload.get("review")),
            danmaku_count=parse_count_text(
                payload.get("video_review") or payload.get("danmaku")
            ),
            tag_names=[],
            hit_columns=[],
            raw_payload=payload,
        )
