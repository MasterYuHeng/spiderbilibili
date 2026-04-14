from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from math import ceil
from typing import Any

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import Float, Select, case, cast, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.models.analysis import AiSummary, TopicCluster, TopicVideoRelation
from app.models.base import utc_now
from app.models.task import TaskVideo
from app.models.video import Video, VideoMetricSnapshot, VideoTextContent
from app.schemas.task import (
    TaskAnalysisAdvancedRead,
    TaskAnalysisPayload,
    TaskAnalysisSummaryRead,
    TaskTopicListPayload,
    TaskTopicRead,
    TaskVideoAiSummaryRead,
    TaskVideoListPayload,
    TaskVideoMetricsRead,
    TaskVideoResultRead,
    TaskVideoTextRead,
)
from app.services.statistics_service import StatisticsService, TaskStatisticsResult
from app.services.task_service import get_task_or_raise, resolve_page_size
from app.services.task_state_machine import is_terminal_status


@dataclass(slots=True)
class TaskVideoRow:
    task_video: TaskVideo
    video: Video
    metric_snapshot: VideoMetricSnapshot | None
    text_content: VideoTextContent | None
    ai_summary: AiSummary | None


@dataclass(slots=True)
class TaskVideoMetricFilters:
    min_view_count: int | None = None
    max_view_count: int | None = None
    min_like_count: int | None = None
    max_like_count: int | None = None
    min_coin_count: int | None = None
    max_coin_count: int | None = None
    min_favorite_count: int | None = None
    max_favorite_count: int | None = None
    min_share_count: int | None = None
    max_share_count: int | None = None
    min_reply_count: int | None = None
    max_reply_count: int | None = None
    min_danmaku_count: int | None = None
    max_danmaku_count: int | None = None
    min_relevance_score: float | None = None
    max_relevance_score: float | None = None
    min_heat_score: float | None = None
    max_heat_score: float | None = None
    min_composite_score: float | None = None
    max_composite_score: float | None = None
    min_like_view_ratio: float | None = None
    max_like_view_ratio: float | None = None


@dataclass(slots=True)
class CachedTaskAnalysisSnapshot:
    statistics: TaskStatisticsResult
    generated_at: datetime | None = None
    top_videos: list[TaskVideoResultRead] | None = None
    has_ai_summaries: bool | None = None


def list_task_videos(
    session: Session,
    task_id: str,
    *,
    page: int,
    page_size: int | None,
    sort_by: str = "composite_score",
    sort_order: str = "desc",
    topic: str | None = None,
    filters: TaskVideoMetricFilters | None = None,
) -> TaskVideoListPayload:
    task = get_task_or_raise(session, task_id)
    resolved_page_size = resolve_page_size(page_size, default_page_size=20)

    normalized_topic = _normalize_topic_filter(topic)
    base_statement = _build_task_video_statement(
        task.id,
        sort_by=sort_by,
        sort_order=sort_order,
        topic=normalized_topic,
        filters=filters,
    )
    total = int(
        session.scalar(
            select(func.count())
            .select_from(
                _build_task_video_count_subquery(
                    task.id,
                    topic=normalized_topic,
                    filters=filters,
                )
            )
        )
        or 0
    )
    total_pages = ceil(total / resolved_page_size) if total else 0

    paged_statement = (
        base_statement.offset((page - 1) * resolved_page_size).limit(resolved_page_size)
    )
    rows = _fetch_task_video_rows(session, paged_statement)

    return TaskVideoListPayload(
        task_id=task.id,
        items=[_build_task_video_read(row) for row in rows],
        page=page,
        page_size=resolved_page_size,
        total=total,
        total_pages=total_pages,
    )


def get_task_video_results(
    session: Session,
    task_id: str,
    *,
    sort_by: str = "composite_score",
    sort_order: str = "desc",
    topic: str | None = None,
    filters: TaskVideoMetricFilters | None = None,
) -> list[TaskVideoResultRead]:
    task = get_task_or_raise(session, task_id)
    normalized_topic = _normalize_topic_filter(topic)
    statement = _build_task_video_statement(
        task.id,
        sort_by=sort_by,
        sort_order=sort_order,
        topic=normalized_topic,
        filters=filters,
    )
    rows = _fetch_task_video_rows(session, statement)
    return [_build_task_video_read(row) for row in rows]


