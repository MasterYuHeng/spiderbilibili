import { mount, type VueWrapper } from '@vue/test-utils'
import { ElMessage, ElMessageBox, type MessageBoxData, type MessageHandler } from 'element-plus'
import type { ComponentPublicInstance } from 'vue'
import { beforeEach, vi } from 'vitest'

import { createTestRouter, createTestingPlugins, flushPromises } from '@/test/test-utils'
import TopicAnalysisView from '@/views/TopicAnalysisView.vue'

const {
  exportTaskResultsMock,
  getTaskAnalysisMock,
  getTaskProgressMock,
  updateTaskAnalysisWeightsMock,
} = vi.hoisted(() => ({
  exportTaskResultsMock: vi.fn(),
  getTaskAnalysisMock: vi.fn(),
  getTaskProgressMock: vi.fn(),
  updateTaskAnalysisWeightsMock: vi.fn(),
}))

vi.mock('@/api/tasks', () => ({
  exportTaskResults: exportTaskResultsMock,
  getTaskAnalysis: getTaskAnalysisMock,
  getTaskProgress: getTaskProgressMock,
  updateTaskAnalysisWeights: updateTaskAnalysisWeightsMock,
}))

async function mountView(path = '/tasks/task-001/topics') {
  const router = createTestRouter([
    {
      path: '/tasks/:taskId/topics',
      component: TopicAnalysisView,
    },
    {
      path: '/tasks/:taskId',
      component: { template: '<div>detail page</div>' },
    },
  ])

  await router.push(path)
  await router.isReady()

  const wrapper = mount(TopicAnalysisView, {
    global: {
      plugins: createTestingPlugins(router),
      stubs: {
        CommunityTrendChart: { template: '<div class="chart-stub">community chart</div>' },
        DepthTrendChart: { template: '<div class="chart-stub">depth chart</div>' },
        TopicDonutChart: { template: '<div class="chart-stub">topic donut</div>' },
        TopicEvolutionComparisonChart: {
          template: '<div class="chart-stub">topic evolution comparison</div>',
        },
        TopicEvolutionChart: { template: '<div class="chart-stub">topic evolution</div>' },
        TopicHeatBarChart: { template: '<div class="chart-stub">topic heat</div>' },
        VideoHistoryChart: { template: '<div class="chart-stub">video history</div>' },
        'el-date-picker': {
          template: '<div class="date-picker-stub"><slot /></div>',
        },
        EmptyState: {
          props: ['title', 'description'],
          template: '<div class="empty-state">{{ title }}{{ description }}</div>',
        },
        InsightText: {
          props: ['text'],
          template: '<span>{{ text }}</span>',
        },
        StatCard: {
          props: ['label', 'value'],
          template: '<div class="stat-card">{{ label }}{{ value }}</div>',
        },
        TaskLifecycleNotice: { template: '<div class="lifecycle-stub">notice</div>' },
        TaskSearchContextCard: { template: '<div class="search-context-stub">context</div>' },
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
      source_keyword: 'AI',
      enabled: false,
      requested_synonym_count: null,
      generated_synonyms: [],
      expanded_keywords: ['AI'],
      status: 'skipped',
      model_name: null,
      error_message: null,
      generated_at: null,
    },
    search_keywords_used: ['AI'],
    expanded_keyword_count: 0,
    latest_log: {
      id: 'log-001',
      level: 'info',
      stage: 'report',
      message: 'analysis ready',
      payload: null,
      created_at: '2026-04-14T10:08:00Z',
    },
    ...overrides,
  }
}

function buildAnalysis(overrides: Record<string, unknown> = {}) {
  return {
    task_id: 'task-001',
    status: 'success',
    generated_at: '2026-04-14T10:08:00Z',
    summary: {
      total_videos: 1,
      average_view_count: 1200,
      average_like_count: 180,
      average_coin_count: 40,
      average_favorite_count: 52,
      average_share_count: 12,
      average_reply_count: 16,
      average_danmaku_count: 6,
      average_composite_score: 0.86,
      average_engagement_rate: 0.255,
    },
    topics: [
      {
        id: 'topic-ai',
        name: 'AI',
        normalized_name: 'ai',
        description: 'AI topic',
        keywords: ['AI'],
        video_count: 1,
        total_heat_score: 0.79,
        average_heat_score: 0.79,
        video_ratio: 1,
        average_engagement_rate: 0.255,
        cluster_order: 1,
        representative_video: {
          video_id: 'video-001',
          bvid: 'BV1topic',
          title: 'AI topic video',
          url: 'https://www.bilibili.com/video/BV1topic',
          composite_score: 0.86,
        },
      },
    ],
    top_videos: [],
    advanced: {
      hot_topics: [],
      keyword_cooccurrence: [],
      publish_date_distribution: [],
      duration_heat_correlation: {
        metric: 'duration_seconds_vs_heat_score',
        correlation: null,
      },
      momentum_topics: [],
      explosive_videos: [],
      depth_topics: [],
      deep_videos: [],
      community_topics: [],
      community_videos: [],
      topic_evolution: [],
      latest_hot_topic: {
        topic: null,
        reason: null,
        supporting_points: [],
      },
      topic_insights: [],
      video_insights: [],
      metric_definitions: [],
      metric_weight_configs: [
        {
          metric_key: 'burst_score',
          metric_name: '爆发力',
          category: '增长动能',
          formula:
            '0.45 * 搜索初始播放到当前播放增长率归一化 + 0.35 * 发布以来小时均播放归一化 + 0.20 * 历史快照小时增速归一化',
          normalization_note: '用户填写的是相对权重，系统会自动归一化后再参与计算。',
          customized: false,
          components: [
            {
              key: 'search_growth',
              label: '搜索初始播放到当前播放增长率归一化',
              weight: 0.45,
              default_weight: 0.45,
              effective_weight: 0.45,
            },
            {
              key: 'publish_velocity',
              label: '发布以来小时均播放归一化',
              weight: 0.35,
              default_weight: 0.35,
              effective_weight: 0.35,
            },
            {
              key: 'history_velocity',
              label: '历史快照小时增速归一化',
              weight: 0.2,
              default_weight: 0.2,
              effective_weight: 0.2,
            },
          ],
        },
        {
          metric_key: 'topic_heat_index',
          metric_name: '主题热度指数',
          category: '主题演化',
          formula: '1.00 * 主题总热度 + 1.00 * 当期平均爆发力 + 1.00 * 当期平均社区扩散',
          normalization_note: '用户填写的是相对权重，系统会自动归一化后再参与计算。',
          customized: false,
          components: [
            {
              key: 'total_heat_score',
              label: '主题总热度',
              weight: 1,
              default_weight: 1,
              effective_weight: 1,
            },
            {
              key: 'average_burst_score',
              label: '当期平均爆发力',
              weight: 1,
              default_weight: 1,
              effective_weight: 1,
            },
            {
              key: 'average_community_score',
              label: '当期平均社区扩散',
              weight: 1,
              default_weight: 1,
              effective_weight: 1,
            },
          ],
        },
      ],
      recommendations: [],
      popular_authors: [],
      topic_hot_authors: [],
      author_analysis_notes: [],
      data_notes: ['当前分析使用默认指标权重。'],
    },
    has_ai_summaries: true,
    has_topics: true,
    ...overrides,
  }
}

describe('TopicAnalysisView', () => {
  beforeEach(() => {
    exportTaskResultsMock.mockReset()
    getTaskAnalysisMock.mockReset()
    getTaskProgressMock.mockReset()
    updateTaskAnalysisWeightsMock.mockReset()
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({
      value: '',
      action: 'confirm',
    } as MessageBoxData)
    vi.spyOn(ElMessage, 'success').mockImplementation(
      () =>
        ({
          close: () => undefined,
        }) as MessageHandler,
    )
    vi.spyOn(ElMessage, 'error').mockImplementation(
      () =>
        ({
          close: () => undefined,
        }) as MessageHandler,
    )
  })

  it('submits updated metric weights after confirmation and refreshes analysis output', async () => {
    const baseAnalysis = buildAnalysis()
    getTaskProgressMock.mockResolvedValue(buildProgress())
    getTaskAnalysisMock.mockResolvedValue(baseAnalysis)
    updateTaskAnalysisWeightsMock.mockResolvedValue(
      buildAnalysis({
        advanced: {
          ...baseAnalysis.advanced,
          metric_weight_configs: [
            {
              metric_key: 'burst_score',
              metric_name: '爆发力',
              category: '增长动能',
              formula:
                '0.80 * 搜索初始播放到当前播放增长率归一化 + 0.15 * 发布以来小时均播放归一化 + 0.05 * 历史快照小时增速归一化',
              normalization_note: '用户填写的是相对权重，系统会自动归一化后再参与计算。',
              customized: true,
              components: [
                {
                  key: 'search_growth',
                  label: '搜索初始播放到当前播放增长率归一化',
                  weight: 0.8,
                  default_weight: 0.45,
                  effective_weight: 0.8,
                },
                {
                  key: 'publish_velocity',
                  label: '发布以来小时均播放归一化',
                  weight: 0.15,
                  default_weight: 0.35,
                  effective_weight: 0.15,
                },
                {
                  key: 'history_velocity',
                  label: '历史快照小时增速归一化',
                  weight: 0.05,
                  default_weight: 0.2,
                  effective_weight: 0.05,
                },
              ],
            },
            baseAnalysis.advanced.metric_weight_configs[1],
          ],
          data_notes: ['当前分析使用自定义指标权重。'],
        },
      }),
    )

    const { wrapper } = await mountView()

    const searchGrowthInput = wrapper.getComponent(
      '[data-testid="metric-weight-burst_score-search_growth"]',
    ) as VueWrapper<ComponentPublicInstance>
    searchGrowthInput.vm.$emit('update:modelValue', 0.8)
    const publishVelocityInput = wrapper.getComponent(
      '[data-testid="metric-weight-burst_score-publish_velocity"]',
    ) as VueWrapper<ComponentPublicInstance>
    publishVelocityInput.vm.$emit('update:modelValue', 0.15)
    const historyVelocityInput = wrapper.getComponent(
      '[data-testid="metric-weight-burst_score-history_velocity"]',
    ) as VueWrapper<ComponentPublicInstance>
    historyVelocityInput.vm.$emit('update:modelValue', 0.05)
    await flushPromises()

    await wrapper.get('[data-testid="metric-weight-submit-button"]').trigger('click')
    await flushPromises()
    await flushPromises()

    expect(ElMessageBox.confirm).toHaveBeenCalled()
    expect(updateTaskAnalysisWeightsMock).toHaveBeenCalledWith(
      'task-001',
      expect.objectContaining({
        metrics: expect.arrayContaining([
          expect.objectContaining({
            metric_key: 'burst_score',
            components: [
              { key: 'search_growth', weight: 0.8 },
              { key: 'publish_velocity', weight: 0.15 },
              { key: 'history_velocity', weight: 0.05 },
            ],
          }),
        ]),
      }),
    )
    expect(wrapper.text()).toContain('0.80 * 搜索初始播放到当前播放增长率归一化')
    expect(wrapper.text()).toContain('已自定义')
    expect(wrapper.text()).toContain('当前分析使用自定义指标权重。')
  })
})
