<template>
  <div class="page-stack">
    <section class="page-hero">
      <div>
        <h3>结果筛选与优先级判断</h3>
      </div>
      <div class="page-hero__aside">
        <span>命中结果</span>
        <strong>{{ payload?.total ?? 0 }}</strong>
      </div>
    </section>

    <TaskLifecycleNotice
      v-if="taskProgress"
      :status="taskProgress.status"
      :error-message="taskProgress.error_message"
      :extra-params="taskProgress.extra_params"
      :latest-log-message="taskProgress.latest_log?.message ?? null"
      :current-stage="taskProgress.current_stage"
    />

    <TaskSearchContextCard
      v-if="taskProgress"
      :task-keyword="taskProgress.keyword_expansion?.source_keyword ?? workspaceStore.currentTaskLabel"
      :keyword-expansion="taskProgress.keyword_expansion"
      :search-keywords-used="taskProgress.search_keywords_used"
      :expanded-keyword-count="taskProgress.expanded_keyword_count"
      :crawl-mode="taskCrawlMode"
      title="搜索口径与命中来源"
      description="这里会说明任务实际使用了哪些搜索词，下面的视频列表也会标出每条视频是由哪个词召回的。"
      compact
    />

    <section class="panel-section">
      <div class="filter-layout">
        <section class="filter-card filter-card--compact">
          <div class="filter-card__header">
            <div>
              <h4>基础筛选</h4>
            </div>
            <button
              type="button"
              class="filter-card__toggle"
              @click="advancedFiltersVisible = !advancedFiltersVisible"
            >
              {{ advancedFiltersVisible ? '收起进阶筛选' : `展开进阶筛选（${activeFilterCount} 项已启用）` }}
            </button>
          </div>
          <div class="range-grid range-grid--triple">
            <div class="range-field">
              <span class="range-field__label">主题</span>
              <el-select v-model="filters.topic" clearable placeholder="按主题筛选">
                <el-option
                  v-for="topic in topics"
                  :key="topic.id"
                  :label="topic.name"
                  :value="topic.name"
                />
              </el-select>
            </div>

            <div class="range-field">
              <span class="range-field__label">排序字段</span>
              <el-select v-model="filters.sortBy">
                <el-option
                  v-for="option in sortOptions"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
            </div>

            <div class="range-field">
              <span class="range-field__label">排序方向</span>
              <el-select v-model="filters.sortOrder">
                <el-option label="降序" value="desc" />
                <el-option label="升序" value="asc" />
              </el-select>
            </div>
          </div>
        </section>

        <section
          v-for="group in visibleFilterGroups"
          :key="group.title"
          class="filter-card"
        >
          <div class="filter-card__header">
            <div>
              <h4>{{ group.title }}</h4>
            </div>
          </div>

          <div class="range-grid">
            <div
              v-for="field in group.fields"
              :key="field.minKey"
              class="range-field"
            >
              <span class="range-field__label">{{ field.label }}</span>
              <div class="range-field__pair">
                <el-input-number
                  v-model="filters[field.minKey]"
                  :min="0"
                  :step="field.step ?? 1"
                  controls-position="right"
                  :placeholder="`最小${field.label}`"
                />
                <span class="range-field__divider">至</span>
                <el-input-number
                  v-model="filters[field.maxKey]"
                  :min="0"
                  :step="field.step ?? 1"
                  controls-position="right"
                  :placeholder="`最大${field.label}`"
                />
              </div>
            </div>
          </div>
        </section>
      </div>

      <div class="toolbar">
        <div class="toolbar__actions">
          <el-button type="primary" @click="applyFilters">应用筛选</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </div>
        <div class="toolbar__actions">
          <el-select v-model="exportDataset" class="toolbar__field">
            <el-option label="视频数据" value="videos" />
            <el-option label="AI 摘要" value="summaries" />
          </el-select>
          <el-select v-model="exportFormat" class="toolbar__field">
            <el-option label="Excel" value="excel" />
            <el-option label="CSV" value="csv" />
            <el-option label="JSON" value="json" />
          </el-select>
          <el-button :loading="exporting" @click="handleExport">导出当前筛选结果</el-button>
        </div>
      </div>

      <el-table
        v-loading="loading"
        :data="payload?.items ?? []"
        row-key="video_id"
        class="app-table"
      >
        <el-table-column label="视频" min-width="320">
          <template #default="{ row }">
            <div class="video-cell">
              <a :href="row.url" target="_blank" rel="noreferrer">{{ row.title }}</a>
              <small>{{ row.author_name || '未知作者' }} / {{ formatDateTime(row.published_at) }}</small>
              <InsightText
                tag="p"
                :text="row.ai_summary?.summary || row.text_content?.combined_text_preview || row.description || '--'"
              />
            </div>
          </template>
        </el-table-column>

        <el-table-column label="主题" width="180">
          <template #default="{ row }">
            <div class="tag-cluster">
              <el-tag v-if="row.ai_summary?.primary_topic" effect="dark">
                {{ row.ai_summary.primary_topic }}
              </el-tag>
              <el-tag
                v-for="topic in row.ai_summary?.topics ?? []"
                :key="topic"
                type="info"
                effect="plain"
              >
                {{ topic }}
              </el-tag>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="命中来源词" width="220">
          <template #default="{ row }">
            <div v-if="row.matched_keywords.length" class="metric-stack">
              <span>主命中词 {{ row.primary_matched_keyword || '--' }}</span>
              <span>命中次数 {{ row.keyword_match_count }}</span>
              <div class="tag-cluster">
                <el-tag
                  v-for="keyword in row.matched_keywords"
                  :key="`${row.video_id}-${keyword}`"
                  effect="plain"
                  type="warning"
                >
                  {{ keyword }}
                </el-tag>
              </div>
            </div>
            <span v-else>--</span>
          </template>
        </el-table-column>

        <el-table-column label="核心指标" width="200">
          <template #default="{ row }">
            <div class="metric-stack">
              <span>播放 {{ formatCompactNumber(row.metrics.view_count) }}</span>
              <span>点赞 {{ formatCompactNumber(row.metrics.like_count) }}</span>
              <span>投币 {{ formatCompactNumber(row.metrics.coin_count) }}</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="互动指标" width="220">
          <template #default="{ row }">
            <div class="metric-stack">
              <span>收藏 {{ formatCompactNumber(row.metrics.favorite_count) }}</span>
              <span>分享 {{ formatCompactNumber(row.metrics.share_count) }}</span>
              <span>评论 {{ formatCompactNumber(row.metrics.reply_count) }}</span>
              <span>弹幕 {{ formatCompactNumber(row.metrics.danmaku_count) }}</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="比率与评分" width="220">
          <template #default="{ row }">
            <div class="metric-stack">
              <span>赞播比 {{ formatPercent(row.metrics.like_view_ratio, 2) }}</span>
              <span>综合 {{ formatScore(row.composite_score) }}</span>
              <span>热度 {{ formatScore(row.heat_score) }}</span>
              <span>相关 {{ formatScore(row.relevance_score) }}</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="时长 / 发布时间" width="180">
          <template #default="{ row }">
            <div class="metric-stack">
              <span>{{ formatDuration(row.duration_seconds) }}</span>
              <span>{{ formatDateTime(row.published_at) }}</span>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <EmptyState
        v-if="!loading && !(payload?.items.length)"
        :title="emptyState.title"
        :description="emptyState.description"
      />

      <div class="pagination-bar">
        <el-pagination
          background
          layout="prev, pager, next, sizes, total"
          :current-page="filters.page"
          :page-size="filters.pageSize"
          :page-sizes="[10, 20, 50]"
          :total="payload?.total ?? 0"
          @current-change="handlePageChange"
          @size-change="handleSizeChange"
        />
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { getErrorMessage, isRequestCanceled } from '@/api/client'
import { exportTaskResults, getTaskProgress, getTaskTopics, getTaskVideos } from '@/api/tasks'
import type {
  ExportDataset,
  ExportFormat,
  TaskProgressPayload,
  TaskTopic,
  TaskVideoListPayload,
  VideoSortBy,
} from '@/api/types'
import EmptyState from '@/components/common/EmptyState.vue'
import InsightText from '@/components/common/InsightText.vue'
import TaskLifecycleNotice from '@/components/tasks/TaskLifecycleNotice.vue'
import TaskSearchContextCard from '@/components/tasks/TaskSearchContextCard.vue'
import { useTaskWorkspaceStore, type VideoFilterState } from '@/stores/taskWorkspace'
import {
  formatCompactNumber,
  formatDateTime,
  formatDuration,
  formatPercent,
  formatScore,
  normalizeNullableNumber,
  triggerBlobDownload,
} from '@/utils/format'
import { isActiveTaskStatus } from '@/utils/taskStatus'

