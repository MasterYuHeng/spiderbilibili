import { mount } from '@vue/test-utils'
import { vi } from 'vitest'

import { createTestRouter, createTestingPlugins, flushPromises } from '@/test/test-utils'
import TaskAcceptanceView from '@/views/TaskAcceptanceView.vue'

const { getTaskAcceptanceMock, getTaskProgressMock } = vi.hoisted(() => ({
  getTaskAcceptanceMock: vi.fn(),
  getTaskProgressMock: vi.fn(),
}))

vi.mock('@/api/tasks', () => ({
  getTaskAcceptance: getTaskAcceptanceMock,
  getTaskProgress: getTaskProgressMock,
}))

describe('TaskAcceptanceView', () => {
  it('renders stage 15 acceptance sections and counts', async () => {
    getTaskProgressMock.mockResolvedValue({
      task_id: 'task-001',
      status: 'partial_success',
      current_stage: 'topic',
      progress_percent: 100,
      total_candidates: 8,
      processed_videos: 8,
      analyzed_videos: 8,
      clustered_topics: 3,
      started_at: null,
      finished_at: null,
      error_message: null,
      extra_params: null,
      latest_log: null,
    })
    getTaskAcceptanceMock.mockResolvedValue({
      task_id: 'task-001',
      task_status: 'partial_success',
      overall_status: 'warn',
      sections: [
        {
          name: 'functional',
          checks: [
            {
              code: 'task-videos-available',
              title: 'Video results are available',
              status: 'pass',
              message: 'At least one task video result is available.',
              actual: 8,
              expected: null,
            },
          ],
        },
        {
          name: 'data',
          checks: [
            {
              code: 'video-dedupe',
              title: 'Video dedupe',
              status: 'warn',
              message: 'No duplicate task videos were detected.',
              actual: { duplicate_video_count: 0 },
              expected: null,
            },
          ],
        },
      ],
    })

    const router = createTestRouter([
      {
        path: '/tasks/:taskId/acceptance',
        component: TaskAcceptanceView,
      },
      {
        path: '/tasks/:taskId',
        component: {
          template: '<div>detail page</div>',
        },
      },
    ])

    await router.push('/tasks/task-001/acceptance')
    await router.isReady()

    const wrapper = mount(TaskAcceptanceView, {
      global: {
        plugins: createTestingPlugins(router),
      },
    })

    await flushPromises()
    await flushPromises()

    expect(getTaskProgressMock).toHaveBeenCalledWith(
      'task-001',
      expect.objectContaining({
        signal: expect.any(AbortSignal),
      }),
    )
    expect(getTaskAcceptanceMock).toHaveBeenCalledWith(
      'task-001',
      expect.objectContaining({
        signal: expect.any(AbortSignal),
      }),
    )
    expect(wrapper.text()).toContain('任务验收总览')
    expect(wrapper.text()).toContain('功能验收')
    expect(wrapper.text()).toContain('数据验收')
    expect(wrapper.text()).toContain('通过项')
    expect(wrapper.text()).toContain('警告项')
  })
})
