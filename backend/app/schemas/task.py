from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

ALLOWED_IP_STRATEGIES = {"local_sleep", "proxy_pool", "custom_proxy"}
ALLOWED_CRAWL_MODES = {"keyword", "hot"}
ALLOWED_SEARCH_SCOPES = {"site", "partition"}
ALLOWED_HOT_AUTHOR_SUMMARY_BASES = {"time", "heat"}
ALLOWED_KEYWORD_SYNONYM_COUNTS = {1, 2, 3, 5}


class TaskCreateRequest(BaseModel):
    crawl_mode: str | None = Field(default="keyword", max_length=50)
    keyword: str | None = Field(default=None, max_length=255)
    search_scope: str | None = Field(default="site", max_length=50)
    partition_tid: int | None = Field(default=None, ge=1)
    partition_name: str | None = Field(default=None, max_length=100)
    published_within_days: int | None = Field(default=None, ge=1, le=3650)
    requested_video_limit: int | None = Field(default=None, ge=1)
    max_pages: int | None = Field(default=None, ge=1)
    hot_author_total_count: int | None = Field(default=None, ge=0, le=50)
    topic_hot_author_count: int | None = Field(default=None, ge=0, le=10)
    hot_author_video_limit: int | None = Field(default=None, ge=1, le=50)
    hot_author_summary_basis: str | None = Field(default=None, max_length=20)
    enable_proxy: bool | None = None
    min_sleep_seconds: float | None = Field(default=None, gt=0)
    max_sleep_seconds: float | None = Field(default=None, gt=0)
    source_ip_strategy: str | None = Field(default=None, max_length=50)
    enable_keyword_synonym_expansion: bool | None = None
    keyword_synonym_count: int | None = Field(default=None, ge=1)

    @field_validator("crawl_mode")
    @classmethod
    def validate_crawl_mode(cls, value: str | None) -> str:
        normalized = (value or "keyword").strip()
        if normalized not in ALLOWED_CRAWL_MODES:
            allowed_values = ", ".join(sorted(ALLOWED_CRAWL_MODES))
            raise ValueError(f"crawl_mode must be one of: {allowed_values}.")
        return normalized

    @field_validator("keyword")
    @classmethod
    def validate_keyword(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        return normalized or None

    @field_validator("search_scope")
    @classmethod
    def validate_search_scope(cls, value: str | None) -> str:
        normalized = (value or "site").strip()
        if normalized not in ALLOWED_SEARCH_SCOPES:
            allowed_values = ", ".join(sorted(ALLOWED_SEARCH_SCOPES))
            raise ValueError(f"search_scope must be one of: {allowed_values}.")
        return normalized

    @field_validator("partition_name")
    @classmethod
    def validate_partition_name(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        return normalized or None

    @field_validator("source_ip_strategy")
    @classmethod
    def validate_source_ip_strategy(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        if normalized not in ALLOWED_IP_STRATEGIES:
            allowed_values = ", ".join(sorted(ALLOWED_IP_STRATEGIES))
            raise ValueError(f"source_ip_strategy must be one of: {allowed_values}.")
        return normalized

    @field_validator("hot_author_summary_basis")
    @classmethod
    def validate_hot_author_summary_basis(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        if normalized not in ALLOWED_HOT_AUTHOR_SUMMARY_BASES:
            allowed_values = ", ".join(sorted(ALLOWED_HOT_AUTHOR_SUMMARY_BASES))
            raise ValueError(
                f"hot_author_summary_basis must be one of: {allowed_values}."
            )
        return normalized

    @model_validator(mode="after")
    def validate_partition_scope(self) -> "TaskCreateRequest":
        if self.crawl_mode == "keyword" and not self.keyword:
            raise ValueError("keyword is required when crawl_mode is keyword.")

        if self.crawl_mode == "hot":
            self.keyword = "当前热度"

        if self.search_scope == "partition" and self.partition_tid is None:
            raise ValueError(
                "partition_tid is required when search_scope is partition."
            )

        if self.search_scope != "partition":
            self.partition_tid = None
            self.partition_name = None

        hot_author_total_count = self.hot_author_total_count or 0
        topic_hot_author_count = self.topic_hot_author_count or 0
        if hot_author_total_count > 0 or topic_hot_author_count > 0:
            if self.hot_author_video_limit is None:
                self.hot_author_video_limit = 10
            if self.hot_author_summary_basis is None:
                self.hot_author_summary_basis = "time"
        else:
            self.hot_author_video_limit = self.hot_author_video_limit or 10
            self.hot_author_summary_basis = self.hot_author_summary_basis or "time"

        if self.crawl_mode != "keyword":
            self.enable_keyword_synonym_expansion = False
            self.keyword_synonym_count = None
            return self

        self.enable_keyword_synonym_expansion = bool(
            self.enable_keyword_synonym_expansion
        )
        if not self.enable_keyword_synonym_expansion:
            self.keyword_synonym_count = None
            return self

        if self.keyword_synonym_count is None:
            raise ValueError(
                "keyword_synonym_count is required when "
                "keyword synonym expansion is enabled."
            )

        if self.keyword_synonym_count not in ALLOWED_KEYWORD_SYNONYM_COUNTS:
            allowed_values = ", ".join(
                str(item) for item in sorted(ALLOWED_KEYWORD_SYNONYM_COUNTS)
            )
            raise ValueError(
                "keyword_synonym_count must be one of: "
                f"{allowed_values} when keyword synonym expansion is enabled."
            )

        return self


class TaskLogRead(BaseModel):
    id: str
    level: str
    stage: str
    message: str
    payload: dict[str, Any] | list[Any] | str | None = None
    created_at: datetime


class TaskSummary(BaseModel):
    id: str
    keyword: str
    status: str
    requested_video_limit: int
    max_pages: int
    min_sleep_seconds: float
    max_sleep_seconds: float
    enable_proxy: bool
    source_ip_strategy: str
    total_candidates: int
    processed_videos: int
    analyzed_videos: int
    clustered_topics: int
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class KeywordExpansionRead(BaseModel):
    source_keyword: str
    enabled: bool
    requested_synonym_count: int | None = None
    generated_synonyms: list[str] = Field(default_factory=list)
    expanded_keywords: list[str] = Field(default_factory=list)
    status: str
    model_name: str | None = None
    error_message: str | None = None
    generated_at: str | None = None


class TaskDetail(TaskSummary):
    extra_params: dict[str, Any] | None = None
    keyword_expansion: KeywordExpansionRead | None = None
    search_keywords_used: list[str] = Field(default_factory=list)
    expanded_keyword_count: int = 0
    current_stage: str
    progress_percent: int
    log_total: int = 0
    logs_truncated: bool = False
    logs: list[TaskLogRead] = Field(default_factory=list)


class TaskDispatchRead(BaseModel):
    celery_task_id: str | None = None
    task_name: str


class TaskCreatePayload(BaseModel):
    task: TaskDetail
    dispatch: TaskDispatchRead


class TaskDeletePayload(BaseModel):
    task_id: str
    deleted: bool = True
    deleted_at: datetime | None = None


class TaskRestorePayload(BaseModel):
    task_id: str
    restored: bool = True


class TaskBulkDeletePayload(BaseModel):
    deleted_count: int
    blocked_count: int = 0


class TaskListPayload(BaseModel):
    items: list[TaskSummary]
    page: int
    page_size: int
    total: int
    total_pages: int


class TaskProgressPayload(BaseModel):
    task_id: str
    status: str
    current_stage: str
    progress_percent: int
    total_candidates: int
    processed_videos: int
    analyzed_videos: int
    clustered_topics: int
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    extra_params: dict[str, Any] | None = None
    keyword_expansion: KeywordExpansionRead | None = None
    search_keywords_used: list[str] = Field(default_factory=list)
    expanded_keyword_count: int = 0
    latest_log: TaskLogRead | None = None


class TaskVideoMetricsRead(BaseModel):
    view_count: int = 0
    like_count: int = 0
    coin_count: int = 0
    favorite_count: int = 0
    share_count: int = 0
    reply_count: int = 0
    danmaku_count: int = 0
    like_view_ratio: float | None = None
    coin_view_ratio: float | None = None
    favorite_view_ratio: float | None = None
    share_view_ratio: float | None = None
    reply_view_ratio: float | None = None
    danmaku_view_ratio: float | None = None
    engagement_rate: float | None = None
    captured_at: datetime | None = None


class TaskVideoTextRead(BaseModel):
    has_description: bool
    has_subtitle: bool
    language_code: str
    description_text: str | None = None
    subtitle_text: str | None = None
    combined_text_preview: str


class TaskVideoAiSummaryRead(BaseModel):
    summary: str
    topics: list[str] = Field(default_factory=list)
    primary_topic: str | None = None
    tone: str | None = None
    confidence: float | None = None
    model_name: str | None = None


class TaskVideoResultRead(BaseModel):
    video_id: str
    bvid: str
    aid: int | None = None
    title: str
    url: str
    author_name: str | None = None
    author_mid: str | None = None
    cover_url: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    published_at: datetime | None = None
    duration_seconds: int | None = None
    search_rank: int | None = None
    matched_keywords: list[str] = Field(default_factory=list)
    primary_matched_keyword: str | None = None
    keyword_match_count: int = 0
    keyword_hit_title: bool
    keyword_hit_description: bool
    keyword_hit_tags: bool
    relevance_score: float
    heat_score: float
    composite_score: float
    is_selected: bool
    metrics: TaskVideoMetricsRead
    text_content: TaskVideoTextRead | None = None
    ai_summary: TaskVideoAiSummaryRead | None = None


class TaskVideoListPayload(BaseModel):
    task_id: str
    items: list[TaskVideoResultRead]
    page: int
    page_size: int
    total: int
    total_pages: int


class TopicRepresentativeVideoRead(BaseModel):
    video_id: str
    bvid: str
    title: str
    url: str
    composite_score: float


class TaskTopicRead(BaseModel):
    id: str
    name: str
    normalized_name: str
    description: str | None = None
    keywords: list[str] = Field(default_factory=list)
    video_count: int
    total_heat_score: float
    average_heat_score: float
    video_ratio: float | None = None
    average_engagement_rate: float | None = None
    cluster_order: int | None = None
    representative_video: TopicRepresentativeVideoRead | None = None


class TaskTopicListPayload(BaseModel):
    task_id: str
    items: list[TaskTopicRead]


class TaskAnalysisSummaryRead(BaseModel):
    total_videos: int
    average_view_count: float
    average_like_count: float
    average_coin_count: float
    average_favorite_count: float
    average_share_count: float
    average_reply_count: float
    average_danmaku_count: float
    average_composite_score: float
    average_engagement_rate: float


class TaskAnalysisCooccurrenceRead(BaseModel):
    left: str
    right: str
    count: int


class TaskAnalysisTimeBucketRead(BaseModel):
    bucket: str
    video_count: int


class TaskAnalysisCorrelationRead(BaseModel):
    metric: str
    correlation: float | None = None


class TaskAnalysisVideoHistoryPointRead(BaseModel):
    label: str
    captured_at: datetime | None = None
    view_count: int = 0
    like_count: int = 0
    share_count: int = 0
    danmaku_count: int = 0


class TaskAnalysisVideoInsightRead(BaseModel):
    video_id: str
    bvid: str
    title: str
    url: str
    author_name: str | None = None
    author_mid: str | None = None
    cover_url: str | None = None
    published_at: datetime | None = None
    topic_name: str | None = None
    composite_score: float
    heat_score: float
    relevance_score: float
    view_count: int = 0
    like_count: int = 0
    share_count: int = 0
    engagement_rate: float | None = None
    like_view_ratio: float | None = None
    coin_view_ratio: float | None = None
    favorite_view_ratio: float | None = None
    share_view_ratio: float | None = None
    reply_view_ratio: float | None = None
    danmaku_view_ratio: float | None = None
    search_play_count: int | None = None
    search_to_current_view_growth_ratio: float | None = None
    published_hours: float | None = None
    views_per_hour_since_publish: float | None = None
    views_per_day_since_publish: float | None = None
    historical_snapshot_count: int = 0
    historical_view_growth_ratio: float | None = None
    historical_view_velocity_per_hour: float | None = None
    burst_score: float | None = None
    depth_score: float | None = None
    community_score: float | None = None
    completion_proxy_score: float | None = None
    history: list[TaskAnalysisVideoHistoryPointRead] = Field(default_factory=list)


class TaskAnalysisTopicInsightRead(BaseModel):
    topic_id: str
    topic_name: str
    video_count: int
    total_heat_score: float
    average_view_count: float
    average_engagement_rate: float
    average_like_view_ratio: float | None = None
    average_share_rate: float | None = None
    average_burst_score: float | None = None
    average_depth_score: float | None = None
    average_community_score: float | None = None
    historical_coverage_ratio: float | None = None
    latest_publish_at: datetime | None = None
    representative_video: TopicRepresentativeVideoRead | None = None
    summary: str | None = None


class TaskAnalysisTopicTrendPointRead(BaseModel):
    bucket: str
    video_count: int
    total_heat_score: float
    topic_heat_index: float
    average_burst_score: float | None = None
    average_community_score: float | None = None


class TaskAnalysisTopicTrendRead(BaseModel):
    topic_id: str
    topic_name: str
    trend_direction: str
    latest_bucket: str | None = None
    latest_topic_heat_index: float | None = None
    peak_bucket: str | None = None
    peak_topic_heat_index: float | None = None
    points: list[TaskAnalysisTopicTrendPointRead] = Field(default_factory=list)


class TaskAnalysisRecommendationRead(BaseModel):
    key: str
    title: str
    description: str | None = None
    topic_name: str | None = None
    videos: list[TaskAnalysisVideoInsightRead] = Field(default_factory=list)


class TaskAnalysisAuthorRepresentativeVideoRead(BaseModel):
    bvid: str
    title: str
    url: str
    topic_name: str | None = None
    composite_score: float | None = None


class TaskAnalysisAuthorVideoRead(BaseModel):
    bvid: str
    title: str
    url: str
    description: str | None = None
    published_at: datetime | None = None
    duration_seconds: int | None = None
    view_count: int = 0
    like_count: int = 0
    coin_count: int = 0
    favorite_count: int = 0
    share_count: int = 0
    reply_count: int = 0
    danmaku_count: int = 0
    like_view_ratio: float | None = None
    engagement_rate: float | None = None
    tags: list[str] = Field(default_factory=list)
    summary: str | None = None
    ai_summary: str | None = None
    content_focus: list[str] = Field(default_factory=list)


class TaskAnalysisPopularAuthorRead(BaseModel):
    author_name: str
    author_mid: str | None = None
    source_video_count: int
    source_topic_count: int
    source_total_heat_score: float
    source_total_composite_score: float
    source_average_engagement_rate: float
    source_average_view_count: float
    popularity_score: float
    dominant_topics: list[str] = Field(default_factory=list)
    style_tags: list[str] = Field(default_factory=list)
    selection_reasons: list[str] = Field(default_factory=list)
    representative_video: TaskAnalysisAuthorRepresentativeVideoRead | None = None
    fetched_video_count: int = 0
    fetched_average_view_count: float = 0
    fetched_average_engagement_rate: float = 0
    recent_publish_count: int = 0
    summary_basis: str
    summary_text: str | None = None
    ai_creator_profile: str | None = None
    ai_recent_content_summary: str | None = None
    ai_content_strategy: list[str] = Field(default_factory=list)
    content_keywords: list[str] = Field(default_factory=list)
    analysis_points: list[str] = Field(default_factory=list)
    videos: list[TaskAnalysisAuthorVideoRead] = Field(default_factory=list)


class TaskAnalysisTopicHotAuthorRead(BaseModel):
    topic_id: str
    topic_name: str
    authors: list[TaskAnalysisPopularAuthorRead] = Field(default_factory=list)


class TaskAnalysisLatestHotTopicRead(BaseModel):
    topic: TaskAnalysisTopicInsightRead | None = None
    reason: str | None = None
    supporting_points: list[str] = Field(default_factory=list)


class TaskAnalysisMetricDefinitionRead(BaseModel):
    key: str
    name: str
    category: str
    meaning: str
    formula: str
    interpretation: str
    limitations: str | None = None


class TaskAnalysisMetricWeightComponentRead(BaseModel):
    key: str
    label: str
    weight: float = Field(ge=0)
    default_weight: float = Field(ge=0)
    effective_weight: float = Field(ge=0)


class TaskAnalysisMetricWeightConfigRead(BaseModel):
    metric_key: str
    metric_name: str
    category: str
    formula: str
    normalization_note: str | None = None
    customized: bool = False
    components: list[TaskAnalysisMetricWeightComponentRead] = Field(
        default_factory=list
    )


class TaskAnalysisMetricWeightComponentWrite(BaseModel):
    key: str = Field(min_length=1, max_length=100)
    weight: float = Field(ge=0)


class TaskAnalysisMetricWeightConfigWrite(BaseModel):
    metric_key: str = Field(min_length=1, max_length=100)
    components: list[TaskAnalysisMetricWeightComponentWrite] = Field(
        default_factory=list
    )


class TaskAnalysisWeightsUpdateRequest(BaseModel):
    metrics: list[TaskAnalysisMetricWeightConfigWrite] = Field(
        default_factory=list,
        min_length=1,
    )


class TaskAnalysisAdvancedRead(BaseModel):
    hot_topics: list[TaskTopicRead] = Field(default_factory=list)
    keyword_cooccurrence: list[TaskAnalysisCooccurrenceRead] = Field(
        default_factory=list
    )
    publish_date_distribution: list[TaskAnalysisTimeBucketRead] = Field(
        default_factory=list
    )
    duration_heat_correlation: TaskAnalysisCorrelationRead
    momentum_topics: list[TaskAnalysisTopicInsightRead] = Field(default_factory=list)
    explosive_videos: list[TaskAnalysisVideoInsightRead] = Field(default_factory=list)
    depth_topics: list[TaskAnalysisTopicInsightRead] = Field(default_factory=list)
    deep_videos: list[TaskAnalysisVideoInsightRead] = Field(default_factory=list)
    community_topics: list[TaskAnalysisTopicInsightRead] = Field(default_factory=list)
    community_videos: list[TaskAnalysisVideoInsightRead] = Field(default_factory=list)
    topic_evolution: list[TaskAnalysisTopicTrendRead] = Field(default_factory=list)
    latest_hot_topic: TaskAnalysisLatestHotTopicRead = Field(
        default_factory=TaskAnalysisLatestHotTopicRead
    )
    topic_insights: list[TaskAnalysisTopicInsightRead] = Field(default_factory=list)
    video_insights: list[TaskAnalysisVideoInsightRead] = Field(default_factory=list)
    metric_definitions: list[TaskAnalysisMetricDefinitionRead] = Field(
        default_factory=list
    )
    metric_weight_configs: list[TaskAnalysisMetricWeightConfigRead] = Field(
        default_factory=list
    )
    recommendations: list[TaskAnalysisRecommendationRead] = Field(default_factory=list)
    popular_authors: list[TaskAnalysisPopularAuthorRead] = Field(default_factory=list)
    topic_hot_authors: list[TaskAnalysisTopicHotAuthorRead] = Field(
        default_factory=list
    )
    author_analysis_notes: list[str] = Field(default_factory=list)
    data_notes: list[str] = Field(default_factory=list)


class TaskAnalysisPayload(BaseModel):
    task_id: str
    status: str
    generated_at: datetime
    summary: TaskAnalysisSummaryRead
    topics: list[TaskTopicRead] = Field(default_factory=list)
    top_videos: list[TaskVideoResultRead] = Field(default_factory=list)
    advanced: TaskAnalysisAdvancedRead
    has_ai_summaries: bool
    has_topics: bool


class TaskReportSectionRead(BaseModel):
    key: str
    title: str
    summary: str
    bullets: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class TaskReportAiOutputRead(BaseModel):
    key: str
    title: str
    audience: str
    content: str
    generation_mode: str
    model_name: str | None = None


class TaskReportPayload(BaseModel):
    task_id: str
    status: str
    generated_at: datetime
    task_keyword: str | None = None
    title: str
    subtitle: str | None = None
    executive_summary: str
    latest_hot_topic_name: str | None = None
    keyword_expansion: KeywordExpansionRead | None = None
    search_keywords_used: list[str] = Field(default_factory=list)
    expanded_keyword_count: int = 0
    featured_videos: list[TaskAnalysisVideoInsightRead] = Field(default_factory=list)
    recommendations: list[TaskAnalysisRecommendationRead] = Field(default_factory=list)
    popular_authors: list[TaskAnalysisPopularAuthorRead] = Field(default_factory=list)
    topic_hot_authors: list[TaskAnalysisTopicHotAuthorRead] = Field(
        default_factory=list
    )
    sections: list[TaskReportSectionRead] = Field(default_factory=list)
    ai_outputs: list[TaskReportAiOutputRead] = Field(default_factory=list)
    report_markdown: str


class TaskAcceptanceCheckRead(BaseModel):
    code: str
    title: str
    status: str
    message: str
    actual: Any | None = None
    expected: Any | None = None


class TaskAcceptanceSectionRead(BaseModel):
    name: str
    checks: list[TaskAcceptanceCheckRead] = Field(default_factory=list)


class TaskAcceptancePayload(BaseModel):
    task_id: str
    task_status: str
    overall_status: str
    sections: list[TaskAcceptanceSectionRead] = Field(default_factory=list)
