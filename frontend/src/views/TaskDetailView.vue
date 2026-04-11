<template>
  <div class="page-stack">
    <section class="page-hero">
      <div>
        <h3>{{ detail?.keyword ?? '任务详情' }}</h3>
      </div>
      <div class="page-hero__aside">
        <span>当前进度</span>
        <strong>{{ progress ? `${progress.progress_percent}%` : '--' }}</strong>
        <TaskStatusBadge v-if="progress" :status="progress.status" />
      </div>
    </section>

    <TaskLifecycleNotice
      v-if="detail && progress"
      :status="progress.status"
      :error-message="progress.error_message"
      :extra-params="detail.extra_params"
      :latest-log-message="progress.latest_log?.message ?? null"
      :current-stage="progress.current_stage"
    />

    <section class="stats-grid">
      <StatCard
        label="采集候选"
        :value="formatNumber(progress?.total_candidates ?? detail?.total_candidates ?? 0)"
      />
      <StatCard
        label="已处理视频"
        :value="formatNumber(progress?.processed_videos ?? detail?.processed_videos ?? 0)"
      />
      <StatCard
        label="AI 已分析"
        :value="formatNumber(progress?.analyzed_videos ?? detail?.analyzed_videos ?? 0)"
      />
      <StatCard
        label="主题数"
        :value="formatNumber(progress?.clustered_topics ?? detail?.clustered_topics ?? 0)"
      />
    </section>

    <section class="panel-section">
      <div class="panel-section__head">
        <div>
          <h4>执行概况</h4>
        </div>
        <div class="toolbar__actions">
          <el-button @click="refreshAll">刷新</el-button>
          <el-button
            v-if="canRetry"
            type="warning"
            :loading="retrying"
            @click="handleRetry"
          >
            Retry
          </el-button>
          <RouterLink class="toolbar__link" :to="`/tasks/${taskId}/report`">查看任务报告</RouterLink>
          <RouterLink class="toolbar__link" :to="`/tasks/${taskId}/acceptance`">查看上线验收</RouterLink>
          <RouterLink class="toolbar__link" :to="`/tasks/${taskId}/videos`">查看视频结果</RouterLink>
          <RouterLink class="toolbar__link" :to="`/tasks/${taskId}/topics`">查看主题分析</RouterLink>
          <RouterLink class="toolbar__link" :to="`/tasks/${taskId}/authors`">查看 UP 主分析</RouterLink>
        </div>
      </div>

      <div v-if="detail && progress" class="detail-grid detail-grid--compact">
        <article class="detail-card">
          <h5>执行信息</h5>
          <dl class="detail-list">
            <div>
              <dt>当前阶段</dt>
              <dd>{{ stageLabel(progress.current_stage) }}</dd>
            </div>
            <div>
              <dt>创建时间</dt>
              <dd>{{ formatDateTime(detail.created_at) }}</dd>
            </div>
            <div>
              <dt>开始时间</dt>
              <dd>{{ formatDateTime(progress.started_at) }}</dd>
            </div>
            <div>
              <dt>结束时间</dt>
              <dd>{{ formatDateTime(progress.finished_at) }}</dd>
            </div>
            <div>
              <dt>抓取方式</dt>
              <dd>{{ taskModeLabel }}</dd>
            </div>
            <div>
              <dt>抓取范围</dt>
              <dd>{{ taskScopeLabel }}</dd>
            </div>
            <div>
              <dt>发布时间</dt>
              <dd>{{ publishedWithinLabel }}</dd>
            </div>
          </dl>
        </article>

        <article class="detail-card">
          <h5>运行设置</h5>
          <dl class="detail-list">
            <div>
              <dt>目标视频数</dt>
              <dd>{{ formatNumber(detail.requested_video_limit) }}</dd>
            </div>
            <div>
              <dt>最大页数</dt>
              <dd>{{ formatNumber(detail.max_pages) }}</dd>
            </div>
            <div>
              <dt>抓取节奏</dt>
              <dd>{{ runtimeWindow }}</dd>
            </div>
            <div>
              <dt>启用代理</dt>
              <dd>{{ detail.enable_proxy ? '是' : '否' }}</dd>
            </div>
            <div>
              <dt>代理策略</dt>
              <dd>{{ detail.enable_proxy ? taskStrategyLabel : '未启用' }}</dd>
            </div>
            <div>
              <dt>最近异常</dt>
              <dd>{{ progress.error_message || detail.error_message || '--' }}</dd>
            </div>
          </dl>
        </article>
      </div>

      <div v-if="progress" class="progress-card progress-card--compact">
        <div class="progress-card__head">
          <div>
            <span>整体进度</span>
            <strong>{{ progress.progress_percent }}%</strong>
          </div>
          <small>{{ stageLabel(progress.current_stage) }}</small>
        </div>
        <el-progress :percentage="progress.progress_percent" :stroke-width="12" />
        <p v-if="progress.latest_log" class="progress-card__log">
          最新日志：{{ progress.latest_log.message }}
        </p>
      </div>
    </section>

    <section class="panel-section">
      <div class="panel-section__head">
        <div>
          <h4>日志流</h4>
        </div>
        <div class="toolbar__actions">
          <el-button :loading="loading" @click="handleRefreshLogs">刷新日志</el-button>
        </div>
      </div>

      <EmptyState
        v-if="!loading && !(detail?.logs.length)"
        title="日志还在生成中"
        description="任务启动后，这里会逐步出现执行日志。"
      />

      <div v-else class="log-list log-list--grid">
        <article v-for="log in detail?.logs ?? []" :key="log.id" class="log-item">
          <div class="log-item__meta">
            <span class="log-item__level">{{ log.level.toUpperCase() }}</span>
            <strong>{{ stageLabel(log.stage) }}</strong>
            <small>{{ formatDateTime(log.created_at) }}</small>
          </div>
          <p>{{ log.message }}</p>
          <pre v-if="log.payload">{{ formatPayload(log.payload) }}</pre>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import { getErrorMessage } from '@/api/client'
