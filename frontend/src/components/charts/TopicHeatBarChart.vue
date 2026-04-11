<template>
  <div ref="chartRef" class="chart-surface"></div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { TaskTopic } from '@/api/types'
import { init, type EChartsType } from './chartCore'

const props = defineProps<{
  topics: TaskTopic[]
  activeTopic: string | null
}>()

const emit = defineEmits<{
  select: [topicName: string]
}>()

const chartRef = ref<HTMLDivElement | null>(null)
let chart: EChartsType | null = null

function renderChart() {
  if (!chartRef.value) {
    return
  }

  const sorted = [...props.topics]
    .sort((left, right) => right.total_heat_score - left.total_heat_score)
    .slice(0, 8)

  if (!chart) {
    chart = init(chartRef.value)
    chart.on('click', (params) => {
      if (typeof params.name === 'string') {
        emit('select', params.name)
      }
    })
  }

  chart.setOption({
    backgroundColor: 'transparent',
    grid: {
      left: 24,
      right: 18,
      top: 24,
      bottom: 18,
      containLabel: true,
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
    },
    xAxis: {
      type: 'value',
      axisLabel: { color: '#6e5440' },
      splitLine: {
        lineStyle: {
          color: 'rgba(110, 84, 64, 0.12)',
        },
      },
    },
    yAxis: {
      type: 'category',
      data: sorted.map((topic) => topic.name),
      axisLabel: { color: '#3d2d21' },
    },
    series: [
      {
        type: 'bar',
        data: sorted.map((topic) => ({
          name: topic.name,
          value: topic.total_heat_score,
          itemStyle: {
            color: topic.name === props.activeTopic ? '#ca5c1f' : '#d6a06f',
            borderRadius: [0, 8, 8, 0],
          },
        })),
      },
    ],
  })

  chart.resize()
}

function handleResize() {
  chart?.resize()
}

onMounted(() => {
  renderChart()
  window.addEventListener('resize', handleResize)
})

watch(
  () => [props.topics, props.activeTopic],
  () => {
    renderChart()
  },
  { deep: true },
)

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  chart?.dispose()
  chart = null
})
</script>
