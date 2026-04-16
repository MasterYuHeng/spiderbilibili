<template>
  <div class="page-stack">
    <section class="page-hero">
      <div>
        <h3>任务验收总览</h3>
      </div>
      <div class="page-hero__aside">
        <span>验收结果</span>
        <strong>{{ statusText(acceptance?.overall_status) }}</strong>
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

    <section class="stats-grid">
      <StatCard label="通过项" :value="String(passCount)" />
      <StatCard label="警告项" :value="String(warnCount)" />
      <StatCard label="失败项" :value="String(failCount)" />
      <StatCard label="任务状态" :value="taskProgress ? statusLabel(taskProgress.status) : '--'" />
    </section>

    <section class="panel-section">
      <div class="panel-section__head">
        <div>
          <h4>验收概览</h4>
        </div>
        <div class="toolbar__actions">
          <el-button @click="refreshAll">刷新报告</el-button>
          <el-button v-if="acceptance" @click="showDiagnostics = !showDiagnostics">
            {{ showDiagnostics ? '隐藏技术细节' : '查看技术细节' }}
          </el-button>
          <RouterLink class="toolbar__link" :to="`/tasks/${taskId}`">返回任务详情</RouterLink>
        </div>
      </div>

      <EmptyState
        v-if="!loading && !acceptance"
        title="还没有验收报告"
        description="请先确认任务已创建，并且后端可以正常返回任务级验收数据。"
      />

      <div v-else class="acceptance-grid">
        <article
          v-for="section in acceptance?.sections ?? []"
          :key="section.name"
          class="acceptance-section"
        >
          <div class="acceptance-section__head">
            <div>
              <h5>{{ sectionTitle(section.name) }}</h5>
            </div>
            <span class="acceptance-check__status" :class="statusClass(sectionStatus(section.name))">
              {{ statusText(sectionStatus(section.name)) }}
            </span>
          </div>

          <div class="acceptance-checks">
            <article
              v-for="check in section.checks"
              :key="check.code"
              class="acceptance-check"
            >
              <div class="acceptance-check__head">
                <div>
                  <strong>{{ check.title }}</strong>
                  <small v-if="showDiagnostics">{{ check.code }}</small>
                </div>
                <span class="acceptance-check__status" :class="statusClass(check.status)">
                  {{ statusText(check.status) }}
                </span>
              </div>
              <p>{{ check.message }}</p>
              <pre v-if="showDiagnostics && check.actual !== null && check.actual !== undefined">{{
                formatValue(check.actual)
              }}</pre>
              <p
                v-if="showDiagnostics && check.expected !== null && check.expected !== undefined"
                class="acceptance-check__expected"
              >
                目标值：{{ formatValue(check.expected) }}
              </p>
            </article>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { getErrorMessage, isRequestCanceled } from '@/api/client'
import { getTaskAcceptance, getTaskProgress } from '@/api/tasks'
import type {
  TaskAcceptancePayload,
  TaskAcceptanceSection,
  TaskProgressPayload,
  TaskStatus,
} from '@/api/types'
import EmptyState from '@/components/common/EmptyState.vue'
import StatCard from '@/components/common/StatCard.vue'
import TaskLifecycleNotice from '@/components/tasks/TaskLifecycleNotice.vue'
import { useTaskWorkspaceStore } from '@/stores/taskWorkspace'
import { statusLabel } from '@/utils/format'
import { isActiveTaskStatus } from '@/utils/taskStatus'

type CheckStatus = 'pass' | 'warn' | 'fail'

const route = useRoute()
const workspaceStore = useTaskWorkspaceStore()

const taskId = computed(() => String(route.params.taskId))
const acceptance = ref<TaskAcceptancePayload | null>(null)
const taskProgress = ref<TaskProgressPayload | null>(null)
const loading = ref(false)
const showDiagnostics = ref(false)
let timer: number | null = null
let pollInFlight = false
let progressController: AbortController | null = null
let acceptanceController: AbortController | null = null
const latestProgressLogId = ref('')