def get_task_video_rows(
    session: Session,
    task_id: str,
    *,
    sort_by: str = "composite_score",
    sort_order: str = "desc",
    topic: str | None = None,
    filters: TaskVideoMetricFilters | None = None,
) -> list[TaskVideoRow]:
    task = get_task_or_raise(session, task_id)
    normalized_topic = _normalize_topic_filter(topic)
    statement = _build_task_video_statement(
        task.id,
        sort_by=sort_by,
        sort_order=sort_order,
        topic=normalized_topic,
        filters=filters,
    )
    return _fetch_task_video_rows(session, statement)


def get_task_topics(session: Session, task_id: str) -> TaskTopicListPayload:
    task = get_task_or_raise(session, task_id)
    cached_snapshot = _get_cached_analysis_snapshot(task)
    statistics = (
        cached_snapshot.statistics
        if cached_snapshot is not None
        else StatisticsService(
            session,
            include_external_author_fetch=False,
        ).calculate_task_statistics(task.id)
    )

    return TaskTopicListPayload(
        task_id=task.id,
        items=statistics.topics,
    )


def get_task_analysis(session: Session, task_id: str) -> TaskAnalysisPayload:
    task = get_task_or_raise(session, task_id)
    cached_snapshot = _get_cached_analysis_snapshot(task)
    statistics = (
        cached_snapshot.statistics
        if cached_snapshot is not None
        else StatisticsService(
            session,
            include_external_author_fetch=False,
        ).calculate_task_statistics(task.id)
    )

    if cached_snapshot is not None and cached_snapshot.top_videos is not None:
        top_videos = cached_snapshot.top_videos
    else:
        top_video_rows = _fetch_task_video_rows(
            session,
            _build_task_video_statement(task.id).limit(10),
        )
        top_videos = [_build_task_video_read(row) for row in top_video_rows]

    has_ai_summaries = (
        cached_snapshot.has_ai_summaries
        if cached_snapshot is not None
        and cached_snapshot.has_ai_summaries is not None
        else _task_has_ai_summaries(session, task.id)
    )

    return TaskAnalysisPayload(
        task_id=task.id,
        status=task.status.value,
        generated_at=(
            cached_snapshot.generated_at
            if cached_snapshot is not None and cached_snapshot.generated_at is not None
            else utc_now()
        ),
        summary=statistics.summary,
        topics=statistics.topics,
        top_videos=top_videos,
        advanced=statistics.advanced,
        has_ai_summaries=has_ai_summaries,
        has_topics=bool(statistics.topics),
    )


def _build_task_video_statement(
    task_id: str,
    *,
    sort_by: str = "composite_score",
    sort_order: str = "desc",
    topic: str | None = None,
    filters: TaskVideoMetricFilters | None = None,
) -> Select[tuple]:
    latest_snapshot, latest_snapshot_ids = _build_latest_snapshot_aliases()

    statement = (
        select(TaskVideo, Video, latest_snapshot, VideoTextContent, AiSummary)
        .join(Video, Video.id == TaskVideo.video_id)
        .outerjoin(
            latest_snapshot_ids,
            (latest_snapshot_ids.c.task_id == TaskVideo.task_id)
            & (latest_snapshot_ids.c.video_id == TaskVideo.video_id),
        )
        .outerjoin(
            latest_snapshot,
            latest_snapshot.id == latest_snapshot_ids.c.snapshot_id,
        )
        .outerjoin(
            VideoTextContent,
            (VideoTextContent.task_id == TaskVideo.task_id)
            & (VideoTextContent.video_id == TaskVideo.video_id),
        )
        .outerjoin(
            AiSummary,
            (AiSummary.task_id == TaskVideo.task_id)
            & (AiSummary.video_id == TaskVideo.video_id),
        )
        .where(TaskVideo.task_id == task_id)
    )

    if topic is not None:
        statement = (
            statement.join(
                TopicVideoRelation,
                (TopicVideoRelation.task_id == TaskVideo.task_id)
                & (TopicVideoRelation.video_id == TaskVideo.video_id),
            )
            .join(
                TopicCluster,
                TopicCluster.id == TopicVideoRelation.topic_cluster_id,
            )
            .where(_build_topic_filter_condition(topic))
        )

    statement = _apply_metric_filters(statement, latest_snapshot, filters)
    return statement.order_by(
        *_build_video_sort_expressions(
            sort_by,
            sort_order,
            latest_snapshot=latest_snapshot,
        )
    )


