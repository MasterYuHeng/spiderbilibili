from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import combinations
from math import sqrt

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.models.analysis import AiSummary, TopicCluster, TopicVideoRelation
from app.models.base import utc_now
from app.models.enums import TaskStage
from app.models.task import CrawlTask, TaskVideo
from app.models.video import Video, VideoMetricSnapshot
from app.schemas.task import (
    TaskAnalysisAdvancedRead,
    TaskAnalysisCooccurrenceRead,
    TaskAnalysisCorrelationRead,
    TaskAnalysisLatestHotTopicRead,
    TaskAnalysisMetricDefinitionRead,
    TaskAnalysisRecommendationRead,
    TaskAnalysisSummaryRead,
    TaskAnalysisTimeBucketRead,
    TaskAnalysisTopicInsightRead,
    TaskAnalysisTopicTrendPointRead,
    TaskAnalysisTopicTrendRead,
    TaskAnalysisVideoHistoryPointRead,
    TaskAnalysisVideoInsightRead,
    TaskTopicRead,
    TaskVideoMetricsRead,
    TopicRepresentativeVideoRead,
)
from app.services.analysis_weight_service import (
    build_metric_definitions,
    build_metric_weight_configs,
    calculate_metric_score,
    resolve_metric_weight_map,
)
from app.services.popular_author_service import (
    PopularAuthorAnalysisResult,
    PopularAuthorAnalysisService,
)
from app.services.system_config_service import get_statistics_defaults
from app.services.task_log_service import create_task_log


@dataclass(slots=True)
class TaskStatisticsResult:
    summary: TaskAnalysisSummaryRead
    topics: list[TaskTopicRead]
    advanced: TaskAnalysisAdvancedRead


@dataclass(slots=True)
class _VideoMetricRow:
    task_video: TaskVideo
    video: Video
    metric_snapshot: VideoMetricSnapshot | None
    ai_summary: AiSummary | None


@dataclass(slots=True)
class _TopicMetricRow:
    topic_cluster: TopicCluster
    relation: TopicVideoRelation
    task_video: TaskVideo
    video: Video
    metric_snapshot: VideoMetricSnapshot | None


@dataclass(slots=True)
class _VideoInsightSeed:
    video_id: str
    bvid: str
    title: str
    url: str
    author_name: str | None
    author_mid: str | None
    cover_url: str | None
    published_at: datetime | None
    topic_name: str | None
    composite_score: float
    heat_score: float
    relevance_score: float
    view_count: int
    like_count: int
    share_count: int
    engagement_rate: float | None
    like_view_ratio: float | None
    coin_view_ratio: float | None
    favorite_view_ratio: float | None
    share_view_ratio: float | None
    reply_view_ratio: float | None
    danmaku_view_ratio: float | None
    search_play_count: int | None
    search_to_current_view_growth_ratio: float | None
    published_hours: float | None
    views_per_hour_since_publish: float | None
    views_per_day_since_publish: float | None
    historical_snapshot_count: int
    historical_view_growth_ratio: float | None
    historical_view_velocity_per_hour: float | None
    completion_proxy_score: float | None
    history: list[TaskAnalysisVideoHistoryPointRead]


