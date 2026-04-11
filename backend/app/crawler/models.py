from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class SearchPageData:
    keyword: str
    page: int
    page_size: int
    total_results: int
    total_pages: int
    candidates: list["SearchVideoCandidate"]
    raw_payload: dict[str, Any]


@dataclass(slots=True)
class SearchVideoCandidate:
    keyword: str
    bvid: str
    aid: int | None
    title: str
    description: str
    author_name: str | None
    author_mid: str | None
    url: str
    cover_url: str | None
    published_at: datetime | None
    duration_seconds: int | None
    search_rank: int
    play_count: int = 0
    like_count: int = 0
    favorite_count: int = 0
    comment_count: int = 0
    danmaku_count: int = 0
    tag_names: list[str] = field(default_factory=list)
    hit_columns: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class VideoPageRef:
    cid: int
    page: int
    part: str
    duration_seconds: int | None


@dataclass(slots=True)
class VideoMetrics:
    view_count: int = 0
    like_count: int = 0
    coin_count: int = 0
    favorite_count: int = 0
    share_count: int = 0
    reply_count: int = 0
    danmaku_count: int = 0


@dataclass(slots=True)
class VideoDetailData:
    bvid: str
    aid: int | None
    title: str
    description: str
    author_name: str | None
    author_mid: str | None
    url: str
    cover_url: str | None
    published_at: datetime | None
    duration_seconds: int | None
    tags: list[str]
    metrics: VideoMetrics
    pages: list[VideoPageRef]
    raw_payload: dict[str, Any]

    @property
    def primary_cid(self) -> int | None:
        return self.pages[0].cid if self.pages else None


@dataclass(slots=True)
class SubtitleSegmentData:
    segment_index: int
    start_seconds: float | None
    end_seconds: float | None
    content: str


@dataclass(slots=True)
class SubtitleData:
    subtitle_url: str
    language_code: str
    language_name: str
    segments: list[SubtitleSegmentData]
    raw_payload: dict[str, Any]

    @property
    def combined_text(self) -> str:
        return "\n".join(
            segment.content
            for segment in self.segments
            if segment.content
        )


@dataclass(slots=True)
class CrawledVideoBundle:
    candidate: SearchVideoCandidate
    detail: VideoDetailData
    subtitle: SubtitleData | None = None


@dataclass(slots=True)
class ScoredVideo:
    bundle: CrawledVideoBundle
    keyword_hit_title: bool
    keyword_hit_description: bool
    keyword_hit_tags: bool
    relevance_score: float
    heat_score: float
    composite_score: float
    is_selected: bool = True
