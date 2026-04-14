import { mount, type VueWrapper } from '@vue/test-utils'
import type { ComponentPublicInstance } from 'vue'
import { beforeEach, vi } from 'vitest'

import { createTestRouter, createTestingPlugins, flushPromises } from '@/test/test-utils'
import TaskCreateView from '@/views/TaskCreateView.vue'

const { createTaskMock } = vi.hoisted(() => ({
  createTaskMock: vi.fn(),
}))

vi.mock('@/api/tasks', () => ({
  createTask: createTaskMock,
}))

async function mountView() {
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

  return { wrapper, router }
}

function findSelects(wrapper: ReturnType<typeof mount>) {
  return wrapper.findAllComponents({ name: 'ElSelect' })
}

function findKeywordExpansionSwitch(wrapper: ReturnType<typeof mount>) {
  return wrapper.getComponent({ name: 'ElSwitch' })
}

function findSelectByTestId(wrapper: ReturnType<typeof mount>, testId: string) {
  return wrapper.getComponent(
    `[data-testid="${testId}"]`,
  ) as VueWrapper<ComponentPublicInstance>
}

describe('TaskCreateView', () => {
  beforeEach(() => {
    createTaskMock.mockReset()
  })

  it('submits a trimmed keyword with enabled synonym expansion', async () => {
    createTaskMock.mockResolvedValue({
      task: {
        id: 'task-001',
        keyword: 'AI workflow',
      },
      dispatch: {
        celery_task_id: 'celery-001',
        task_name: 'app.worker.run_crawl_task',
      },
    })

    const { wrapper, router } = await mountView()

    const keywordInput = wrapper.findComponent({ name: 'ElInput' })
    expect(keywordInput.exists()).toBe(true)
    keywordInput.vm.$emit('update:modelValue', '  AI workflow  ')

    const expansionSwitch = findKeywordExpansionSwitch(wrapper)
    expansionSwitch.vm.$emit('update:modelValue', true)
    await flushPromises()

    const countSelect = findSelectByTestId(wrapper, 'keyword-expansion-count')
    countSelect.vm.$emit('update:modelValue', 3)
    await flushPromises()

    await wrapper.find('[data-testid="submit-button"]').trigger('click')
    await flushPromises()
    await flushPromises()

    expect(createTaskMock).toHaveBeenCalledWith(
      expect.objectContaining({
        keyword: 'AI workflow',
        crawl_mode: 'keyword',
        enable_keyword_synonym_expansion: true,
        keyword_synonym_count: 3,
        partition_name: null,
      }),
    )
    expect(router.currentRoute.value.fullPath).toBe('/tasks/task-001')
  })

  it('clears expansion fields and fixes max_pages for hot partition mode', async () => {
    createTaskMock.mockResolvedValue({
      task: {
        id: 'task-002',
        keyword: '当前热度',
      },
      dispatch: {
        celery_task_id: 'celery-002',
        task_name: 'app.worker.run_crawl_task',
      },
    })

    const { wrapper } = await mountView()

    const selects = findSelects(wrapper)
    selects[0].vm.$emit('update:modelValue', 'hot')
    selects[1].vm.$emit('update:modelValue', 'partition')
    await flushPromises()

    const partitionSelect = findSelectByTestId(wrapper, 'partition-select')
    partitionSelect.vm.$emit('update:modelValue', 4)
    await flushPromises()

    await wrapper.find('[data-testid="submit-button"]').trigger('click')
    await flushPromises()

    expect(createTaskMock).toHaveBeenCalledWith(
      expect.objectContaining({
        keyword: '',
        crawl_mode: 'hot',
        search_scope: 'partition',
        partition_tid: 4,
        partition_name: '游戏区',
        enable_keyword_synonym_expansion: false,
        keyword_synonym_count: null,
        max_pages: 1,
      }),
    )
  })

  it('restores the default synonym count after toggling expansion off and on again', async () => {
    createTaskMock.mockResolvedValue({
      task: {
        id: 'task-003',
        keyword: 'OpenAI',
      },
      dispatch: {
        celery_task_id: 'celery-003',
        task_name: 'app.worker.run_crawl_task',
      },
    })

    const { wrapper } = await mountView()

    const keywordInput = wrapper.findComponent({ name: 'ElInput' })
    keywordInput.vm.$emit('update:modelValue', 'OpenAI')

    const expansionSwitch = findKeywordExpansionSwitch(wrapper)
    expansionSwitch.vm.$emit('update:modelValue', true)
    await flushPromises()

    let countSelect = findSelectByTestId(wrapper, 'keyword-expansion-count')
    countSelect.vm.$emit('update:modelValue', 5)
    await flushPromises()

    expansionSwitch.vm.$emit('update:modelValue', false)
    await flushPromises()
    expansionSwitch.vm.$emit('update:modelValue', true)
    await flushPromises()

    countSelect = findSelectByTestId(wrapper, 'keyword-expansion-count')
    expect(countSelect.exists()).toBe(true)

    await wrapper.find('[data-testid="submit-button"]').trigger('click')
    await flushPromises()

    expect(createTaskMock).toHaveBeenCalledWith(
      expect.objectContaining({
        keyword: 'OpenAI',
        enable_keyword_synonym_expansion: true,
        keyword_synonym_count: 1,
      }),
    )
  })

  it('submits custom published_within_days when user chooses custom time window', async () => {
    createTaskMock.mockResolvedValue({
      task: {
        id: 'task-004',
        keyword: '自定义时间窗',
      },
      dispatch: {
        celery_task_id: 'celery-004',
        task_name: 'app.worker.run_crawl_task',
      },
    })

    const { wrapper } = await mountView()

    const keywordInput = wrapper.findComponent({ name: 'ElInput' })
    keywordInput.vm.$emit('update:modelValue', '自定义时间窗')

    const publishedWithinSelect = findSelectByTestId(wrapper, 'published-within-select')
    publishedWithinSelect.vm.$emit('update:modelValue', 'custom')
    await flushPromises()

    const publishedWithinCustomInput = wrapper.getComponent(
      '[data-testid="published-within-custom-input"]',
    ) as VueWrapper<ComponentPublicInstance>
    publishedWithinCustomInput.vm.$emit('update:modelValue', 45)
    await flushPromises()

    await wrapper.find('[data-testid="submit-button"]').trigger('click')
    await flushPromises()

    expect(createTaskMock).toHaveBeenCalledWith(
      expect.objectContaining({
        keyword: '自定义时间窗',
        published_within_days: 45,
      }),
    )
  })
})