type NumericFilterKey = {
  [K in keyof VideoFilterState]: VideoFilterState[K] extends number | null ? K : never
}[keyof VideoFilterState]

interface RangeFieldConfig {
  label: string
  minKey: NumericFilterKey
  maxKey: NumericFilterKey
  step?: number
}

interface FilterGroup {
  title: string
  description: string
  hint?: string
  fields: RangeFieldConfig[]
}

const sortOptions: Array<{ label: string; value: VideoSortBy }> = [
  { label: '综合评分', value: 'composite_score' },
  { label: '热度分', value: 'heat_score' },
  { label: '相关性', value: 'relevance_score' },
  { label: '发布时间', value: 'published_at' },
  { label: '播放量', value: 'view_count' },
  { label: '点赞量', value: 'like_count' },
  { label: '投币量', value: 'coin_count' },
  { label: '收藏量', value: 'favorite_count' },
  { label: '分享量', value: 'share_count' },
  { label: '评论量', value: 'reply_count' },
  { label: '弹幕量', value: 'danmaku_count' },
  { label: '赞播比', value: 'like_view_ratio' },
]

const filterGroups: FilterGroup[] = [
  {
    title: '核心播放指标',
    description: '按播放、点赞、投币这些最常用的数据维度直接缩小结果。',
    fields: [
      { label: '播放量', minKey: 'minViewCount', maxKey: 'maxViewCount' },
      { label: '点赞量', minKey: 'minLikeCount', maxKey: 'maxLikeCount' },
      { label: '投币量', minKey: 'minCoinCount', maxKey: 'maxCoinCount' },
    ],
  },
  {
    title: '互动指标',
    description: '用收藏、分享、评论、弹幕细化互动表现。',
    fields: [
      { label: '收藏量', minKey: 'minFavoriteCount', maxKey: 'maxFavoriteCount' },
      { label: '分享量', minKey: 'minShareCount', maxKey: 'maxShareCount' },
      { label: '评论量', minKey: 'minReplyCount', maxKey: 'maxReplyCount' },
      { label: '弹幕量', minKey: 'minDanmakuCount', maxKey: 'maxDanmakuCount' },
    ],
  },
  {
    title: '评分指标',
    description: '同时保留热度、相关性和综合评分的筛选能力。',
    fields: [
      { label: '相关性', minKey: 'minRelevanceScore', maxKey: 'maxRelevanceScore', step: 0.01 },
      { label: '热度分', minKey: 'minHeatScore', maxKey: 'maxHeatScore', step: 0.01 },
      { label: '综合评分', minKey: 'minCompositeScore', maxKey: 'maxCompositeScore', step: 0.01 },
    ],
  },
  {
    title: '比率指标',
    description: '适合筛选播放量不一定最高，但转化效率更高的视频。',
    hint: '赞播比输入 0-1 之间的小数，例如 0.08 表示 8%',
    fields: [
      { label: '赞播比', minKey: 'minLikeViewRatio', maxKey: 'maxLikeViewRatio', step: 0.001 },
    ],
  },
]

