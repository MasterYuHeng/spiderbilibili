"""Crawler package."""

from app.crawler.browser_client import BilibiliBrowserClient
from app.crawler.client import BilibiliHttpClient
from app.crawler.dedupe import dedupe_search_candidates
from app.crawler.detail_spider import BilibiliDetailSpider
from app.crawler.hot_spider import BilibiliHotSpider
from app.crawler.models import (
    CrawledVideoBundle,
    ScoredVideo,
    SearchPageData,
    SearchVideoCandidate,
    SubtitleData,
    SubtitleSegmentData,
    VideoDetailData,
    VideoMetrics,
    VideoPageRef,
)
from app.crawler.raw_archive import RawArchiveStore
from app.crawler.search_spider import BilibiliSearchSpider
from app.crawler.subtitle_spider import BilibiliSubtitleSpider

__all__ = [
    "BilibiliBrowserClient",
    "BilibiliDetailSpider",
    "BilibiliHotSpider",
    "BilibiliHttpClient",
    "BilibiliSearchSpider",
    "BilibiliSubtitleSpider",
    "CrawledVideoBundle",
    "RawArchiveStore",
    "ScoredVideo",
    "SearchPageData",
    "SearchVideoCandidate",
    "SubtitleData",
    "SubtitleSegmentData",
    "VideoDetailData",
    "VideoMetrics",
    "VideoPageRef",
    "dedupe_search_candidates",
]
