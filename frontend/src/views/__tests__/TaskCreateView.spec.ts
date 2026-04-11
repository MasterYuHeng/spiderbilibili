import { mount } from '@vue/test-utils'
import { vi } from 'vitest'

import { createTestRouter, createTestingPlugins, flushPromises } from '@/test/test-utils'
import TaskCreateView from '@/views/TaskCreateView.vue'

const { createTaskMock } = vi.hoisted(() => ({
  createTaskMock: vi.fn(),
}))

vi.mock('@/api/tasks', () => ({
  createTask: createTaskMock,
}))

describe('TaskCreateView', () => {
  it('submits a trimmed keyword and navigates to task detail', async () => {
    createTaskMock.mockResolvedValue({
      task: {
        id: 'task-001',
      },
      dispatch: {
        celery_task_id: 'celery-001',
        task_name: 'app.worker.run_crawl_task',
      },
    })

    const router = createTestRouter([
      {
        path: '/tasks/create',
        component: TaskCreateView,
      },
      {
        path: '/tasks/:taskId',
        component: {
          template: '<div>detail page</div>',
        },
      },
    ])

    await router.push('/tasks/create')
    await router.isReady()

    const wrapper = mount(TaskCreateView, {
      global: {
        plugins: createTestingPlugins(router),
      },
    })

    const keywordInput = wrapper.findComponent({ name: 'ElInput' })
    expect(keywordInput.exists()).toBe(true)

    keywordInput.vm.$emit('update:modelValue', '  AI workflow  ')
    await wrapper.find('.task-form__actions .el-button--primary').trigger('click')
    await flushPromises()
    await flushPromises()

    expect(createTaskMock).toHaveBeenCalledWith(
      expect.objectContaining({
        keyword: 'AI workflow',
      }),
    )
    expect(router.currentRoute.value.fullPath).toBe('/tasks/task-001')
  })
})
