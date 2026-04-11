<template>
  <div class="page-stack">
    <section class="stats-grid">
      <StatCard label="运行中" :value="String(activeTaskCount)" />
      <StatCard label="需关注" :value="String(needsAttentionCount)" />
      <StatCard label="已完成" :value="String(finishedTaskCount)" />
      <StatCard label="当前页条数" :value="String(listPayload?.items.length ?? 0)" />
    </section>

    <section class="panel-section">
      <div class="toolbar">
        <el-select v-model="statusFilter" placeholder="筛选任务状态" class="toolbar__field">
          <el-option label="全部状态" value="all" />
          <el-option label="待处理" value="pending" />
          <el-option label="已入队" value="queued" />
          <el-option label="运行中" value="running" />
          <el-option label="已暂停" value="paused" />
          <el-option label="部分成功" value="partial_success" />
          <el-option label="成功" value="success" />
          <el-option label="失败" value="failed" />
          <el-option label="已取消" value="cancelled" />
        </el-select>

        <div class="toolbar__actions">
          <el-button @click="fetchTasks">刷新</el-button>
          <RouterLink class="toolbar__link toolbar__link--secondary" to="/tasks/trash">
            回收站
          </RouterLink>
          <RouterLink class="toolbar__link" to="/tasks/create">新建任务</RouterLink>
        </div>
      </div>

      <el-table v-loading="loading" :data="listPayload?.items ?? []" row-key="id" class="app-table">
        <el-table-column label="任务" min-width="240">
          <template #default="{ row }">
            <div class="task-title-cell">
              <strong>{{ row.keyword }}</strong>
              <small>创建于 {{ formatDateTime(row.created_at) }}</small>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="130">
          <template #default="{ row }">
            <TaskStatusBadge :status="row.status" />
          </template>
        </el-table-column>
        <el-table-column label="采集进度" width="160">
          <template #default="{ row }">
            {{ formatNumber(row.processed_videos) }} / {{ formatNumber(row.total_candidates) }}
          </template>
        </el-table-column>
        <el-table-column label="AI 分析" width="160">
          <template #default="{ row }">
            {{ formatNumber(row.analyzed_videos) }} / {{ formatNumber(row.total_candidates) }}
          </template>
        </el-table-column>
        <el-table-column label="AI 完成度" width="170">
          <template #default="{ row }">
            <el-progress
              :percentage="
                row.total_candidates
                  ? Math.round((row.analyzed_videos / row.total_candidates) * 100)
                  : 0
              "
              :stroke-width="10"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="340" fixed="right">
          <template #default="{ row }">
            <div class="table-actions">
              <el-button link type="primary" @click="openTask(row.id, row.keyword)">详情</el-button>
              <el-button link @click="openTask(row.id, row.keyword, 'videos')">结果</el-button>
              <el-button link @click="openTask(row.id, row.keyword, 'report')">报告</el-button>
              <el-button
                v-if="canPauseTask(row.status)"
                link
                type="warning"
                :disabled="isRowBusy(row.id)"
                @click="handlePause(row.id)"
              >
                暂停
              </el-button>
              <el-button
                v-if="canResumeTask(row.status)"
                link
                type="success"
                :disabled="isRowBusy(row.id)"
                @click="handleResume(row.id)"
              >
                继续
              </el-button>
              <el-button
                v-if="canCancelTask(row.status)"
                link
                type="danger"
                :disabled="isRowBusy(row.id)"
                @click="handleCancel(row.id)"
              >
                取消
              </el-button>
              <el-button
                v-if="isRetryableStatus(row.status)"
                link
                type="warning"
                :disabled="isRowBusy(row.id)"
                @click="handleRetry(row.id)"
              >
                重试
              </el-button>
              <el-button
                v-if="canDeleteTask(row.status)"
                link
                type="danger"
                :disabled="isRowBusy(row.id)"
                @click="openDeleteDialog(row.id, row.keyword)"
              >
                回收站
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <EmptyState
        v-if="!loading && !listPayload?.items.length"
        title="当前没有符合条件的任务"
        description="可以先新建任务，或者切换筛选条件查看其他记录。"
      />

      <div class="pagination-bar">
        <el-pagination
          background
          layout="prev, pager, next, sizes, total"
          :current-page="workspaceStore.taskListPage"
          :page-size="workspaceStore.taskListPageSize"
          :page-sizes="[10, 20, 50]"
          :total="listPayload?.total ?? 0"
          @current-change="handlePageChange"
          @size-change="handleSizeChange"
        />
      </div>
    </section>

    <transition name="task-delete-modal">
      <div
        v-if="deleteDialogVisible"
        class="task-delete-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="task-delete-modal-title"
        @click.self="closeDeleteDialog"
      >
        <div class="task-delete-modal__panel">
          <div class="task-delete-modal__header">
            <p class="task-delete-modal__eyebrow">回收站确认</p>
            <h4 id="task-delete-modal-title">移入回收站</h4>
          </div>
          <div class="task-delete-modal__body">
            <p class="task-delete-modal__title">{{ pendingDeleteTaskKeyword || '当前任务' }}</p>
            <p class="task-delete-modal__description">
              确认将这个任务移入回收站吗？移入后仍然可以在回收站中恢复。
            </p>
          </div>
          <div class="task-delete-modal__actions">
            <el-button @click="closeDeleteDialog">取消</el-button>
            <el-button
              type="danger"
              :loading="Boolean(pendingDeleteTaskId) && isRowBusy(pendingDeleteTaskId)"
              @click="confirmDeleteTask"
            >
              确认移入
            </el-button>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'

