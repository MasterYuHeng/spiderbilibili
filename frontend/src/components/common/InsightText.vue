<template>
  <component :is="tag" ref="root" class="insight-text"></component>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { formatInsightHtml } from '@/utils/aiText'

const props = withDefaults(
  defineProps<{
    text: string | null | undefined
    tag?: string
    stripLeadingTitle?: string | null
  }>(),
  {
    tag: 'p',
    stripLeadingTitle: null,
  },
)

const root = ref<HTMLElement | null>(null)
const formattedHtml = computed(() =>
  formatInsightHtml(props.text, { stripLeadingTitle: props.stripLeadingTitle }),
)

function syncHtml() {
  if (root.value) {
    root.value.innerHTML = formattedHtml.value
  }
}

watch(formattedHtml, () => {
  syncHtml()
})

onMounted(() => {
  syncHtml()
})
</script>

<style scoped>
.insight-text {
  margin: 0;
  white-space: normal;
  word-break: break-word;
  line-height: 1.8;
}

.insight-text :deep(strong) {
  color: #1a120d;
  font-weight: 800;
  background: linear-gradient(transparent 58%, rgba(130, 75, 32, 0.14) 58%);
}
</style>
