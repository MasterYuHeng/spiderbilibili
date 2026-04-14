import { mount } from '@vue/test-utils'
import { beforeEach, vi } from 'vitest'

import { createTestRouter, createTestingPlugins, flushPromises } from '@/test/test-utils'
import TaskDetailView from '@/views/TaskDetailView.vue'

const { getTaskDetailMock, getTaskProgressMock, retryTaskMock } = vi.hoisted(() => ({
  getTaskDetailMock: vi.fn(),
  getTaskProgressMock: vi.fn(),
  retryTaskMock: vi.fn(),
}))

vi.mock('@/api/tasks', () => ({
  getTaskDetail: getTaskDetailMock,
  getTaskProgress: getTaskProgressMock,
  retryTask: retryTaskMock,
}))

async function mountView(path = '/tasks/task-001') {
  const router = createTestRouter([
    {
      path: '/tasks/:taskId',
      component: TaskDetailView,
    },
    {
      path: '/tasks/:taskId/videos',
      component: {
        template: '<div>videos page</div>',
      },
    },
    {
      path: '/tasks/:taskId/topics',
      component: {
        template: '<div>topics page</div>',
      },
    },
    {
      path: '/tasks/:taskId/authors',
      component: {
        template: '<div>authors page</div>',
      },
    },
    {
      path: '/tasks/:taskId/report',
      component: {
        template: '<div>report page</div>',
      },
    },
    {
      path: '/tasks/:taskId/acceptance',
      component: {
        template: '<div>acceptance page</div>',
      },
    },
  ])

  await router.push(path)
  await router.isReady()

  const wrapper = mount(TaskDetailView, {
    global: {
      plugins: createTestingPlugins(router),
    },
  })

  await flushPromises()
  await flushPromises()

  return { wrapper, router }
}

function buildDetail(overrides: Record<string, unknown> = {}) {
  return {
    id: 'task-001',
    keyword: '和平精英',
    status: 'success',
    requested_video_limit: 100,
    max_pages: 5,
    min_sleep_seconds: 1,
    max_sleep_seconds: 3,
    enable_proxy: false,
    source_ip_strategy: 'local_sleep',
    total_candidates: 32,
    processed_videos: 28,
    analyzed_videos: 24,
    clustered_topics: 6,
    started_at: '2026-04-14T10:00:00Z',
    finished_at: '2026-04-14T10:08:00Z',
    error_message: null,
    created_at: '2026-04-14T09:59:00Z',
    updated_at: '2026-04-14T10:08:00Z',
    deleted_at: null,
    extra_params: {
      task_options: {
        crawl_mode: 'keyword',
        search_scope: 'site',
        published_within_days: 30,
        requested_video_limit: 100,
        max_pages: 5,
        min_sleep_seconds: 1,
        max_sleep_seconds: 3,
        enable_proxy: false,
        source_ip_strategy: 'local_sleep',
      },
    },
    keyword_expansion: {
      source_keyword: '和平精英',
      enabled: true,
      requested_synonym_count: 1,
      generated_synonyms: ['吃鸡'],
      expanded_keywords: ['和平精英', '吃鸡'],
      status: 'success',
      model_name: 'gpt-5.4',
      error_message: null,
      generated_at: '2026-04-14T10:00:10Z',
    },
    search_keywords_used: ['和平精英', '吃鸡'],
    expanded_keyword_count: 1,
    current_stage: 'report',
    progress_percent: 100,
    log_total: 2,
    logs_truncated: false,
    logs: [
      {
        id: 'log-2',
        level: 'info',
        stage: 'report',
        message: '报告已生成',
        payload: null,
        created_at: '2026-04-14T10:08:00Z',
      },
      {
        id: 'log-1',
        level: 'info',
        stage: 'search',
        message: '搜索完成',
        payload: { keywords: ['和平精英', '吃鸡'] },
        created_at: '2026-04-14T10:01:00Z',
      },
    ],
    ...overrides,
  }
}

