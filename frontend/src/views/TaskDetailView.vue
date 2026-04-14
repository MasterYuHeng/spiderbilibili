<template>
  <div class="page-stack">
    <section class="page-hero">
      <div>
        <h3>{{ detail?.keyword || workspaceStore.currentTaskLabel || '任务详情' }}</h3>
        <p class="page-hero__description">
          查看当前任务的执行状态、搜索口径、运行配置和最新日志。
        </p>
      </div>
      <div class="page-hero__aside">
        <span>执行进度</span>
        <strong>{{ progressPercentLabel }}</strong>
      </div>
    </section>

    <TaskLifecycleNotice
      v-if="currentStatus"
      :status="currentStatus"
      :error-message="currentErrorMessage"
      :extra-params="taskExtraParams"
      :latest-log-message="latestLogMessage"
      :current-stage="currentStage"
    />

    <TaskSearchContextCard
      v-if="detail || progress"
      :task-keyword="detail?.keyword ?? workspaceStore.currentTaskLabel"
      :keyword-expansion="displayKeywordExpansion"
      :search-keywords-used="displaySearchKeywordsUsed"
      :expanded-keyword-count="displayExpandedKeywordCount"
      :crawl-mode="taskCrawlMode"
      title="搜索口径"
      description="这里会说明任务最终实际使用了哪些搜索词。后续主题分析、UP 主分析和任务报告都基于这一批召回样本。"
    />

    <section class="stats-grid">
      <StatCard label="候选视频" :value="formatNumber(currentTotalCandidates)" />
      <StatCard label="已处理视频" :value="formatNumber(currentProcessedVideos)" />
      <StatCard label="已分析视频" :value="formatNumber(currentAnalyzedVideos)" />
      <StatCard label="主题数量" :value="formatNumber(currentClusteredTopics)" />
    </section>

    <section class="panel-section">
      <div class="panel-section__head">
        <div>
          <h4>任务总览</h4>
        </div>
        <div class="toolbar__actions">
          <el-button @click="refreshAll">刷新详情</el-button>
          <el-button v-if="canRetry" type="warning" :loading="retrying" @click="handleRetry">
            重试任务
          </el-button>
          <RouterLink class="toolbar__link" :to="`/tasks/${taskId}/videos`">查看视频结果</RouterLink>
          <RouterLink class="toolbar__link" :to="`/tasks/${taskId}/topics`">查看主题分析</RouterLink>
          <RouterLink class="toolbar__link" :to="`/tasks/${taskId}/authors`">查看 UP 主分析</RouterLink>
          <RouterLink class="toolbar__link" :to="`/tasks/${taskId}/report`">查看任务报告</RouterLink>
          <RouterLink class="toolbar__link" :to="`/tasks/${taskId}/acceptance`">查看上线验收</RouterLink>
        </div>
      </div>

      <div class="overview-grid">
        <article class="overview-card">
          <div class="overview-card__head">
            <h5>执行状态</h5>
            <TaskStatusBadge v-if="currentStatus" :status="currentStatus" />
          </div>
          <dl class="detail-list">
            <div>
              <dt>当前阶段</dt>
              <dd>{{ currentStageLabel }}</dd>
            </div>
            <div>
              <dt>抓取模式</dt>
              <dd>{{ taskModeLabel }}</dd>
            </div>
            <div>
              <dt>抓取范围</dt>
              <dd>{{ taskScopeLabel }}</dd>
            </div>
            <div>
              <dt>发布时间范围</dt>
              <dd>{{ publishedWithinLabel }}</dd>
            </div>
            <div>
              <dt>创建时间</dt>
              <dd>{{ formatDateTime(detail?.created_at) }}</dd>
            </div>
            <div>
              <dt>开始时间</dt>
              <dd>{{ formatDateTime(currentStartedAt) }}</dd>
            </div>
            <div>
              <dt>结束时间</dt>
              <dd>{{ formatDateTime(currentFinishedAt) }}</dd>
            </div>
            <div>
              <dt>日志条数</dt>
              <dd>{{ formatNumber(detail?.log_total ?? 0) }}</dd>
            </div>
          </dl>
        </article>

        <article class="overview-card">
          <div class="overview-card__head">
            <h5>运行配置</h5>
          </div>
          <dl class="detail-list">
            <div>
              <dt>目标视频数</dt>
              <dd>{{ requestedVideoLimitLabel }}</dd>
            </div>
            <div>
              <dt>最大页数</dt>
              <dd>{{ maxPagesLabel }}</dd>
            </div>
            <div>
              <dt>休眠窗口</dt>
              <dd>{{ runtimeWindow }}</dd>
            </div>
            <div>
              <dt>代理设置</dt>
              <dd>{{ proxyLabel }}</dd>
            </div>
            <div>
              <dt>IP 策略</dt>
              <dd>{{ taskStrategyLabel }}</dd>
            </div>
            <div>
              <dt>最新错误</dt>
              <dd class="detail-list__multiline">{{ currentErrorMessage || '--' }}</dd>
            </div>
          </dl>
        </article>
      </div>
    </section>

    <section class="panel-section">
      <div class="panel-section__head">
        <div>
          <h4>执行进度</h4>
        </div>
      </div>

      <div class="progress-panel">
        <div class="progress-panel__bar">
          <el-progress :percentage="progressPercentValue" :stroke-width="12" />
        </div>
        <div class="progress-panel__meta">
          <span>当前阶段：{{ currentStageLabel }}</span>
          <span>候选 {{ formatNumber(currentTotalCandidates) }}</span>
          <span>已处理 {{ formatNumber(currentProcessedVideos) }}</span>
          <span>已分析 {{ formatNumber(currentAnalyzedVideos) }}</span>
        </div>
      </div>

      <div v-if="progress?.latest_log" class="latest-log-card">
        <div class="latest-log-card__head">
          <strong>最新进度日志</strong>
          <small>{{ formatDateTime(progress.latest_log.created_at) }}</small>
        </div>
        <p>{{ progress.latest_log.message }}</p>
      </div>
    </section>

    <section class="panel-section">
      <div class="panel-section__head">
        <div>
          <h4>任务日志</h4>
        </div>
        <div class="toolbar__actions">
          <el-button @click="handleRefreshLogs">刷新日志</el-button>
        </div>
      </div>

      <EmptyState
        v-if="!loading && !displayLogs.length"
        title="当前还没有日志"
        description="任务开始执行后，这里会展示最近一段执行日志。"
      />

      <div v-else class="log-list">
        <article v-for="log in displayLogs" :key="log.id" class="log-card">
          <div class="log-card__head">
            <div class="log-card__tags">
              <el-tag effect="plain">{{ stageLabel(log.stage) }}</el-tag>
              <el-tag :type="log.level === 'error' ? 'danger' : log.level === 'warning' ? 'warning' : 'info'" effect="plain">
                {{ log.level }}
              </el-tag>
            </div>
            <small>{{ formatDateTime(log.created_at) }}</small>
          </div>
          <p>{{ log.message }}</p>
          <pre v-if="log.payload !== null && log.payload !== undefined">{{ formatPayload(log.payload) }}</pre>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import { getErrorMessage, isRequestCanceled } from '@/api/client'
