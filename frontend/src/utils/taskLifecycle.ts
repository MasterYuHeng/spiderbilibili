import type { TaskDetail, TaskProgressPayload, TaskStatus } from '@/api/types'
import { formatNumber } from '@/utils/format'

export interface TaskLifecycleNoticeData {
  tone: 'neutral' | 'warning' | 'danger' | 'success'
  title: string
  description: string
  metrics: Array<{ label: string; value: string }>
}

type TaskLike = Pick<TaskDetail, 'status' | 'error_message' | 'extra_params'> &
  Partial<Pick<TaskProgressPayload, 'current_stage'>> & {
    latestLogMessage?: string | null
  }

function toRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function toNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function getCrawlStats(extraParams: Record<string, unknown> | null) {
  return toRecord(extraParams?.crawl_stats)
}

function buildMetrics(extraParams: Record<string, unknown> | null): Array<{ label: string; value: string }> {
  const crawlStats = getCrawlStats(extraParams)
  const successCount = toNumber(crawlStats?.success_count)
  const failureCount = toNumber(crawlStats?.failure_count)
  const subtitleCount = toNumber(crawlStats?.subtitle_count)
  const candidateCount = toNumber(crawlStats?.candidate_count)
  const metrics: Array<{ label: string; value: string }> = []

  if (candidateCount !== null) {
    metrics.push({ label: '候选视频', value: formatNumber(candidateCount) })
  }
  if (successCount !== null) {
    metrics.push({ label: '成功入库', value: formatNumber(successCount) })
  }
  if (failureCount !== null && failureCount > 0) {
    metrics.push({ label: '抓取失败', value: formatNumber(failureCount) })
  }
  if (subtitleCount !== null) {
    metrics.push({ label: '命中字字幕', value: formatNumber(subtitleCount) })
  }

  return metrics
}

function buildFailureDescription(task: TaskLike): string {
  if (task.error_message?.includes('AI analysis failed')) {
    return '任务在 AI 分析阶段失败，当前没有可用的 AI 摘要与主题结果，请先检查日志和模型配置。'
  }

  return task.error_message
    ? `任务执行失败：${task.error_message}`
    : '任务执行失败，请优先查看最近错误日志和后端服务状态。'
}

function statusTitle(status: TaskStatus): string {
  const titles: Record<TaskStatus, string> = {
    pending: '任务已创建，等待处理',
    queued: '任务已入队，等待 Worker 接手',
    running: '任务正在执行中',
    paused: '任务已暂停',
    partial_success: '任务已部分完成',
    success: '任务已完成',
    failed: '任务执行失败',
    cancelled: '任务已取消',
  }

  return titles[status]
}

export function buildTaskLifecycleNotice(task: TaskLike): TaskLifecycleNoticeData {
  const isTerminalArtifactPending =
    (task.status === 'success' || task.status === 'partial_success') &&
    (task.current_stage === 'author' || task.current_stage === 'report')

  if (task.status === 'success' && !isTerminalArtifactPending) {
    return {
      tone: 'success',
      title: statusTitle(task.status),
      description: '',
      metrics: buildMetrics(task.extra_params),
    }
  }

  if (task.status === 'partial_success' && !isTerminalArtifactPending) {
    return {
      tone: 'warning',
      title: statusTitle(task.status),
      description: '',
      metrics: buildMetrics(task.extra_params),
    }
  }

  if (isTerminalArtifactPending) {
    return {
      tone: task.status === 'success' ? 'neutral' : 'warning',
      title: '任务收尾中',
      description: '',
      metrics: buildMetrics(task.extra_params),
    }
  }

  if (task.status === 'failed' || task.status === 'cancelled') {
    return {
      tone: 'danger',
      title: statusTitle(task.status),
      description: buildFailureDescription(task),
      metrics: buildMetrics(task.extra_params),
    }
  }

  if (task.status === 'paused') {
    return {
      tone: 'warning',
      title: statusTitle(task.status),
      description: '',
      metrics: buildMetrics(task.extra_params),
    }
  }

  return {
    tone: 'neutral',
    title: statusTitle(task.status),
    description: '',
    metrics: buildMetrics(task.extra_params),
  }
}