class StatisticsService:
    def __init__(
        self,
        session: Session,
        *,
        popular_author_service: PopularAuthorAnalysisService | None = None,
        include_external_author_fetch: bool = True,
    ) -> None:
        self.session = session
        self.popular_author_service = popular_author_service
        self.include_external_author_fetch = include_external_author_fetch
        self._metric_weight_map = resolve_metric_weight_map(None)

    def calculate_task_statistics(self, task_id: str) -> TaskStatisticsResult:
        defaults = get_statistics_defaults(self.session)
        task = self.session.get(CrawlTask, task_id)
        self._metric_weight_map = resolve_metric_weight_map(
            task.extra_params if task is not None else None
        )
        video_rows = self._load_video_rows(task_id)
        topic_rows = self._load_topic_rows(task_id)
        history_by_video_id = self._load_video_history(
            task_id,
            [row.video.id for row in video_rows]
        )
        primary_topic_by_video_id = self._build_primary_topic_map(video_rows, topic_rows)
        video_insight_seeds = self._build_video_insight_seeds(
            video_rows,
            history_by_video_id=history_by_video_id,
            primary_topic_by_video_id=primary_topic_by_video_id,
        )
        video_insights = self._finalize_video_insight_seeds(video_insight_seeds)
        video_insight_by_id = {item.video_id: item for item in video_insights}

        summary = self._build_summary(video_rows)
        topics = self._build_topics(
            topic_rows,
            total_videos=len(video_rows),
            top_topic_limit=defaults["top_topic_limit"],
        )
        base_topic_insights = self._build_topic_insights(
            topic_rows,
            video_insight_by_id=video_insight_by_id,
        )
        momentum_topics = self._sort_topic_insights(base_topic_insights, mode="momentum")
        depth_topics = self._sort_topic_insights(base_topic_insights, mode="depth")
        community_topics = self._sort_topic_insights(
            base_topic_insights,
            mode="community",
        )
        explosive_videos = self._sort_video_insights(video_insights, mode="momentum")
        deep_videos = self._sort_video_insights(video_insights, mode="depth")
        community_videos = self._sort_video_insights(video_insights, mode="community")
        topic_evolution = self._build_topic_evolution(
            topic_rows,
            video_insight_by_id=video_insight_by_id,
        )
        latest_hot_topic = self._build_latest_hot_topic(
            base_topic_insights,
            topic_evolution=topic_evolution,
        )
        recommendations = self._build_recommendations(
            video_insights,
            latest_hot_topic=latest_hot_topic,
        )
        data_notes = self._build_data_notes(video_insights)
        metric_definitions = build_metric_definitions(self._metric_weight_map)
        metric_weight_configs = build_metric_weight_configs(self._metric_weight_map)
        author_analysis = self._build_popular_author_analysis(
            task=task,
            video_insights=video_insights,
            topic_insights=base_topic_insights,
        )

        advanced = TaskAnalysisAdvancedRead(
            hot_topics=topics[: defaults["top_topic_limit"]],
            keyword_cooccurrence=self._build_keyword_cooccurrence(
                video_rows,
                limit=defaults["cooccurrence_limit"],
            ),
            publish_date_distribution=self._build_publish_distribution(
                video_rows,
                limit=defaults["distribution_bucket_limit"],
            ),
            duration_heat_correlation=self._build_duration_heat_correlation(video_rows),
            momentum_topics=momentum_topics[: defaults["top_topic_limit"]],
            explosive_videos=explosive_videos[: defaults["top_topic_limit"]],
            depth_topics=depth_topics[: defaults["top_topic_limit"]],
            deep_videos=deep_videos[: defaults["top_topic_limit"]],
            community_topics=community_topics[: defaults["top_topic_limit"]],
            community_videos=community_videos[: defaults["top_topic_limit"]],
            topic_evolution=topic_evolution[: defaults["top_topic_limit"]],
            latest_hot_topic=latest_hot_topic,
            topic_insights=base_topic_insights,
            video_insights=video_insights,
            metric_definitions=metric_definitions,
            metric_weight_configs=metric_weight_configs,
            recommendations=recommendations,
            popular_authors=author_analysis.popular_authors,
            topic_hot_authors=author_analysis.topic_hot_authors,
            author_analysis_notes=author_analysis.author_analysis_notes,
            data_notes=data_notes,
        )

        return TaskStatisticsResult(
            summary=summary,
            topics=topics,
            advanced=advanced,
        )

    def generate_and_persist(self, task: CrawlTask) -> TaskStatisticsResult:
        result = self.calculate_task_statistics(task.id)
        top_videos = self._load_top_video_snapshot(task.id, limit=10)
        has_ai_summaries = (
            self.session.scalar(
                select(AiSummary.id).where(AiSummary.task_id == task.id).limit(1)
            )
            is not None
        )
        generated_at = utc_now()
        task.extra_params = self._merge_analysis_payload(
            task.extra_params,
            {
                "analysis_snapshot": {
                    "generated_at": generated_at.isoformat(),
                    "summary": result.summary.model_dump(mode="json"),
                    "topics": [
                        topic.model_dump(mode="json") for topic in result.topics
                    ],
                    "advanced": result.advanced.model_dump(mode="json"),
                    "top_videos": [
                        item.model_dump(mode="json") for item in top_videos
                    ],
                    "has_ai_summaries": has_ai_summaries,
                }
            },
        )
        self.session.commit()

        create_task_log(
            self.session,
            task=task,
            stage=TaskStage.TOPIC,
            message="Generated topic statistics and extended analysis snapshot.",
            payload={
                "topic_count": len(result.topics),
                "hot_topic_count": len(result.advanced.hot_topics),
                "cooccurrence_count": len(result.advanced.keyword_cooccurrence),
                "explosive_video_count": len(result.advanced.explosive_videos),
                "recommendation_count": len(result.advanced.recommendations),
                "popular_author_count": len(result.advanced.popular_authors),
            },
        )
        self.session.commit()
        create_task_log(
            self.session,
            task=task,
            stage=TaskStage.AUTHOR,
            message="Generated popular author analysis snapshot.",
            payload={
                "popular_author_count": len(result.advanced.popular_authors),
                "topic_hot_author_group_count": len(result.advanced.topic_hot_authors),
                "note_count": len(result.advanced.author_analysis_notes),
            },
        )
        self.session.commit()
        return result

    def _build_popular_author_analysis(
        self,
        *,
        task: CrawlTask | None,
        video_insights: list[TaskAnalysisVideoInsightRead],
        topic_insights: list[TaskAnalysisTopicInsightRead],
    ):
        if task is None:
            return PopularAuthorAnalysisResult()

        service = self.popular_author_service
        owns_service = service is None
        if service is None:
            service = PopularAuthorAnalysisService(self.session)
        try:
            return service.build_for_task(
                task,
                video_insights=video_insights,
                topic_insights=topic_insights,
                fetch_author_videos=self.include_external_author_fetch,
            )
        finally:
            if owns_service:
                service.close()

    def _load_top_video_snapshot(self, task_id: str, *, limit: int) -> list:
        from app.services.task_result_service import get_task_video_results

        return get_task_video_results(self.session, task_id)[:limit]

    def _load_video_rows(self, task_id: str) -> list[_VideoMetricRow]:
        latest_snapshot_ids = self._build_latest_snapshot_ids_subquery()
        latest_snapshot = aliased(VideoMetricSnapshot)
        statement = (
            select(TaskVideo, Video, latest_snapshot, AiSummary)
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
                AiSummary,
                (AiSummary.task_id == TaskVideo.task_id)
                & (AiSummary.video_id == TaskVideo.video_id),
            )
            .where(TaskVideo.task_id == task_id)
            .order_by(TaskVideo.composite_score.desc(), Video.created_at.desc())
        )
        return [
            _VideoMetricRow(
                task_video=task_video,
                video=video,
                metric_snapshot=metric_snapshot,
                ai_summary=ai_summary,
            )
            for task_video, video, metric_snapshot, ai_summary in self.session.execute(
                statement
            ).all()
        ]

    def _load_topic_rows(self, task_id: str) -> list[_TopicMetricRow]:
        latest_snapshot_ids = self._build_latest_snapshot_ids_subquery()
        latest_snapshot = aliased(VideoMetricSnapshot)
        statement = (
            select(TopicCluster, TopicVideoRelation, TaskVideo, Video, latest_snapshot)
            .join(
                TopicVideoRelation,
                TopicVideoRelation.topic_cluster_id == TopicCluster.id,
            )
            .join(
                TaskVideo,
                (TaskVideo.task_id == TopicVideoRelation.task_id)
                & (TaskVideo.video_id == TopicVideoRelation.video_id),
            )
            .join(Video, Video.id == TopicVideoRelation.video_id)
            .outerjoin(
                latest_snapshot_ids,
                (latest_snapshot_ids.c.task_id == TopicVideoRelation.task_id)
                & (latest_snapshot_ids.c.video_id == TopicVideoRelation.video_id),
            )
            .outerjoin(
                latest_snapshot,
                latest_snapshot.id == latest_snapshot_ids.c.snapshot_id,
            )
            .where(TopicCluster.task_id == task_id)
            .order_by(
                TopicCluster.cluster_order.asc().nulls_last(),
                TaskVideo.composite_score.desc(),
            )
        )
        result_rows = self.session.execute(statement).all()
        return [
            _TopicMetricRow(
                topic_cluster=topic_cluster,
                relation=relation,
                task_video=task_video,
                video=video,
                metric_snapshot=metric_snapshot,
            )
            for (
                topic_cluster,
                relation,
                task_video,
                video,
                metric_snapshot,
            ) in result_rows
        ]

    def _load_video_history(
        self,
        task_id: str,
        video_ids: list[str],
    ) -> dict[str, list[VideoMetricSnapshot]]:
        if not video_ids:
            return {}

        statement = (
            select(VideoMetricSnapshot)
            .where(
                VideoMetricSnapshot.task_id == task_id,
                VideoMetricSnapshot.video_id.in_(video_ids),
            )
            .order_by(
                VideoMetricSnapshot.video_id.asc(),
                VideoMetricSnapshot.captured_at.asc(),
                VideoMetricSnapshot.created_at.asc(),
                VideoMetricSnapshot.id.asc(),
            )
        )
        history_by_video_id: dict[str, list[VideoMetricSnapshot]] = defaultdict(list)
        for snapshot in self.session.scalars(statement):
            history_by_video_id[snapshot.video_id].append(snapshot)
        return history_by_video_id

    def _build_summary(
        self,
        rows: list[_VideoMetricRow],
    ) -> TaskAnalysisSummaryRead:
        total = len(rows)
        if total == 0:
            return TaskAnalysisSummaryRead(
                total_videos=0,
                average_view_count=0,
                average_like_count=0,
                average_coin_count=0,
                average_favorite_count=0,
                average_share_count=0,
                average_reply_count=0,
                average_danmaku_count=0,
                average_composite_score=0,
                average_engagement_rate=0,
            )

        view_total = 0
        like_total = 0
        coin_total = 0
        favorite_total = 0
        share_total = 0
        reply_total = 0
        danmaku_total = 0
        composite_score_total = 0.0
        engagement_rate_total = 0.0

        for row in rows:
            metric_snapshot = row.metric_snapshot
            view_total += self._metric_value(metric_snapshot, "view_count")
            like_total += self._metric_value(metric_snapshot, "like_count")
            coin_total += self._metric_value(metric_snapshot, "coin_count")
            favorite_total += self._metric_value(metric_snapshot, "favorite_count")
            share_total += self._metric_value(metric_snapshot, "share_count")
            reply_total += self._metric_value(metric_snapshot, "reply_count")
            danmaku_total += self._metric_value(metric_snapshot, "danmaku_count")
            composite_score_total += float(row.task_video.composite_score)
            engagement_rate_total += self._calculate_engagement_rate(metric_snapshot)

        def average(value: float) -> float:
            return round(value / total, 4)

        return TaskAnalysisSummaryRead(
            total_videos=total,
            average_view_count=average(float(view_total)),
            average_like_count=average(float(like_total)),
            average_coin_count=average(float(coin_total)),
            average_favorite_count=average(float(favorite_total)),
            average_share_count=average(float(share_total)),
            average_reply_count=average(float(reply_total)),
            average_danmaku_count=average(float(danmaku_total)),
            average_composite_score=average(composite_score_total),
            average_engagement_rate=average(engagement_rate_total),
        )

    def _build_topics(
        self,
        rows: list[_TopicMetricRow],
        *,
        total_videos: int,
        top_topic_limit: int,
    ) -> list[TaskTopicRead]:
        grouped: dict[str, list[_TopicMetricRow]] = defaultdict(list)
        for row in rows:
            grouped[row.topic_cluster.id].append(row)

        topic_items: list[TaskTopicRead] = []
        for topic_id, topic_rows in grouped.items():
            cluster = topic_rows[0].topic_cluster
            unique_video_ids = {item.video.id for item in topic_rows}
            representative = max(
                topic_rows,
                key=lambda item: (
                    item.relation.is_primary,
                    item.task_video.composite_score,
                    item.video.created_at,
                ),
            )
            engagement_total = sum(
                self._calculate_engagement_rate(item.metric_snapshot)
                for item in topic_rows
            )

            topic_items.append(
                TaskTopicRead(
                    id=topic_id,
                    name=cluster.name,
                    normalized_name=cluster.normalized_name,
                    description=cluster.description,
                    keywords=list(cluster.keywords or []),
                    video_count=len(unique_video_ids),
                    total_heat_score=float(cluster.total_heat_score),
                    average_heat_score=float(cluster.average_heat_score),
                    video_ratio=round(
                        len(unique_video_ids) / total_videos,
                        4,
                    )
                    if total_videos
                    else 0.0,
                    average_engagement_rate=round(
                        engagement_total / len(topic_rows),
                        4,
                    )
                    if topic_rows
                    else 0.0,
                    cluster_order=cluster.cluster_order,
                    representative_video=TopicRepresentativeVideoRead(
                        video_id=representative.video.id,
                        bvid=representative.video.bvid,
                        title=representative.video.title,
                        url=representative.video.url,
                        composite_score=float(representative.task_video.composite_score),
                    ),
                )
            )

        topic_items.sort(
            key=lambda item: (
                item.cluster_order is None,
                item.cluster_order or 0,
                -item.total_heat_score,
                -item.video_count,
            )
        )
        return topic_items[: max(top_topic_limit, len(topic_items))]

    def _build_primary_topic_map(
        self,
        video_rows: list[_VideoMetricRow],
        topic_rows: list[_TopicMetricRow],
    ) -> dict[str, str | None]:
        primary_topic_by_video_id: dict[str, str | None] = {}
        for row in sorted(
            topic_rows,
            key=lambda item: (
                not item.relation.is_primary,
                -(float(item.task_video.composite_score)),
            ),
        ):
            primary_topic_by_video_id.setdefault(row.video.id, row.topic_cluster.name)

        for row in video_rows:
            if row.video.id in primary_topic_by_video_id:
                continue
            primary_topic_by_video_id[row.video.id] = (
                row.ai_summary.primary_topic if row.ai_summary is not None else None
            )
        return primary_topic_by_video_id

    def _build_video_insight_seeds(
        self,
        rows: list[_VideoMetricRow],
        *,
        history_by_video_id: dict[str, list[VideoMetricSnapshot]],
        primary_topic_by_video_id: dict[str, str | None],
    ) -> list[_VideoInsightSeed]:
        now = utc_now()
        seeds: list[_VideoInsightSeed] = []

        for row in rows:
            metrics = row.metric_snapshot
            view_count = self._metric_value(metrics, "view_count")
            like_count = self._metric_value(metrics, "like_count")
            share_count = self._metric_value(metrics, "share_count")
            like_view_ratio = self._calculate_ratio(metrics, "like_count")
            coin_view_ratio = self._calculate_ratio(metrics, "coin_count")
            favorite_view_ratio = self._calculate_ratio(metrics, "favorite_count")
            share_view_ratio = self._calculate_ratio(metrics, "share_count")
            reply_view_ratio = self._calculate_ratio(metrics, "reply_count")
            danmaku_view_ratio = self._calculate_ratio(metrics, "danmaku_count")
            engagement_rate = self._calculate_engagement_rate(metrics)
            published_hours = self._hours_between(row.video.published_at, now)
            views_per_hour_since_publish = (
                round(view_count / max(published_hours, 1.0), 4)
                if published_hours is not None
                else None
            )
            views_per_day_since_publish = (
                round(view_count / max(published_hours / 24, 1.0), 4)
                if published_hours is not None
                else None
            )

            search_play_count = self._extract_search_metric(metrics, "play_count")
            search_to_current_view_growth_ratio = None
            if (
                search_play_count is not None
                and search_play_count > 0
                and view_count >= 0
            ):
                search_to_current_view_growth_ratio = round(
                    (view_count - search_play_count) / search_play_count,
                    4,
                )

            completion_proxy_score = self._calculate_completion_proxy_score(
                favorite_view_ratio=favorite_view_ratio,
                coin_view_ratio=coin_view_ratio,
                reply_view_ratio=reply_view_ratio,
                danmaku_view_ratio=danmaku_view_ratio,
            )

            video_history = history_by_video_id.get(row.video.id, [])
            seeds.append(
                _VideoInsightSeed(
                    video_id=row.video.id,
                    bvid=row.video.bvid,
                    title=row.video.title,
                    url=row.video.url,
                    author_name=row.video.author_name,
                    author_mid=row.video.author_mid,
                    cover_url=row.video.cover_url,
                    published_at=row.video.published_at,
                    topic_name=primary_topic_by_video_id.get(row.video.id),
                    composite_score=float(row.task_video.composite_score),
                    heat_score=float(row.task_video.heat_score),
                    relevance_score=float(row.task_video.relevance_score),
                    view_count=view_count,
                    like_count=like_count,
                    share_count=share_count,
                    engagement_rate=engagement_rate,
                    like_view_ratio=like_view_ratio,
                    coin_view_ratio=coin_view_ratio,
                    favorite_view_ratio=favorite_view_ratio,
                    share_view_ratio=share_view_ratio,
                    reply_view_ratio=reply_view_ratio,
                    danmaku_view_ratio=danmaku_view_ratio,
                    search_play_count=search_play_count,
                    search_to_current_view_growth_ratio=search_to_current_view_growth_ratio,
                    published_hours=published_hours,
                    views_per_hour_since_publish=views_per_hour_since_publish,
                    views_per_day_since_publish=views_per_day_since_publish,
                    historical_snapshot_count=len(video_history),
                    historical_view_growth_ratio=self._calculate_history_growth_ratio(
                        video_history
                    ),
                    historical_view_velocity_per_hour=(
                        self._calculate_history_velocity_per_hour(video_history)
                    ),
                    completion_proxy_score=completion_proxy_score,
                    history=self._build_history_points(
                        metrics=metrics,
                        snapshots=video_history,
                    ),
                )
            )

        return seeds

    def _finalize_video_insight_seeds(
        self,
        seeds: list[_VideoInsightSeed],
    ) -> list[TaskAnalysisVideoInsightRead]:
        maxima = {
            "search_growth": max(
                (max(item.search_to_current_view_growth_ratio or 0.0, 0.0) for item in seeds),
                default=0.0,
            ),
            "publish_velocity": max(
                (item.views_per_hour_since_publish or 0.0 for item in seeds),
                default=0.0,
            ),
            "history_velocity": max(
                (item.historical_view_velocity_per_hour or 0.0 for item in seeds),
                default=0.0,
            ),
            "like_ratio": max((item.like_view_ratio or 0.0 for item in seeds), default=0.0),
            "coin_ratio": max((item.coin_view_ratio or 0.0 for item in seeds), default=0.0),
            "favorite_ratio": max(
                (item.favorite_view_ratio or 0.0 for item in seeds),
                default=0.0,
            ),
            "completion_proxy": max(
                (item.completion_proxy_score or 0.0 for item in seeds),
                default=0.0,
            ),
            "engagement_rate": max(
                (item.engagement_rate or 0.0 for item in seeds),
                default=0.0,
            ),
            "share_ratio": max((item.share_view_ratio or 0.0 for item in seeds), default=0.0),
            "reply_ratio": max((item.reply_view_ratio or 0.0 for item in seeds), default=0.0),
            "danmaku_ratio": max(
                (item.danmaku_view_ratio or 0.0 for item in seeds),
                default=0.0,
            ),
        }

        insights: list[TaskAnalysisVideoInsightRead] = []
        for seed in seeds:
            burst_score = round(
                calculate_metric_score(
                    "burst_score",
                    {
                        "search_growth": self._normalize_positive(
                            seed.search_to_current_view_growth_ratio,
                            maxima["search_growth"],
                        ),
                        "publish_velocity": self._normalize_positive(
                            seed.views_per_hour_since_publish,
                            maxima["publish_velocity"],
                        ),
                        "history_velocity": self._normalize_positive(
                            seed.historical_view_velocity_per_hour,
                            maxima["history_velocity"],
                        ),
                    },
                    self._metric_weight_map["burst_score"],
                ),
                4,
            )
            depth_score = round(
                calculate_metric_score(
                    "depth_score",
                    {
                        "like_ratio": self._normalize_positive(
                            seed.like_view_ratio,
                            maxima["like_ratio"],
                        ),
                        "coin_ratio": self._normalize_positive(
                            seed.coin_view_ratio,
                            maxima["coin_ratio"],
                        ),
                        "favorite_ratio": self._normalize_positive(
                            seed.favorite_view_ratio,
                            maxima["favorite_ratio"],
                        ),
                        "completion_proxy_score": self._normalize_positive(
                            seed.completion_proxy_score,
                            maxima["completion_proxy"],
                        ),
                        "engagement_rate": self._normalize_positive(
                            seed.engagement_rate,
                            maxima["engagement_rate"],
                        ),
                    },
                    self._metric_weight_map["depth_score"],
                ),
                4,
            )
            community_score = round(
                calculate_metric_score(
                    "community_score",
                    {
                        "share_ratio": self._normalize_positive(
                            seed.share_view_ratio,
                            maxima["share_ratio"],
                        ),
                        "reply_ratio": self._normalize_positive(
                            seed.reply_view_ratio,
                            maxima["reply_ratio"],
                        ),
                        "danmaku_ratio": self._normalize_positive(
                            seed.danmaku_view_ratio,
                            maxima["danmaku_ratio"],
                        ),
                        "engagement_rate": self._normalize_positive(
                            seed.engagement_rate,
                            maxima["engagement_rate"],
                        ),
                    },
                    self._metric_weight_map["community_score"],
                ),
                4,
            )

            insights.append(
                TaskAnalysisVideoInsightRead(
                    video_id=seed.video_id,
                    bvid=seed.bvid,
                    title=seed.title,
                    url=seed.url,
                    author_name=seed.author_name,
                    author_mid=seed.author_mid,
                    cover_url=seed.cover_url,
                    published_at=seed.published_at,
                    topic_name=seed.topic_name,
                    composite_score=seed.composite_score,
                    heat_score=seed.heat_score,
                    relevance_score=seed.relevance_score,
                    view_count=seed.view_count,
                    like_count=seed.like_count,
                    share_count=seed.share_count,
                    engagement_rate=seed.engagement_rate,
                    like_view_ratio=seed.like_view_ratio,
                    coin_view_ratio=seed.coin_view_ratio,
                    favorite_view_ratio=seed.favorite_view_ratio,
                    share_view_ratio=seed.share_view_ratio,
                    reply_view_ratio=seed.reply_view_ratio,
                    danmaku_view_ratio=seed.danmaku_view_ratio,
                    search_play_count=seed.search_play_count,
                    search_to_current_view_growth_ratio=seed.search_to_current_view_growth_ratio,
                    published_hours=seed.published_hours,
                    views_per_hour_since_publish=seed.views_per_hour_since_publish,
                    views_per_day_since_publish=seed.views_per_day_since_publish,
                    historical_snapshot_count=seed.historical_snapshot_count,
                    historical_view_growth_ratio=seed.historical_view_growth_ratio,
                    historical_view_velocity_per_hour=seed.historical_view_velocity_per_hour,
                    burst_score=burst_score,
                    depth_score=depth_score,
                    community_score=community_score,
                    completion_proxy_score=seed.completion_proxy_score,
                    history=seed.history,
                )
            )

        return insights

    def _build_topic_insights(
        self,
        rows: list[_TopicMetricRow],
        *,
        video_insight_by_id: dict[str, TaskAnalysisVideoInsightRead],
    ) -> list[TaskAnalysisTopicInsightRead]:
        grouped: dict[str, list[_TopicMetricRow]] = defaultdict(list)
        for row in rows:
            grouped[row.topic_cluster.id].append(row)

        topic_insights: list[TaskAnalysisTopicInsightRead] = []
        for topic_id, topic_rows in grouped.items():
            cluster = topic_rows[0].topic_cluster
            unique_rows: dict[str, _TopicMetricRow] = {}
            for row in topic_rows:
                unique_rows.setdefault(row.video.id, row)

            video_insights = [
                video_insight_by_id[video_id]
                for video_id in unique_rows
                if video_id in video_insight_by_id
            ]
            if not video_insights:
                continue

            representative = max(
                unique_rows.values(),
                key=lambda item: (
                    item.relation.is_primary,
                    item.task_video.composite_score,
                    item.video.created_at,
                ),
            )

            average_view_count = self._average(
                [float(item.view_count) for item in video_insights]
            )
            average_engagement_rate = self._average(
                [item.engagement_rate or 0.0 for item in video_insights]
            )
            average_like_view_ratio = self._average_nullable(
                [item.like_view_ratio for item in video_insights]
            )
            average_share_rate = self._average_nullable(
                [item.share_view_ratio for item in video_insights]
            )
            average_burst_score = self._average_nullable(
                [item.burst_score for item in video_insights]
            )
            average_depth_score = self._average_nullable(
                [item.depth_score for item in video_insights]
            )
            average_community_score = self._average_nullable(
                [item.community_score for item in video_insights]
            )
            historical_coverage_ratio = round(
                sum(1 for item in video_insights if item.historical_snapshot_count > 1)
                / len(video_insights),
                4,
            )
            latest_publish_at = max(
                (item.published_at for item in video_insights if item.published_at is not None),
                default=None,
            )

            topic_insights.append(
                TaskAnalysisTopicInsightRead(
                    topic_id=topic_id,
                    topic_name=cluster.name,
                    video_count=len(video_insights),
                    total_heat_score=float(cluster.total_heat_score),
                    average_view_count=average_view_count,
                    average_engagement_rate=average_engagement_rate,
                    average_like_view_ratio=average_like_view_ratio,
                    average_share_rate=average_share_rate,
                    average_burst_score=average_burst_score,
                    average_depth_score=average_depth_score,
                    average_community_score=average_community_score,
                    historical_coverage_ratio=historical_coverage_ratio,
                    latest_publish_at=latest_publish_at,
                    representative_video=TopicRepresentativeVideoRead(
                        video_id=representative.video.id,
                        bvid=representative.video.bvid,
                        title=representative.video.title,
                        url=representative.video.url,
                        composite_score=float(representative.task_video.composite_score),
                    ),
                    summary=self._build_topic_summary(
                        cluster.name,
                        video_count=len(video_insights),
                        average_burst_score=average_burst_score,
                        average_depth_score=average_depth_score,
                        average_community_score=average_community_score,
                    ),
                )
            )

        return topic_insights

    def _sort_topic_insights(
        self,
        items: list[TaskAnalysisTopicInsightRead],
        *,
        mode: str,
    ) -> list[TaskAnalysisTopicInsightRead]:
        sort_key = {
            "momentum": lambda item: (
                item.average_burst_score or 0.0,
                item.total_heat_score,
                item.average_share_rate or 0.0,
            ),
            "depth": lambda item: (
                item.average_depth_score or 0.0,
                item.average_like_view_ratio or 0.0,
                item.total_heat_score,
            ),
            "community": lambda item: (
                item.average_community_score or 0.0,
                item.average_share_rate or 0.0,
                item.total_heat_score,
            ),
        }[mode]
        return sorted(items, key=sort_key, reverse=True)

    def _sort_video_insights(
        self,
        items: list[TaskAnalysisVideoInsightRead],
        *,
        mode: str,
    ) -> list[TaskAnalysisVideoInsightRead]:
        sort_key = {
            "momentum": lambda item: (
                item.burst_score or 0.0,
                item.views_per_hour_since_publish or 0.0,
                item.community_score or 0.0,
            ),
            "depth": lambda item: (
                item.depth_score or 0.0,
                item.like_view_ratio or 0.0,
                item.completion_proxy_score or 0.0,
            ),
            "community": lambda item: (
                item.community_score or 0.0,
                item.share_view_ratio or 0.0,
                item.reply_view_ratio or 0.0,
            ),
        }[mode]
        return sorted(items, key=sort_key, reverse=True)

    def _build_topic_evolution(
        self,
        rows: list[_TopicMetricRow],
        *,
        video_insight_by_id: dict[str, TaskAnalysisVideoInsightRead],
    ) -> list[TaskAnalysisTopicTrendRead]:
        grouped: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
        topic_names: dict[str, str] = {}

        for row in rows:
            topic_id = row.topic_cluster.id
            topic_names[topic_id] = row.topic_cluster.name
            video_insight = video_insight_by_id.get(row.video.id)
            if video_insight is None:
                continue

            bucket = (
                row.video.published_at.date().isoformat()
                if row.video.published_at is not None
                else "unknown"
            )
            bucket_state = grouped[topic_id].setdefault(
                bucket,
                {
                    "video_ids": set(),
                    "total_heat_score": 0.0,
                    "burst_scores": [],
                    "community_scores": [],
                },
            )
            video_ids = bucket_state["video_ids"]
            if row.video.id in video_ids:
                continue
            video_ids.add(row.video.id)
            bucket_state["total_heat_score"] += float(row.task_video.heat_score)
            bucket_state["burst_scores"].append(video_insight.burst_score or 0.0)
            bucket_state["community_scores"].append(video_insight.community_score or 0.0)

        trends: list[TaskAnalysisTopicTrendRead] = []
        for topic_id, bucket_map in grouped.items():
            points: list[TaskAnalysisTopicTrendPointRead] = []
            for bucket in sorted(bucket_map, key=lambda value: (value == "unknown", value)):
                bucket_state = bucket_map[bucket]
                video_count = len(bucket_state["video_ids"])
                average_burst_score = self._average_nullable(bucket_state["burst_scores"])
                average_community_score = self._average_nullable(
                    bucket_state["community_scores"]
                )
                total_heat_score = round(float(bucket_state["total_heat_score"]), 4)
                topic_heat_index = round(
                    calculate_metric_score(
                        "topic_heat_index",
                        {
                            "total_heat_score": total_heat_score,
                            "average_burst_score": average_burst_score or 0.0,
                            "average_community_score": average_community_score or 0.0,
                        },
                        self._metric_weight_map["topic_heat_index"],
                    ),
                    4,
                )
                points.append(
                    TaskAnalysisTopicTrendPointRead(
                        bucket=bucket,
                        video_count=video_count,
                        total_heat_score=total_heat_score,
                        topic_heat_index=topic_heat_index,
                        average_burst_score=average_burst_score,
                        average_community_score=average_community_score,
                    )
                )

            if not points:
                continue

            latest_point = points[-1]
            peak_point = max(points, key=lambda item: item.topic_heat_index)
            trends.append(
                TaskAnalysisTopicTrendRead(
                    topic_id=topic_id,
                    topic_name=topic_names.get(topic_id, topic_id),
                    trend_direction=self._infer_trend_direction(points),
                    latest_bucket=latest_point.bucket,
                    latest_topic_heat_index=latest_point.topic_heat_index,
                    peak_bucket=peak_point.bucket,
                    peak_topic_heat_index=peak_point.topic_heat_index,
                    points=points,
                )
            )

        return sorted(
            trends,
            key=lambda item: (
                item.latest_topic_heat_index or 0.0,
                item.peak_topic_heat_index or 0.0,
            ),
            reverse=True,
        )

    def _build_latest_hot_topic(
        self,
        topic_insights: list[TaskAnalysisTopicInsightRead],
        *,
        topic_evolution: list[TaskAnalysisTopicTrendRead],
    ) -> TaskAnalysisLatestHotTopicRead:
        if not topic_insights:
            return TaskAnalysisLatestHotTopicRead()

        max_heat_score = max((item.total_heat_score for item in topic_insights), default=0.0)
        evolution_by_topic_id = {item.topic_id: item for item in topic_evolution}
        now = utc_now()

        scored_topics: list[tuple[float, TaskAnalysisTopicInsightRead]] = []
        for item in topic_insights:
            age_hours = self._hours_between(item.latest_publish_at, now)
            recency_score = 0.0
            if age_hours is not None:
                recency_score = max(0.0, min(1.0, 1 - age_hours / (24 * 14)))

            evolution_score = (
                evolution_by_topic_id.get(item.topic_id).latest_topic_heat_index or 0.0
                if item.topic_id in evolution_by_topic_id
                else 0.0
            )
            topic_score = round(
                0.30 * self._normalize_positive(item.total_heat_score, max_heat_score)
                + 0.25 * (item.average_burst_score or 0.0)
                + 0.20 * (item.average_community_score or 0.0)
                + 0.15 * recency_score
                + 0.10 * self._normalize_positive(evolution_score, 5.0),
                4,
            )
            scored_topics.append((topic_score, item))

        scored_topics.sort(key=lambda item: item[0], reverse=True)
        topic_score, topic = scored_topics[0]
        evolution = evolution_by_topic_id.get(topic.topic_id)

        supporting_points = [
            f"综合热点得分 {topic_score:.2f}，主题总热度 {topic.total_heat_score:.2f}。",
            f"爆发力均值 {topic.average_burst_score or 0:.2f}，社区扩散均值 {topic.average_community_score or 0:.2f}。",
        ]
        if evolution is not None and evolution.latest_bucket is not None:
            supporting_points.append(
                f"发布时间线最新高点出现在 {evolution.latest_bucket}，热度指数 {evolution.latest_topic_heat_index or 0:.2f}。"
            )
        if topic.representative_video is not None:
            supporting_points.append(
                f"代表视频为《{topic.representative_video.title}》。"
            )

        return TaskAnalysisLatestHotTopicRead(
            topic=topic,
            reason=(
                f"{topic.topic_name} 同时具备较高的主题热度、近期爆发力和社区扩散能力，"
                "是当前检索结果中最值得优先关注的热点主题。"
            ),
            supporting_points=supporting_points,
        )

    def _build_recommendations(
        self,
        video_insights: list[TaskAnalysisVideoInsightRead],
        *,
        latest_hot_topic: TaskAnalysisLatestHotTopicRead,
    ) -> list[TaskAnalysisRecommendationRead]:
        if not video_insights:
            return []

        recommendations = [
            TaskAnalysisRecommendationRead(
                key="overall_hot",
                title="当前搜索结果里最热门的视频",
                description="优先推荐综合评分、热度和当前讨论度都更靠前的内容。",
                videos=sorted(
                    video_insights,
                    key=lambda item: (
                        item.composite_score,
                        item.heat_score,
                        item.view_count,
                    ),
                    reverse=True,
                )[:5],
            ),
            TaskAnalysisRecommendationRead(
                key="emerging_hot",
                title="当前最有爆发潜力的视频",
                description="适合想追新、看增速和话题升温速度的场景。",
                videos=self._sort_video_insights(video_insights, mode="momentum")[:5],
            ),
            TaskAnalysisRecommendationRead(
                key="community_pick",
                title="当前最适合扩散讨论的视频",
                description="分享率、评论率和弹幕密度更突出，适合吃瓜群众快速跟进。",
                videos=self._sort_video_insights(video_insights, mode="community")[:5],
            ),
        ]

        if latest_hot_topic.topic is not None:
            topic_videos = [
                item
                for item in video_insights
                if item.topic_name == latest_hot_topic.topic.topic_name
            ]
            recommendations.append(
                TaskAnalysisRecommendationRead(
                    key="latest_hot_topic",
                    title="当前最热主题下的推荐视频",
                    description="直接聚焦到最新热点主题，优先看该主题内部最强样本。",
                    topic_name=latest_hot_topic.topic.topic_name,
                    videos=sorted(
                        topic_videos,
                        key=lambda item: (
                            item.composite_score,
                            item.community_score or 0.0,
                            item.burst_score or 0.0,
                        ),
                        reverse=True,
                    )[:5],
                )
            )

        return recommendations

    def _build_data_notes(
        self,
        video_insights: list[TaskAnalysisVideoInsightRead],
    ) -> list[str]:
        total_videos = len(video_insights)
        historical_videos = sum(
            1 for item in video_insights if item.historical_snapshot_count > 1
        )
        customized_metric_names = [
            item.metric_name
            for item in build_metric_weight_configs(self._metric_weight_map)
            if item.customized
        ]
        return [
            (
                "实时在线人数和官方完播率当前未采集，页面中的完播相关内容使用互动深度代理指标，"
                "适合做趋势判断，不等同于平台后台口径。"
            ),
            (
                f"当前结果中有 {historical_videos}/{total_videos} 条视频具备跨任务历史快照，"
                "这些视频的增长率和热度演化判断更可靠。"
            ),
            (
                "爆发力同时参考搜索初始播放、发布时间速度和跨任务历史增速；"
                "社区指标重点参考分享、评论和弹幕扩散效率。"
            ),
            (
                "当前无法稳定采集视频自发布以来的官方全量播放/点赞时间序列，"
                "爆发视频历史曲线基于搜索基线、当前快照和跨任务快照历史构建。"
            ),
            (
                "当前分析使用默认指标权重。"
                if not customized_metric_names
                else "当前分析启用了自定义指标权重："
                f"{'、'.join(customized_metric_names)}。"
            ),
        ]

    def _build_metric_definitions(self) -> list[TaskAnalysisMetricDefinitionRead]:
        return build_metric_definitions(self._metric_weight_map)

    def _build_keyword_cooccurrence(
        self,
        rows: list[_VideoMetricRow],
        *,
        limit: int,
    ) -> list[TaskAnalysisCooccurrenceRead]:
        pair_counter: Counter[tuple[str, str]] = Counter()

        for row in rows:
            if row.ai_summary is None:
                continue
            topics = []
            seen: set[str] = set()
            for topic in row.ai_summary.topics:
                normalized = topic.strip()
                if not normalized or normalized.casefold() in seen:
                    continue
                topics.append(normalized)
                seen.add(normalized.casefold())
            for left, right in combinations(sorted(topics), 2):
                pair_counter[(left, right)] += 1

        ranked = sorted(
            pair_counter.items(),
            key=lambda item: (-item[1], item[0][0], item[0][1]),
        )
        return [
            TaskAnalysisCooccurrenceRead(left=left, right=right, count=count)
            for (left, right), count in ranked[:limit]
        ]

    def _build_publish_distribution(
        self,
        rows: list[_VideoMetricRow],
        *,
        limit: int,
    ) -> list[TaskAnalysisTimeBucketRead]:
        bucket_counter: Counter[str] = Counter()

        for row in rows:
            if row.video.published_at is None:
                bucket = "unknown"
            else:
                bucket = row.video.published_at.date().isoformat()
            bucket_counter[bucket] += 1

        ranked_buckets = sorted(bucket_counter.items(), key=lambda item: item[0])
        return [
            TaskAnalysisTimeBucketRead(bucket=bucket, video_count=count)
            for bucket, count in ranked_buckets[:limit]
        ]

    def _build_duration_heat_correlation(
        self,
        rows: list[_VideoMetricRow],
    ) -> TaskAnalysisCorrelationRead:
        pairs = [
            (
                float(row.video.duration_seconds),
                float(row.task_video.heat_score),
            )
            for row in rows
            if row.video.duration_seconds is not None
        ]
        correlation = self._pearson_correlation(pairs)
        return TaskAnalysisCorrelationRead(
            metric="duration_seconds_vs_heat_score",
            correlation=correlation,
        )

    @staticmethod
    def _build_latest_snapshot_ids_subquery():
        ranked = (
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
        return (
            select(
                ranked.c.snapshot_id,
                ranked.c.task_id,
                ranked.c.video_id,
            )
            .where(ranked.c.row_number == 1)
            .subquery()
        )

    @staticmethod
    def _metric_value(
        metric_snapshot: VideoMetricSnapshot | TaskVideoMetricsRead | None,
        metric_name: str,
    ) -> int:
        return int(getattr(metric_snapshot, metric_name, 0) or 0)

    def _calculate_engagement_rate(
        self,
        metrics: VideoMetricSnapshot | TaskVideoMetricsRead | None,
    ) -> float:
        view_count = self._metric_value(metrics, "view_count")
        if view_count <= 0:
            return 0.0
        return round(
            calculate_metric_score(
                "engagement_rate",
                {
                    "like_ratio": self._calculate_ratio(metrics, "like_count") or 0.0,
                    "coin_ratio": self._calculate_ratio(metrics, "coin_count") or 0.0,
                    "favorite_ratio": self._calculate_ratio(metrics, "favorite_count")
                    or 0.0,
                    "share_ratio": self._calculate_ratio(metrics, "share_count") or 0.0,
                    "reply_ratio": self._calculate_ratio(metrics, "reply_count") or 0.0,
                    "danmaku_ratio": self._calculate_ratio(metrics, "danmaku_count")
                    or 0.0,
                },
                self._metric_weight_map["engagement_rate"],
            ),
            6,
        )

    @classmethod
    def _calculate_ratio(
        cls,
        metrics: VideoMetricSnapshot | TaskVideoMetricsRead | None,
        metric_name: str,
    ) -> float | None:
        view_count = cls._metric_value(metrics, "view_count")
        if view_count <= 0:
            return None
        return round(cls._metric_value(metrics, metric_name) / view_count, 6)

    @staticmethod
    def _extract_search_metric(
        metrics: VideoMetricSnapshot | None,
        key: str,
    ) -> int | None:
        if metrics is None or not isinstance(metrics.metrics_payload, dict):
            return None
        search_metrics = metrics.metrics_payload.get("search_metrics")
        if not isinstance(search_metrics, dict):
            return None
        value = search_metrics.get(key)
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _build_history_points(
        cls,
        *,
        metrics: VideoMetricSnapshot | None,
        snapshots: list[VideoMetricSnapshot],
    ) -> list[TaskAnalysisVideoHistoryPointRead]:
        points: list[TaskAnalysisVideoHistoryPointRead] = []

        search_play_count = cls._extract_search_metric(metrics, "play_count")
        search_like_count = cls._extract_search_metric(metrics, "like_count") or 0
        search_danmaku_count = cls._extract_search_metric(metrics, "danmaku_count") or 0
        if search_play_count is not None:
            points.append(
                TaskAnalysisVideoHistoryPointRead(
                    label="search_baseline",
                    view_count=search_play_count,
                    like_count=search_like_count,
                    share_count=0,
                    danmaku_count=search_danmaku_count,
                )
            )

        for snapshot in snapshots:
            points.append(
                TaskAnalysisVideoHistoryPointRead(
                    label="snapshot",
                    captured_at=snapshot.captured_at,
                    view_count=snapshot.view_count,
                    like_count=snapshot.like_count,
                    share_count=snapshot.share_count,
                    danmaku_count=snapshot.danmaku_count,
                )
            )
        return points

    @staticmethod
    def _calculate_history_growth_ratio(
        snapshots: list[VideoMetricSnapshot],
    ) -> float | None:
        if len(snapshots) < 2:
            return None
        start = snapshots[0].view_count
        end = snapshots[-1].view_count
        if start <= 0:
            return None
        return round((end - start) / start, 4)

    @staticmethod
    def _calculate_history_velocity_per_hour(
        snapshots: list[VideoMetricSnapshot],
    ) -> float | None:
        if len(snapshots) < 2:
            return None
        start = snapshots[0]
        end = snapshots[-1]
        hours = StatisticsService._hours_between(start.captured_at, end.captured_at)
        if hours is None or hours <= 0:
            return None
        return round((end.view_count - start.view_count) / hours, 4)

    def _calculate_completion_proxy_score(
        self,
        *,
        favorite_view_ratio: float | None,
        coin_view_ratio: float | None,
        reply_view_ratio: float | None,
        danmaku_view_ratio: float | None,
    ) -> float | None:
        values = [
            favorite_view_ratio or 0.0,
            coin_view_ratio or 0.0,
            reply_view_ratio or 0.0,
            danmaku_view_ratio or 0.0,
        ]
        if not any(values):
            return None
        return round(
            calculate_metric_score(
                "completion_proxy_score",
                {
                    "favorite_ratio": values[0],
                    "coin_ratio": values[1],
                    "reply_ratio": values[2],
                    "danmaku_ratio": values[3],
                },
                self._metric_weight_map["completion_proxy_score"],
            ),
            6,
        )

    @staticmethod
    def _normalize_positive(value: float | None, maximum: float) -> float:
        if value is None or maximum <= 0:
            return 0.0
        return round(max(min(value, maximum), 0.0) / maximum, 6)

    @staticmethod
    def _average(values: list[float]) -> float:
        if not values:
            return 0.0
        return round(sum(values) / len(values), 4)

    @staticmethod
    def _average_nullable(values: list[float | None]) -> float | None:
        normalized = [value for value in values if value is not None]
        if not normalized:
            return None
        return round(sum(normalized) / len(normalized), 4)

    @staticmethod
    def _hours_between(
        start: datetime | None,
        end: datetime | None,
    ) -> float | None:
        if start is None or end is None:
            return None
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        if end.tzinfo is None:
            end = end.replace(tzinfo=UTC)
        delta = end - start
        return round(delta.total_seconds() / 3600, 4)

    @staticmethod
    def _build_topic_summary(
        topic_name: str,
        *,
        video_count: int,
        average_burst_score: float | None,
        average_depth_score: float | None,
        average_community_score: float | None,
    ) -> str:
        return (
            f"{topic_name} 当前覆盖 {video_count} 条视频，"
            f"爆发力 {average_burst_score or 0:.2f}，"
            f"深度 {average_depth_score or 0:.2f}，"
            f"社区扩散 {average_community_score or 0:.2f}。"
        )

    @staticmethod
    def _infer_trend_direction(
        points: list[TaskAnalysisTopicTrendPointRead],
    ) -> str:
        if len(points) < 2:
            return "stable"
        first_point = points[0]
        latest_point = points[-1]
        delta = latest_point.topic_heat_index - first_point.topic_heat_index
        threshold = max(0.08, abs(first_point.topic_heat_index) * 0.15)
        if delta > threshold:
            return "rising"
        if delta < -threshold:
            return "cooling"
        return "stable"

    @staticmethod
    def _pearson_correlation(pairs: list[tuple[float, float]]) -> float | None:
        if len(pairs) < 2:
            return None
        xs = [item[0] for item in pairs]
        ys = [item[1] for item in pairs]
        mean_x = sum(xs) / len(xs)
        mean_y = sum(ys) / len(ys)
        numerator = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
        denominator_x = sqrt(sum((x - mean_x) ** 2 for x in xs))
        denominator_y = sqrt(sum((y - mean_y) ** 2 for y in ys))
        denominator = denominator_x * denominator_y
        if denominator == 0:
            return None
        return round(numerator / denominator, 4)

    @staticmethod
    def _merge_analysis_payload(
        extra_params: dict | None,
        payload: dict[str, object],
    ) -> dict[str, object]:
        merged = dict(extra_params or {})
        merged.update(payload)
        return merged
