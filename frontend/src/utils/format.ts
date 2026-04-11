import type { TaskStatus } from '@/api/types'

const datetimeFormatter = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
})

const numberFormatter = new Intl.NumberFormat('zh-CN')

export function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return '--'
  }

  return datetimeFormatter.format(new Date(value))
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return '--'
  }

  return numberFormatter.format(value)
}

export function formatCompactNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return '--'
  }

  if (value >= 100000000) {
    return `${(value / 100000000).toFixed(1)}亿`
  }

  if (value >= 10000) {
    return `${(value / 10000).toFixed(1)}万`
  }

  return formatNumber(value)
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) {
    return '--'
  }

  return `${(value * 100).toFixed(digits)}%`
}

export function formatScore(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) {
    return '--'
  }

  return value.toFixed(digits)
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) {
    return '--'
  }

  const minutes = Math.floor(seconds / 60)
  const remainSeconds = seconds % 60
  return `${minutes}:${String(remainSeconds).padStart(2, '0')}`
}

export function statusLabel(status: TaskStatus): string {
  const labels: Record<TaskStatus, string> = {
    pending: '待处理',
    queued: '已排队',
    running: '运行中',
    paused: '已暂停',
    partial_success: '部分成功',
    success: '成功',
    failed: '失败',
    cancelled: '已取消',
  }

  return labels[status] ?? status
}

export function isRetryableStatus(status: TaskStatus | null | undefined): boolean {
  return status === 'failed' || status === 'cancelled' || status === 'partial_success'
}

export function stageLabel(stage: string): string {
  const labels: Record<string, string> = {
    task: '任务初始化',
    search: '搜索采集',
    detail: '详情抓取',
    subtitle: '字幕处理',
    text: '文本清洗',
    ai: 'AI 分析',
    topic: '主题聚类',
    author: 'UP 主分析',
    report: '任务报告',
    export: '导出结果',
  }

  return labels[stage] ?? stage
}

export function normalizeNullableNumber(value: number | null | undefined): number | null {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return null
  }

  return value
}

export function triggerBlobDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.append(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}
