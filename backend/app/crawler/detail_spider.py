from __future__ import annotations

from typing import Any

from app.crawler.browser_client import BilibiliBrowserClient
from app.crawler.client import BilibiliHttpClient
from app.crawler.exceptions import BilibiliCrawlerError, BilibiliParseError
from app.crawler.models import VideoDetailData, VideoMetrics, VideoPageRef
from app.crawler.raw_archive import RawArchiveStore
from app.crawler.utils import (
    datetime_from_timestamp,
    ensure_https_url,
    parse_count_text,
    parse_duration_text,
    strip_html_tags,
)


class BilibiliDetailSpider:
    endpoint = "/x/web-interface/view/detail"

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

    def fetch_video_detail(self, bvid: str) -> VideoDetailData:
        params = {"bvid": bvid}
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
            self.raw_archive.save_json("detail", bvid, payload)

        return self.parse_video_detail(payload)

    @staticmethod
    def parse_video_detail(payload: dict[str, Any]) -> VideoDetailData:
        data = payload.get("data") or {}
        view = data.get("View") or {}
        if not view:
            raise BilibiliParseError("Video detail payload is missing View data.")

        tags = [strip_html_tags(tag.get("tag_name")) for tag in data.get("Tags") or []]
        tags = [tag for tag in tags if tag]

        stat = view.get("stat") or {}
        pages = [
            VideoPageRef(
                cid=int(item.get("cid") or 0),
                page=int(item.get("page") or 1),
                part=strip_html_tags(str(item.get("part") or "")),
                duration_seconds=parse_duration_text(item.get("duration")),
            )
            for item in view.get("pages") or []
            if item.get("cid") is not None
        ]

        return VideoDetailData(
            bvid=str(view.get("bvid") or ""),
            aid=int(view["aid"]) if view.get("aid") is not None else None,
            title=strip_html_tags(str(view.get("title") or "")),
            description=strip_html_tags(str(view.get("desc") or "")),
            author_name=strip_html_tags(
                str((data.get("Card") or {}).get("card", {}).get("name") or "")
            )
            or None,
            author_mid=str((data.get("Card") or {}).get("card", {}).get("mid") or "")
            or None,
            url=f"{BilibiliHttpClient.site_origin}/video/{view.get('bvid')}",
            cover_url=ensure_https_url(view.get("pic")),
            published_at=datetime_from_timestamp(view.get("pubdate")),
            duration_seconds=parse_duration_text(view.get("duration")),
            tags=tags,
            metrics=VideoMetrics(
                view_count=parse_count_text(stat.get("view")),
                like_count=parse_count_text(stat.get("like")),
                coin_count=parse_count_text(stat.get("coin")),
                favorite_count=parse_count_text(stat.get("favorite")),
                share_count=parse_count_text(stat.get("share")),
                reply_count=parse_count_text(stat.get("reply")),
                danmaku_count=parse_count_text(stat.get("danmaku")),
            ),
            pages=pages,
            raw_payload=payload,
        )
