from datetime import datetime, timezone

from app.crawler.models import (
    CrawledVideoBundle,
    SearchVideoCandidate,
    SubtitleData,
    SubtitleSegmentData,
    VideoDetailData,
    VideoMetrics,
    VideoPageRef,
)
from app.services.video_score_service import (
    DEFAULT_HEAT_WEIGHT,
    DEFAULT_RELEVANCE_WEIGHT,
    VideoScoreService,
)


def build_bundle(*, keyword_in_title: bool, view_count: int) -> CrawledVideoBundle:
    title = "AI 教程入门" if keyword_in_title else "数据分析教程"
    candidate = SearchVideoCandidate(
        keyword="AI",
        bvid=f"BV{view_count}",
        aid=view_count,
        title=title,
        description="适合零基础学习 AI",
        author_name="测试UP",
        author_mid="123",
        url=f"https://www.bilibili.com/video/BV{view_count}",
        cover_url=None,
        published_at=datetime.now(timezone.utc),
        duration_seconds=600,
        search_rank=1,
        play_count=view_count,
        like_count=view_count // 10,
        favorite_count=view_count // 20,
        comment_count=view_count // 50,
        danmaku_count=view_count // 40,
        tag_names=["AI", "教程"],
        hit_columns=["title", "description"] if keyword_in_title else ["description"],
        raw_payload={},
    )
    detail = VideoDetailData(
        bvid=candidate.bvid,
        aid=candidate.aid,
        title=title,
        description="适合零基础学习 AI",
        author_name="测试UP",
        author_mid="123",
        url=candidate.url,
        cover_url=None,
        published_at=candidate.published_at,
        duration_seconds=600,
        tags=["AI", "教程"],
        metrics=VideoMetrics(
            view_count=view_count,
            like_count=view_count // 10,
            coin_count=view_count // 25,
            favorite_count=view_count // 20,
            share_count=view_count // 100,
            reply_count=view_count // 50,
            danmaku_count=view_count // 40,
        ),
        pages=[VideoPageRef(cid=1, page=1, part="P1", duration_seconds=600)],
        raw_payload={},
    )
    subtitle = SubtitleData(
        subtitle_url="https://example.com/subtitle.json",
        language_code="zh-CN",
        language_name="中文",
        segments=[
            SubtitleSegmentData(
                segment_index=0,
                start_seconds=0.0,
                end_seconds=3.0,
                content="欢迎学习 AI",
            )
        ],
        raw_payload={},
    )
    return CrawledVideoBundle(candidate=candidate, detail=detail, subtitle=subtitle)


def test_video_score_service_balances_relevance_and_heat() -> None:
    service = VideoScoreService()
    relevant_bundle = build_bundle(keyword_in_title=True, view_count=5_000)
    hot_bundle = build_bundle(keyword_in_title=False, view_count=500_000)

    relevant_score = service.score_video("AI", relevant_bundle)
    hot_score = service.score_video("AI", hot_bundle)

    assert relevant_score.keyword_hit_title is True
    assert relevant_score.relevance_score > hot_score.relevance_score
    assert hot_score.heat_score > relevant_score.heat_score
    assert relevant_score.composite_score > 0
    assert hot_score.composite_score > 0


def test_video_score_service_uses_updated_default_weights() -> None:
    service = VideoScoreService()
    bundle = build_bundle(keyword_in_title=True, view_count=50_000)

    score = service.score_video("AI", bundle)

    expected = round(
        (score.relevance_score * DEFAULT_RELEVANCE_WEIGHT)
        + (score.heat_score * DEFAULT_HEAT_WEIGHT),
        4,
    )

    assert score.composite_score == expected
