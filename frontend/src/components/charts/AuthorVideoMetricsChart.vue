<template>
  <div ref="chartRef" class="chart-surface"></div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { TaskAnalysisAuthorVideo } from '@/api/types'
import { init, type EChartsType } from './chartCore'

const props = defineProps<{
  videos: TaskAnalysisAuthorVideo[]
}>()

const chartRef = ref<HTMLDivElement | null>(null)
let chart: EChartsType | null = null

function truncateTitle(title: string, max = 10) {
  return title.length > max ? `${title.slice(0, max)}...` : title
}

function renderChart() {
  if (!chartRef.value) {
    return
  }

  const videos = [...props.videos]
    .sort((left, right) => right.view_count - left.view_count)
    .slice(0, 8)

  if (!chart) {
    chart = init(chartRef.value)
  }

  chart.setOption({
    backgroundColor: 'transparent',
    grid: {
      left: 28,
      right: 18,
      top: 24,
      bottom: 52,
      containLabel: true,
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
    },
    legend: {
      bottom: 0,
      textStyle: {
        color: '#6e5440',
      },
    },
    xAxis: {
      type: 'category',
      data: videos.map((video) => truncateTitle(video.title)),
      axisLabel: {
        color: '#3d2d21',
        interval: 0,
        rotate: videos.length > 4 ? 18 : 0,
      },
    },
    yAxis: [
      {
        type: 'value',
        name: '播放',
        axisLabel: { color: '#6e5440' },
        splitLine: {
          lineStyle: {
            color: 'rgba(110, 84, 64, 0.12)',
          },
        },
      },
      {
        type: 'value',
        name: '互动率',
        axisLabel: {
          color: '#6e5440',
          formatter: '{value}%',
        },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: '播放量',
        type: 'bar',
        data: videos.map((video) => video.view_count),
        itemStyle: {
          color: '#d6a06f',
          borderRadius: [8, 8, 0, 0],
        },
      },
      {
        name: '互动率',
        type: 'line',
        yAxisIndex: 1,
        smooth: true,
        symbolSize: 8,
        data: videos.map((video) => Number(((video.engagement_rate || 0) * 100).toFixed(2))),
        lineStyle: {
          color: '#266245',
          width: 3,
        },
        itemStyle: {
          color: '#266245',
        },
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
  () => props.videos,
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
