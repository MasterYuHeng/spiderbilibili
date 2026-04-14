from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.base import utc_now
from app.models.enums import LogLevel, TaskStage, TaskStatus
from app.models.task import CrawlTask, TaskVideo
from app.models.video import (
    Video,
    VideoMetricSnapshot,
    VideoSubtitleSegment,
    VideoTextContent,
)
from app.services.crawl_pipeline_service import CrawlPipelineService
from app.services.task_log_service import get_task_logs
from app.testsupport import (
    build_detail,
    build_search_candidate,
    build_subtitle,
)


class FakeSearchSpider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def search_keyword(self, keyword: str, *, max_pages: int, limit: int):
        self.calls.append(keyword)
        return [
            build_search_candidate("BV1success", keyword, search_rank=1),
            build_search_candidate("BV1failed", keyword, search_rank=2),
        ]


class FakeDetailSpider:
    def fetch_video_detail(self, bvid: str):
        if bvid == "BV1failed":
            from app.crawler.exceptions import BilibiliRequestError

            raise BilibiliRequestError("detail fetch failed")
        detail = build_detail(bvid)
        detail.aid = sum(ord(char) for char in bvid)
        return detail


class FakeSubtitleSpider:
    def fetch_best_subtitle(self, bvid: str, cid: int | None):
        if bvid == "BV1success":
            return build_subtitle()
        return None


class FakeRawArchive:
    root_dir = "E:/code/fullstack/spiderbilibili/backend/data/raw/test-task"


class FakeKeywordExpansionService:
    def __init__(self, result: dict | None = None) -> None:
        self.result = result or {}
        self.calls: list[dict] = []

    def expand_keyword(
        self,
        *,
        source_keyword: str,
        requested_synonym_count: int | None,
        enabled: bool = True,
    ) -> dict:
        self.calls.append(
            {
                "source_keyword": source_keyword,
                "requested_synonym_count": requested_synonym_count,
                "enabled": enabled,
            }
        )
        return dict(self.result)


class KeywordAwareSearchSpider:
    def __init__(self, mapping: dict[str, list]) -> None:
        self.mapping = mapping
        self.calls: list[str] = []

    def search_keyword(self, keyword: str, *, max_pages: int, limit: int):
        self.calls.append(keyword)
        return list(self.mapping.get(keyword, []))


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return factory()