const allChecks = computed(() => acceptance.value?.sections.flatMap((section) => section.checks) ?? [])
const passCount = computed(() => allChecks.value.filter((check) => check.status === 'pass').length)
const warnCount = computed(() => allChecks.value.filter((check) => check.status === 'warn').length)
const failCount = computed(() => allChecks.value.filter((check) => check.status === 'fail').length)

function shouldPoll(status: TaskStatus | undefined): boolean {
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
  acceptanceController?.abort()
  progressController = null
  acceptanceController = null
}

function syncPolling() {
  clearTimer()
  if (!shouldPoll(taskProgress.value?.status)) {
    return
  }

  timer = window.setInterval(() => {
    void pollTaskAcceptance()
  }, 8000)
}

function statusText(status: CheckStatus | undefined): string {
  if (status === 'pass') {
    return '通过'
  }
  if (status === 'warn') {
    return '警告'
  }
  if (status === 'fail') {
    return '失败'
  }
  return '--'
}

function statusClass(status: CheckStatus | undefined): string {
  return `acceptance-check__status--${status ?? 'unknown'}`
}

function sectionTitle(name: string): string {
  const labels: Record<string, string> = {
    functional: '功能验收',
    data: '数据验收',
    stability: '稳定性验收',
    compliance: '合规性验收',
  }
  return labels[name] ?? name
}

function sectionStatus(name: string): CheckStatus {
  const section = acceptance.value?.sections.find((item) => item.name === name)
  if (!section) {
    return 'warn'
  }
  return reduceStatuses(section)
}

function reduceStatuses(section: TaskAcceptanceSection): CheckStatus {
  if (section.checks.some((check) => check.status === 'fail')) {
    return 'fail'
  }
  if (section.checks.some((check) => check.status === 'warn')) {
    return 'warn'
  }
  return 'pass'
}

function formatValue(value: unknown): string {
  if (typeof value === 'string') {
    return value
  }
  return JSON.stringify(value, null, 2)
}

async function fetchTaskProgress() {
  const controller = replaceController(progressController)
  progressController = controller
  try {
    const response = await getTaskProgress(taskId.value, { signal: controller.signal })
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

async function fetchAcceptance(options: { silent?: boolean } = {}) {
  const controller = replaceController(acceptanceController)
  acceptanceController = controller
  if (!acceptance.value || !options.silent) {
    loading.value = true
  }
  try {
    const response = await getTaskAcceptance(taskId.value, { signal: controller.signal })
    if (acceptanceController !== controller) {
      return
    }
    acceptance.value = response
  } catch (error) {
    if (!isRequestCanceled(error)) {
      ElMessage.error(getErrorMessage(error, '加载阶段 15 验收报告失败。'))
    }
  } finally {
    if (acceptanceController === controller) {
      acceptanceController = null
      loading.value = false
    }
  }
}

async function pollTaskAcceptance() {
  if (pollInFlight) {
    return
  }

  pollInFlight = true
  try {
    const previousStatus = taskProgress.value?.status
    const previousProgress = taskProgress.value?.progress_percent ?? 0
    await fetchTaskProgress()
    const currentStatus = taskProgress.value?.status
    const currentProgress = taskProgress.value?.progress_percent ?? 0

    if (
      !acceptance.value ||
      currentStatus !== previousStatus ||
      (currentProgress === 100 && previousProgress !== 100)
    ) {
      await fetchAcceptance({ silent: true })
    }
  } catch (error) {
    if (!isRequestCanceled(error)) {
      ElMessage.error(getErrorMessage(error, '更新阶段 15 验收报告失败。'))
    }
    clearTimer()
  } finally {
    pollInFlight = false
  }
}

async function refreshAll() {
  workspaceStore.setCurrentTaskId(taskId.value)
  await Promise.all([fetchTaskProgress(), fetchAcceptance()])
}

watch(taskId, async () => {
  clearTimer()
  abortPendingRequests()
  acceptance.value = null
  taskProgress.value = null
  latestProgressLogId.value = ''
  showDiagnostics.value = false
  await refreshAll()
})

onMounted(async () => {
  latestProgressLogId.value = ''
  await refreshAll()
})

onBeforeUnmount(() => {
  clearTimer()
  abortPendingRequests()
})
</script>