const route = useRoute()
const workspaceStore = useTaskWorkspaceStore()

const taskId = computed(() => String(route.params.taskId))
const payload = ref<TaskVideoListPayload | null>(null)
const taskProgress = ref<TaskProgressPayload | null>(null)
const topics = ref<TaskTopic[]>([])
const loading = ref(false)
const exporting = ref(false)
const latestProgressLogId = ref('')
const advancedFiltersVisible = ref(false)

let timer: number | null = null
let pollInFlight = false
let progressController: AbortController | null = null
let topicsController: AbortController | null = null
let videosController: AbortController | null = null

const filters = reactive<VideoFilterState>(workspaceStore.ensureVideoFilters(taskId.value))
const taskCrawlMode = computed<'keyword' | 'hot'>(() => {
  const taskOptions = taskProgress.value?.extra_params?.task_options
  if (taskOptions && typeof taskOptions === 'object') {
    return String((taskOptions as Record<string, unknown>).crawl_mode || 'keyword') === 'hot'
      ? 'hot'
      : 'keyword'
  }
  return 'keyword'
})

const exportDataset = computed({
  get: () => workspaceStore.exportDataset as ExportDataset,
  set: (value: ExportDataset) => {
    workspaceStore.setExportDataset(value)
  },
})

const exportFormat = computed({
  get: () => workspaceStore.exportFormat as ExportFormat,
  set: (value: ExportFormat) => {
    workspaceStore.setExportFormat(value)
  },
})
const activeFilterCount = computed(() => {
  const values = [
    filters.topic,
    filters.minViewCount,
    filters.maxViewCount,
    filters.minLikeCount,
    filters.maxLikeCount,
    filters.minCoinCount,
    filters.maxCoinCount,
    filters.minFavoriteCount,
    filters.maxFavoriteCount,
    filters.minShareCount,
    filters.maxShareCount,
    filters.minReplyCount,
    filters.maxReplyCount,
    filters.minDanmakuCount,
    filters.maxDanmakuCount,
    filters.minRelevanceScore,
    filters.maxRelevanceScore,
    filters.minHeatScore,
    filters.maxHeatScore,
    filters.minCompositeScore,
    filters.maxCompositeScore,
    filters.minLikeViewRatio,
    filters.maxLikeViewRatio,
  ]

  return values.filter((value) => value !== null && value !== undefined && value !== '').length
})
const visibleFilterGroups = computed(() => (advancedFiltersVisible.value ? filterGroups : []))