import { getTaskDetail, getTaskProgress, retryTask } from '@/api/tasks'
import type {
  KeywordExpansionPayload,
  TaskDetail,
  TaskLog,
  TaskProgressPayload,
  TaskStatus,
} from '@/api/types'
import EmptyState from '@/components/common/EmptyState.vue'
import StatCard from '@/components/common/StatCard.vue'
import TaskLifecycleNotice from '@/components/tasks/TaskLifecycleNotice.vue'
import TaskSearchContextCard from '@/components/tasks/TaskSearchContextCard.vue'
import TaskStatusBadge from '@/components/tasks/TaskStatusBadge.vue'
import { useTaskWorkspaceStore } from '@/stores/taskWorkspace'
import {
  formatDateTime,
  formatNumber,
  isRetryableStatus,
  stageLabel,
} from '@/utils/format'
import { isActiveTaskStatus } from '@/utils/taskStatus'

const DETAIL_LOG_LIMIT = 80
const DETAIL_STALE_MS = 15000

const route = useRoute()
const router = useRouter()
const workspaceStore = useTaskWorkspaceStore()

const taskId = computed(() => String(route.params.taskId))
const detail = ref<TaskDetail | null>(null)
const progress = ref<TaskProgressPayload | null>(null)
const loading = ref(false)
const retrying = ref(false)
const latestDetailLogId = ref('')
const lastDetailFetchedAt = ref(0)

let timer: number | null = null
let pollInFlight = false
let detailController: AbortController | null = null
let progressController: AbortController | null = null

function readTaskOptions(source: Record<string, unknown> | null | undefined): Record<string, unknown> | null {
  if (!source) {
    return null
  }
  const taskOptions = source.task_options
  return taskOptions && typeof taskOptions === 'object'
    ? (taskOptions as Record<string, unknown>)
    : null
}

const taskExtraParams = computed(() => detail.value?.extra_params ?? progress.value?.extra_params ?? null)
const taskOptions = computed(() => readTaskOptions(taskExtraParams.value))

