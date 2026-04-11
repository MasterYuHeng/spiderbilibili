from __future__ import annotations

from datetime import datetime, timezone

from app.crawler.models import (
    SearchVideoCandidate,
    SubtitleData,
    SubtitleSegmentData,
    VideoDetailData,
    VideoMetrics,
    VideoPageRef,
)


def build_search_candidate(
    bvid: str,
    keyword: str,
    *,
    search_rank: int,
    published_at: datetime | None = None,
) -> SearchVideoCandidate:
    return SearchVideoCandidate(
        keyword=keyword,
        bvid=bvid,
        aid=1,
        title=f"{keyword} 示例视频",
        description=f"{keyword} 示例描述",
        author_name="测试UP",
        author_mid="1001",
        url=f"https://www.bilibili.com/video/{bvid}",
        cover_url=None,
        published_at=published_at or datetime.now(timezone.utc),
        duration_seconds=600,
        search_rank=search_rank,
        play_count=1000,
        like_count=100,
        favorite_count=50,
        comment_count=10,
        danmaku_count=5,
        tag_names=[keyword, "测试"],
        hit_columns=["title", "description"],
        raw_payload={},
    )


def build_detail(bvid: str) -> VideoDetailData:
    return VideoDetailData(
        bvid=bvid,
        aid=1,
        title="AI 示例视频",
        description="AI 示例描述",
        author_name="测试UP",
        author_mid="1001",
        url=f"https://www.bilibili.com/video/{bvid}",
        cover_url=None,
        published_at=datetime.now(timezone.utc),
        duration_seconds=600,
        tags=["AI", "测试"],
        metrics=VideoMetrics(
            view_count=1000,
            like_count=100,
            coin_count=20,
            favorite_count=50,
            share_count=5,
            reply_count=10,
            danmaku_count=5,
        ),
        pages=[VideoPageRef(cid=1, page=1, part="P1", duration_seconds=600)],
        raw_payload={},
    )


def build_subtitle() -> SubtitleData:
    return SubtitleData(
        subtitle_url="https://example.com/subtitle.json",
        language_code="zh-CN",
        language_name="中文",
        segments=[
            SubtitleSegmentData(
                segment_index=0,
                start_seconds=0.0,
                end_seconds=2.0,
                content="AI 示例字幕",
            )
        ],
        raw_payload={},
    )
