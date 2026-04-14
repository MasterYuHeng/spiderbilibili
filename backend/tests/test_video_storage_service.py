from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.crawler.models import (
    CrawledVideoBundle,
    SearchVideoCandidate,
    SubtitleData,
    SubtitleSegmentData,
    VideoDetailData,
    VideoMetrics,
    VideoPageRef,
)
from app.db.base import Base
from app.models.enums import TaskStatus
from app.models.task import CrawlTask, TaskVideo
from app.services.video_score_service import VideoScoreService
from app.services.video_storage_service import VideoStorageService


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return factory()


def _build_scored_video(
    *,
    keyword: str,
    matched_keywords: list[str],
    primary_matched_keyword: str | None,
):
    published_at = datetime.now(timezone.utc)
    candidate = SearchVideoCandidate(
        keyword=keyword,
        bvid="BV1storage",
        aid=12001,
        title="和平精英视频",
        description="和平精英示例描述",
        author_name="测试UP",
        author_mid="1001",
        url="https://www.bilibili.com/video/BV1storage",
        cover_url=None,
        published_at=published_at,
        duration_seconds=600,
        search_rank=1,
        play_count=1000,
        like_count=100,
        favorite_count=50,
        comment_count=20,
        danmaku_count=10,
        tag_names=["和平精英", "吃鸡"],
        hit_columns=["title", "description"],
        matched_keywords=matched_keywords,
        primary_matched_keyword=primary_matched_keyword,
        raw_payload={},
    )
    detail = VideoDetailData(
        bvid="BV1storage",
        aid=12001,
        title="和平精英视频",
        description="和平精英示例描述",
        author_name="测试UP",
        author_mid="1001",
        url="https://www.bilibili.com/video/BV1storage",
        cover_url=None,
        published_at=published_at,
        duration_seconds=600,
        tags=["和平精英", "吃鸡"],
        metrics=VideoMetrics(
            view_count=1000,
            like_count=100,
            coin_count=20,
            favorite_count=50,
            share_count=5,
            reply_count=10,
            danmaku_count=10,
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
                content="和平精英示例字幕",
            )
        ],
        raw_payload={},
    )
    bundle = CrawledVideoBundle(candidate=candidate, detail=detail, subtitle=subtitle)
    return VideoScoreService().score_video(keyword, bundle)


def test_video_storage_service_persists_keyword_match_fields() -> None:
    with build_session() as session:
        task = CrawlTask(
            keyword="和平精英",
            status=TaskStatus.RUNNING,
            requested_video_limit=5,
            max_pages=2,
            min_sleep_seconds=Decimal("0.01"),
            max_sleep_seconds=Decimal("0.01"),
            enable_proxy=False,
            source_ip_strategy="local_sleep",
        )
        session.add(task)
        session.commit()

        storage_service = VideoStorageService(session)
        scored_video = _build_scored_video(
            keyword="和平精英",
            matched_keywords=["和平精英", "吃鸡"],
            primary_matched_keyword="和平精英",
        )
        storage_service.persist_scored_video(task, scored_video)
        session.commit()

        task_video = session.scalar(select(TaskVideo).where(TaskVideo.task_id == task.id))
        assert task_video is not None
        assert task_video.matched_keywords == ["和平精英", "吃鸡"]
        assert task_video.primary_matched_keyword == "和平精英"
        assert task_video.keyword_match_count == 2


def test_video_storage_service_keeps_hot_mode_keyword_match_fields_empty() -> None:
    with build_session() as session:
        task = CrawlTask(
            keyword="当前热度",
            status=TaskStatus.RUNNING,
            requested_video_limit=5,
            max_pages=2,
            min_sleep_seconds=Decimal("0.01"),
            max_sleep_seconds=Decimal("0.01"),
            enable_proxy=False,
            source_ip_strategy="local_sleep",
        )
        session.add(task)
        session.commit()

        storage_service = VideoStorageService(session)
        scored_video = _build_scored_video(
            keyword="",
            matched_keywords=[],
            primary_matched_keyword=None,
        )
        storage_service.persist_scored_video(task, scored_video)
        session.commit()

        task_video = session.scalar(select(TaskVideo).where(TaskVideo.task_id == task.id))
        assert task_video is not None
        assert task_video.matched_keywords == []
        assert task_video.primary_matched_keyword is None
        assert task_video.keyword_match_count == 0
