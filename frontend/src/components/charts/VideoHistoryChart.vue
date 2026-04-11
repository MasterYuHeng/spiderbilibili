<template>
  <div ref="chartRef" class="chart-surface"></div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { init, type EChartsType } from './chartCore'

interface VideoHistoryPoint {
  label: string
  view_count: number
  like_count: number
  share_count: number
}

const props = defineProps<{
  points: VideoHistoryPoint[]
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
      data: props.points.map((point) => point.label),
      axisLabel: {
        color: '#6e5440',
      },
    },
    yAxis: [
      {
        type: 'value',
        name: '播放 / 点赞',
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
        name: '分享',
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
        name: '播放量',
        type: 'line',
        smooth: true,
        data: props.points.map((point) => point.view_count),
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
        name: '点赞量',
        type: 'line',
        smooth: true,
        data: props.points.map((point) => point.like_count),
        itemStyle: {
          color: '#7d5a44',
        },
        lineStyle: {
          width: 2,
        },
      },
      {
        name: '分享量',
        type: 'bar',
        yAxisIndex: 1,
        data: props.points.map((point) => point.share_count),
        itemStyle: {
          color: 'rgba(60, 122, 108, 0.7)',
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