def _build_task_video_count_subquery(
    task_id: str,
    *,
    topic: str | None = None,
    filters: TaskVideoMetricFilters | None = None,
):
    latest_snapshot, latest_snapshot_ids = _build_latest_snapshot_aliases()
    statement = select(TaskVideo.id).where(TaskVideo.task_id == task_id).distinct()
    statement = (
        statement.outerjoin(
            latest_snapshot_ids,
            (latest_snapshot_ids.c.task_id == TaskVideo.task_id)
            & (latest_snapshot_ids.c.video_id == TaskVideo.video_id),
        ).outerjoin(
            latest_snapshot,
            latest_snapshot.id == latest_snapshot_ids.c.snapshot_id,
        )
    )
    if topic is not None:
        statement = (
            statement.join(
                TopicVideoRelation,
                (TopicVideoRelation.task_id == TaskVideo.task_id)
                & (TopicVideoRelation.video_id == TaskVideo.video_id),
            )
            .join(
                TopicCluster,
                TopicCluster.id == TopicVideoRelation.topic_cluster_id,
            )
            .where(_build_topic_filter_condition(topic))
        )
    statement = _apply_metric_filters(statement, latest_snapshot, filters)
    return statement.subquery()


def _build_latest_snapshot_aliases() -> tuple[type[VideoMetricSnapshot], Any]:
    latest_snapshot_ranked = (
        select(
            VideoMetricSnapshot.id.label("snapshot_id"),
            VideoMetricSnapshot.task_id.label("task_id"),
            VideoMetricSnapshot.video_id.label("video_id"),
            func.row_number()
            .over(
                partition_by=(
                    VideoMetricSnapshot.task_id,
                    VideoMetricSnapshot.video_id,
                ),
                order_by=(
                    VideoMetricSnapshot.captured_at.desc(),
                    VideoMetricSnapshot.created_at.desc(),
                    VideoMetricSnapshot.id.desc(),
                ),
            )
            .label("row_number"),
        ).subquery()
    )
    latest_snapshot_ids = (
        select(
            latest_snapshot_ranked.c.snapshot_id,
            latest_snapshot_ranked.c.task_id,
            latest_snapshot_ranked.c.video_id,
        )
        .where(latest_snapshot_ranked.c.row_number == 1)
        .subquery()
    )
    return aliased(VideoMetricSnapshot), latest_snapshot_ids


def _fetch_task_video_rows(
    session: Session,
    statement: Select[tuple],
) -> list[TaskVideoRow]:
    result_rows = session.execute(statement).all()
    return [
        TaskVideoRow(
            task_video=task_video,
            video=video,
            metric_snapshot=metric_snapshot,
            text_content=text_content,
            ai_summary=ai_summary,
        )
        for task_video, video, metric_snapshot, text_content, ai_summary in result_rows
    ]


