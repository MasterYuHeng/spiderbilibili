<template>
  <div ref="chartRef" class="chart-surface"></div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { init, type EChartsType } from './chartCore'

interface DepthTrendPoint {
  bucket: string
  average_depth_score: number
  average_completion_proxy_score: number
  average_like_view_ratio: number
}

const props = defineProps<{
  points: DepthTrendPoint[]
}>()

const chartRef = ref<HTMLDivElement | null>(null)
let chart: EChartsType | null = null

function toPercent(value: number) {
  return Number((value * 100).toFixed(2))
}

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
        name: '深度分',
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
        name: '点赞率(%)',
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
        name: '内容深度',
        type: 'line',
        smooth: true,
        data: props.points.map((point) => point.average_depth_score),
        itemStyle: {
          color: '#b13a4e',
        },
        lineStyle: {
          width: 3,
        },
      },
      {
        name: '完播代理分',
        type: 'line',
        smooth: true,
        data: props.points.map((point) => point.average_completion_proxy_score),
        itemStyle: {
          color: '#d67732',
        },
        lineStyle: {
          width: 2,
        },
        areaStyle: {
          color: 'rgba(214, 119, 50, 0.10)',
        },
      },
      {
        name: '点赞率',
        type: 'bar',
        yAxisIndex: 1,
        data: props.points.map((point) => toPercent(point.average_like_view_ratio)),
        itemStyle: {
          color: 'rgba(82, 124, 172, 0.68)',
          borderRadius: [8, 8, 0, 0],
        },
        barMaxWidth: 24,
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
