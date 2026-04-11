import { defineStore } from 'pinia'

import type { ExportFormat, TaskReportPayload, TaskStatus, VideoSortBy } from '@/api/types'

export interface VideoFilterState {
  page: number
  pageSize: number
  sortBy: VideoSortBy
  sortOrder: 'asc' | 'desc'
  topic: string | null
  minViewCount: number | null
  maxViewCount: number | null
  minLikeCount: number | null
  maxLikeCount: number | null
  minCoinCount: number | null
  maxCoinCount: number | null
  minFavoriteCount: number | null
  maxFavoriteCount: number | null
  minDanmakuCount: number | null
  maxDanmakuCount: number | null
  minShareCount: number | null
  maxShareCount: number | null
  minReplyCount: number | null
  maxReplyCount: number | null
  minRelevanceScore: number | null
  maxRelevanceScore: number | null
  minHeatScore: number | null
  maxHeatScore: number | null
  minCompositeScore: number | null
  maxCompositeScore: number | null
  minLikeViewRatio: number | null
  maxLikeViewRatio: number | null
}

function createDefaultVideoFilters(): VideoFilterState {
  return {
    page: 1,
    pageSize: 10,
    sortBy: 'composite_score',
    sortOrder: 'desc',
    topic: null,
    minViewCount: null,
    maxViewCount: null,
    minLikeCount: null,
    maxLikeCount: null,
    minCoinCount: null,
    maxCoinCount: null,
    minFavoriteCount: null,
    maxFavoriteCount: null,
    minDanmakuCount: null,
    maxDanmakuCount: null,
    minShareCount: null,
    maxShareCount: null,
    minReplyCount: null,
    maxReplyCount: null,
    minRelevanceScore: null,
    maxRelevanceScore: null,
    minHeatScore: null,
    maxHeatScore: null,
    minCompositeScore: null,
    maxCompositeScore: null,
    minLikeViewRatio: null,
    maxLikeViewRatio: null,
  }
}

export const useTaskWorkspaceStore = defineStore('taskWorkspace', {
  state: () => ({
    currentTaskId: '' as string,
    currentTaskLabel: '' as string,
    taskListStatus: 'all' as TaskStatus | 'all',
    taskListPage: 1,
    taskListPageSize: 10,
    exportFormat: 'excel' as ExportFormat,
    exportDataset: 'videos' as 'videos' | 'topics' | 'summaries',
    videoFiltersByTask: {} as Record<string, VideoFilterState>,
    taskReportsByTask: {} as Record<string, TaskReportPayload>,
  }),
  actions: {
    setCurrentTaskId(taskId: string | null | undefined) {
      const nextTaskId = taskId ?? ''
      if (this.currentTaskId !== nextTaskId) {
        this.currentTaskLabel = ''
      }
      this.currentTaskId = nextTaskId
    },
    setCurrentTaskContext(taskId: string | null | undefined, label?: string | null) {
      this.currentTaskId = taskId ?? ''
      this.currentTaskLabel = label?.trim() ?? ''
    },
    setCurrentTaskLabel(label: string | null | undefined) {
      this.currentTaskLabel = label?.trim() ?? ''
    },
    setTaskListStatus(status: TaskStatus | 'all') {
      this.taskListStatus = status
      this.taskListPage = 1
    },
    setTaskListPage(page: number) {
      this.taskListPage = page
    },
    setTaskListPageSize(pageSize: number) {
      this.taskListPageSize = pageSize
      this.taskListPage = 1
    },
    ensureVideoFilters(taskId: string) {
      if (!this.videoFiltersByTask[taskId]) {
        this.videoFiltersByTask[taskId] = createDefaultVideoFilters()
      }

      return this.videoFiltersByTask[taskId]
    },
    updateVideoFilters(taskId: string, patch: Partial<VideoFilterState>) {
      const current = this.ensureVideoFilters(taskId)
      this.videoFiltersByTask[taskId] = { ...current, ...patch }
    },
    resetVideoFilters(taskId: string) {
      this.videoFiltersByTask[taskId] = createDefaultVideoFilters()
    },
    setExportFormat(format: ExportFormat) {
      this.exportFormat = format
    },
    setExportDataset(dataset: 'videos' | 'topics' | 'summaries') {
      this.exportDataset = dataset
    },
    cacheTaskReport(report: TaskReportPayload) {
      this.taskReportsByTask[report.task_id] = report
    },
  },
})
