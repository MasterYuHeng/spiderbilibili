<template>
  <div ref="chartRef" class="chart-surface"></div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { TaskTopic } from '@/api/types'
import { formatPercent } from '@/utils/format'
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
    tooltip: {
      trigger: 'item',
      formatter: (params: { name: string; value: number; percent: number }) =>
        `${params.name}<br/>视频数 ${params.value}<br/>占比 ${params.percent}%`,
    },
    series: [
      {
        type: 'pie',
        radius: ['48%', '72%'],
        itemStyle: {
          borderRadius: 10,
          borderColor: '#f7efe3',
          borderWidth: 4,
        },
        label: {
          color: '#5a422f',
          formatter: ({ name, data }: { name: string; data: { videoRatio: number | null } }) =>
            `${name}\n${formatPercent(data.videoRatio, 1)}`,
        },
        emphasis: {
          scale: true,
          scaleSize: 6,
        },
        data: props.topics.map((topic) => ({
          name: topic.name,
          value: topic.video_count,
          videoRatio: topic.video_ratio,
          selected: topic.name === props.activeTopic,
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