def test_crawl_pipeline_service_updates_task_summary_and_logs() -> None:
    with build_session() as session:
        task = CrawlTask(
            keyword="AI",
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

        service = CrawlPipelineService(
            session,
            search_spider=FakeSearchSpider(),
            detail_spider=FakeDetailSpider(),
            subtitle_spider=FakeSubtitleSpider(),
            raw_archive=FakeRawArchive(),
        )
        result = service.run_task(task)

        assert result.candidate_count == 2
        assert result.success_count == 1
        assert result.failure_count == 1
        assert result.subtitle_count == 1
        assert task.total_candidates == 2
        assert task.processed_videos == 2
        assert task.extra_params["crawl_stats"]["success_count"] == 1
        assert task.extra_params["crawl_progress"]["selected_count"] == 2
        assert task.extra_params["crawl_progress"]["detail_processed_count"] == 2
        assert task.extra_params["crawl_progress"]["detail_failure_count"] == 1
        assert task.extra_params["crawl_progress"]["current_phase"] == "text"
        assert task.extra_params["storage_stats"]["persisted_video_count"] == 1
        assert task.extra_params["crawl_preview"][0]["bvid"] == "BV1success"

        logs = get_task_logs(session, task.id)
        assert logs[0].stage == TaskStage.SEARCH
        assert any(
            log.stage == TaskStage.DETAIL
            and log.message == "Started candidate detail crawl."
            for log in logs
        )
        assert any(log.stage == TaskStage.TEXT for log in logs)
        assert any(log.level == LogLevel.WARNING for log in logs)

        stored_video = session.scalar(
            select(Video).where(Video.bvid == "BV1success")
        )
        assert stored_video is not None
        assert stored_video.title

        metric_snapshot = session.scalar(
            select(VideoMetricSnapshot).where(
                VideoMetricSnapshot.task_id == task.id,
                VideoMetricSnapshot.video_id == stored_video.id,
            )
        )
        assert metric_snapshot is not None
        assert metric_snapshot.view_count == 1000

        text_content = session.scalar(
            select(VideoTextContent).where(
                VideoTextContent.task_id == task.id,
                VideoTextContent.video_id == stored_video.id,
            )
        )
        assert text_content is not None
        assert text_content.has_description is True
        assert text_content.has_subtitle is True
        assert text_content.combined_text_hash

        subtitle_segments = session.scalars(
            select(VideoSubtitleSegment).where(
                VideoSubtitleSegment.text_content_id == text_content.id
            )
        ).all()
        assert len(subtitle_segments) == 1


def test_crawl_pipeline_service_is_idempotent_for_same_task_outputs() -> None:
    with build_session() as session:
        task = CrawlTask(
            keyword="AI",
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

        service = CrawlPipelineService(
            session,
            search_spider=FakeSearchSpider(),
            detail_spider=FakeDetailSpider(),
            subtitle_spider=FakeSubtitleSpider(),
            raw_archive=FakeRawArchive(),
        )

        service.run_task(task)
        service.run_task(task)

        stored_videos = session.scalars(select(Video)).all()
        metric_snapshots = session.scalars(
            select(VideoMetricSnapshot).where(VideoMetricSnapshot.task_id == task.id)
        ).all()
        text_contents = session.scalars(
            select(VideoTextContent).where(VideoTextContent.task_id == task.id)
        ).all()
        subtitle_segments = session.scalars(select(VideoSubtitleSegment)).all()

        assert len(stored_videos) == 1
        assert len(metric_snapshots) == 1
        assert len(text_contents) == 1
        assert len(subtitle_segments) == 1


def test_crawl_pipeline_service_does_not_reset_previous_outputs_before_search_success(
) -> None:
    class FailingSearchSpider:
        def search_keyword(self, keyword: str, *, max_pages: int, limit: int):
            from app.crawler.exceptions import BilibiliRequestError

            raise BilibiliRequestError("search failed")

    with build_session() as session:
        task = CrawlTask(
            keyword="AI",
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

        seed_service = CrawlPipelineService(
            session,
            search_spider=FakeSearchSpider(),
            detail_spider=FakeDetailSpider(),
            subtitle_spider=FakeSubtitleSpider(),
            raw_archive=FakeRawArchive(),
        )
        seed_service.run_task(task)

        seeded_text_count = session.scalar(
            select(func.count())
            .select_from(VideoTextContent)
            .where(VideoTextContent.task_id == task.id)
        )
        assert seeded_text_count == 1

        failing_service = CrawlPipelineService(
            session,
            search_spider=FailingSearchSpider(),
            detail_spider=FakeDetailSpider(),
            subtitle_spider=FakeSubtitleSpider(),
            raw_archive=FakeRawArchive(),
        )

        with pytest.raises(Exception, match="search failed"):
            failing_service.run_task(task)

        remaining_texts = session.scalars(
            select(VideoTextContent).where(VideoTextContent.task_id == task.id)
        ).all()
        remaining_metrics = session.scalars(
            select(VideoMetricSnapshot).where(VideoMetricSnapshot.task_id == task.id)
        ).all()

        assert len(remaining_texts) == 1
        assert len(remaining_metrics) == 1


def test_crawl_pipeline_service_preserves_original_storage_exception() -> None:
    class ExplodingStorageService:
        def reset_task_outputs(self, task: CrawlTask) -> None:
            return None

        def persist_scored_video(self, task: CrawlTask, scored_video) -> None:
            raise RuntimeError("storage failed")

    with build_session() as session:
        task = CrawlTask(
            keyword="AI",
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

        service = CrawlPipelineService(
            session,
            search_spider=FakeSearchSpider(),
            detail_spider=FakeDetailSpider(),
            subtitle_spider=FakeSubtitleSpider(),
            raw_archive=FakeRawArchive(),
        )
        service.storage_service = ExplodingStorageService()

        with pytest.raises(RuntimeError, match="storage failed"):
            service.run_task(task)


def test_crawl_pipeline_service_filters_candidates_by_recent_publish_window() -> None:
    class RecentWindowSearchSpider:
        def search_keyword(self, keyword: str, *, max_pages: int, limit: int):
            return [
                build_search_candidate(
                    "BV1recent",
                    keyword,
                    search_rank=1,
                    published_at=utc_now() - timedelta(days=2),
                ),
                build_search_candidate(
                    "BV1old",
                    keyword,
                    search_rank=2,
                    published_at=utc_now() - timedelta(days=10),
                ),
            ]

    with build_session() as session:
        task = CrawlTask(
            keyword="AI",
            status=TaskStatus.RUNNING,
            requested_video_limit=5,
            max_pages=2,
            min_sleep_seconds=Decimal("0.01"),
            max_sleep_seconds=Decimal("0.01"),
            enable_proxy=False,
            source_ip_strategy="local_sleep",
            extra_params={"task_options": {"published_within_days": 7}},
        )
        session.add(task)
        session.commit()

        service = CrawlPipelineService(
            session,
            search_spider=RecentWindowSearchSpider(),
            detail_spider=FakeDetailSpider(),
            subtitle_spider=FakeSubtitleSpider(),
            raw_archive=FakeRawArchive(),
        )
        result = service.run_task(task)

        assert result.candidate_count == 1
        assert result.success_count == 1
        assert task.total_candidates == 1
        assert task.extra_params["crawl_stats"]["raw_candidate_count"] == 2
        assert task.extra_params["crawl_stats"]["filtered_out_count"] == 1


def test_crawl_pipeline_service_persists_search_summary_fallback(
) -> None:
    class SearchSummaryOnlySearchSpider:
        def search_keyword(self, keyword: str, *, max_pages: int, limit: int):
            candidate = build_search_candidate(
                "BV1summary",
                keyword,
                search_rank=1,
            )
            candidate.description = "Search summary from result page"
            return [candidate]

    class EmptyDescriptionDetailSpider:
        def fetch_video_detail(self, bvid: str):
            detail = build_detail(bvid)
            detail.description = ""
            return detail

    class NoSubtitleSpider:
        def fetch_best_subtitle(self, bvid: str, cid: int | None):
            return None

    with build_session() as session:
        task = CrawlTask(
            keyword="AI",
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

        service = CrawlPipelineService(
            session,
            search_spider=SearchSummaryOnlySearchSpider(),
            detail_spider=EmptyDescriptionDetailSpider(),
            subtitle_spider=NoSubtitleSpider(),
            raw_archive=FakeRawArchive(),
        )
        service.run_task(task)

        stored_video = session.scalar(select(Video).where(Video.bvid == "BV1summary"))
        assert stored_video is not None

        text_content = session.scalar(
            select(VideoTextContent).where(
                VideoTextContent.task_id == task.id,
                VideoTextContent.video_id == stored_video.id,
            )
        )
        assert text_content is not None
        assert text_content.has_description is True
        assert text_content.description_text == "Search summary from result page"
        assert (
            text_content.combined_text
            == "Video Search Summary:\nSearch summary from result page"
        )


def test_crawl_pipeline_service_runs_keyword_expansion_before_search() -> None:
    search_spider = KeywordAwareSearchSpider(
        {
            "和平精英": [build_search_candidate("BV1origin", "和平精英", search_rank=1)],
            "吃鸡": [build_search_candidate("BV1synonym", "吃鸡", search_rank=1)],
        }
    )
    keyword_expansion_service = FakeKeywordExpansionService(
        {
            "source_keyword": "和平精英",
            "enabled": True,
            "requested_synonym_count": 1,
            "generated_synonyms": ["吃鸡"],
            "expanded_keywords": ["和平精英", "吃鸡"],
            "status": "success",
            "model_name": "gpt-4.1-mini",
            "error_message": None,
            "generated_at": "2026-04-13T12:00:00Z",
        }
    )

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
            extra_params={
                "task_options": {
                    "crawl_mode": "keyword",
                    "search_scope": "site",
                    "enable_keyword_synonym_expansion": True,
                    "keyword_synonym_count": 1,
                }
            },
        )
        session.add(task)
        session.commit()

        service = CrawlPipelineService(
            session,
            search_spider=search_spider,
            detail_spider=FakeDetailSpider(),
            subtitle_spider=FakeSubtitleSpider(),
            raw_archive=FakeRawArchive(),
            keyword_expansion_service=keyword_expansion_service,
        )
        result = service.run_task(task)

        assert result.candidate_count == 2
        assert result.success_count == 2
        assert search_spider.calls == ["和平精英", "吃鸡"]
        assert len(keyword_expansion_service.calls) == 1
        assert task.extra_params["keyword_expansion"]["status"] == "success"
        assert task.extra_params["keyword_expansion"]["generated_synonyms"] == ["吃鸡"]
        assert task.extra_params["crawl_stats"]["search_keyword_count"] == 2
        assert task.extra_params["crawl_stats"]["expanded_keyword_count"] == 1
        assert task.extra_params["crawl_stats"]["search_keywords_used"] == [
            "和平精英",
            "吃鸡",
        ]

        logs = get_task_logs(session, task.id)
        assert any(log.message == "Starting keyword expansion." for log in logs)
        assert any(log.message == "Keyword expansion succeeded." for log in logs)
        assert any(
            log.message == "Finished multi-keyword search merge." for log in logs
        )


def test_crawl_pipeline_service_reuses_persisted_keyword_expansion() -> None:
    search_spider = KeywordAwareSearchSpider(
        {
            "和平精英": [build_search_candidate("BV1origin", "和平精英", search_rank=1)],
            "吃鸡": [build_search_candidate("BV1synonym", "吃鸡", search_rank=1)],
        }
    )
    keyword_expansion_service = FakeKeywordExpansionService(
        {
            "source_keyword": "和平精英",
            "enabled": True,
            "requested_synonym_count": 1,
            "generated_synonyms": ["吃鸡"],
            "expanded_keywords": ["和平精英", "吃鸡"],
            "status": "success",
            "model_name": "gpt-4.1-mini",
            "error_message": None,
            "generated_at": "2026-04-13T12:00:00Z",
        }
    )

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
            extra_params={
                "task_options": {
                    "crawl_mode": "keyword",
                    "search_scope": "site",
                    "enable_keyword_synonym_expansion": True,
                    "keyword_synonym_count": 1,
                },
                "keyword_expansion": {
                    "source_keyword": "和平精英",
                    "enabled": True,
                    "requested_synonym_count": 1,
                    "generated_synonyms": ["吃鸡"],
                    "expanded_keywords": ["和平精英", "吃鸡"],
                    "status": "success",
                    "model_name": "gpt-4.1-mini",
                    "error_message": None,
                    "generated_at": "2026-04-13T12:00:00Z",
                },
            },
        )
        session.add(task)
        session.commit()

        service = CrawlPipelineService(
            session,
            search_spider=search_spider,
            detail_spider=FakeDetailSpider(),
            subtitle_spider=FakeSubtitleSpider(),
            raw_archive=FakeRawArchive(),
            keyword_expansion_service=keyword_expansion_service,
        )
        service.run_task(task)

        assert keyword_expansion_service.calls == []
        assert search_spider.calls == ["和平精英", "吃鸡"]
        assert task.extra_params["keyword_expansion"]["status"] == "success"

        logs = get_task_logs(session, task.id)
        assert not any(log.message == "Starting keyword expansion." for log in logs)


def test_crawl_pipeline_service_falls_back_to_source_keyword_when_expansion_fails() -> None:
    search_spider = KeywordAwareSearchSpider(
        {
            "和平精英": [build_search_candidate("BV1origin", "和平精英", search_rank=1)],
            "吃鸡": [build_search_candidate("BV1synonym", "吃鸡", search_rank=1)],
        }
    )
    keyword_expansion_service = FakeKeywordExpansionService(
        {
            "source_keyword": "和平精英",
            "enabled": True,
            "requested_synonym_count": 1,
            "generated_synonyms": [],
            "expanded_keywords": ["和平精英"],
            "status": "fallback",
            "model_name": "gpt-4.1-mini",
            "error_message": "AI keyword expansion returned no valid synonyms.",
            "generated_at": "2026-04-13T12:00:00Z",
        }
    )

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
            extra_params={
                "task_options": {
                    "crawl_mode": "keyword",
                    "search_scope": "site",
                    "enable_keyword_synonym_expansion": True,
                    "keyword_synonym_count": 1,
                }
            },
        )
        session.add(task)
        session.commit()

        service = CrawlPipelineService(
            session,
            search_spider=search_spider,
            detail_spider=FakeDetailSpider(),
            subtitle_spider=FakeSubtitleSpider(),
            raw_archive=FakeRawArchive(),
            keyword_expansion_service=keyword_expansion_service,
        )
        result = service.run_task(task)

        assert result.candidate_count == 1
        assert search_spider.calls == ["和平精英"]
        assert len(keyword_expansion_service.calls) == 1
        assert task.extra_params["keyword_expansion"]["status"] == "fallback"
        assert task.extra_params["crawl_stats"]["search_keyword_count"] == 1
        assert task.extra_params["crawl_stats"]["expanded_keyword_count"] == 0
        assert task.extra_params["crawl_stats"]["search_keywords_used"] == ["和平精英"]

        logs = get_task_logs(session, task.id)
        assert any(
            log.message == "Keyword expansion failed, fallback to source keyword."
            and log.level == LogLevel.WARNING
            for log in logs
        )


def test_crawl_pipeline_service_merges_duplicate_candidates_across_search_keywords() -> None:
    search_spider = KeywordAwareSearchSpider(
        {
            "和平精英": [build_search_candidate("BV1dup", "和平精英", search_rank=8)],
            "吃鸡": [build_search_candidate("BV1dup", "吃鸡", search_rank=2)],
        }
    )
    keyword_expansion_service = FakeKeywordExpansionService(
        {
            "source_keyword": "和平精英",
            "enabled": True,
            "requested_synonym_count": 1,
            "generated_synonyms": ["吃鸡"],
            "expanded_keywords": ["和平精英", "吃鸡"],
            "status": "success",
            "model_name": "gpt-4.1-mini",
            "error_message": None,
            "generated_at": "2026-04-13T12:00:00Z",
        }
    )

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
            extra_params={
                "task_options": {
                    "crawl_mode": "keyword",
                    "search_scope": "site",
                    "enable_keyword_synonym_expansion": True,
                    "keyword_synonym_count": 1,
                }
            },
        )
        session.add(task)
        session.commit()

        service = CrawlPipelineService(
            session,
            search_spider=search_spider,
            detail_spider=FakeDetailSpider(),
            subtitle_spider=FakeSubtitleSpider(),
            raw_archive=FakeRawArchive(),
            keyword_expansion_service=keyword_expansion_service,
        )
        result = service.run_task(task)

        assert result.candidate_count == 1
        assert result.success_count == 1
        assert task.total_candidates == 1
        assert task.extra_params["crawl_stats"]["raw_candidate_count"] == 2
        assert task.extra_params["crawl_preview"][0]["matched_keywords"] == [
            "和平精英",
            "吃鸡",
        ]
        assert (
            task.extra_params["crawl_preview"][0]["primary_matched_keyword"] == "和平精英"
        )
        assert task.extra_params["crawl_preview"][0]["keyword_match_count"] == 2

        stored_task_video = session.scalar(
            select(TaskVideo).where(TaskVideo.task_id == task.id)
        )
        assert stored_task_video is not None
        assert stored_task_video.matched_keywords == ["和平精英", "吃鸡"]
        assert stored_task_video.primary_matched_keyword == "和平精英"
        assert stored_task_video.keyword_match_count == 2
