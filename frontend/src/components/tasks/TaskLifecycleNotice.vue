<template>
  <section class="task-notice" :class="`task-notice--${notice.tone}`">
    <div class="task-notice__head">
      <TaskStatusBadge :status="status" />
      <div>
        <h4>{{ notice.title }}</h4>
        <p v-if="notice.description">{{ notice.description }}</p>
      </div>
    </div>

    <div v-if="notice.metrics.length" class="task-notice__metrics">
      <span v-for="item in notice.metrics" :key="item.label" class="task-notice__metric">
        <strong>{{ item.value }}</strong>
        <small>{{ item.label }}</small>
      </span>
    </div>

    <slot />
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import type { TaskDetail, TaskStatus } from '@/api/types'
import { buildTaskLifecycleNotice } from '@/utils/taskLifecycle'

import TaskStatusBadge from './TaskStatusBadge.vue'

const props = defineProps<{
  status: TaskStatus
  errorMessage?: string | null
  extraParams?: TaskDetail['extra_params']
  latestLogMessage?: string | null
  currentStage?: string | null
}>()

const notice = computed(() =>
  buildTaskLifecycleNotice({
    status: props.status,
    error_message: props.errorMessage ?? null,
    extra_params: props.extraParams ?? null,
    current_stage: props.currentStage ?? undefined,
    latestLogMessage: props.latestLogMessage ?? null,
  }),
)
</script>
