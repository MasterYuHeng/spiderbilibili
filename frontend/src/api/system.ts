import { apiClient } from '@/api/client'
import type { AiSettingsPayload, ApiResponse, BilibiliConfig, DeepSeekConfig } from '@/api/types'

export async function getAiSettings(signal?: AbortSignal): Promise<AiSettingsPayload> {
  const response = await apiClient.get<ApiResponse<AiSettingsPayload>>('/ai-settings', { signal })
  return response.data.data as AiSettingsPayload
}

export async function updateDeepSeekApiKey(
  apiKey: string,
  signal?: AbortSignal,
): Promise<DeepSeekConfig> {
  const response = await apiClient.put<ApiResponse<DeepSeekConfig>>(
    '/ai-settings/deepseek',
    { api_key: apiKey },
    { signal },
  )
  return response.data.data as DeepSeekConfig
}

export async function updateBilibiliCookie(
  cookie: string,
  signal?: AbortSignal,
): Promise<BilibiliConfig> {
  const response = await apiClient.put<ApiResponse<BilibiliConfig>>(
    '/bilibili-settings',
    { cookie },
    { signal },
  )
  return response.data.data as BilibiliConfig
}

export async function importBilibiliCookieFromBrowser(
  payload: {
    browser?: string | null
    profile_directory?: string | null
    user_data_dir?: string | null
  },
  signal?: AbortSignal,
): Promise<BilibiliConfig> {
  const response = await apiClient.post<ApiResponse<BilibiliConfig>>(
    '/bilibili-settings/import-browser',
    payload,
    {
      signal,
      timeout: 240000,
    },
  )
  return response.data.data as BilibiliConfig
}