const emptyState = computed(() => {
  if (
    taskProgress.value?.status === 'running' ||
    taskProgress.value?.status === 'queued' ||
    taskProgress.value?.status === 'pending'
  ) {
    return {
      title: '任务仍在处理中',
      description: '结果会随着采集和 AI 分析逐步进入这里，可以稍后刷新，或回到任务详情查看实时进度。',
    }
  }

  if (taskProgress.value?.status === 'failed') {
    return {
      title: '任务失败，暂时没有可展示的视频结果',
      description:
        taskProgress.value.error_message ||
        '请先查看任务详情中的错误日志，确认采集或 AI 环节的失败原因。',
    }
  }

  return {
    title: '当前筛选下没有视频',
    description: '可以放宽主题或指标区间，或者切换到其他任务查看结果。',
  }
})

function syncFiltersFromStore() {
  Object.assign(filters, workspaceStore.ensureVideoFilters(taskId.value))
}

function buildQueryParams() {
  return {
    page: filters.page,
    page_size: filters.pageSize,
    sort_by: filters.sortBy,
    sort_order: filters.sortOrder,
    topic: filters.topic,
    min_view_count: normalizeNullableNumber(filters.minViewCount),
    max_view_count: normalizeNullableNumber(filters.maxViewCount),
    min_like_count: normalizeNullableNumber(filters.minLikeCount),
    max_like_count: normalizeNullableNumber(filters.maxLikeCount),
    min_coin_count: normalizeNullableNumber(filters.minCoinCount),
    max_coin_count: normalizeNullableNumber(filters.maxCoinCount),
    min_favorite_count: normalizeNullableNumber(filters.minFavoriteCount),
    max_favorite_count: normalizeNullableNumber(filters.maxFavoriteCount),
    min_share_count: normalizeNullableNumber(filters.minShareCount),
    max_share_count: normalizeNullableNumber(filters.maxShareCount),
    min_reply_count: normalizeNullableNumber(filters.minReplyCount),
    max_reply_count: normalizeNullableNumber(filters.maxReplyCount),
    min_danmaku_count: normalizeNullableNumber(filters.minDanmakuCount),
    max_danmaku_count: normalizeNullableNumber(filters.maxDanmakuCount),
    min_relevance_score: normalizeNullableNumber(filters.minRelevanceScore),
    max_relevance_score: normalizeNullableNumber(filters.maxRelevanceScore),
    min_heat_score: normalizeNullableNumber(filters.minHeatScore),
    max_heat_score: normalizeNullableNumber(filters.maxHeatScore),
    min_composite_score: normalizeNullableNumber(filters.minCompositeScore),
    max_composite_score: normalizeNullableNumber(filters.maxCompositeScore),
    min_like_view_ratio: normalizeNullableNumber(filters.minLikeViewRatio),
    max_like_view_ratio: normalizeNullableNumber(filters.maxLikeViewRatio),
  }
}