import { getErrorMessage } from '@/api/client'
import {
  cancelTask,
  deleteTask,
  listTasks,
  pauseTask,
  resumeTask,
  retryTask,
} from '@/api/tasks'
import type { TaskListPayload, TaskStatus } from '@/api/types'
import EmptyState from '@/components/common/EmptyState.vue'
import StatCard from '@/components/common/StatCard.vue'
import TaskStatusBadge from '@/components/tasks/TaskStatusBadge.vue'
import { useTaskWorkspaceStore } from '@/stores/taskWorkspace'
import { formatDateTime, formatNumber, isRetryableStatus } from '@/utils/format'
import {
  canCancelTask,
  canDeleteTask,
  canPauseTask,
  canResumeTask,
  isActiveTaskStatus,
} from '@/utils/taskStatus'

const router = useRouter()
const workspaceStore = useTaskWorkspaceStore()
const listPayload = ref<TaskListPayload | null>(null)
const loading = ref(false)
const actingTaskId = ref('')
const deleteDialogVisible = ref(false)
const pendingDeleteTaskId = ref('')
const pendingDeleteTaskKeyword = ref('')
let timer: number | null = null

const activeTaskCount = computed(
  () => (listPayload.value?.items ?? []).filter((item) => isActiveTaskStatus(item.status)).length,
)
const needsAttentionCount = computed(
  () =>
    (listPayload.value?.items ?? []).filter(
      (item) =>
        item.status === 'failed' || item.status === 'partial_success' || item.status === 'cancelled',
    ).length,
)
const finishedTaskCount = computed(
  () =>
    (listPayload.value?.items ?? []).filter(
      (item) => item.status === 'success' || item.status === 'partial_success',
    ).length,
)

const statusFilter = computed({
  get: () => workspaceStore.taskListStatus,
  set: (value: TaskStatus | 'all') => {
    workspaceStore.setTaskListStatus(value)
  },
})

async function fetchTasks() {
  loading.value = true
  try {
    const payload = await listTasks({
      page: workspaceStore.taskListPage,
      page_size: workspaceStore.taskListPageSize,
      status: workspaceStore.taskListStatus === 'all' ? undefined : workspaceStore.taskListStatus,
    })

    if (payload.total_pages > 0 && workspaceStore.taskListPage > payload.total_pages) {
      workspaceStore.setTaskListPage(payload.total_pages)
      return
    }

    listPayload.value = payload
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '加载任务列表失败。'))
  } finally {
    loading.value = false
    syncAutoRefresh()
  }
}

function clearTimer() {
  if (timer !== null) {
    window.clearInterval(timer)
    timer = null
  }
}

function syncAutoRefresh() {
  clearTimer()
  const hasActiveTask = (listPayload.value?.items ?? []).some((item) =>
    isActiveTaskStatus(item.status),
  )

  if (!hasActiveTask) {
    return
  }

  timer = window.setInterval(() => {
    void fetchTasks()
  }, 10000)
}

function isRowBusy(taskId: string) {
  return actingTaskId.value === taskId
}

function openDeleteDialog(taskId: string, keyword: string) {
  pendingDeleteTaskId.value = taskId
  pendingDeleteTaskKeyword.value = keyword
  deleteDialogVisible.value = true
}

function closeDeleteDialog() {
  deleteDialogVisible.value = false
  pendingDeleteTaskId.value = ''
  pendingDeleteTaskKeyword.value = ''
}

function handlePageChange(page: number) {
  workspaceStore.setTaskListPage(page)
}

function handleSizeChange(pageSize: number) {
  workspaceStore.setTaskListPageSize(pageSize)
}

