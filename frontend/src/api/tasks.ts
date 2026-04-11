import type { AxiosResponse } from 'axios';

import { apiClient, toRequestError } from './client';
import type {
  ApiResponse,
  TaskAcceptancePayload,
  TaskBulkDeletePayload,
  DownloadArtifact,
  ExportDataset,
  ExportFormat,
  ListTaskParams,
  TaskAnalysisPayload,
  TaskCreatePayload,
  TaskCreateRequest,
  TaskDeletePayload,
  TaskDetail,
  TaskListPayload,
  TaskProgressPayload,
  TaskReportPayload,
  TaskRestorePayload,
  TaskTopicListPayload,
  TaskVideoListPayload,
  VideoQueryParams,
} from './types';

interface RequestOptions {
  signal?: AbortSignal;
}

interface TaskDetailOptions extends RequestOptions {
  logLimit?: number;
}

function unwrapData<T>(response: AxiosResponse<ApiResponse<T>>): T {
  const body = response.data;
  if (!body.success || body.data === null) {
    throw new Error(body.message || 'API request failed.');
  }

  return body.data;
}

function buildVideoParams(params: VideoQueryParams): Record<string, string | number> {
  const entries = Object.entries(params).filter(
    ([, value]) => value !== null && value !== undefined,
  );
  return Object.fromEntries(entries) as Record<string, string | number>;
}

function getFilenameFromDisposition(disposition: string | undefined, fallback: string): string {
  if (!disposition) {
    return fallback;
  }

  const match = disposition.match(/filename="?([^"]+)"?/);
  return match?.[1] ?? fallback;
}

async function requestData<T>(request: () => Promise<AxiosResponse<ApiResponse<T>>>): Promise<T> {
  try {
    const response = await request();
    return unwrapData(response);
  } catch (error) {
    throw toRequestError(error);
  }
}

async function getTaskResource<T>(
  taskId: string,
  resourcePath: string,
  options: RequestOptions = {},
  params?: Record<string, string | number | null | undefined>,
): Promise<T> {
  return requestData(() =>
    apiClient.get<ApiResponse<T>>(`/tasks/${taskId}${resourcePath}`, {
      params,
      signal: options.signal,
    }),
  );
}

export async function createTask(payload: TaskCreateRequest): Promise<TaskCreatePayload> {
  return requestData(() => apiClient.post<ApiResponse<TaskCreatePayload>>('/tasks', payload));
}

export async function retryTask(taskId: string): Promise<TaskCreatePayload> {
  return requestData(() =>
    apiClient.post<ApiResponse<TaskCreatePayload>>(`/tasks/${taskId}/retry`),
  );
}

export async function pauseTask(taskId: string): Promise<TaskDetail> {
  return requestData(() => apiClient.post<ApiResponse<TaskDetail>>(`/tasks/${taskId}/pause`));
}

export async function resumeTask(taskId: string): Promise<TaskCreatePayload> {
  return requestData(() =>
    apiClient.post<ApiResponse<TaskCreatePayload>>(
      `/tasks/${taskId}/resume`,
    ),
  );
}

export async function cancelTask(taskId: string): Promise<TaskDetail> {
  return requestData(() => apiClient.post<ApiResponse<TaskDetail>>(`/tasks/${taskId}/cancel`));
}

export async function deleteTask(taskId: string): Promise<TaskDeletePayload> {
  return requestData(() =>
    apiClient.delete<ApiResponse<TaskDeletePayload>>(`/tasks/${taskId}`),
  );
}

export async function deleteAllTasks(): Promise<TaskBulkDeletePayload> {
  return requestData(() => apiClient.delete<ApiResponse<TaskBulkDeletePayload>>('/tasks'));
}

export async function listTasks(params: ListTaskParams): Promise<TaskListPayload> {
  return requestData(() => apiClient.get<ApiResponse<TaskListPayload>>('/tasks', { params }));
}

export async function listTrashTasks(params: ListTaskParams): Promise<TaskListPayload> {
  return requestData(() => apiClient.get<ApiResponse<TaskListPayload>>('/tasks/trash', { params }));
}

export async function restoreTask(taskId: string): Promise<TaskRestorePayload> {
  return requestData(() =>
    apiClient.post<ApiResponse<TaskRestorePayload>>(`/tasks/${taskId}/restore`),
  );
}

export async function permanentlyDeleteTask(taskId: string): Promise<TaskDeletePayload> {
  return requestData(() =>
    apiClient.delete<ApiResponse<TaskDeletePayload>>(`/tasks/${taskId}/permanent`),
  );
}

export async function emptyTrash(): Promise<TaskBulkDeletePayload> {
  return requestData(() => apiClient.delete<ApiResponse<TaskBulkDeletePayload>>('/tasks/trash'));
}

export async function getTaskDetail(
  taskId: string,
  options: TaskDetailOptions = {},
): Promise<TaskDetail> {
  return getTaskResource(taskId, '', options, options.logLimit ? { log_limit: options.logLimit } : undefined);
}

export async function getTaskProgress(
  taskId: string,
  options: RequestOptions = {},
): Promise<TaskProgressPayload> {
  return getTaskResource(taskId, '/progress', options);
}

export async function getTaskVideos(
  taskId: string,
  params: VideoQueryParams,
  options: RequestOptions = {},
): Promise<TaskVideoListPayload> {
  return getTaskResource(taskId, '/videos', options, buildVideoParams(params));
}

export async function getTaskTopics(
  taskId: string,
  options: RequestOptions = {},
): Promise<TaskTopicListPayload> {
  return getTaskResource(taskId, '/topics', options);
}

export async function getTaskAnalysis(
  taskId: string,
  options: RequestOptions = {},
): Promise<TaskAnalysisPayload> {
  return getTaskResource(taskId, '/analysis', options);
}

export async function getTaskAcceptance(
  taskId: string,
  options: RequestOptions = {},
): Promise<TaskAcceptancePayload> {
  return getTaskResource(taskId, '/acceptance', options);
}

export async function getTaskReport(
  taskId: string,
  options: RequestOptions = {},
): Promise<TaskReportPayload> {
  return getTaskResource(taskId, '/report', options);
}

export async function exportTaskResults(
  taskId: string,
  dataset: ExportDataset,
  format: ExportFormat,
  params: VideoQueryParams = {},
): Promise<DownloadArtifact> {
  try {
    const response = await apiClient.get(`/tasks/${taskId}/export`, {
      params: {
        dataset,
        format,
        ...buildVideoParams(params),
      },
      responseType: 'blob',
    });

    const fallback = `${taskId}-${dataset}.${format === 'excel' ? 'xlsx' : format}`;
    return {
      blob: response.data as Blob,
      filename: getFilenameFromDisposition(response.headers['content-disposition'], fallback),
    };
  } catch (error) {
    throw toRequestError(error);
  }
}