def _build_task_video_read(row: TaskVideoRow) -> TaskVideoResultRead:
    metrics = row.metric_snapshot
    text_content = row.text_content
    ai_summary = row.ai_summary
    like_view_ratio = _calculate_metric_ratio(metrics, numerator="like_count")
    coin_view_ratio = _calculate_metric_ratio(metrics, numerator="coin_count")
    favorite_view_ratio = _calculate_metric_ratio(
        metrics,
        numerator="favorite_count",
    )
    share_view_ratio = _calculate_metric_ratio(metrics, numerator="share_count")
    reply_view_ratio = _calculate_metric_ratio(metrics, numerator="reply_count")
    danmaku_view_ratio = _calculate_metric_ratio(metrics, numerator="danmaku_count")
    engagement_rate = _calculate_engagement_rate(metrics)

    return TaskVideoResultRead(
        video_id=row.video.id,
        bvid=row.video.bvid,
        aid=row.video.aid,
        title=row.video.title,
        url=row.video.url,
        author_name=row.video.author_name,
        author_mid=row.video.author_mid,
        cover_url=row.video.cover_url,
        description=row.video.description,
        tags=list(row.video.tags or []),
        published_at=row.video.published_at,
        duration_seconds=row.video.duration_seconds,
        search_rank=row.task_video.search_rank,
        matched_keywords=list(row.task_video.matched_keywords or []),
        primary_matched_keyword=row.task_video.primary_matched_keyword,
        keyword_match_count=row.task_video.keyword_match_count,
        keyword_hit_title=row.task_video.keyword_hit_title,
        keyword_hit_description=row.task_video.keyword_hit_description,
        keyword_hit_tags=row.task_video.keyword_hit_tags,
        relevance_score=_to_float(row.task_video.relevance_score) or 0.0,
        heat_score=_to_float(row.task_video.heat_score) or 0.0,
        composite_score=_to_float(row.task_video.composite_score) or 0.0,
        is_selected=row.task_video.is_selected,
        metrics=TaskVideoMetricsRead(
            view_count=metrics.view_count if metrics is not None else 0,
            like_count=metrics.like_count if metrics is not None else 0,
            coin_count=metrics.coin_count if metrics is not None else 0,
            favorite_count=metrics.favorite_count if metrics is not None else 0,
            share_count=metrics.share_count if metrics is not None else 0,
            reply_count=metrics.reply_count if metrics is not None else 0,
            danmaku_count=metrics.danmaku_count if metrics is not None else 0,
            like_view_ratio=like_view_ratio,
            coin_view_ratio=coin_view_ratio,
            favorite_view_ratio=favorite_view_ratio,
            share_view_ratio=share_view_ratio,
            reply_view_ratio=reply_view_ratio,
            danmaku_view_ratio=danmaku_view_ratio,
            engagement_rate=engagement_rate,
            captured_at=metrics.captured_at if metrics is not None else None,
        ),
        text_content=(
            TaskVideoTextRead(
                has_description=text_content.has_description,
                has_subtitle=text_content.has_subtitle,
                language_code=text_content.language_code,
                description_text=text_content.description_text,
                subtitle_text=text_content.subtitle_text,
                combined_text_preview=_build_preview(text_content.combined_text),
            )
            if text_content is not None
            else None
        ),
        ai_summary=(
            TaskVideoAiSummaryRead(
                summary=ai_summary.summary,
                topics=list(ai_summary.topics or []),
                primary_topic=ai_summary.primary_topic,
                tone=ai_summary.tone,
                confidence=_to_float(ai_summary.confidence),
                model_name=ai_summary.model_name,
            )
            if ai_summary is not None
            else None
        ),
    )


def _build_preview(value: str, *, max_length: int = 500) -> str:
    if len(value) <= max_length:
        return value
    return f"{value[:max_length].rstrip()}..."


def _build_video_sort_expressions(
    sort_by: str,
    sort_order: str,
    *,
    latest_snapshot: type[VideoMetricSnapshot],
) -> Sequence[Any]:
    sort_column = {
        "published_at": Video.published_at,
        "view_count": latest_snapshot.view_count,
        "like_count": latest_snapshot.like_count,
        "coin_count": latest_snapshot.coin_count,
        "favorite_count": latest_snapshot.favorite_count,
        "share_count": latest_snapshot.share_count,
        "reply_count": latest_snapshot.reply_count,
        "danmaku_count": latest_snapshot.danmaku_count,
        "like_view_ratio": _build_like_view_ratio_expression(latest_snapshot),
        "relevance_score": TaskVideo.relevance_score,
        "heat_score": TaskVideo.heat_score,
        "composite_score": TaskVideo.composite_score,
    }.get(sort_by, TaskVideo.composite_score)

    primary_sort = (
        sort_column.asc().nulls_last()
        if sort_order == "asc"
        else sort_column.desc().nulls_last()
    )

    if sort_by in {"published_at", "heat_score"}:
        return (
            primary_sort,
            TaskVideo.composite_score.desc(),
            TaskVideo.search_rank.asc().nulls_last(),
            Video.created_at.desc(),
        )

    return (
        primary_sort,
        TaskVideo.search_rank.asc().nulls_last(),
        Video.created_at.desc(),
    )


