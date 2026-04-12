import axios, { AxiosError } from 'axios'

const rawBaseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() ?? ''

function normalizeBaseUrl(baseUrl: string): string {
  if (!baseUrl) {
    return '/api'
  }

  const sanitizedBaseUrl = baseUrl.replace(/\/+$/, '')
  if (!sanitizedBaseUrl) {
    return '/api'
  }

  return sanitizedBaseUrl.endsWith('/api') ? sanitizedBaseUrl : `${sanitizedBaseUrl}/api`
}

export const apiClient = axios.create({
  baseURL: normalizeBaseUrl(rawBaseUrl),
  timeout: 30000,
})

function toDetailsRecord(details: unknown): Record<string, unknown> | null {
  return details && typeof details === 'object' && !Array.isArray(details)
    ? (details as Record<string, unknown>)
    : null
}

function getFriendlyValidationMessage(details: unknown): string | null {
  if (!Array.isArray(details)) {
    return null
  }

  for (const item of details) {
    if (!item || typeof item !== 'object') {
      continue
    }

    const record = item as Record<string, unknown>
    const location = Array.isArray(record.loc) ? record.loc.map(String) : []
    const field = location.at(-1)

    if (field === 'keyword') {
      return '关键词不能为空。'
    }
  }

  return '请求参数校验失败，请检查输入内容。'
}

function getFriendlyServerMessage(
  code: unknown,
  message: unknown,
  details: unknown,
): string | null {
  if (typeof code !== 'string') {
    return null
  }

  if (code === 'request_validation_error') {
    return getFriendlyValidationMessage(details)
  }

  if (typeof message !== 'string') {
    return null
  }

  const detailRecord = toDetailsRecord(details)

  if (message.includes('requested_video_limit exceeds')) {
    return `采集数量超过系统上限，当前最大允许值为 ${detailRecord?.max_allowed ?? '配置上限'}。`
  }

  if (message.includes('max_pages exceeds')) {
    return `采集页数超过系统上限，当前最大允许值为 ${detailRecord?.max_allowed ?? '配置上限'}。`
  }

  if (message.includes('min_sleep_seconds cannot be greater')) {
    return '最小休眠时间不能大于最大休眠时间。'
  }

  if (message.includes('Non-proxy tasks must use the local_sleep IP strategy')) {
    return '未启用代理时，只能使用 local_sleep 策略。'
  }

  if (message.includes('Failed to enqueue crawl task')) {
    return '任务已创建，但队列入队失败，请检查 Celery 或 Redis 服务。'
  }

  if (message.includes('Task not found')) {
    return '任务不存在，可能已被删除。'
  }

  if (message.includes('Internal server error')) {
    return '服务内部异常，请稍后重试。'
  }

  return null
}

export function toRequestError(error: unknown): Error {
  if (error instanceof Error) {
    return error
  }

  if (error && typeof error === 'object' && 'message' in error) {
    return new Error(String(error.message))
  }

  return new Error('Request failed unexpectedly.')
}

export function isRequestCanceled(error: unknown): boolean {
  return axios.isCancel(error) || (error instanceof AxiosError && error.code === 'ERR_CANCELED')
}

export function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof AxiosError) {
    const response = error.response?.data
    if (response && typeof response === 'object') {
      const record = response as Record<string, unknown>
      const friendlyMessage = getFriendlyServerMessage(
        record.error && typeof record.error === 'object'
          ? (record.error as Record<string, unknown>).code
          : null,
        record.message,
        record.error && typeof record.error === 'object'
          ? (record.error as Record<string, unknown>).details
          : null,
      )
      if (friendlyMessage) {
        return friendlyMessage
      }

      if (typeof record.message === 'string' && record.message.trim()) {
        return record.message
      }
    }
  }

  if (error instanceof Error && error.message.trim()) {
    return error.message
  }

  return fallback
}

export { normalizeBaseUrl }
