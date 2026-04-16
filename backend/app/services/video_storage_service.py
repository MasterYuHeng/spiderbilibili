from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.crawler.models import ScoredVideo
from app.models.analysis import AiSummary, TopicCluster, TopicVideoRelation
from app.models.base import utc_now
from app.models.task import CrawlTask, TaskVideo
from app.models.video import (
    Video,
    VideoMetricSnapshot,
    VideoSubtitleSegment,
    VideoTextContent,
)
from app.services.text_clean_service import TextCleanService


class VideoStorageService:
    def __init__(
        self,
        session: Session,
        *,
        text_clean_service: TextCleanService | None = None,
    ) -> None:
        self.session = session
        self.text_clean_service = text_clean_service or TextCleanService()

    def reset_task_outputs(self, task: CrawlTask) -> None:
        text_content_ids = self.session.scalars(
            select(VideoTextContent.id).where(VideoTextContent.task_id == task.id)
        ).all()
        if text_content_ids:
            self.session.execute(
                delete(VideoSubtitleSegment).where(
                    VideoSubtitleSegment.text_content_id.in_(text_content_ids)
                )
            )

        self.session.execute(
            delete(TopicVideoRelation).where(TopicVideoRelation.task_id == task.id)
        )
        self.session.execute(
            delete(TopicCluster).where(TopicCluster.task_id == task.id)
        )
        self.session.execute(delete(AiSummary).where(AiSummary.task_id == task.id))
        self.session.execute(
            delete(VideoTextContent).where(VideoTextContent.task_id == task.id)
        )
        self.session.execute(
            delete(VideoMetricSnapshot).where(VideoMetricSnapshot.task_id == task.id)
        )
        self.session.execute(delete(TaskVideo).where(TaskVideo.task_id == task.id))
        self.session.flush()

    def persist_scored_video(self, task: CrawlTask, scored_video: ScoredVideo) -> Video:
        video = self._upsert_video(scored_video)
        self._upsert_task_video(task, video, scored_video)
        self._upsert_metric_snapshot(task, video, scored_video)
        self._upsert_text_content(task, video, scored_video)
        self.session.flush()
        return video

    def _upsert_video(self, scored_video: ScoredVideo) -> Video:
        detail = scored_video.bundle.detail
        video = self.session.scalar(select(Video).where(Video.bvid == detail.bvid))
        if video is None:
            video = Video(bvid=detail.bvid)
            self.session.add(video)

        video.aid = detail.aid
        video.title = detail.title
        video.url = detail.url
        video.author_name = detail.author_name
        video.author_mid = detail.author_mid
        video.cover_url = detail.cover_url
        video.description = detail.description
        video.tags = detail.tags
        video.published_at = detail.published_at
        video.duration_seconds = detail.duration_seconds
        if video.id is None:
            self.session.flush()
        return video

    def _upsert_task_video(
        self,
        task: CrawlTask,
        video: Video,
        scored_video: ScoredVideo,
    ) -> TaskVideo:
        task_video = self.session.scalar(
            select(TaskVideo).where(
                TaskVideo.task_id == task.id,
                TaskVideo.video_id == video.id,
            )
        )
        if task_video is None:
            task_video = TaskVideo(task_id=task.id, video_id=video.id)
            self.session.add(task_video)

        candidate = scored_video.bundle.candidate
        matched_keywords, primary_matched_keyword = self._build_keyword_match_fields(
            candidate
        )
        task_video.search_rank = candidate.search_rank
        task_video.matched_keywords = matched_keywords
        task_video.primary_matched_keyword = primary_matched_keyword
        task_video.keyword_match_count = len(matched_keywords)
        task_video.keyword_hit_title = scored_video.keyword_hit_title
        task_video.keyword_hit_description = scored_video.keyword_hit_description
        task_video.keyword_hit_tags = scored_video.keyword_hit_tags
        task_video.relevance_score = Decimal(str(scored_video.relevance_score))
        task_video.heat_score = Decimal(str(scored_video.heat_score))
        task_video.composite_score = Decimal(str(scored_video.composite_score))
        task_video.is_selected = scored_video.is_selected
        return task_video

    def _upsert_metric_snapshot(
        self,
        task: CrawlTask,
        video: Video,
        scored_video: ScoredVideo,
    ) -> VideoMetricSnapshot:
        snapshot = self.session.scalar(
            select(VideoMetricSnapshot)
            .where(
                VideoMetricSnapshot.task_id == task.id,
                VideoMetricSnapshot.video_id == video.id,
            )
            .order_by(VideoMetricSnapshot.created_at.desc())
        )
        if snapshot is None:
            snapshot = VideoMetricSnapshot(task_id=task.id, video_id=video.id)
            self.session.add(snapshot)

        metrics = scored_video.bundle.detail.metrics
        snapshot.view_count = metrics.view_count
        snapshot.like_count = metrics.like_count
        snapshot.coin_count = metrics.coin_count
        snapshot.favorite_count = metrics.favorite_count
        snapshot.share_count = metrics.share_count
        snapshot.reply_count = metrics.reply_count
        snapshot.danmaku_count = metrics.danmaku_count
        snapshot.metrics_payload = self._build_metrics_payload(scored_video)
        snapshot.captured_at = utc_now()
        return snapshot

    def _upsert_text_content(
        self,
        task: CrawlTask,
        video: Video,
        scored_video: ScoredVideo,
    ) -> VideoTextContent:
        cleaned_text = self.text_clean_service.build_cleaned_text(
            title=scored_video.bundle.detail.title,
            description=scored_video.bundle.detail.description,
            search_summary=scored_video.bundle.candidate.description,
            subtitle=scored_video.bundle.subtitle,
        )
        text_content = self.session.scalar(
            select(VideoTextContent).where(
                VideoTextContent.task_id == task.id,
                VideoTextContent.video_id == video.id,
            )
        )
        if text_content is None:
            text_content = VideoTextContent(task_id=task.id, video_id=video.id)
            self.session.add(text_content)

        text_content.has_description = cleaned_text.has_description
        text_content.has_subtitle = cleaned_text.has_subtitle
        text_content.description_text = cleaned_text.description_text
        text_content.subtitle_text = cleaned_text.subtitle_text
        text_content.combined_text = cleaned_text.combined_text
        text_content.combined_text_hash = cleaned_text.combined_text_hash
        text_content.language_code = cleaned_text.language_code

        text_content.subtitle_segments.clear()
        for segment in cleaned_text.subtitle_segments:
            text_content.subtitle_segments.append(
                VideoSubtitleSegment(
                    segment_index=segment.segment_index,
                    start_seconds=segment.start_seconds,
                    end_seconds=segment.end_seconds,
                    content=segment.content,
                )
            )

        return text_content

    @staticmethod
    def _build_metrics_payload(scored_video: ScoredVideo) -> dict[str, Any]:
        candidate = scored_video.bundle.candidate
        metrics = scored_video.bundle.detail.metrics
        return {
            "search_metrics": {
                "play_count": candidate.play_count,
                "like_count": candidate.like_count,
                "favorite_count": candidate.favorite_count,
                "comment_count": candidate.comment_count,
                "danmaku_count": candidate.danmaku_count,
            },
            "detail_metrics": {
                "view_count": metrics.view_count,
                "like_count": metrics.like_count,
                "coin_count": metrics.coin_count,
                "favorite_count": metrics.favorite_count,
                "share_count": metrics.share_count,
                "reply_count": metrics.reply_count,
                "danmaku_count": metrics.danmaku_count,
            },
            "score_snapshot": {
                "relevance_score": scored_video.relevance_score,
                "heat_score": scored_video.heat_score,
                "composite_score": scored_video.composite_score,
            },
        }

    @staticmethod
    def _build_keyword_match_fields(candidate) -> tuple[list[str], str | None]:
        matched_keywords: list[str] = []
        seen: set[str] = set()
        for item in list(getattr(candidate, "matched_keywords", []) or []):
            normalized_item = str(item or "").strip()
            if not normalized_item or normalized_item in seen:
                continue
            matched_keywords.append(normalized_item)
            seen.add(normalized_item)

        primary_matched_keyword = (
            str(getattr(candidate, "primary_matched_keyword", None) or "").strip()
            or None
        )
        if primary_matched_keyword and primary_matched_keyword not in seen:
            matched_keywords.append(primary_matched_keyword)
            seen.add(primary_matched_keyword)

        if primary_matched_keyword is None and matched_keywords:
            primary_matched_keyword = matched_keywords[0]

        return matched_keywords, primary_matched_keyword
