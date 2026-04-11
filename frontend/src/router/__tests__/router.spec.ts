import { mount } from '@vue/test-utils'

import App from '@/App.vue'
import { router } from '@/router'
import { createTestingPlugins, flushPromises } from '@/test/test-utils'

describe('router', () => {
  it('redirects root path to the task creation page', async () => {
    await router.push('/')
    await router.isReady()
    await flushPromises()

    const wrapper = mount(App, {
      global: {
        plugins: createTestingPlugins(router),
      },
    })
    await flushPromises()

    expect(router.currentRoute.value.fullPath).toBe('/tasks/create')
    expect(wrapper.text()).toContain('开始一次新的热点采集')
  })

  it('resolves task video route metadata correctly', () => {
    const resolved = router.resolve('/tasks/task-001/videos')

    expect(resolved.name).toBe('task-videos')
    expect(resolved.meta.title).toBe('视频结果')
  })

  it('resolves task acceptance route metadata correctly', () => {
    const resolved = router.resolve('/tasks/task-001/acceptance')

    expect(resolved.name).toBe('task-acceptance')
    expect(resolved.meta.title).toBe('上线验收')
  })

  it('resolves task author route metadata correctly', () => {
    const resolved = router.resolve('/tasks/task-001/authors')

    expect(resolved.name).toBe('task-authors')
    expect(resolved.meta.title).toBe('UP 主分析')
  })

  it('resolves trash route metadata correctly', () => {
    const resolved = router.resolve('/tasks/trash')

    expect(resolved.name).toBe('task-trash')
    expect(resolved.meta.title).toBe('回收站')
  })
})
