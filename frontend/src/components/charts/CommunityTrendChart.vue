<template>
  <div ref="chartRef" class="chart-surface"></div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { init, type EChartsType } from './chartCore'

interface CommunityTrendPoint {
  bucket: string
  average_community_score: number
  average_share_view_ratio: number
  average_reply_view_ratio: number
}

const props = defineProps<{
  points: CommunityTrendPoint[]
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
        name: '扩散分',
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
        name: '比率(%)',
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
        name: '社区扩散',
        type: 'line',
        smooth: true,
        data: props.points.map((point) => point.average_community_score),
        itemStyle: {
          color: '#2e7467',
        },
        lineStyle: {
          width: 3,
        },
        areaStyle: {
          color: 'rgba(46, 116, 103, 0.12)',
        },
      },
      {
        name: '分享率',
        type: 'bar',
        yAxisIndex: 1,
        data: props.points.map((point) => toPercent(point.average_share_view_ratio)),
        itemStyle: {
          color: 'rgba(75, 111, 173, 0.68)',
          borderRadius: [8, 8, 0, 0],
        },
        barMaxWidth: 24,
      },
      {
        name: '评论率',
        type: 'line',
        yAxisIndex: 1,
        smooth: true,
        data: props.points.map((point) => toPercent(point.average_reply_view_ratio)),
        itemStyle: {
          color: '#9a4d1c',
        },
        lineStyle: {
          width: 2,
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
