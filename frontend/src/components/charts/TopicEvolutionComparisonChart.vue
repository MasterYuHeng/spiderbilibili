<template>
  <div ref="chartRef" class="chart-surface"></div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { init, type EChartsType } from './chartCore'

interface TopicComparisonSeries {
  topic_name: string
  values: number[]
}

const props = defineProps<{
  buckets: string[]
  series: TopicComparisonSeries[]
}>()

const chartRef = ref<HTMLDivElement | null>(null)
let chart: EChartsType | null = null

const palette = ['#bd5b20', '#266245', '#4b6fad', '#b5731d', '#5b4b8a', '#b84f5d', '#2f7a78', '#7d5a3c']

function renderChart() {
  if (!chartRef.value) {
    return
  }

  if (!chart) {
    chart = init(chartRef.value)
  }

  chart.setOption({
    backgroundColor: 'transparent',
    color: palette,
    grid: {
      left: 28,
      right: 28,
      top: 46,
      bottom: 36,
      containLabel: true,
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'line',
      },
      valueFormatter: (value: number | string) => `${Number(value).toFixed(2)}`,
    },
    legend: {
      type: 'scroll',
      top: 0,
      textStyle: {
        color: '#6e5440',
      },
    },
    xAxis: {
      type: 'category',
      data: props.buckets,
      axisLabel: {
        color: '#6e5440',
      },
      boundaryGap: false,
    },
    yAxis: {
      type: 'value',
      name: '热度指数',
      axisLabel: {
        color: '#6e5440',
      },
      splitLine: {
        lineStyle: {
          color: 'rgba(110, 84, 64, 0.12)',
        },
      },
    },
    series: props.series.map((item, index) => ({
      name: item.topic_name,
      type: 'line',
      smooth: true,
      data: item.values,
      showSymbol: props.buckets.length <= 12,
      symbolSize: 7,
      lineStyle: {
        width: index < 3 ? 3 : 2,
      },
      emphasis: {
        focus: 'series',
      },
      areaStyle: index === 0
        ? {
            color: 'rgba(189, 91, 32, 0.12)',
          }
        : undefined,
    })),
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
  () => [props.buckets, props.series],
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
