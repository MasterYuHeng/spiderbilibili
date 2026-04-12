<template>
  <aside class="sidebar">
    <div class="sidebar__brand">
      <p class="sidebar__eyebrow">Bilibili Hot Search</p>
      <h1>B站热点搜索</h1>
    </div>

    <nav class="sidebar__nav">
      <RouterLink
        v-for="item in primaryItems"
        :key="item.to"
        class="sidebar__link"
        :class="{ 'is-active': route.path === item.to }"
        :to="item.to"
      >
        <span>{{ item.label }}</span>
      </RouterLink>
    </nav>

    <section class="sidebar__task">
      <div class="sidebar__task-head">
        <span>当前任务</span>
        <strong>{{ taskTitle }}</strong>
      </div>
      <p v-if="!currentTaskId" class="sidebar__task-empty">暂未选择任务</p>
      <RouterLink
        v-for="item in taskItems"
        :key="item.name"
        class="sidebar__task-link"
        :class="{ 'is-active': route.name === item.name }"
        :to="item.to"
      >
        <span>{{ item.label }}</span>
      </RouterLink>
    </section>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

const props = defineProps<{
  currentTaskId: string
  currentTaskLabel: string
}>()

const route = useRoute()

const primaryItems = [
  { to: '/tasks/create', label: '创建任务' },
  { to: '/tasks', label: '任务列表' },
  { to: '/tasks/trash', label: '回收站' },
  { to: '/settings/ai', label: '系统设置' },
]

const taskTitle = computed(() =>
  props.currentTaskId
    ? props.currentTaskLabel || `任务 ${props.currentTaskId.slice(0, 8)}`
    : '暂未选择任务',
)

const taskItems = computed(() => {
  if (!props.currentTaskId) {
    return []
  }

  return [
    { name: 'task-detail', label: '任务详情', to: `/tasks/${props.currentTaskId}` },
    { name: 'task-videos', label: '视频结果', to: `/tasks/${props.currentTaskId}/videos` },
    { name: 'task-topics', label: '主题分析', to: `/tasks/${props.currentTaskId}/topics` },
    { name: 'task-authors', label: 'UP 主分析', to: `/tasks/${props.currentTaskId}/authors` },
    { name: 'task-report', label: '任务报告', to: `/tasks/${props.currentTaskId}/report` },
    { name: 'task-acceptance', label: '上线验收', to: `/tasks/${props.currentTaskId}/acceptance` },
  ]
})
</script>
