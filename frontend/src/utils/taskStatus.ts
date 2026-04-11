import type { TaskStatus } from '@/api/types'

export function isActiveTaskStatus(status: TaskStatus | undefined): boolean {
  return status === 'pending' || status === 'queued' || status === 'running'
}

export function canPauseTask(status: TaskStatus): boolean {
  return isActiveTaskStatus(status)
}

export function canResumeTask(status: TaskStatus): boolean {
  return status === 'paused'
}

export function canCancelTask(status: TaskStatus): boolean {
  return isActiveTaskStatus(status) || status === 'paused'
}

export function canDeleteTask(status: TaskStatus): boolean {
  return Boolean(status)
}
