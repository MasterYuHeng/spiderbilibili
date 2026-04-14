export interface ApiErrorPayload {
  code: string;
  details: Record<string, unknown> | unknown[] | string | null;
}

export interface ApiResponse<T> {
  success: boolean;
  message: string;
  data: T | null;
  error: ApiErrorPayload | null;
  request_id: string | null;
}

export type AiKeySource = 'runtime' | 'environment' | 'unset';

export interface DeepSeekConfig {
  provider: 'deepseek';
  effective_provider: string;
  api_key: string;
  api_key_configured: boolean;
  key_source: AiKeySource;
  base_url: string;
  model: string;
  fallback_model: string | null;
  timeout_seconds: number;
  max_retries: number;
  updated_at: string | null;
}

export interface BilibiliAccountProfile {
  is_login: boolean;
  mid: string | null;
  username: string | null;
  level: number | null;
  avatar_url: string | null;
}

export interface BrowserProfile {
  id: string;
  label: string;
  directory_name: string;
  cookie_db_exists: boolean;
}

export interface BrowserSource {
  browser: string;
  label: string;
  user_data_dir: string;
  default_profile_id: string | null;
  profiles: BrowserProfile[];
}

export interface BilibiliConfig {
  provider: 'bilibili';
  cookie: string;
  cookie_configured: boolean;
  key_source: AiKeySource;
  sessdata: string;
  bili_jct: string;
  dede_user_id: string;
  buvid3: string;
  buvid4: string;
  account_profile: BilibiliAccountProfile | null;
  import_summary: string | null;
  validation_message: string | null;
  browser_sources: BrowserSource[];
  updated_at: string | null;
}

export interface AiSettingsPayload {
  deepseek: DeepSeekConfig;
  bilibili: BilibiliConfig;
}

export type TaskStatus =
  | 'pending'
  | 'queued'
  | 'running'
  | 'paused'
  | 'partial_success'
  | 'success'
  | 'failed'
  | 'cancelled';

export type ExportDataset = 'videos' | 'topics' | 'summaries';
export type ExportFormat = 'json' | 'csv' | 'excel';
export type TaskCrawlMode = 'keyword' | 'hot';
export type TaskSearchScope = 'site' | 'partition';
export type KeywordSynonymCount = 1 | 2 | 3 | 5;
export type VideoSortBy =
  | 'composite_score'
  | 'heat_score'
  | 'relevance_score'
  | 'published_at'
  | 'view_count'
  | 'like_count'
  | 'coin_count'
  | 'favorite_count'
  | 'share_count'
  | 'reply_count'
  | 'danmaku_count'
  | 'like_view_ratio';

export interface TaskLog {
  id: string;
  level: string;
  stage: string;
  message: string;
  payload: Record<string, unknown> | unknown[] | string | null;
  created_at: string;
}

