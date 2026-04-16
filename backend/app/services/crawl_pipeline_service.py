from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.crawler.browser_client import BilibiliBrowserClient
from app.crawler.client import BilibiliHttpClient
from app.crawler.dedupe import dedupe_search_candidates
from app.crawler.detail_spider import BilibiliDetailSpider
from app.crawler.exceptions import BilibiliCrawlerError
from app.crawler.hot_spider import BilibiliHotSpider
from app.crawler.models import CrawledVideoBundle, ScoredVideo
from app.crawler.raw_archive import RawArchiveStore
from app.crawler.search_spider import BilibiliSearchSpider
from app.crawler.subtitle_spider import BilibiliSubtitleSpider
from app.models.base import utc_now
from app.models.enums import LogLevel, TaskStage
from app.models.task import CrawlTask
from app.services.keyword_expansion_service import KeywordExpansionService
from app.services.system_config_service import (
    build_bilibili_runtime_settings,
    get_system_config_value,
)
from app.services.task_log_service import create_task_log
from app.services.task_service import assert_task_execution_allowed
from app.services.video_score_service import VideoScoreService
from app.services.video_storage_service import VideoStorageService


@dataclass(slots=True)
class CrawlPipelineResult:
    candidate_count: int
    selected_count: int
    video_concurrency: int
    success_count: int
    failure_count: int
    subtitle_count: int
    top_videos: list[dict[str, Any]]
    raw_archive_dir: str | None