function persistFilters() {
  workspaceStore.updateVideoFilters(taskId.value, { ...filters })
}

function shouldPoll(status: TaskProgressPayload['status'] | undefined): boolean {
  return isActiveTaskStatus(status)
}

function clearTimer() {
  if (timer !== null) {
    window.clearInterval(timer)
    timer = null
  }
}

function replaceController(current: AbortController | null): AbortController {
  current?.abort()
  return new AbortController()
}

function abortPendingRequests() {
  progressController?.abort()
  topicsController?.abort()
  videosController?.abort()
  progressController = null
  topicsController = null
  videosController = null
}

function syncPolling() {
  clearTimer()
  if (!shouldPoll(taskProgress.value?.status)) {
    return
  }

  timer = window.setInterval(() => {
    void pollTaskProgress()
  }, 8000)
}

async function fetchTopics() {
  const controller = replaceController(topicsController)
  topicsController = controller
  try {
    const response = await getTaskTopics(taskId.value, {
      signal: controller.signal,
    })
    if (topicsController !== controller) {
      return
    }
    topics.value = response.items
  } catch (error) {
    if (!isRequestCanceled(error)) {
      ElMessage.error(getErrorMessage(error, '加载主题列表失败。'))
    }
  } finally {
    if (topicsController === controller) {
      topicsController = null
    }
  }
}

async function fetchTaskProgress() {
  const controller = replaceController(progressController)
  progressController = controller
  try {
    const response = await getTaskProgress(taskId.value, {
      signal: controller.signal,
    })
    if (progressController !== controller) {
      return
    }
    taskProgress.value = response
    latestProgressLogId.value = response.latest_log?.id ?? latestProgressLogId.value
    syncPolling()
  } catch (error) {
    if (isRequestCanceled(error)) {
      return
    }
    throw error
  } finally {
    if (progressController === controller) {
      progressController = null
    }
  }
}

async function fetchVideos() {
  const controller = replaceController(videosController)
  videosController = controller
  loading.value = true
  try {
    const response = await getTaskVideos(taskId.value, buildQueryParams(), {
      signal: controller.signal,
    })
    if (videosController !== controller) {
      return
    }
    payload.value = response
    persistFilters()
  } catch (error) {
    if (!isRequestCanceled(error)) {
      ElMessage.error(getErrorMessage(error, '加载视频结果失败。'))
    }
  } finally {
    if (videosController === controller) {
      videosController = null
      loading.value = false
    }
  }
}

async function pollTaskProgress() {
  if (pollInFlight) {
    return
  }

  pollInFlight = true
  try {
    const previousStatus = taskProgress.value?.status
    const previousProcessed = taskProgress.value?.processed_videos ?? 0
    const previousAnalyzed = taskProgress.value?.analyzed_videos ?? 0
    const previousTopics = taskProgress.value?.clustered_topics ?? 0
    await fetchTaskProgress()
    const currentStatus = taskProgress.value?.status
    const currentProcessed = taskProgress.value?.processed_videos ?? 0
    const currentAnalyzed = taskProgress.value?.analyzed_videos ?? 0
    const currentTopics = taskProgress.value?.clustered_topics ?? 0

    const shouldRefreshVideos =
      currentStatus !== previousStatus ||
      currentProcessed !== previousProcessed ||
      currentAnalyzed !== previousAnalyzed
    const shouldRefreshTopics =
      currentStatus !== previousStatus ||
      currentTopics !== previousTopics ||
      (!topics.value.length && currentTopics > 0)

    if (shouldRefreshVideos || shouldRefreshTopics) {
      await Promise.all([
        shouldRefreshTopics ? fetchTopics() : Promise.resolve(),
        shouldRefreshVideos ? fetchVideos() : Promise.resolve(),
      ])
    }
  } catch (error) {
    if (!isRequestCanceled(error)) {
      ElMessage.error(getErrorMessage(error, '更新任务进度失败。'))
    }
    clearTimer()
  } finally {
    pollInFlight = false
  }
}