const currentStatus = computed<TaskStatus | null>(() => progress.value?.status ?? detail.value?.status ?? null)
const currentStage = computed(() => progress.value?.current_stage || detail.value?.current_stage || '')
const currentStageLabel = computed(() => stageLabel(currentStage.value || 'task'))
const currentErrorMessage = computed(() => progress.value?.error_message || detail.value?.error_message || null)
const currentStartedAt = computed(() => progress.value?.started_at ?? detail.value?.started_at ?? null)
const currentFinishedAt = computed(() => progress.value?.finished_at ?? detail.value?.finished_at ?? null)
const currentTotalCandidates = computed(() => progress.value?.total_candidates ?? detail.value?.total_candidates ?? 0)
const currentProcessedVideos = computed(() => progress.value?.processed_videos ?? detail.value?.processed_videos ?? 0)
const currentAnalyzedVideos = computed(() => progress.value?.analyzed_videos ?? detail.value?.analyzed_videos ?? 0)
const currentClusteredTopics = computed(() => progress.value?.clustered_topics ?? detail.value?.clustered_topics ?? 0)
const latestLogMessage = computed(
  () => progress.value?.latest_log?.message ?? detail.value?.logs.at(0)?.message ?? null,
)

const progressPercentValue = computed(() => {
  const raw = progress.value?.progress_percent ?? detail.value?.progress_percent ?? 0
  return Math.max(0, Math.min(100, raw))
})
const progressPercentLabel = computed(() => `${progressPercentValue.value}%`)

const displayKeywordExpansion = computed<KeywordExpansionPayload | null>(
  () => progress.value?.keyword_expansion ?? detail.value?.keyword_expansion ?? null,
)
const displaySearchKeywordsUsed = computed(
  () => progress.value?.search_keywords_used ?? detail.value?.search_keywords_used ?? [],
)
const displayExpandedKeywordCount = computed(
  () => progress.value?.expanded_keyword_count ?? detail.value?.expanded_keyword_count ?? 0,
)

const taskCrawlMode = computed<'keyword' | 'hot'>(() =>
  String(taskOptions.value?.crawl_mode || 'keyword') === 'hot' ? 'hot' : 'keyword',
)
const taskModeLabel = computed(() => (taskCrawlMode.value === 'hot' ? '热榜抓取' : '关键词抓取'))
const taskScopeLabel = computed(() => {
  if (taskCrawlMode.value === 'hot') {
    return String(taskOptions.value?.search_scope || 'site') === 'partition' ? '热榜分区' : '全站热榜'
  }
  return String(taskOptions.value?.search_scope || 'site') === 'partition' ? '分区搜索' : '全站搜索'
})
const taskStrategyLabel = computed(() => String(taskOptions.value?.source_ip_strategy || '--'))
const publishedWithinLabel = computed(() => {
  const days = taskOptions.value?.published_within_days
  if (days === null || days === undefined) {
    return '不限'
  }
  return `${days} 天内`
})
const requestedVideoLimitLabel = computed(() => {
  const limit = taskOptions.value?.requested_video_limit
  return limit === null || limit === undefined ? '--' : String(limit)
})
const maxPagesLabel = computed(() => {
  const maxPages = taskOptions.value?.max_pages
  return maxPages === null || maxPages === undefined ? '--' : String(maxPages)
})
const runtimeWindow = computed(() => {
  const minSleep = taskOptions.value?.min_sleep_seconds
  const maxSleep = taskOptions.value?.max_sleep_seconds
  if (minSleep === null || minSleep === undefined || maxSleep === null || maxSleep === undefined) {
    return '--'
  }
  return `${minSleep}s - ${maxSleep}s`
})
const proxyLabel = computed(() => (taskOptions.value?.enable_proxy ? '已启用代理' : '本地直连'))
const canRetry = computed(() => isRetryableStatus(currentStatus.value))
const displayLogs = computed<TaskLog[]>(() => detail.value?.logs ?? [])

function shouldPoll(status: TaskStatus | null | undefined): boolean {
  return Boolean(status && isActiveTaskStatus(status))
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
  detailController?.abort()
  progressController?.abort()
  detailController = null
  progressController = null
}

function syncPolling() {
  clearTimer()
  if (!shouldPoll(currentStatus.value)) {
    return
  }

  timer = window.setInterval(() => {
    void pollTaskProgress()
  }, 8000)
}

function resetState() {
  detail.value = null
  progress.value = null
  latestDetailLogId.value = ''
  lastDetailFetchedAt.value = 0
}

function formatPayload(payload: TaskLog['payload']): string {
  if (typeof payload === 'string') {
    return payload
  }
  return JSON.stringify(payload, null, 2)
}

