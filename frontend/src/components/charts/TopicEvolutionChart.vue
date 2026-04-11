<template>
  <div ref="chartRef" class="chart-surface"></div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { init, type EChartsType } from './chartCore'

interface TopicEvolutionPoint {
  bucket: string
  topic_heat_index: number
  total_heat_score: number
  video_count: number
}

const props = defineProps<{
  points: TopicEvolutionPoint[]
}>()

const chartRef = ref<HTMLDivElement | null>(null)
let chart: EChartsType | null = null

function renderChart() {
  if (!chartRef.value || !props.points.length) {
    return
  }

  if (!chart) {
    chart = init(chartRef.value)
  }

  chart.setOption({
    backgroundColor: 'transparent',
    grid: {
      left: 28,
      right: 28,
      top: 30,
      bottom: 28,
      containLabel: true,
    },
    tooltip: {
      trigger: 'axis',
    },
    legend: {
      top: 0,
      textStyle: {
        color: '#6e5440',
      },
    },
    xAxis: {
      type: 'category',
      data: props.points.map((point) => point.bucket),
      axisLabel: {
        color: '#6e5440',
      },
    },
    yAxis: [
      {
        type: 'value',
        name: '热度',
        axisLabel: {
          color: '#6e5440',
        },
        splitLine: {
          lineStyle: {
            color: 'rgba(110, 84, 64, 0.12)',
          },
        },
      },
      {
        type: 'value',
        name: '视频数',
        axisLabel: {
          color: '#6e5440',
        },
        splitLine: {
          show: false,
        },
      },
    ],
    series: [
      {
        name: '主题热度指数',
        type: 'line',
        smooth: true,
        data: props.points.map((point) => point.topic_heat_index),
        itemStyle: {
          color: '#bd5b20',
        },
        lineStyle: {
          width: 3,
        },
        areaStyle: {
          color: 'rgba(189, 91, 32, 0.14)',
        },
      },
      {
        name: '总热度',
        type: 'line',
        smooth: true,
        data: props.points.map((point) => point.total_heat_score),
        itemStyle: {
          color: '#d6a06f',
        },
        lineStyle: {
          width: 2,
        },
      },
      {
        name: '视频数',
        type: 'bar',
        yAxisIndex: 1,
        data: props.points.map((point) => point.video_count),
        itemStyle: {
          color: 'rgba(75, 111, 173, 0.68)',
          borderRadius: [8, 8, 0, 0],
        },
        barMaxWidth: 28,
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
  () => props.points,
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