export interface TaskSummary {
  id: string;
  keyword: string;
  status: TaskStatus;
  requested_video_limit: number;
  max_pages: number;
  min_sleep_seconds: number;
  max_sleep_seconds: number;
  enable_proxy: boolean;
  source_ip_strategy: string;
  total_candidates: number;
  processed_videos: number;
  analyzed_videos: number;
  clustered_topics: number;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export type KeywordExpansionStatus =
  | 'skipped'
  | 'pending'
  | 'success'
  | 'fallback'
  | 'failed';

export interface KeywordExpansionPayload {
  source_keyword: string;
  enabled: boolean;
  requested_synonym_count: KeywordSynonymCount | null;
  generated_synonyms: string[];
  expanded_keywords: string[];
  status: KeywordExpansionStatus | string;
  model_name: string | null;
  error_message: string | null;
  generated_at: string | null;
}

export interface TaskDetail extends TaskSummary {
  extra_params: Record<string, unknown> | null;
  keyword_expansion: KeywordExpansionPayload | null;
  search_keywords_used: string[];
  expanded_keyword_count: number;
  current_stage: string;
  progress_percent: number;
  log_total: number;
  logs_truncated: boolean;
  logs: TaskLog[];
}

export interface TaskDispatch {
  celery_task_id: string | null;
  task_name: string;
}

export interface TaskCreatePayload {
  task: TaskDetail;
  dispatch: TaskDispatch;
}

export interface TaskDeletePayload {
  task_id: string;
  deleted: boolean;
  deleted_at?: string | null;
}

export interface TaskRestorePayload {
  task_id: string;
  restored: boolean;
}

export interface TaskBulkDeletePayload {
  deleted_count: number;
  blocked_count?: number;
}

export interface TaskListPayload {
  items: TaskSummary[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface TaskProgressPayload {
  task_id: string;
  status: TaskStatus;
  current_stage: string;
  progress_percent: number;
  total_candidates: number;
  processed_videos: number;
  analyzed_videos: number;
  clustered_topics: number;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
  extra_params: Record<string, unknown> | null;
  keyword_expansion: KeywordExpansionPayload | null;
  search_keywords_used: string[];
  expanded_keyword_count: number;
  latest_log: TaskLog | null;
}

export interface TaskVideoMetrics {
  view_count: number;
  like_count: number;
  coin_count: number;
  favorite_count: number;
  share_count: number;
  reply_count: number;
  danmaku_count: number;
  like_view_ratio: number | null;
  coin_view_ratio: number | null;
  favorite_view_ratio: number | null;
  share_view_ratio: number | null;
  reply_view_ratio: number | null;
  danmaku_view_ratio: number | null;
  engagement_rate: number | null;
  captured_at: string | null;
}

export interface TaskVideoText {
  has_description: boolean;
  has_subtitle: boolean;
  language_code: string;
  description_text: string | null;
  subtitle_text: string | null;
  combined_text_preview: string;
}

export interface TaskVideoAiSummary {
  summary: string;
  topics: string[];
  primary_topic: string | null;
  tone: string | null;
  confidence: number | null;
  model_name: string | null;
}

export interface TaskVideoResult {
  video_id: string;
  bvid: string;
  aid: number | null;
  title: string;
  url: string;
  author_name: string | null;
  author_mid: string | null;
  cover_url: string | null;
  description: string | null;
  tags: string[];
  published_at: string | null;
  duration_seconds: number | null;
  search_rank: number | null;
  matched_keywords: string[];
  primary_matched_keyword: string | null;
  keyword_match_count: number;
  keyword_hit_title: boolean;
  keyword_hit_description: boolean;
  keyword_hit_tags: boolean;
  relevance_score: number;
  heat_score: number;
  composite_score: number;
  is_selected: boolean;
  metrics: TaskVideoMetrics;
  text_content: TaskVideoText | null;
  ai_summary: TaskVideoAiSummary | null;
}

export interface TaskVideoListPayload {
  task_id: string;
  items: TaskVideoResult[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface TopicRepresentativeVideo {
  video_id: string;
  bvid: string;
  title: string;
  url: string;
  composite_score: number;
}

export interface TaskTopic {
  id: string;
  name: string;
  normalized_name: string;
  description: string | null;
  keywords: string[];
  video_count: number;
  total_heat_score: number;
  average_heat_score: number;
  video_ratio: number | null;
  average_engagement_rate: number | null;
  cluster_order: number | null;
  representative_video: TopicRepresentativeVideo | null;
}

export interface TaskTopicListPayload {
  task_id: string;
  items: TaskTopic[];
}

export interface TaskAnalysisSummary {
  total_videos: number;
  average_view_count: number;
  average_like_count: number;
  average_coin_count: number;
  average_favorite_count: number;
  average_share_count: number;
  average_reply_count: number;
  average_danmaku_count: number;
  average_composite_score: number;
  average_engagement_rate: number;
}

export interface TaskAnalysisCooccurrence {
  left: string;
  right: string;
  count: number;
}

export interface TaskAnalysisTimeBucket {
  bucket: string;
  video_count: number;
}

export interface TaskAnalysisCorrelation {
  metric: string;
  correlation: number | null;
}

export interface TaskAnalysisVideoHistoryPoint {
  label: string;
  captured_at: string | null;
  view_count: number;
  like_count: number;
  share_count: number;
  danmaku_count: number;
}

export interface TaskAnalysisVideoInsight {
  video_id: string;
  bvid: string;
  title: string;
  url: string;
  author_name: string | null;
  author_mid: string | null;
  cover_url: string | null;
  published_at: string | null;
  topic_name: string | null;
  composite_score: number;
  heat_score: number;
  relevance_score: number;
  view_count: number;
  like_count: number;
  share_count: number;
  engagement_rate: number | null;
  like_view_ratio: number | null;
  coin_view_ratio: number | null;
  favorite_view_ratio: number | null;
  share_view_ratio: number | null;
  reply_view_ratio: number | null;
  danmaku_view_ratio: number | null;
  search_play_count: number | null;
  search_to_current_view_growth_ratio: number | null;
  published_hours: number | null;
  views_per_hour_since_publish: number | null;
  views_per_day_since_publish: number | null;
  historical_snapshot_count: number;
  historical_view_growth_ratio: number | null;
  historical_view_velocity_per_hour: number | null;
  burst_score: number | null;
  depth_score: number | null;
  community_score: number | null;
  completion_proxy_score: number | null;
  history: TaskAnalysisVideoHistoryPoint[];
}

export interface TaskAnalysisTopicInsight {
  topic_id: string;
  topic_name: string;
  video_count: number;
  total_heat_score: number;
  average_view_count: number;
  average_engagement_rate: number;
  average_like_view_ratio: number | null;
  average_share_rate: number | null;
  average_burst_score: number | null;
  average_depth_score: number | null;
  average_community_score: number | null;
  historical_coverage_ratio: number | null;
  latest_publish_at: string | null;
  representative_video: TopicRepresentativeVideo | null;
  summary: string | null;
}

export interface TaskAnalysisTopicTrendPoint {
  bucket: string;
  video_count: number;
  total_heat_score: number;
  topic_heat_index: number;
  average_burst_score: number | null;
  average_community_score: number | null;
}

export interface TaskAnalysisTopicTrend {
  topic_id: string;
  topic_name: string;
  trend_direction: 'rising' | 'cooling' | 'stable' | string;
  latest_bucket: string | null;
  latest_topic_heat_index: number | null;
  peak_bucket: string | null;
  peak_topic_heat_index: number | null;
  points: TaskAnalysisTopicTrendPoint[];
}

export interface TaskAnalysisRecommendation {
  key: string;
  title: string;
  description: string | null;
  topic_name: string | null;
  videos: TaskAnalysisVideoInsight[];
}

export interface TaskAnalysisAuthorRepresentativeVideo {
  bvid: string;
  title: string;
  url: string;
  topic_name: string | null;
  composite_score: number | null;
}

export interface TaskAnalysisAuthorVideo {
  bvid: string;
  title: string;
  url: string;
  description: string | null;
  published_at: string | null;
  duration_seconds: number | null;
  view_count: number;
  like_count: number;
  coin_count: number;
  favorite_count: number;
  share_count: number;
  reply_count: number;
  danmaku_count: number;
  like_view_ratio: number | null;
  engagement_rate: number | null;
  tags: string[];
  summary: string | null;
  ai_summary: string | null;
  content_focus: string[];
}

export interface TaskAnalysisPopularAuthor {
  author_name: string;
  author_mid: string | null;
  source_video_count: number;
  source_topic_count: number;
  source_total_heat_score: number;
  source_total_composite_score: number;
  source_average_engagement_rate: number;
  source_average_view_count: number;
  popularity_score: number;
  dominant_topics: string[];
  style_tags: string[];
  selection_reasons: string[];
  representative_video: TaskAnalysisAuthorRepresentativeVideo | null;
  fetched_video_count: number;
  fetched_average_view_count: number;
  fetched_average_engagement_rate: number;
  recent_publish_count: number;
  summary_basis: string;
  summary_text: string | null;
  ai_creator_profile: string | null;
  ai_recent_content_summary: string | null;
  ai_content_strategy: string[];
  content_keywords: string[];
  analysis_points: string[];
  videos: TaskAnalysisAuthorVideo[];
}

export interface TaskAnalysisTopicHotAuthor {
  topic_id: string;
  topic_name: string;
  authors: TaskAnalysisPopularAuthor[];
}

export interface TaskAnalysisLatestHotTopic {
  topic: TaskAnalysisTopicInsight | null;
  reason: string | null;
  supporting_points: string[];
}

export interface TaskAnalysisMetricDefinition {
  key: string;
  name: string;
  category: string;
  meaning: string;
  formula: string;
  interpretation: string;
  limitations: string | null;
}

export interface TaskAnalysisMetricWeightComponent {
  key: string;
  label: string;
  weight: number;
  default_weight: number;
  effective_weight: number;
}

export interface TaskAnalysisMetricWeightConfig {
  metric_key: string;
  metric_name: string;
  category: string;
  formula: string;
  normalization_note: string | null;
  customized: boolean;
  components: TaskAnalysisMetricWeightComponent[];
}

export interface TaskAnalysisMetricWeightComponentWrite {
  key: string;
  weight: number;
}

export interface TaskAnalysisMetricWeightConfigWrite {
  metric_key: string;
  components: TaskAnalysisMetricWeightComponentWrite[];
}

export interface TaskAnalysisWeightsUpdateRequest {
  metrics: TaskAnalysisMetricWeightConfigWrite[];
}

export interface TaskAnalysisAdvanced {
  hot_topics: TaskTopic[];
  keyword_cooccurrence: TaskAnalysisCooccurrence[];
  publish_date_distribution: TaskAnalysisTimeBucket[];
  duration_heat_correlation: TaskAnalysisCorrelation;
  momentum_topics: TaskAnalysisTopicInsight[];
  explosive_videos: TaskAnalysisVideoInsight[];
  depth_topics: TaskAnalysisTopicInsight[];
  deep_videos: TaskAnalysisVideoInsight[];
  community_topics: TaskAnalysisTopicInsight[];
  community_videos: TaskAnalysisVideoInsight[];
  topic_evolution: TaskAnalysisTopicTrend[];
  latest_hot_topic: TaskAnalysisLatestHotTopic;
  topic_insights: TaskAnalysisTopicInsight[];
  video_insights: TaskAnalysisVideoInsight[];
  metric_definitions: TaskAnalysisMetricDefinition[];
  metric_weight_configs: TaskAnalysisMetricWeightConfig[];
  recommendations: TaskAnalysisRecommendation[];
  popular_authors: TaskAnalysisPopularAuthor[];
  topic_hot_authors: TaskAnalysisTopicHotAuthor[];
  author_analysis_notes: string[];
  data_notes: string[];
}

export interface TaskAnalysisPayload {
  task_id: string;
  status: TaskStatus;
  generated_at: string;
  summary: TaskAnalysisSummary;
  topics: TaskTopic[];
  top_videos: TaskVideoResult[];
  advanced: TaskAnalysisAdvanced;
  has_ai_summaries: boolean;
  has_topics: boolean;
}

export interface TaskReportSection {
  key: string;
  title: string;
  summary: string;
  bullets: string[];
  evidence: string[];
}

export interface TaskReportAiOutput {
  key: string;
  title: string;
  audience: string;
  content: string;
  generation_mode: string;
  model_name: string | null;
}

export interface TaskReportPayload {
  task_id: string;
  status: TaskStatus;
  generated_at: string;
  task_keyword: string | null;
  title: string;
  subtitle: string | null;
  executive_summary: string;
  latest_hot_topic_name: string | null;
  keyword_expansion: KeywordExpansionPayload | null;
  search_keywords_used: string[];
  expanded_keyword_count: number;
  featured_videos: TaskAnalysisVideoInsight[];
  recommendations: TaskAnalysisRecommendation[];
  popular_authors: TaskAnalysisPopularAuthor[];
  topic_hot_authors: TaskAnalysisTopicHotAuthor[];
  sections: TaskReportSection[];
  ai_outputs: TaskReportAiOutput[];
  report_markdown: string;
}

export interface TaskAcceptanceCheck {
  code: string;
  title: string;
  status: 'pass' | 'warn' | 'fail';
  message: string;
  actual: unknown;
  expected: unknown;
}

export interface TaskAcceptanceSection {
  name: string;
  checks: TaskAcceptanceCheck[];
}

export interface TaskAcceptancePayload {
  task_id: string;
  task_status: TaskStatus;
  overall_status: 'pass' | 'warn' | 'fail';
  sections: TaskAcceptanceSection[];
}

export interface TaskCreateRequest {
  keyword: string;
  crawl_mode: TaskCrawlMode | null;
  search_scope: TaskSearchScope | null;
  partition_tid: number | null;
  partition_name: string | null;
  published_within_days: number | null;
  requested_video_limit: number | null;
  max_pages: number | null;
  hot_author_total_count: number | null;
  topic_hot_author_count: number | null;
  hot_author_video_limit: number | null;
  hot_author_summary_basis: 'time' | 'heat' | null;
  enable_proxy: boolean | null;
  min_sleep_seconds: number | null;
  max_sleep_seconds: number | null;
  source_ip_strategy: string | null;
  enable_keyword_synonym_expansion?: boolean | null;
  keyword_synonym_count?: KeywordSynonymCount | null;
}

export interface ListTaskParams {
  page?: number;
  page_size?: number;
  status?: TaskStatus;
}

export interface VideoQueryParams {
  page?: number;
  page_size?: number;
  sort_by?: VideoSortBy;
  sort_order?: 'asc' | 'desc';
  topic?: string | null;
  min_view_count?: number | null;
  max_view_count?: number | null;
  min_like_count?: number | null;
  max_like_count?: number | null;
  min_coin_count?: number | null;
  max_coin_count?: number | null;
  min_favorite_count?: number | null;
  max_favorite_count?: number | null;
  min_share_count?: number | null;
  max_share_count?: number | null;
  min_reply_count?: number | null;
  max_reply_count?: number | null;
  min_danmaku_count?: number | null;
  max_danmaku_count?: number | null;
  min_relevance_score?: number | null;
  max_relevance_score?: number | null;
  min_heat_score?: number | null;
  max_heat_score?: number | null;
  min_composite_score?: number | null;
  max_composite_score?: number | null;
  min_like_view_ratio?: number | null;
  max_like_view_ratio?: number | null;
}

export interface DownloadArtifact {
  blob: Blob;
  filename: string;
}
