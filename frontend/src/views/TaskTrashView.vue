<template>
  <div class="page-stack">
    <section class="stats-grid">
      <StatCard label="可恢复" :value="String(restorableCount)" />
      <StatCard label="已完成结果" :value="String(completedCount)" />
      <StatCard label="失败任务" :value="String(failedCount)" />
      <StatCard label="当前页条数" :value="String(listPayload?.items.length ?? 0)" />
    </section>

    <section class="panel-section">
      <div class="toolbar">
        <el-select v-model="statusFilter" placeholder="筛选任务状态" class="toolbar__field">
          <el-option label="全部状态" value="all" />
          <el-option label="已暂停" value="paused" />
          <el-option label="部分成功" value="partial_success" />
          <el-option label="成功" value="success" />
          <el-option label="失败" value="failed" />
          <el-option label="已取消" value="cancelled" />
        </el-select>

        <div class="toolbar__actions">
          <el-button @click="fetchTrashTasks">刷新</el-button>
          <el-button
            type="danger"
            plain
            :loading="emptying"
            :disabled="loading || !listPayload?.total"
            @click="handleEmptyTrash"
          >
            清空回收站
          </el-button>
          <RouterLink class="toolbar__link toolbar__link--secondary" to="/tasks">返回任务列表</RouterLink>
        </div>
      </div>

      <el-table v-loading="loading" :data="listPayload?.items ?? []" row-key="id" class="app-table">
        <el-table-column label="任务" min-width="240">
          <template #default="{ row }">
            <div class="task-title-cell">
              <strong>{{ row.keyword }}</strong>
              <small>删除于 {{ formatDateTime(row.deleted_at) }}</small>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="原状态" width="130">
          <template #default="{ row }">
            <TaskStatusBadge :status="row.status" />
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="采集结果" width="160">
          <template #default="{ row }">
            {{ formatNumber(row.processed_videos) }} / {{ formatNumber(row.total_candidates) }}
          </template>
        </el-table-column>
        <el-table-column label="AI 结果" width="150">
          <template #default="{ row }">
            {{ formatNumber(row.analyzed_videos) }} / {{ formatNumber(row.total_candidates) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <div class="table-actions">
              <el-button
                link
                type="primary"
                :disabled="isRowBusy(row.id)"
                @click="handleRestore(row.id, row.keyword)"
              >
                恢复
              </el-button>
              <el-button
                link
                type="danger"
                :disabled="isRowBusy(row.id)"
                @click="openPermanentDeleteDialog(row.id, row.keyword)"
              >
                彻底删除
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <EmptyState
        v-if="!loading && !listPayload?.items.length"
        title="回收站是空的"
        description="移入回收站的任务会先出现在这里，便于恢复或再次确认。"
      />

      <div class="pagination-bar">
        <el-pagination
          background
          layout="prev, pager, next, sizes, total"
          :current-page="page"
          :page-size="pageSize"
          :page-sizes="[10, 20, 50]"
          :total="listPayload?.total ?? 0"
          @current-change="handlePageChange"
          @size-change="handleSizeChange"
        />
      </div>
    </section>

    <transition name="task-delete-modal">
      <div
        v-if="permanentDeleteDialogVisible"
        class="task-delete-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="task-delete-modal-title"
        @click.self="closePermanentDeleteDialog"
      >
        <div class="task-delete-modal__panel">
          <div class="task-delete-modal__header">
            <p class="task-delete-modal__eyebrow">永久删除确认</p>
            <h4 id="task-delete-modal-title">彻底删除任务</h4>
          </div>
          <div class="task-delete-modal__body">
            <p class="task-delete-modal__title">{{ pendingPermanentDeleteKeyword || '当前任务' }}</p>
            <p class="task-delete-modal__description">
              确认彻底删除这个任务吗？删除后将无法恢复，历史分析结果和报告也会一起移除。
            </p>
          </div>
          <div class="task-delete-modal__actions">
            <el-button @click="closePermanentDeleteDialog">取消</el-button>
            <el-button
              type="danger"
              :loading="
                Boolean(pendingPermanentDeleteTaskId) && isRowBusy(pendingPermanentDeleteTaskId)
              "
              @click="confirmPermanentDelete"
            >
              彻底删除
            </el-button>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'

import { getErrorMessage } from '@/api/client'
import {
  emptyTrash,
  listTrashTasks,
  permanentlyDeleteTask,
  restoreTask,
} from '@/api/tasks'
import type { TaskListPayload, TaskStatus } from '@/api/types'
import EmptyState from '@/components/common/EmptyState.vue'
import StatCard from '@/components/common/StatCard.vue'
import TaskStatusBadge from '@/components/tasks/TaskStatusBadge.vue'
import { useTaskWorkspaceStore } from '@/stores/taskWorkspace'
import { formatDateTime, formatNumber } from '@/utils/format'

const workspaceStore = useTaskWorkspaceStore()

const listPayload = ref<TaskListPayload | null>(null)
const loading = ref(false)
const emptying = ref(false)
const actingTaskId = ref('')
const permanentDeleteDialogVisible = ref(false)
const pendingPermanentDeleteTaskId = ref('')
const pendingPermanentDeleteKeyword = ref('')
const page = ref(1)
const pageSize = ref(10)
const statusFilter = ref<TaskStatus | 'all'>('all')

const restorableCount = computed(() => listPayload.value?.items.length ?? 0)
const completedCount = computed(
  () =>
    (listPayload.value?.items ?? []).filter(
      (item) => item.status === 'success' || item.status === 'partial_success',
    ).length,
)
const failedCount = computed(
  () =>
    (listPayload.value?.items ?? []).filter(
      (item) => item.status === 'failed' || item.status === 'cancelled',
    ).length,
)

async function fetchTrashTasks() {
  loading.value = true
  try {
    const payload = await listTrashTasks({
      page: page.value,
      page_size: pageSize.value,
      status: statusFilter.value === 'all' ? undefined : statusFilter.value,
    })

    if (payload.total_pages > 0 && page.value > payload.total_pages) {
      page.value = payload.total_pages
      return
    }

    listPayload.value = payload
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '加载回收站失败。'))
  } finally {
    loading.value = false
  }
}

