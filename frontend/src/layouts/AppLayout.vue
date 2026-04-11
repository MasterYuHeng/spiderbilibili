<template>
  <div class="app-shell">
    <AppSidebar :current-task-id="currentTaskId" :current-task-label="currentTaskLabel" />
    <div class="app-main">
      <AppHeader :current-task-id="currentTaskId" :current-task-label="currentTaskLabel" />
      <main class="app-content">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { RouterView, useRoute } from 'vue-router'
import { computed, watch } from 'vue'

import AppHeader from '@/components/layout/AppHeader.vue'
import AppSidebar from '@/components/layout/AppSidebar.vue'
import { useTaskWorkspaceStore } from '@/stores/taskWorkspace'

const route = useRoute()
const workspaceStore = useTaskWorkspaceStore()

const currentTaskId = computed(() => workspaceStore.currentTaskId)
const currentTaskLabel = computed(() => workspaceStore.currentTaskLabel)

watch(
  () => route.params.taskId,
  (taskId) => {
    workspaceStore.setCurrentTaskId(typeof taskId === 'string' ? taskId : '')
  },
  { immediate: true },
)
</script>