import { getTaskDetail, getTaskProgress, retryTask } from '@/api/tasks'
import type { TaskDetail, TaskProgressPayload, TaskStatus } from '@/api/types'
import EmptyState from '@/components/common/EmptyState.vue'
import StatCard from '@/components/common/StatCard.vue'
import TaskLifecycleNotice from '@/components/tasks/TaskLifecycleNotice.vue'
import TaskStatusBadge from '@/components/tasks/TaskStatusBadge.vue'
import { useTaskWorkspaceStore } from '@/stores/taskWorkspace'
import { formatDateTime, formatNumber, isRetryableStatus, stageLabel } from '@/utils/format'
import { isActiveTaskStatus } from '@/utils/taskStatus'

const route = useRoute()
const router = useRouter()
const workspaceStore = useTaskWorkspaceStore()

const taskId = computed(() => String(route.params.taskId))
const detail = ref<TaskDetail | null>(null)
const progress = ref<TaskProgressPayload | null>(null)
const loading = ref(false)
const retrying = ref(false)
const latestDetailLogId = ref('')
let timer: number | null = null
let pollInFlight = false
let lastDetailFetchedAt = 0
const DETAIL_LOG_LIMIT = 80
const canRetry = computed(() => isRetryableStatus(progress.value?.status ?? detail.value?.status))

const taskOptions = computed<Record<string, unknown>>(() => {
  const extraParams = detail.value?.extra_params
  if (!extraParams || typeof extraParams !== 'object') {
    return {}
  }

  const raw = extraParams.task_options
  return raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {}
})

const taskModeLabel = computed(() => {
  return String(taskOptions.value.crawl_mode || 'keyword') === 'hot' ? '当前热度抓取' : '关键词抓取'
})

const taskScopeLabel = computed(() => {
  if (String(taskOptions.value.search_scope || 'site') === 'partition') {
    return String(taskOptions.value.partition_name || taskOptions.value.partition_tid || '指定分区')
  }

  return 'B 站全站'
})

const taskStrategyLabel = computed(() => {
  const labels: Record<string, string> = {
    local_sleep: '本机节流',
    proxy_pool: '代理池轮换',
    custom_proxy: '自定义代理',
  }

  return labels[detail.value?.source_ip_strategy || 'local_sleep'] ?? detail.value?.source_ip_strategy ?? '--'
})