async function fetchDetail(force = false) {
  const now = Date.now()
  if (!force && detail.value && now - lastDetailFetchedAt.value < 1000) {
    return
  }

  const controller = replaceController(detailController)
  detailController = controller
  if (!detail.value) {
    loading.value = true
  }

  try {
    workspaceStore.setCurrentTaskId(taskId.value)
    const response = await getTaskDetail(taskId.value, {
      signal: controller.signal,
      logLimit: DETAIL_LOG_LIMIT,
    })
    if (detailController !== controller) {
      return
    }

    detail.value = response
    latestDetailLogId.value = response.logs[0]?.id ?? ''
    lastDetailFetchedAt.value = now
    workspaceStore.setCurrentTaskContext(response.id, response.keyword)
    syncPolling()
  } catch (error) {
    if (!isRequestCanceled(error)) {
      ElMessage.error(getErrorMessage(error, '加载任务详情失败。'))
    }
  } finally {
    if (detailController === controller) {
      detailController = null
      loading.value = false
    }
  }
}

async function fetchProgress() {
  const controller = replaceController(progressController)
  progressController = controller
  try {
    const response = await getTaskProgress(taskId.value, { signal: controller.signal })
    if (progressController !== controller) {
      return
    }

    progress.value = response
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

async function pollTaskProgress() {
  if (pollInFlight) {
    return
  }

  pollInFlight = true
  try {
    const previousStatus = currentStatus.value
    const previousStage = currentStage.value
    const previousLogId = progress.value?.latest_log?.id ?? latestDetailLogId.value
    await fetchProgress()
    const currentLogId = progress.value?.latest_log?.id ?? ''
    const statusChanged = currentStatus.value !== previousStatus
    const stageChanged = currentStage.value !== previousStage
    const logChanged = Boolean(currentLogId && currentLogId !== previousLogId)
    const detailStale = Date.now() - lastDetailFetchedAt.value > DETAIL_STALE_MS
    const terminalAndStale = !shouldPoll(currentStatus.value) && detailStale

    if (!detail.value || statusChanged || stageChanged || logChanged || terminalAndStale) {
      await fetchDetail(true)
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

async function refreshAll() {
  await Promise.all([fetchProgress(), fetchDetail(true)])
}

async function handleRefreshLogs() {
  await fetchDetail(true)
}

async function handleRetry() {
  retrying.value = true
  try {
    const response = await retryTask(taskId.value)
    workspaceStore.setCurrentTaskContext(response.task.id, response.task.keyword)
    ElMessage.success('已创建重试任务。')
    await router.push(`/tasks/${response.task.id}`)
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '重试任务失败。'))
  } finally {
    retrying.value = false
  }
}

watch(
  taskId,
  async () => {
    clearTimer()
    abortPendingRequests()
    resetState()
    await refreshAll()
  },
  { immediate: false },
)

onMounted(async () => {
  await refreshAll()
})

onBeforeUnmount(() => {
  clearTimer()
  abortPendingRequests()
})
</script>

<style scoped>
.page-hero__description {
  margin: 8px 0 0;
  color: var(--muted);
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.overview-card,
.latest-log-card,
.log-card {
  border: 1px solid rgba(100, 72, 46, 0.12);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.6);
}

.overview-card,
.latest-log-card,
.log-card {
  padding: 16px;
}

.overview-card__head,
.latest-log-card__head,
.log-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.overview-card__head h5 {
  margin: 0;
}

.detail-list {
  margin: 14px 0 0;
  display: grid;
  gap: 12px;
}

.detail-list div {
  display: grid;
  gap: 6px;
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(255, 248, 241, 0.72);
}

.detail-list dt,
.detail-list dd {
  margin: 0;
}

.detail-list dt {
  color: var(--muted);
  font-size: 13px;
}

.detail-list dd {
  color: var(--text);
  font-weight: 700;
}

.detail-list__multiline {
  white-space: pre-wrap;
  word-break: break-word;
}

.progress-panel {
  display: grid;
  gap: 14px;
}

.progress-panel__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  color: var(--muted);
}

.latest-log-card p,
.log-card p {
  margin: 12px 0 0;
  color: var(--text);
  line-height: 1.7;
}

.log-list {
  display: grid;
  gap: 12px;
}

.log-card__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.log-card small,
.latest-log-card small {
  color: var(--muted);
}

.log-card pre {
  margin: 12px 0 0;
  white-space: pre-wrap;
  word-break: break-word;
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(255, 248, 241, 0.72);
  color: var(--text);
}

@media (max-width: 960px) {
  .overview-grid {
    grid-template-columns: 1fr;
  }

  .progress-panel__meta,
  .overview-card__head,
  .latest-log-card__head,
  .log-card__head {
    flex-direction: column;
  }
}
</style>
