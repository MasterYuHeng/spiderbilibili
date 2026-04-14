import { mount } from '@vue/test-utils'
import { beforeEach, vi } from 'vitest'

import { createTestRouter, createTestingPlugins, flushPromises } from '@/test/test-utils'
import VideoListView from '@/views/VideoListView.vue'

const {
  exportTaskResultsMock,
  getTaskProgressMock,
  getTaskTopicsMock,
  getTaskVideosMock,
} = vi.hoisted(() => ({
  exportTaskResultsMock: vi.fn(),
  getTaskProgressMock: vi.fn(),
  getTaskTopicsMock: vi.fn(),
  getTaskVideosMock: vi.fn(),
}))

vi.mock('@/api/tasks', () => ({
  exportTaskResults: exportTaskResultsMock,
  getTaskProgress: getTaskProgressMock,
  getTaskTopics: getTaskTopicsMock,
  getTaskVideos: getTaskVideosMock,
}))

async function mountView(path = '/tasks/task-001/videos') {
  const router = createTestRouter([
    {
      path: '/tasks/:taskId/videos',
      component: VideoListView,
    },
  ])

  await router.push(path)
  await router.isReady()

  const wrapper = mount(VideoListView, {
    global: {
      plugins: createTestingPlugins(router),
    },
  })

  await flushPromises()
  await flushPromises()

  return { wrapper, router }
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
    clustered_topics: 3,
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

function buildVideoPayload(overrides: Record<string, unknown> = {}) {
  return {
    task_id: 'task-001',
    page: 1,
    page_size: 10,
    total: 1,
    total_pages: 1,
    items: [
      {
        video_id: 'video-001',
        bvid: 'BV1xx411c7mD',
        aid: 123,
        title: '和平精英新版本吃鸡技巧',
        url: 'https://www.bilibili.com/video/BV1xx411c7mD',
        author_name: '测试作者',
        author_mid: '10001',
        cover_url: null,
        description: '视频描述',
        tags: ['和平精英', '吃鸡'],
        published_at: '2026-04-13T10:00:00Z',
        duration_seconds: 300,
        search_rank: 1,
        matched_keywords: ['和平精英', '吃鸡'],
        primary_matched_keyword: '和平精英',
        keyword_match_count: 2,
        keyword_hit_title: true,
        keyword_hit_description: false,
        keyword_hit_tags: true,
        relevance_score: 0.93,
        heat_score: 0.82,
        composite_score: 0.88,
        is_selected: true,
        metrics: {
          view_count: 120000,
          like_count: 8000,
          coin_count: 3200,
          favorite_count: 2100,
          share_count: 400,
          reply_count: 560,
          danmaku_count: 1200,
          like_view_ratio: 0.066,
          coin_view_ratio: 0.026,
          favorite_view_ratio: 0.017,
          share_view_ratio: 0.003,
          reply_view_ratio: 0.004,
          danmaku_view_ratio: 0.01,
          engagement_rate: 0.12,
          captured_at: '2026-04-14T10:06:00Z',
        },
        text_content: null,
        ai_summary: {
          summary: '视频总结',
          topics: ['版本攻略'],
          primary_topic: '版本攻略',
          tone: null,
          confidence: 0.91,
          model_name: 'gpt-5.4',
        },
      },
    ],
    ...overrides,
  }
}

describe('VideoListView', () => {
  beforeEach(() => {
    exportTaskResultsMock.mockReset()
    getTaskProgressMock.mockReset()
    getTaskTopicsMock.mockReset()
    getTaskVideosMock.mockReset()
  })

  it('renders matched keyword sources for multi-hit videos', async () => {
    getTaskProgressMock.mockResolvedValue(buildProgress())
    getTaskTopicsMock.mockResolvedValue({
      task_id: 'task-001',
      items: [
        {
          id: 'topic-001',
          name: '版本攻略',
          normalized_name: '版本攻略',
          description: null,
          keywords: ['攻略'],
          video_count: 1,
          total_heat_score: 0.82,
          average_heat_score: 0.82,
          video_ratio: 1,
          average_engagement_rate: 0.12,
          cluster_order: 1,
          representative_video: null,
        },
      ],
    })
    getTaskVideosMock.mockResolvedValue(buildVideoPayload())

    const { wrapper } = await mountView()

    expect(wrapper.text()).toContain('搜索口径与命中来源')
    expect(wrapper.text()).toContain('命中来源词')
    expect(wrapper.text()).toContain('主命中词 和平精英')
    expect(wrapper.text()).toContain('命中次数 2')
    expect(wrapper.text()).toContain('吃鸡')
    expect(wrapper.text()).toContain('和平精英')
  })

  it('does not fabricate keyword search context for hot mode results', async () => {
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
    getTaskTopicsMock.mockResolvedValue({
      task_id: 'task-001',
      items: [],
    })
    getTaskVideosMock.mockResolvedValue(
      buildVideoPayload({
        items: [
          {
            ...buildVideoPayload().items[0],
            matched_keywords: [],
            primary_matched_keyword: null,
            keyword_match_count: 0,
          },
        ],
      }),
    )

    const { wrapper } = await mountView()

    expect(wrapper.text()).toContain('热榜模式')
    expect(wrapper.text()).toContain('热榜模式不会执行关键词搜索')
    expect(wrapper.text()).not.toContain('实际搜索词当前热榜')
  })
})