def _apply_metric_filters(
    statement: Select[tuple],
    latest_snapshot: type[VideoMetricSnapshot],
    filters: TaskVideoMetricFilters | None,
) -> Select[tuple]:
    if filters is None:
        return statement

    if filters.min_view_count is not None:
        statement = statement.where(
            latest_snapshot.view_count >= filters.min_view_count
        )
    if filters.max_view_count is not None:
        statement = statement.where(
            latest_snapshot.view_count <= filters.max_view_count
        )
    if filters.min_like_count is not None:
        statement = statement.where(
            latest_snapshot.like_count >= filters.min_like_count
        )
    if filters.max_like_count is not None:
        statement = statement.where(
            latest_snapshot.like_count <= filters.max_like_count
        )
    if filters.min_coin_count is not None:
        statement = statement.where(
            latest_snapshot.coin_count >= filters.min_coin_count
        )
    if filters.max_coin_count is not None:
        statement = statement.where(
            latest_snapshot.coin_count <= filters.max_coin_count
        )
    if filters.min_favorite_count is not None:
        statement = statement.where(
            latest_snapshot.favorite_count >= filters.min_favorite_count
        )
    if filters.max_favorite_count is not None:
        statement = statement.where(
            latest_snapshot.favorite_count <= filters.max_favorite_count
        )
    if filters.min_share_count is not None:
        statement = statement.where(
            latest_snapshot.share_count >= filters.min_share_count
        )
    if filters.max_share_count is not None:
        statement = statement.where(
            latest_snapshot.share_count <= filters.max_share_count
        )
    if filters.min_reply_count is not None:
        statement = statement.where(
            latest_snapshot.reply_count >= filters.min_reply_count
        )
    if filters.max_reply_count is not None:
        statement = statement.where(
            latest_snapshot.reply_count <= filters.max_reply_count
        )
    if filters.min_danmaku_count is not None:
        statement = statement.where(
            latest_snapshot.danmaku_count >= filters.min_danmaku_count
        )
    if filters.max_danmaku_count is not None:
        statement = statement.where(
            latest_snapshot.danmaku_count <= filters.max_danmaku_count
        )
    if filters.min_relevance_score is not None:
        statement = statement.where(
            TaskVideo.relevance_score >= filters.min_relevance_score
        )
    if filters.max_relevance_score is not None:
        statement = statement.where(
            TaskVideo.relevance_score <= filters.max_relevance_score
        )
    if filters.min_heat_score is not None:
        statement = statement.where(TaskVideo.heat_score >= filters.min_heat_score)
    if filters.max_heat_score is not None:
        statement = statement.where(TaskVideo.heat_score <= filters.max_heat_score)
    if filters.min_composite_score is not None:
        statement = statement.where(
            TaskVideo.composite_score >= filters.min_composite_score
        )
    if filters.max_composite_score is not None:
        statement = statement.where(
            TaskVideo.composite_score <= filters.max_composite_score
        )
    if filters.min_like_view_ratio is not None:
        statement = statement.where(
            _build_like_view_ratio_expression(latest_snapshot)
            >= filters.min_like_view_ratio
        )
    if filters.max_like_view_ratio is not None:
        statement = statement.where(
            _build_like_view_ratio_expression(latest_snapshot)
            <= filters.max_like_view_ratio
        )
    return statement


def _normalize_topic_filter(topic: str | None) -> str | None:
    if topic is None:
        return None
    normalized = topic.strip().casefold()
    return normalized or None


