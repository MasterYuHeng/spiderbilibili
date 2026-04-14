import { mount } from '@vue/test-utils'
import { beforeEach, vi } from 'vitest'

import { createTestRouter, createTestingPlugins, flushPromises } from '@/test/test-utils'
import TaskReportView from '@/views/TaskReportView.vue'

const { getTaskProgressMock, getTaskReportMock } = vi.hoisted(() => ({
  getTaskProgressMock: vi.fn(),
  getTaskReportMock: vi.fn(),
}))

vi.mock('@/api/tasks', () => ({
  getTaskProgress: getTaskProgressMock,
  getTaskReport: getTaskReportMock,
}))

async function mountView(path = '/tasks/task-001/report') {
  const router = createTestRouter([
    {
      path: '/tasks/:taskId/report',
      component: TaskReportView,
    },
    {
      path: '/tasks/:taskId',
      component: { template: '<div>detail page</div>' },
    },
    {
      path: '/tasks/:taskId/topics',
      component: { template: '<div>topic page</div>' },
    },
    {
      path: '/tasks/:taskId/authors',
      component: { template: '<div>author page</div>' },
    },
  ])

  await router.push(path)
  await router.isReady()

  const wrapper = mount(TaskReportView, {
    global: {
      plugins: createTestingPlugins(router),
      stubs: {
        AuthorComparisonChart: {
          template: '<div class="chart-stub">author comparison</div>',
        },
      },
    },
  })

  await flushPromises()
  await flushPromises()

  return { wrapper }
}

function buildProgress(overrides: Record<string, unknown> = {}) {
  return {
    task_id: 'task-001',
    status: 'success',
    current_stage: 'report',
    progress_percent: 100,
    total_candidates: 20,
    processed_videos: 18,
    analyzed_videos: 16,
    clustered_topics: 4,
    started_at: '2026-04-14T10:00:00Z',
    finished_at: '2026-04-14T10:08:00Z',
    error_message: null,
    extra_params: {
      task_options: {
        crawl_mode: 'keyword',
        search_scope: 'site',
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
      id: 'log-001',
      level: 'info',
      stage: 'report',
      message: '报告已生成',
      payload: null,
      created_at: '2026-04-14T10:08:00Z',
    },
    ...overrides,
  }
}

function buildReport(overrides: Record<string, unknown> = {}) {
  return {
    task_id: 'task-001',
    status: 'success',
    generated_at: '2026-04-14T10:08:00Z',
    task_keyword: '和平精英',
    title: '和平精英热点分析报告',
    subtitle: null,
    executive_summary: '这是当前任务的执行摘要。',
    latest_hot_topic_name: '版本更新',
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
    featured_videos: [],
    recommendations: [],
    popular_authors: [],
    topic_hot_authors: [],
    sections: [],
    ai_outputs: [],
    report_markdown: '# 报告',
    ...overrides,
  }
}

describe('TaskReportView', () => {
  beforeEach(() => {
    getTaskProgressMock.mockReset()
    getTaskReportMock.mockReset()
  })

  it('renders report search context for keyword expansion tasks', async () => {
    getTaskProgressMock.mockResolvedValue(buildProgress())
    getTaskReportMock.mockResolvedValue(buildReport())

    const { wrapper } = await mountView()

    expect(wrapper.text()).toContain('报告搜索口径')
    expect(wrapper.text()).toContain('和平精英')
    expect(wrapper.text()).toContain('吃鸡')
    expect(wrapper.text()).toContain('实际搜索词')
  })

  it('does not fabricate keyword search context for hot mode reports', async () => {
    getTaskProgressMock.mockResolvedValue(
      buildProgress({
        extra_params: {
          task_options: {
            crawl_mode: 'hot',
            search_scope: 'site',
          },
        },
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
      }),
    )
    getTaskReportMock.mockResolvedValue(
      buildReport({
        task_keyword: '当前热榜',
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
      }),
    )

    const { wrapper } = await mountView()

    expect(wrapper.text()).toContain('热榜模式')
    expect(wrapper.text()).toContain('热榜模式不会执行关键词搜索')
    expect(wrapper.text()).not.toContain('实际搜索词当前热榜')
  })
})
