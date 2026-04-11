<template>
  <section class="empty-state">
    <p class="empty-state__eyebrow">{{ eyebrow }}</p>
    <h3>{{ title }}</h3>
    <p>{{ description }}</p>
    <slot />
  </section>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    eyebrow?: string
    title: string
    description: string
  }>(),
  {
    eyebrow: '暂无数据',
  },
)
</script>