function isRowBusy(taskId: string) {
  return actingTaskId.value === taskId
}

function handlePageChange(nextPage: number) {
  page.value = nextPage
}

function handleSizeChange(nextPageSize: number) {
  page.value = 1
  pageSize.value = nextPageSize
}

async function handleRestore(taskId: string, keyword: string) {
  actingTaskId.value = taskId
  try {
    await restoreTask(taskId)
    workspaceStore.setCurrentTaskContext(taskId, keyword)
    ElMessage.success('任务已恢复到任务列表。')
    if ((listPayload.value?.items.length ?? 0) === 1 && page.value > 1) {
      page.value -= 1
    } else {
      await fetchTrashTasks()
    }
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '恢复任务失败。'))
    await fetchTrashTasks()
  } finally {
    actingTaskId.value = ''
  }
}

function openPermanentDeleteDialog(taskId: string, keyword: string) {
  pendingPermanentDeleteTaskId.value = taskId
  pendingPermanentDeleteKeyword.value = keyword
  permanentDeleteDialogVisible.value = true
}

function closePermanentDeleteDialog() {
  permanentDeleteDialogVisible.value = false
  pendingPermanentDeleteTaskId.value = ''
  pendingPermanentDeleteKeyword.value = ''
}

async function confirmPermanentDelete() {
  const taskId = pendingPermanentDeleteTaskId.value
  if (!taskId) {
    return
  }

  actingTaskId.value = taskId
  try {
    await permanentlyDeleteTask(taskId)
    if (workspaceStore.currentTaskId === taskId) {
      workspaceStore.setCurrentTaskContext('', '')
    }
    ElMessage.success('任务已彻底删除。')
    if ((listPayload.value?.items.length ?? 0) === 1 && page.value > 1) {
      page.value -= 1
    } else {
      await fetchTrashTasks()
    }
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '彻底删除任务失败。'))
    await fetchTrashTasks()
  } finally {
    actingTaskId.value = ''
    closePermanentDeleteDialog()
  }
}

async function handleEmptyTrash() {
  try {
    await ElMessageBox.confirm(
      '确认清空整个回收站吗？其中的任务会被彻底删除且无法恢复。',
      '清空回收站',
      {
        type: 'warning',
        confirmButtonText: '清空回收站',
        cancelButtonText: '取消',
      },
    )
  } catch {
    return
  }

  emptying.value = true
  try {
    const currentTaskWasInTrash = (listPayload.value?.items ?? []).some(
      (item) => item.id === workspaceStore.currentTaskId,
    )
    const payload = await emptyTrash()
    if (currentTaskWasInTrash) {
      workspaceStore.setCurrentTaskContext('', '')
    }
    page.value = 1
    ElMessage.success(`已彻底删除 ${payload.deleted_count} 个任务。`)
    await fetchTrashTasks()
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '清空回收站失败。'))
    await fetchTrashTasks()
  } finally {
    emptying.value = false
  }
}

watch([page, pageSize, statusFilter], () => {
  void fetchTrashTasks()
})

onMounted(() => {
  void fetchTrashTasks()
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