function applyFilters() {
  filters.page = 1
  void fetchVideos()
}

function resetFilters() {
  workspaceStore.resetVideoFilters(taskId.value)
  syncFiltersFromStore()
  void fetchVideos()
}

function handlePageChange(page: number) {
  filters.page = page
  void fetchVideos()
}

function handleSizeChange(pageSize: number) {
  filters.page = 1
  filters.pageSize = pageSize
  void fetchVideos()
}

async function handleExport() {
  exporting.value = true
  try {
    const artifact = await exportTaskResults(
      taskId.value,
      exportDataset.value,
      exportFormat.value,
      buildQueryParams(),
    )
    triggerBlobDownload(artifact.blob, artifact.filename)
    ElMessage.success('导出已开始下载。')
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '导出失败，请稍后重试。'))
  } finally {
    exporting.value = false
  }
}

watch(taskId, async () => {
  abortPendingRequests()
  workspaceStore.setCurrentTaskId(taskId.value)
  syncFiltersFromStore()
  payload.value = null
  taskProgress.value = null
  topics.value = []
  latestProgressLogId.value = ''
  advancedFiltersVisible.value = false
  await Promise.all([fetchTaskProgress(), fetchTopics(), fetchVideos()])
})

onMounted(async () => {
  workspaceStore.setCurrentTaskId(taskId.value)
  syncFiltersFromStore()
  payload.value = null
  taskProgress.value = null
  topics.value = []
  latestProgressLogId.value = ''
  advancedFiltersVisible.value = false
  await Promise.all([fetchTaskProgress(), fetchTopics(), fetchVideos()])
})

onBeforeUnmount(() => {
  clearTimer()
  abortPendingRequests()
})
</script>

<style scoped>
.filter-layout {
  display: grid;
  gap: 12px;
}

.filter-card {
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 18px;
  padding: 14px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(248, 250, 252, 0.98)),
    #fff;
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.05);
}

.filter-card--compact {
  background:
    linear-gradient(135deg, rgba(240, 249, 255, 0.92), rgba(255, 251, 235, 0.92)),
    #fff;
}

.filter-card__header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 10px;
}

.filter-card__header h4 {
  margin: 0;
  font-size: 16px;
  color: #0f172a;
}

.filter-card__header p {
  display: none;
}

.filter-card__hint {
  display: none;
}

.filter-card__toggle {
  border: 0;
  padding: 0;
  background: transparent;
  color: var(--accent);
  font-weight: 700;
  cursor: pointer;
}

.range-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px 12px;
}

.range-grid--triple {
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
}

.range-field {
  display: grid;
  gap: 6px;
}

.range-field__label {
  font-size: 13px;
  font-weight: 600;
  color: #334155;
}

.range-field__pair {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  gap: 8px;
  align-items: center;
}

.range-field__pair :deep(.el-input-number),
.range-field :deep(.el-select) {
  width: 100%;
}

.range-field__divider {
  color: #94a3b8;
  font-size: 13px;
}

.metric-stack {
  display: grid;
  gap: 6px;
}

.metric-stack span {
  color: #1e293b;
}

@media (max-width: 960px) {
  .filter-card__header {
    flex-direction: column;
  }

  .filter-card__hint {
    white-space: normal;
  }
}

@media (max-width: 720px) {
  .range-field__pair {
    grid-template-columns: 1fr;
  }

  .range-field__divider {
    display: none;
  }
}
</style>