async function openTask(
  taskId: string,
  keyword = '',
  tab: 'detail' | 'videos' | 'topics' | 'report' | 'acceptance' = 'detail',
) {
  workspaceStore.setCurrentTaskContext(taskId, keyword)
  if (tab === 'videos') {
    await router.push(`/tasks/${taskId}/videos`)
    return
  }

  if (tab === 'topics') {
    await router.push(`/tasks/${taskId}/topics`)
    return
  }

  if (tab === 'report') {
    await router.push(`/tasks/${taskId}/report`)
    return
  }

  if (tab === 'acceptance') {
    await router.push(`/tasks/${taskId}/acceptance`)
    return
  }

  await router.push(`/tasks/${taskId}`)
}

async function handleRetry(taskId: string) {
  actingTaskId.value = taskId
  try {
    const payload = await retryTask(taskId)
    workspaceStore.setCurrentTaskContext(payload.task.id, payload.task.keyword)
    ElMessage.success('已创建重试任务。')
    await fetchTasks()
    await router.push(`/tasks/${payload.task.id}`)
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '重试任务失败。'))
    await fetchTasks()
  } finally {
    actingTaskId.value = ''
  }
}

async function handlePause(taskId: string) {
  actingTaskId.value = taskId
  try {
    await pauseTask(taskId)
    ElMessage.success('任务已暂停。')
    await fetchTasks()
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '暂停任务失败。'))
    await fetchTasks()
  } finally {
    actingTaskId.value = ''
  }
}

async function handleResume(taskId: string) {
  actingTaskId.value = taskId
  try {
    await resumeTask(taskId)
    ElMessage.success('任务已恢复执行。')
    await fetchTasks()
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '恢复任务失败。'))
    await fetchTasks()
  } finally {
    actingTaskId.value = ''
  }
}

async function handleCancel(taskId: string) {
  actingTaskId.value = taskId
  try {
    await cancelTask(taskId)
    ElMessage.success('任务已取消。')
    await fetchTasks()
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '取消任务失败。'))
    await fetchTasks()
  } finally {
    actingTaskId.value = ''
  }
}

async function confirmDeleteTask() {
  const taskId = pendingDeleteTaskId.value
  if (!taskId) {
    return
  }

  actingTaskId.value = taskId
  try {
    await deleteTask(taskId)
    if (workspaceStore.currentTaskId === taskId) {
      workspaceStore.setCurrentTaskContext('', '')
    }
    ElMessage.success('任务已移入回收站。')
    if ((listPayload.value?.items.length ?? 0) === 1 && workspaceStore.taskListPage > 1) {
      workspaceStore.setTaskListPage(workspaceStore.taskListPage - 1)
    } else {
      await fetchTasks()
    }
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '移入回收站失败。'))
    await fetchTasks()
  } finally {
    actingTaskId.value = ''
    closeDeleteDialog()
  }
}

watch(
  () => [
    workspaceStore.taskListStatus,
    workspaceStore.taskListPage,
    workspaceStore.taskListPageSize,
  ],
  () => {
    void fetchTasks()
  },
)

onMounted(() => {
  void fetchTasks()
})

onBeforeUnmount(() => {
  clearTimer()
})
</script>

<style scoped>
.task-delete-modal-enter-active,
.task-delete-modal-leave-active {
  transition: opacity 180ms ease;
}

.task-delete-modal-enter-from,
.task-delete-modal-leave-to {
  opacity: 0;
}

.task-delete-modal {
  position: fixed;
  inset: 0;
  z-index: 2100;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(32, 20, 12, 0.36);
  backdrop-filter: blur(8px);
}

.task-delete-modal__panel {
  width: min(100%, 460px);
  border: 1px solid var(--border);
  border-radius: 28px;
  background:
    linear-gradient(180deg, rgba(255, 251, 246, 0.98), rgba(249, 238, 226, 0.96)),
    var(--panel-strong);
  box-shadow: 0 28px 70px rgba(54, 33, 18, 0.22);
  padding: 24px;
}

.task-delete-modal__header,
.task-delete-modal__body {
  display: flex;
  flex-direction: column;
}

.task-delete-modal__header {
  gap: 6px;
}

.task-delete-modal__eyebrow,
.task-delete-modal__header h4,
.task-delete-modal__title,
.task-delete-modal__description {
  margin: 0;
}

.task-delete-modal__eyebrow {
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--accent);
}

.task-delete-modal__header h4 {
  font-size: 24px;
  color: var(--text);
}

.task-delete-modal__body {
  margin-top: 18px;
  gap: 10px;
}

.task-delete-modal__title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text);
}

.task-delete-modal__description {
  color: var(--muted);
  line-height: 1.7;
}

.task-delete-modal__actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 24px;
}

@media (max-width: 720px) {
  .task-delete-modal {
    padding: 16px;
    align-items: flex-end;
  }

  .task-delete-modal__panel {
    border-radius: 24px 24px 0 0;
    padding: 20px;
  }

  .task-delete-modal__actions {
    flex-direction: column-reverse;
    align-items: stretch;
  }
}
</style>