function buildProgress(overrides: Record<string, unknown> = {}) {
  return {
    task_id: 'task-001',
    status: 'success',
    current_stage: 'report',
    progress_percent: 100,
    total_candidates: 32,
    processed_videos: 28,
    analyzed_videos: 24,
    clustered_topics: 6,
    started_at: '2026-04-14T10:00:00Z',
    finished_at: '2026-04-14T10:08:00Z',
    error_message: null,
    extra_params: {
      task_options: {
        crawl_mode: 'keyword',
        search_scope: 'site',
        published_within_days: 30,
        requested_video_limit: 100,
        max_pages: 5,
        min_sleep_seconds: 1,
        max_sleep_seconds: 3,
        enable_proxy: false,
        source_ip_strategy: 'local_sleep',
      },
    },
    keyword_expansion: {
      source_keyword: '和平精英',
      enabled: true,
      requested_synonym_count: 1,
      generated_synonyms: ['吃鸡'],
      expanded_keywords: ['和平精英', '吃鸡'],
      status: 'success',
      model_name: 'gpt-5.4',
      error_message: null,
      generated_at: '2026-04-14T10:00:10Z',
    },
    search_keywords_used: ['和平精英', '吃鸡'],
    expanded_keyword_count: 1,
    latest_log: {
      id: 'log-2',
      level: 'info',
      stage: 'report',
      message: '报告已生成',
      payload: null,
      created_at: '2026-04-14T10:08:00Z',
    },
    ...overrides,
  }
}

describe('TaskDetailView', () => {
  beforeEach(() => {
    getTaskDetailMock.mockReset()
    getTaskProgressMock.mockReset()
    retryTaskMock.mockReset()
  })

  it('renders keyword expansion details on the task detail page', async () => {
    getTaskDetailMock.mockResolvedValue(buildDetail())
    getTaskProgressMock.mockResolvedValue(buildProgress())

    const { wrapper } = await mountView()

    expect(wrapper.text()).toContain('搜索口径')
    expect(wrapper.text()).toContain('和平精英')
    expect(wrapper.text()).toContain('吃鸡')
    expect(wrapper.text()).toContain('关键词抓取')
    expect(wrapper.text()).toContain('全站搜索')
    expect(wrapper.text()).toContain('任务日志')
    expect(wrapper.text()).toContain('报告已生成')
  })

  it('renders hot mode detail without fabricated search keywords', async () => {
    getTaskDetailMock.mockResolvedValue(
      buildDetail({
        keyword: '当前热榜',
        keyword_expansion: {
          source_keyword: '当前热榜',
          enabled: false,
          requested_synonym_count: null,
          generated_synonyms: [],
          expanded_keywords: ['当前热榜'],
          status: 'skipped',
          model_name: null,
          error_message: null,
          generated_at: null,
        },
        search_keywords_used: [],
        expanded_keyword_count: 0,
        extra_params: {
          task_options: {
            crawl_mode: 'hot',
            search_scope: 'site',
            requested_video_limit: 100,
            max_pages: 1,
            min_sleep_seconds: 1,
            max_sleep_seconds: 3,
            enable_proxy: false,
            source_ip_strategy: 'local_sleep',
          },
        },
      }),
    )
    getTaskProgressMock.mockResolvedValue(
      buildProgress({
        keyword_expansion: {
          source_keyword: '当前热榜',
          enabled: false,
          requested_synonym_count: null,
          generated_synonyms: [],
          expanded_keywords: ['当前热榜'],
          status: 'skipped',
          model_name: null,
          error_message: null,
          generated_at: null,
        },
        search_keywords_used: [],
        expanded_keyword_count: 0,
        extra_params: {
          task_options: {
            crawl_mode: 'hot',
            search_scope: 'site',
            requested_video_limit: 100,
            max_pages: 1,
            min_sleep_seconds: 1,
            max_sleep_seconds: 3,
            enable_proxy: false,
            source_ip_strategy: 'local_sleep',
          },
        },
      }),
    )

    const { wrapper } = await mountView()

    expect(wrapper.text()).toContain('热榜抓取')
    expect(wrapper.text()).toContain('全站热榜')
    expect(wrapper.text()).toContain('热榜模式无需扩词')
    expect(wrapper.text()).toContain('热榜模式不会执行关键词搜索')
    expect(wrapper.text()).not.toContain('实际搜索词当前热榜')
  })
})