def _build_topic_filter_condition(topic: str):
    return or_(
        func.lower(TopicCluster.normalized_name) == topic,
        func.lower(TopicCluster.name) == topic,
    )


def _to_float(value: Decimal | float | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _build_like_view_ratio_expression(
    latest_snapshot: type[VideoMetricSnapshot],
):
    return case(
        (
            latest_snapshot.view_count > 0,
            cast(latest_snapshot.like_count, Float)
            / cast(latest_snapshot.view_count, Float),
        ),
        else_=None,
    )


def _calculate_like_view_ratio(
    metrics: VideoMetricSnapshot | None,
) -> float | None:
    return _calculate_metric_ratio(metrics, numerator="like_count")


def _calculate_metric_ratio(
    metrics: VideoMetricSnapshot | None,
    *,
    numerator: str,
) -> float | None:
    if metrics is None or metrics.view_count <= 0:
        return None
    numerator_value = getattr(metrics, numerator, 0) or 0
    return numerator_value / metrics.view_count


def _calculate_engagement_rate(
    metrics: VideoMetricSnapshot | None,
) -> float | None:
    if metrics is None or metrics.view_count <= 0:
        return None
    total_interactions = (
        metrics.like_count
        + metrics.coin_count
        + metrics.favorite_count
        + metrics.share_count
        + metrics.reply_count
        + metrics.danmaku_count
    )
    return total_interactions / metrics.view_count


def _get_cached_analysis_snapshot(
    task,
) -> CachedTaskAnalysisSnapshot | None:
    if not is_terminal_status(task.status):
        return None
    return load_cached_analysis_snapshot(task.extra_params)


def load_cached_analysis_snapshot(
    extra_params: dict | None,
) -> CachedTaskAnalysisSnapshot | None:
    if not isinstance(extra_params, dict):
        return None

    snapshot = extra_params.get("analysis_snapshot")
    if not isinstance(snapshot, dict):
        return None

    if _is_legacy_analysis_snapshot(snapshot):
        return None

    try:
        summary = TaskAnalysisSummaryRead.model_validate(snapshot.get("summary") or {})
        topics = [
            TaskTopicRead.model_validate(item)
            for item in snapshot.get("topics") or []
        ]
        advanced = TaskAnalysisAdvancedRead.model_validate(
            snapshot.get("advanced") or {}
        )
        generated_at_raw = snapshot.get("generated_at")
        generated_at = (
            datetime.fromisoformat(generated_at_raw)
            if isinstance(generated_at_raw, str)
            else None
        )
        top_videos = (
            [
                TaskVideoResultRead.model_validate(item)
                for item in snapshot.get("top_videos") or []
            ]
            if "top_videos" in snapshot
            else None
        )
        has_ai_summaries = (
            bool(snapshot.get("has_ai_summaries"))
            if "has_ai_summaries" in snapshot
            else None
        )
    except PydanticValidationError:
        return None
    except ValueError:
        return None

    return CachedTaskAnalysisSnapshot(
        statistics=TaskStatisticsResult(
            summary=summary,
            topics=topics,
            advanced=advanced,
        ),
        generated_at=generated_at,
        top_videos=top_videos,
        has_ai_summaries=has_ai_summaries,
    )


def _is_legacy_analysis_snapshot(snapshot: dict) -> bool:
    advanced = snapshot.get("advanced")
    if not isinstance(advanced, dict):
        return True

    required_keys = {
        "momentum_topics",
        "explosive_videos",
        "depth_topics",
        "deep_videos",
        "community_topics",
        "community_videos",
        "topic_evolution",
        "latest_hot_topic",
        "topic_insights",
        "video_insights",
        "metric_definitions",
        "metric_weight_configs",
        "recommendations",
        "data_notes",
    }
    return not required_keys.issubset(set(advanced.keys()))


def _task_has_ai_summaries(session: Session, task_id: str) -> bool:
    return (
        session.scalar(
            select(AiSummary.id).where(AiSummary.task_id == task_id).limit(1)
        )
        is not None
    )
