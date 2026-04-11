<template>
  <div ref="chartRef" class="chart-surface"></div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { TaskAnalysisPopularAuthor } from '@/api/types'
import { init, type EChartsType } from './chartCore'

const props = defineProps<{
  authors: TaskAnalysisPopularAuthor[]
}>()

const chartRef = ref<HTMLDivElement | null>(null)
let chart: EChartsType | null = null

function renderChart() {
  if (!chartRef.value) {
    return
  }

  const authors = [...props.authors].slice(0, 8)
  if (!chart) {
    chart = init(chartRef.value)
  }

  chart.setOption({
    backgroundColor: 'transparent',
    grid: {
      left: 28,
      right: 18,
      top: 24,
      bottom: 42,
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
      data: authors.map((author) => author.author_name),
      axisLabel: {
        color: '#3d2d21',
        interval: 0,
        rotate: authors.length > 4 ? 18 : 0,
      },
    },
    yAxis: [
      {
        type: 'value',
        name: '综合',
        axisLabel: { color: '#6e5440' },
        splitLine: {
          lineStyle: {
            color: 'rgba(110, 84, 64, 0.12)',
          },
        },
      },
      {
        type: 'value',
        name: '比例',
        axisLabel: {
          color: '#6e5440',
          formatter: '{value}%',
        },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: '热点贡献',
        type: 'bar',
        data: authors.map((author) => author.source_total_heat_score),
        itemStyle: {
          color: '#ca5c1f',
          borderRadius: [8, 8, 0, 0],
        },
      },
      {
        name: '热点样本数',
        type: 'bar',
        data: authors.map((author) => author.source_video_count),
        itemStyle: {
          color: '#d6a06f',
          borderRadius: [8, 8, 0, 0],
        },
      },
      {
        name: '补抓互动率',
        type: 'line',
        yAxisIndex: 1,
        data: authors.map((author) =>
          Number((author.fetched_average_engagement_rate * 100).toFixed(2)),
        ),
        smooth: true,
        symbolSize: 8,
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
  () => props.authors,
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
