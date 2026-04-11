import { createPinia } from 'pinia'
import type { Plugin } from 'vue'
import { createRouter, createMemoryHistory, type RouteRecordRaw } from 'vue-router'

export function flushPromises() {
  return new Promise((resolve) => {
    window.setTimeout(resolve, 0)
  })
}

export function createTestRouter(routes: RouteRecordRaw[]) {
  return createRouter({
    history: createMemoryHistory(),
    routes,
  })
}

export function createTestingPlugins(router?: ReturnType<typeof createTestRouter>) {
  const plugins: Plugin[] = [createPinia()]
  if (router) {
    plugins.unshift(router as Plugin)
  }
  return plugins
}
