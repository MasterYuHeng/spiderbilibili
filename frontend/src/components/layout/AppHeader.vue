<template>
  <header class="topbar">
    <div class="topbar__content">
      <h2>{{ pageTitle }}</h2>
    </div>
    <div class="topbar__meta">
      <div class="topbar__chip">
        <span>当前任务</span>
        <strong>{{ taskTitle }}</strong>
      </div>
      <RouterLink v-if="currentTaskId" class="topbar__action" :to="`/tasks/${currentTaskId}`">
        继续查看
      </RouterLink>
      <RouterLink v-else class="topbar__action" to="/tasks/create">新建任务</RouterLink>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

const props = defineProps<{
  currentTaskId: string
  currentTaskLabel: string
}>()

const route = useRoute()

const pageTitle = computed(() => (route.meta.title as string | undefined) ?? '内容洞察控制台')
const taskTitle = computed(() =>
  props.currentTaskId ? props.currentTaskLabel || `任务 ${props.currentTaskId.slice(0, 8)}` : '暂未选择任务',
)
</script>