class CrawlPipelineService:
    def __init__(
        self,
        session: Session,
        *,
        http_client: BilibiliHttpClient | None = None,
        browser_client: BilibiliBrowserClient | None = None,
        search_spider: BilibiliSearchSpider | None = None,
        hot_spider: BilibiliHotSpider | None = None,
        detail_spider: BilibiliDetailSpider | None = None,
        subtitle_spider: BilibiliSubtitleSpider | None = None,
        score_service: VideoScoreService | None = None,
        raw_archive: RawArchiveStore | None = None,
        keyword_expansion_service: KeywordExpansionService | None = None,
    ) -> None:
        self.session = session
        self._owns_http_client = http_client is None
        self._owns_browser_client = browser_client is None
        self.http_client = http_client
        self.browser_client = browser_client
        self.search_spider = search_spider
        self.hot_spider = hot_spider
        self.detail_spider = detail_spider
        self.subtitle_spider = subtitle_spider
        self.score_service = score_service or VideoScoreService()
        self.raw_archive = raw_archive
        self.keyword_expansion_service = keyword_expansion_service
        self.storage_service = VideoStorageService(session)

    def close(self) -> None:
        if self._owns_http_client and self.http_client is not None:
            self.http_client.close()
        if self._owns_browser_client and self.browser_client is not None:
            self.browser_client.close()

    def run_task(
        self,
        task: CrawlTask,
        *,
        expected_dispatch_generation: int | None = None,
    ) -> CrawlPipelineResult:
        logger = get_logger(__name__)
        raw_archive = self.raw_archive or RawArchiveStore(task.id)
        self.raw_archive = raw_archive

        if self.http_client is None:
            runtime_settings = build_bilibili_runtime_settings(
                self.session,
                get_settings(),
            )
            self.http_client = BilibiliHttpClient(
                settings=runtime_settings,
                min_sleep_seconds=float(task.min_sleep_seconds),
                max_sleep_seconds=float(task.max_sleep_seconds),
                use_proxy=task.enable_proxy,
            )
        if self.browser_client is None:
            runtime_settings = build_bilibili_runtime_settings(
                self.session,
                get_settings(),
            )
            self.browser_client = BilibiliBrowserClient(
                settings=runtime_settings,
                use_proxy=task.enable_proxy,
            )
        if self.search_spider is None:
            self.search_spider = BilibiliSearchSpider(
                self.http_client,
                browser_client=self.browser_client,
                raw_archive=raw_archive,
            )
        if self.hot_spider is None:
            self.hot_spider = BilibiliHotSpider(
                self.http_client,
                browser_client=self.browser_client,
                raw_archive=raw_archive,
            )
        if self.detail_spider is None:
            self.detail_spider = BilibiliDetailSpider(
                self.http_client,
                browser_client=self.browser_client,
                raw_archive=raw_archive,
            )
        if self.subtitle_spider is None:
            self.subtitle_spider = BilibiliSubtitleSpider(
                self.http_client,
                browser_client=self.browser_client,
                raw_archive=raw_archive,
            )
        task_options = (
            task.extra_params.get("task_options", {})
            if isinstance(task.extra_params, dict)
            else {}
        )
        crawl_mode = str(task_options.get("crawl_mode") or "keyword")
        search_scope = str(task_options.get("search_scope") or "site")
        partition_tid_raw = task_options.get("partition_tid")
        partition_tid = (
            int(partition_tid_raw) if partition_tid_raw is not None else None
        )
        partition_name = (
            str(task_options.get("partition_name"))
            if task_options.get("partition_name")
            else None
        )
        published_within_days_raw = task_options.get("published_within_days")
        published_within_days = (
            int(published_within_days_raw)
            if published_within_days_raw is not None
            else None
        )
        keyword_expansion, search_keywords_used = self._resolve_keyword_search_context(
            task,
            crawl_mode=crawl_mode,
            task_options=task_options,
            expected_dispatch_generation=expected_dispatch_generation,
        )
        task = assert_task_execution_allowed(
            self.session,
            task.id,
            expected_dispatch_generation=expected_dispatch_generation,
        )

        create_task_log(
            self.session,
            task=task,
            stage=TaskStage.SEARCH,
            message=(
                "Starting Bilibili current hot crawl."
                if crawl_mode == "hot"
                else "Starting Bilibili search crawl."
            ),
            payload={
                "crawl_mode": crawl_mode,
                "keyword": task.keyword,
                "search_scope": search_scope,
                "partition_tid": partition_tid,
                "partition_name": partition_name,
                "published_within_days": published_within_days,
                "max_pages": task.max_pages,
                "requested_video_limit": task.requested_video_limit,
                "search_keyword_count": len(search_keywords_used),
                "search_keywords_used": search_keywords_used,
                "keyword_expansion_status": (
                    keyword_expansion.get("status")
                    if isinstance(keyword_expansion, dict)
                    else None
                ),
            },
        )
        self.session.commit()
        task = assert_task_execution_allowed(
            self.session,
            task.id,
            expected_dispatch_generation=expected_dispatch_generation,
        )

        if crawl_mode == "hot":
            if search_scope == "partition" and partition_tid is not None:
                candidates = self.hot_spider.fetch_partition_hot(
                    partition_tid,
                    limit=task.requested_video_limit,
                )
            else:
                candidates = self.hot_spider.fetch_sitewide_hot(
                    max_pages=task.max_pages,
                    limit=task.requested_video_limit,
                )
        else:
            candidates = self._collect_keyword_candidates(
                task,
                search_keywords_used=search_keywords_used,
                search_scope=search_scope,
                partition_tid=partition_tid,
                expected_dispatch_generation=expected_dispatch_generation,
            )
        deduped_candidates = dedupe_search_candidates(
            candidates,
            source_keyword=task.keyword if crawl_mode == "keyword" else None,
        )
        filtered_candidates = self._filter_candidates_by_publish_time(
            deduped_candidates,
            published_within_days=published_within_days,
        )
        selected_candidates = filtered_candidates[: task.requested_video_limit]
        task.total_candidates = len(filtered_candidates)
        self.session.commit()

        create_task_log(
            self.session,
            task=task,
            stage=TaskStage.SEARCH,
            message="Collected candidate videos for the current crawl mode.",
            payload={
                "raw_candidate_count": len(candidates),
                "candidate_count": len(filtered_candidates),
                "filtered_out_count": len(deduped_candidates)
                - len(filtered_candidates),
                "selected_count": len(selected_candidates),
                "search_keyword_count": len(search_keywords_used),
                "expanded_keyword_count": (
                    max(len(search_keywords_used) - 1, 0)
                    if crawl_mode == "keyword"
                    else 0
                ),
                "search_keywords_used": search_keywords_used,
                "crawl_mode": crawl_mode,
                "search_scope": search_scope,
                "partition_tid": partition_tid,
                "partition_name": partition_name,
                "published_within_days": published_within_days,
            },
        )
        self.session.commit()

        self.storage_service.reset_task_outputs(task)
        self.session.commit()

        scored_videos: list[ScoredVideo] = []
        failures: list[dict[str, str]] = []
        subtitle_count = 0
        scoring_weights = (
            get_system_config_value(self.session, "analysis.scoring_weights") or {}
        )
        http_settings = getattr(self.http_client, "settings", None)
        video_concurrency = max(
            1,
            min(
                len(selected_candidates) or 1,
                int(getattr(http_settings, "crawler_concurrency", 1)),
            ),
        )
        detail_processed_count = 0
        detail_success_count = 0
        detail_failure_count = 0

        self._update_crawl_progress(
            task,
            candidate_count=len(filtered_candidates),
            selected_count=len(selected_candidates),
            video_concurrency=video_concurrency,
            detail_processed_count=detail_processed_count,
            detail_success_count=detail_success_count,
            detail_failure_count=detail_failure_count,
            current_phase="detail",
        )
        create_task_log(
            self.session,
            task=task,
            stage=TaskStage.DETAIL,
            message="Started candidate detail crawl.",
            payload={
                "candidate_count": len(filtered_candidates),
                "selected_count": len(selected_candidates),
                "video_concurrency": video_concurrency,
                "published_within_days": published_within_days,
            },
        )
        self.session.commit()

        ordered_outcomes: list[
            tuple[int, ScoredVideo | None, dict[str, str] | None]
        ] = []
        if video_concurrency == 1:
            for index, candidate in enumerate(selected_candidates, start=1):
                task = assert_task_execution_allowed(
                    self.session,
                    task.id,
                    expected_dispatch_generation=expected_dispatch_generation,
                )
                try:
                    ordered_outcomes.append(
                        (
                            index,
                            self._crawl_candidate(
                                task,
                                candidate,
                                scoring_weights,
                            ),
                            None,
                        )
                    )
                    detail_success_count += 1
                except BilibiliCrawlerError as exc:
                    ordered_outcomes.append(
                        (
                            index,
                            None,
                            {
                                "bvid": candidate.bvid,
                                "error": str(exc),
                                "browser_fallback_attempted": True,
                            },
                        )
                    )
                    detail_failure_count += 1
                detail_processed_count += 1
                self._update_crawl_progress(
                    task,
                    candidate_count=len(filtered_candidates),
                    selected_count=len(selected_candidates),
                    video_concurrency=video_concurrency,
                    detail_processed_count=detail_processed_count,
                    detail_success_count=detail_success_count,
                    detail_failure_count=detail_failure_count,
                    current_phase="detail",
                    current_bvid=candidate.bvid,
                )
        else:
            threaded_failures: list[tuple[int, object, str]] = []
            with ThreadPoolExecutor(max_workers=video_concurrency) as executor:
                future_map = {
                    executor.submit(
                        self._crawl_candidate_http_only,
                        task,
                        candidate,
                        scoring_weights,
                    ): (index, candidate)
                    for index, candidate in enumerate(selected_candidates, start=1)
                }
                for future in as_completed(future_map):
                    task = assert_task_execution_allowed(
                        self.session,
                        task.id,
                        expected_dispatch_generation=expected_dispatch_generation,
                    )
                    index, candidate = future_map[future]
                    try:
                        ordered_outcomes.append((index, future.result(), None))
                        detail_processed_count += 1
                        detail_success_count += 1
                        self._update_crawl_progress(
                            task,
                            candidate_count=len(filtered_candidates),
                            selected_count=len(selected_candidates),
                            video_concurrency=video_concurrency,
                            detail_processed_count=detail_processed_count,
                            detail_success_count=detail_success_count,
                            detail_failure_count=detail_failure_count,
                            current_phase="detail",
                            current_bvid=candidate.bvid,
                        )
                    except BilibiliCrawlerError as exc:
                        threaded_failures.append((index, candidate, str(exc)))

            for index, candidate, error in threaded_failures:
                task = assert_task_execution_allowed(
                    self.session,
                    task.id,
                    expected_dispatch_generation=expected_dispatch_generation,
                )
                try:
                    ordered_outcomes.append(
                        (
                            index,
                            self._crawl_candidate(
                                task,
                                candidate,
                                scoring_weights,
                            ),
                            None,
                        )
                    )
                    detail_success_count += 1
                except BilibiliCrawlerError as fallback_exc:
                    ordered_outcomes.append(
                        (
                            index,
                            None,
                            {
                                "bvid": candidate.bvid,
                                "error": str(fallback_exc),
                                "browser_fallback_attempted": True,
                                "http_error": error,
                            },
                        )
                    )
                    detail_failure_count += 1
                detail_processed_count += 1
                self._update_crawl_progress(
                    task,
                    candidate_count=len(filtered_candidates),
                    selected_count=len(selected_candidates),
                    video_concurrency=video_concurrency,
                    detail_processed_count=detail_processed_count,
                    detail_success_count=detail_success_count,
                    detail_failure_count=detail_failure_count,
                    current_phase="detail",
                    current_bvid=getattr(candidate, "bvid", None),
                )

        for _index, scored_video, failure in sorted(
            ordered_outcomes,
            key=lambda item: item[0],
        ):
            task = assert_task_execution_allowed(
                self.session,
                task.id,
                expected_dispatch_generation=expected_dispatch_generation,
            )
            if scored_video is not None:
                if scored_video.bundle.subtitle is not None:
                    subtitle_count += 1
                self.storage_service.persist_scored_video(task, scored_video)
                scored_videos.append(scored_video)
            elif failure is not None:
                logger.warning(
                    "Failed to crawl {}: {}",
                    failure["bvid"],
                    failure["error"],
                )
                failures.append(failure)
                create_task_log(
                    self.session,
                    task=task,
                    level=LogLevel.WARNING,
                    stage=TaskStage.DETAIL,
                    message="Failed to crawl a candidate video.",
                    payload=failure,
                )

            if self.session.is_active:
                self.session.commit()

        scored_videos.sort(key=lambda item: item.composite_score, reverse=True)
        top_videos = [self._serialize_scored_video(item) for item in scored_videos[:20]]

        create_task_log(
            self.session,
            task=task,
            stage=TaskStage.TEXT,
            message="Persisted crawled videos, metrics, and cleaned texts.",
            payload={
                "persisted_video_count": len(scored_videos),
                "subtitle_segment_count": sum(
                    len(item.bundle.subtitle.segments)
                    for item in scored_videos
                    if item.bundle.subtitle is not None
                ),
            },
        )
        task.extra_params = self._merge_task_crawl_payload(
            task.extra_params,
            {
                "crawl_stats": {
                    "raw_candidate_count": len(candidates),
                    "candidate_count": len(filtered_candidates),
                    "selected_count": len(selected_candidates),
                    "filtered_out_count": len(deduped_candidates)
                    - len(filtered_candidates),
                    "search_keyword_count": len(search_keywords_used),
                    "expanded_keyword_count": (
                        max(len(search_keywords_used) - 1, 0)
                        if crawl_mode == "keyword"
                        else 0
                    ),
                    "search_keywords_used": search_keywords_used,
                    "video_concurrency": video_concurrency,
                    "success_count": len(scored_videos),
                    "failure_count": len(failures),
                    "subtitle_count": subtitle_count,
                    "published_within_days": published_within_days,
                },
                "crawl_progress": {
                    "candidate_count": len(filtered_candidates),
                    "selected_count": len(selected_candidates),
                    "video_concurrency": video_concurrency,
                    "detail_processed_count": detail_processed_count,
                    "detail_success_count": detail_success_count,
                    "detail_failure_count": detail_failure_count,
                    "current_phase": "text",
                    "current_bvid": None,
                },
                "storage_stats": {
                    "persisted_video_count": len(scored_videos),
                    "metric_snapshot_count": len(scored_videos),
                    "text_content_count": len(scored_videos),
                },
                "crawl_preview": top_videos,
                "crawl_failures": failures[:20],
                "raw_archive_dir": (
                    str(raw_archive.root_dir)
                    if raw_archive.root_dir is not None
                    else None
                ),
            },
        )
        self.session.commit()

        create_task_log(
            self.session,
            task=task,
            stage=TaskStage.SUBTITLE,
            message="Finished Bilibili crawl pipeline.",
            payload={
                "success_count": len(scored_videos),
                "failure_count": len(failures),
                "subtitle_count": subtitle_count,
                "video_concurrency": video_concurrency,
                "published_within_days": published_within_days,
            },
        )
        self.session.commit()

        return CrawlPipelineResult(
            candidate_count=len(filtered_candidates),
            selected_count=len(selected_candidates),
            video_concurrency=video_concurrency,
            success_count=len(scored_videos),
            failure_count=len(failures),
            subtitle_count=subtitle_count,
            top_videos=top_videos,
            raw_archive_dir=(
                str(raw_archive.root_dir) if raw_archive.root_dir is not None else None
            ),
        )

    def _resolve_keyword_search_context(
        self,
        task: CrawlTask,
        *,
        crawl_mode: str,
        task_options: dict[str, Any],
        expected_dispatch_generation: int | None,
    ) -> tuple[dict[str, Any] | None, list[str]]:
        if crawl_mode != "keyword":
            search_keywords_used: list[str] = []
            task.extra_params = self._merge_task_crawl_payload(
                task.extra_params,
                {
                    "crawl_stats": {
                        "search_keyword_count": 0,
                        "expanded_keyword_count": 0,
                        "search_keywords_used": search_keywords_used,
                    }
                },
            )
            self.session.commit()
            return None, search_keywords_used

        source_keyword = str(task.keyword or "").strip()
        enabled = bool(task_options.get("enable_keyword_synonym_expansion", False))
        requested_synonym_count = self._coerce_optional_int(
            task_options.get("keyword_synonym_count")
        )
        existing_payload = self._normalize_keyword_expansion_payload(
            (
                task.extra_params.get("keyword_expansion")
                if isinstance(task.extra_params, dict)
                else None
            ),
            source_keyword=source_keyword,
            enabled=enabled,
            requested_synonym_count=requested_synonym_count,
        )

        should_run_expansion = enabled and existing_payload.get("status") == "pending"
        keyword_expansion = existing_payload
        if should_run_expansion:
            create_task_log(
                self.session,
                task=task,
                stage=TaskStage.SEARCH,
                message="Starting keyword expansion.",
                payload={
                    "source_keyword": source_keyword,
                    "requested_synonym_count": requested_synonym_count,
                },
            )
            self.session.commit()
            task = assert_task_execution_allowed(
                self.session,
                task.id,
                expected_dispatch_generation=expected_dispatch_generation,
            )
            if self.keyword_expansion_service is None:
                self.keyword_expansion_service = KeywordExpansionService(
                    self.session,
                )
            keyword_expansion = self.keyword_expansion_service.expand_keyword(
                source_keyword=source_keyword,
                requested_synonym_count=requested_synonym_count,
                enabled=True,
            )
            keyword_expansion = self._normalize_keyword_expansion_payload(
                keyword_expansion,
                source_keyword=source_keyword,
                enabled=True,
                requested_synonym_count=requested_synonym_count,
            )
            task.extra_params = self._merge_task_crawl_payload(
                task.extra_params,
                {"keyword_expansion": keyword_expansion},
            )
            self.session.commit()

            if keyword_expansion["status"] == "success":
                create_task_log(
                    self.session,
                    task=task,
                    stage=TaskStage.SEARCH,
                    message="Keyword expansion succeeded.",
                    payload={
                        "source_keyword": source_keyword,
                        "generated_synonyms": keyword_expansion["generated_synonyms"],
                        "expanded_keywords": keyword_expansion["expanded_keywords"],
                        "model_name": keyword_expansion.get("model_name"),
                    },
                )
            else:
                create_task_log(
                    self.session,
                    task=task,
                    level=LogLevel.WARNING,
                    stage=TaskStage.SEARCH,
                    message="Keyword expansion failed, fallback to source keyword.",
                    payload={
                        "source_keyword": source_keyword,
                        "status": keyword_expansion["status"],
                        "error_message": keyword_expansion.get("error_message"),
                        "expanded_keywords": keyword_expansion["expanded_keywords"],
                        "model_name": keyword_expansion.get("model_name"),
                    },
                )
            self.session.commit()

        search_keywords_used = self._normalize_search_keywords(
            (
                keyword_expansion.get("expanded_keywords")
                if isinstance(keyword_expansion, dict)
                else None
            ),
            source_keyword=source_keyword,
        )
        if not search_keywords_used:
            search_keywords_used = [source_keyword] if source_keyword else []

        task.extra_params = self._merge_task_crawl_payload(
            task.extra_params,
            {
                "keyword_expansion": keyword_expansion,
                "crawl_stats": {
                    "search_keyword_count": len(search_keywords_used),
                    "expanded_keyword_count": max(len(search_keywords_used) - 1, 0),
                    "search_keywords_used": search_keywords_used,
                },
            },
        )
        self.session.commit()
        return keyword_expansion, search_keywords_used

    def _collect_keyword_candidates(
        self,
        task: CrawlTask,
        *,
        search_keywords_used: list[str],
        search_scope: str,
        partition_tid: int | None,
        expected_dispatch_generation: int | None,
    ) -> list:
        all_candidates: list[Any] = []
        total_keywords = len(search_keywords_used)
        search_kwargs = {
            "max_pages": task.max_pages,
            "limit": task.requested_video_limit,
        }
        if search_scope == "partition" and partition_tid is not None:
            search_kwargs["tids"] = partition_tid

        for index, search_keyword in enumerate(search_keywords_used, start=1):
            task = assert_task_execution_allowed(
                self.session,
                task.id,
                expected_dispatch_generation=expected_dispatch_generation,
            )
            create_task_log(
                self.session,
                task=task,
                stage=TaskStage.SEARCH,
                message="Starting keyword search for expansion item.",
                payload={
                    "search_keyword": search_keyword,
                    "search_keyword_index": index,
                    "search_keyword_count": total_keywords,
                    "search_scope": search_scope,
                    "partition_tid": partition_tid,
                },
            )
            self.session.commit()
            all_candidates.extend(
                self.search_spider.search_keyword(
                    search_keyword,
                    **search_kwargs,
                )
            )

        merged_candidates = dedupe_search_candidates(
            all_candidates,
            source_keyword=task.keyword,
        )
        create_task_log(
            self.session,
            task=task,
            stage=TaskStage.SEARCH,
            message="Finished multi-keyword search merge.",
            payload={
                "search_keyword_count": total_keywords,
                "search_keywords_used": search_keywords_used,
                "raw_candidate_count": len(all_candidates),
                "merged_candidate_count": len(merged_candidates),
            },
        )
        self.session.commit()
        return all_candidates

    @staticmethod
    def _serialize_scored_video(item: ScoredVideo) -> dict[str, Any]:
        detail = item.bundle.detail
        subtitle = item.bundle.subtitle
        candidate = item.bundle.candidate
        return {
            "bvid": detail.bvid,
            "title": detail.title,
            "author_name": detail.author_name,
            "url": detail.url,
            "published_at": (
                detail.published_at.isoformat()
                if detail.published_at is not None
                else None
            ),
            "duration_seconds": detail.duration_seconds,
            "description": detail.description[:500],
            "tags": detail.tags[:10],
            "metrics": {
                "view_count": detail.metrics.view_count,
                "like_count": detail.metrics.like_count,
                "coin_count": detail.metrics.coin_count,
                "favorite_count": detail.metrics.favorite_count,
                "share_count": detail.metrics.share_count,
                "reply_count": detail.metrics.reply_count,
                "danmaku_count": detail.metrics.danmaku_count,
            },
            "subtitle": (
                {
                    "language_code": subtitle.language_code,
                    "language_name": subtitle.language_name,
                    "segment_count": len(subtitle.segments),
                    "combined_text_preview": subtitle.combined_text[:500],
                }
                if subtitle is not None
                else None
            ),
            "search_rank": candidate.search_rank,
            "matched_keywords": list(candidate.matched_keywords or []),
            "primary_matched_keyword": candidate.primary_matched_keyword,
            "keyword_match_count": candidate.keyword_match_count,
            "keyword_hit_title": item.keyword_hit_title,
            "keyword_hit_description": item.keyword_hit_description,
            "keyword_hit_tags": item.keyword_hit_tags,
            "relevance_score": item.relevance_score,
            "heat_score": item.heat_score,
            "composite_score": item.composite_score,
        }

    def _crawl_candidate(
        self,
        task: CrawlTask,
        candidate,
        scoring_weights: dict[str, Any],
    ) -> ScoredVideo:
        detail = self.detail_spider.fetch_video_detail(candidate.bvid)
        subtitle = self.subtitle_spider.fetch_best_subtitle(
            detail.bvid,
            detail.primary_cid,
        )
        bundle = CrawledVideoBundle(
            candidate=candidate,
            detail=detail,
            subtitle=subtitle,
        )
        return self.score_service.score_video(
            self._resolve_scoring_keyword(task),
            bundle,
            scoring_weights=scoring_weights,
        )

    def _crawl_candidate_http_only(
        self,
        task: CrawlTask,
        candidate,
        scoring_weights: dict[str, Any],
    ) -> ScoredVideo:
        detail_spider = BilibiliDetailSpider(
            self.http_client,
            browser_client=None,
            raw_archive=self.raw_archive,
        )
        subtitle_spider = BilibiliSubtitleSpider(
            self.http_client,
            browser_client=None,
            raw_archive=self.raw_archive,
        )
        detail = detail_spider.fetch_video_detail(candidate.bvid)
        subtitle = subtitle_spider.fetch_best_subtitle(
            detail.bvid,
            detail.primary_cid,
        )
        bundle = CrawledVideoBundle(
            candidate=candidate,
            detail=detail,
            subtitle=subtitle,
        )
        return self.score_service.score_video(
            self._resolve_scoring_keyword(task),
            bundle,
            scoring_weights=scoring_weights,
        )

    @staticmethod
    def _resolve_scoring_keyword(task: CrawlTask) -> str:
        extra_params = task.extra_params if isinstance(task.extra_params, dict) else {}
        task_options = extra_params.get("task_options")
        if not isinstance(task_options, dict):
            return task.keyword
        return (
            ""
            if str(task_options.get("crawl_mode") or "keyword") == "hot"
            else task.keyword
        )

    @staticmethod
    def _merge_task_crawl_payload(
        extra_params: dict[str, Any] | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        merged = dict(extra_params or {})
        merged.update(payload)
        return merged

    @staticmethod
    def _filter_candidates_by_publish_time(
        candidates: list,
        *,
        published_within_days: int | None,
    ) -> list:
        if not published_within_days:
            return candidates

        cutoff = utc_now() - timedelta(days=published_within_days)
        filtered_candidates = []
        for candidate in candidates:
            published_at = getattr(candidate, "published_at", None)
            if published_at is None:
                continue
            normalized_published_at = (
                published_at.replace(tzinfo=cutoff.tzinfo)
                if published_at.tzinfo is None
                else published_at
            )
            if normalized_published_at >= cutoff:
                filtered_candidates.append(candidate)
        return filtered_candidates

    def _update_crawl_progress(
        self,
        task: CrawlTask,
        *,
        candidate_count: int,
        selected_count: int,
        video_concurrency: int,
        detail_processed_count: int,
        detail_success_count: int,
        detail_failure_count: int,
        current_phase: str,
        current_bvid: str | None = None,
    ) -> None:
        task.processed_videos = detail_processed_count
        task.extra_params = self._merge_task_crawl_payload(
            task.extra_params,
            {
                "crawl_progress": {
                    "candidate_count": candidate_count,
                    "selected_count": selected_count,
                    "video_concurrency": video_concurrency,
                    "detail_processed_count": detail_processed_count,
                    "detail_success_count": detail_success_count,
                    "detail_failure_count": detail_failure_count,
                    "current_phase": current_phase,
                    "current_bvid": current_bvid,
                }
            },
        )
        self.session.commit()

    @staticmethod
    def _normalize_keyword_expansion_payload(
        payload: Any,
        *,
        source_keyword: str,
        enabled: bool,
        requested_synonym_count: int | None,
    ) -> dict[str, Any]:
        normalized_source_keyword = str(source_keyword or "").strip()
        normalized_status = (
            str(payload.get("status") if isinstance(payload, dict) else "")
            .strip()
            .lower()
        )
        if normalized_status not in {
            "skipped",
            "pending",
            "success",
            "fallback",
            "failed",
        }:
            normalized_status = "pending" if enabled else "skipped"

        if not enabled:
            normalized_status = "skipped"

        generated_synonyms = (
            CrawlPipelineService._normalize_generated_synonyms(
                (
                    payload.get("generated_synonyms")
                    if isinstance(payload, dict)
                    else None
                ),
                source_keyword=normalized_source_keyword,
            )
            if normalized_status == "success"
            else []
        )
        if normalized_status == "success" and not generated_synonyms:
            normalized_status = "pending" if enabled else "skipped"

        expanded_keywords = (
            [normalized_source_keyword, *generated_synonyms]
            if generated_synonyms
            else [normalized_source_keyword]
        )
        return {
            "source_keyword": normalized_source_keyword,
            "enabled": enabled,
            "requested_synonym_count": requested_synonym_count if enabled else None,
            "generated_synonyms": generated_synonyms,
            "expanded_keywords": expanded_keywords,
            "status": normalized_status,
            "model_name": (
                str(payload.get("model_name")).strip()
                if isinstance(payload, dict)
                and payload.get("model_name")
                and normalized_status in {"success", "fallback", "failed"}
                else None
            ),
            "error_message": (
                str(payload.get("error_message")).strip()
                if isinstance(payload, dict)
                and payload.get("error_message")
                and normalized_status in {"success", "fallback", "failed"}
                else None
            ),
            "generated_at": (
                str(payload.get("generated_at")).strip()
                if isinstance(payload, dict)
                and payload.get("generated_at")
                and normalized_status in {"success", "fallback", "failed"}
                else None
            ),
        }

    @staticmethod
    def _normalize_generated_synonyms(
        value: Any,
        *,
        source_keyword: str,
    ) -> list[str]:
        normalized_values: list[str] = []
        seen: set[str] = set()
        normalized_source_keyword = str(source_keyword or "").strip()
        for item in value if isinstance(value, list) else []:
            normalized_item = str(item or "").strip()
            if not normalized_item:
                continue
            if normalized_item == normalized_source_keyword:
                continue
            if normalized_item in seen:
                continue
            normalized_values.append(normalized_item)
            seen.add(normalized_item)
        return normalized_values

    @staticmethod
    def _normalize_search_keywords(
        value: Any,
        *,
        source_keyword: str,
    ) -> list[str]:
        normalized_source_keyword = str(source_keyword or "").strip()
        normalized_values: list[str] = []
        seen: set[str] = set()
        if normalized_source_keyword:
            normalized_values.append(normalized_source_keyword)
            seen.add(normalized_source_keyword)
        for item in value if isinstance(value, list) else []:
            normalized_item = str(item or "").strip()
            if not normalized_item or normalized_item in seen:
                continue
            normalized_values.append(normalized_item)
            seen.add(normalized_item)
        return normalized_values

    @staticmethod
    def _coerce_optional_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