const publishedWithinLabel = computed(() => {
  const days = taskOptions.value.published_within_days
  if (days === null || days === undefined || days === '') {
    return '不限'
  }

  const numericDays = Number(days)
  return Number.isFinite(numericDays) && numericDays > 0 ? `最近 ${numericDays} 天` : '不限'
})

const runtimeWindow = computed(
  () => `${detail.value?.min_sleep_seconds ?? '--'}s - ${detail.value?.max_sleep_seconds ?? '--'}s`,
)

function shouldPoll(status: TaskStatus | undefined): boolean {
  return isActiveTaskStatus(status)
}

function clearTimer() {
  if (timer !== null) {
    window.clearInterval(timer)
    timer = null
  }
}

function syncPolling() {
  clearTimer()
  if (!shouldPoll(progress.value?.status)) {
    return
  }

  timer = window.setInterval(() => {
    void pollTaskProgress()
  }, 5000)
}

function formatPayload(payload: Record<string, unknown> | unknown[] | string): string {
  if (typeof payload === 'string') {
    return payload
  }

  return JSON.stringify(payload, null, 2)
}

async function fetchDetail(force = false) {
  if (!force && detail.value && Date.now() - lastDetailFetchedAt < 20000) {
    return
  }

  detail.value = await getTaskDetail(taskId.value, { logLimit: DETAIL_LOG_LIMIT })
  workspaceStore.setCurrentTaskContext(detail.value.id, detail.value.keyword)
  latestDetailLogId.value = detail.value.logs.at(-1)?.id ?? ''
  lastDetailFetchedAt = Date.now()
}

async function fetchProgress(syncDetail = true) {
  progress.value = await getTaskProgress(taskId.value)
  syncPolling()

  const latestProgressLogId = progress.value.latest_log?.id ?? ''
  if (
    syncDetail &&
    (!detail.value ||
      !shouldPoll(progress.value.status) ||
      (latestProgressLogId &&
        latestProgressLogId !== latestDetailLogId.value &&
        Date.now() - lastDetailFetchedAt > 20000))
  ) {
    await fetchDetail(true)
  }
}

async function pollTaskProgress() {
  if (pollInFlight) {
    return
  }

  pollInFlight = true
  try {
    await fetchProgress()
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '更新任务进度失败。'))
    clearTimer()
  } finally {
    pollInFlight = false
  }
}

async function refreshAll() {
  loading.value = true
  try {
    workspaceStore.setCurrentTaskId(taskId.value)
    await Promise.all([fetchDetail(true), fetchProgress(false)])
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '加载任务详情失败。'))
  } finally {
    loading.value = false
  }
}

async function handleRefreshLogs() {
  loading.value = true
  try {
    await fetchDetail(true)
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '刷新日志失败。'))
  } finally {
    loading.value = false
  }
}

async function handleRetry() {
  if (!canRetry.value || retrying.value) {
    return
  }

  retrying.value = true
  try {
    const payload = await retryTask(taskId.value)
    workspaceStore.setCurrentTaskContext(payload.task.id, payload.task.keyword)
    ElMessage.success('已创建重试任务，正在跳转到新任务详情页。')
    await router.push(`/tasks/${payload.task.id}`)
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '重试任务创建失败。'))
  } finally {
    retrying.value = false
  }
}

watch(taskId, () => {
  clearTimer()
  detail.value = null
  progress.value = null
  latestDetailLogId.value = ''
  lastDetailFetchedAt = 0
  void refreshAll()
})

onMounted(() => {
  void refreshAll()
})

onBeforeUnmount(() => {
  clearTimer()
})
</script>

<style scoped>
.detail-grid--compact {
  gap: 10px;
}

.progress-card--compact {
  margin-top: 10px;
  padding: 14px 16px;
}

.progress-card--compact :deep(.el-progress-bar__outer) {
  height: 8px !important;
}

.log-list--grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  align-items: start;
}

@media (max-width: 960px) {
  .log-list--grid {
    grid-template-columns: 1fr;
  }
}
</style>
