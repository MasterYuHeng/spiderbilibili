import { mount } from '@vue/test-utils'

import TaskLifecycleNotice from '@/components/tasks/TaskLifecycleNotice.vue'
import { createTestingPlugins } from '@/test/test-utils'

describe('TaskLifecycleNotice', () => {
  it('renders compact partial success status and metrics', () => {
    const wrapper = mount(TaskLifecycleNotice, {
      props: {
        status: 'partial_success',
        extraParams: {
          crawl_stats: {
            candidate_count: 12,
            success_count: 9,
            failure_count: 3,
            subtitle_count: 4,
          },
        },
        latestLogMessage: 'AI stage finished with fallback summaries.',
        currentStage: 'ai',
      },
      global: {
        plugins: createTestingPlugins(),
      },
    })

    const text = wrapper.text()

    expect(text).toContain('任务已部分完成')
    expect(text).toContain('12')
    expect(text).toContain('9')
    expect(text).toContain('3')
    expect(text).toContain('4')
  })

  it('renders compact pending artifact status', () => {
    const wrapper = mount(TaskLifecycleNotice, {
      props: {
        status: 'success',
        extraParams: {
          crawl_stats: {
            candidate_count: 10,
            success_count: 10,
            subtitle_count: 10,
          },
        },
        latestLogMessage: 'Generating task report snapshot.',
        currentStage: 'report',
      },
      global: {
        plugins: createTestingPlugins(),
      },
    })

    const text = wrapper.text()

    expect(text).toContain('任务收尾中')
    expect(text).toContain('10')
  })
})
