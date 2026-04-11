<template>
  <span class="status-badge" :class="`status-badge--${status}`">{{ label }}</span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import type { TaskStatus } from '@/api/types'
import { statusLabel } from '@/utils/format'

const props = defineProps<{
  status: TaskStatus
}>()

const label = computed(() => statusLabel(props.status))
</script>
