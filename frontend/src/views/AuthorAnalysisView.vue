<template>
  <div class="page-stack">
    <section class="page-hero">
      <div>
        <h3>热门创作者画像与二次抓取拆解</h3>
      </div>
      <div class="page-hero__aside">
        <span>当前任务范围</span>
        <strong>{{ taskScopeLabel }}</strong>
      </div>
    </section>

    <TaskLifecycleNotice
      v-if="taskProgress"
      :status="taskProgress.status"
      :error-message="taskProgress.error_message"
      :extra-params="taskProgress.extra_params"
      :latest-log-message="taskProgress.latest_log?.message ?? null"
      :current-stage="taskProgress.current_stage"
    />

    <section class="stats-grid">
      <StatCard label="热门 UP 主" :value="formatNumber(popularAuthors.length)" />
      <StatCard label="近期活跃" :value="formatNumber(recentlyActiveCount)" />
      <StatCard label="二次抓取视频" :value="formatNumber(totalFetchedVideos)" />
      <StatCard label="覆盖主题" :value="formatNumber(topicHotGroups.length)" />
    </section>

    <section class="panel-section">
      <div class="panel-section__head">
        <div>
          <h4>创作者总览</h4>
        </div>
        <div class="toolbar__actions">
          <el-button @click="refreshAll">刷新分析</el-button>
          <RouterLink class="toolbar__link" :to="`/tasks/${taskId}/topics`">查看主题分析</RouterLink>
          <RouterLink class="toolbar__link" :to="`/tasks/${taskId}/report`">查看任务报告</RouterLink>
        </div>
      </div>

      <EmptyState
        v-if="!loading && !popularAuthors.length"
        title="UP 主分析尚未生成"
        description="任务完成热门 UP 主提取和二次抓取后，这里会展示创作者画像、视频表现和内容聚焦。"
      />

      <template v-else>
        <AuthorComparisonChart :authors="popularAuthors" />

        <div class="overview-grid">
          <article v-if="authorAnalysisNotes.length" class="overview-card">
            <h5>分析说明</h5>
            <div class="compact-list">
              <InsightText
                v-for="note in authorAnalysisNotes.slice(0, 3)"
                :key="note"
                tag="p"
                :text="note"
              />
            </div>
          </article>

          <article v-if="keywordEntries.length" class="overview-card">
            <h5>高频关键词</h5>
            <div class="keyword-grid keyword-grid--compact">
              <article v-for="entry in keywordEntries" :key="entry.label" class="keyword-card">
                <strong>{{ entry.label }}</strong>
                <small>{{ entry.count }} 位 UP 主反复提及</small>
              </article>
            </div>
          </article>
        </div>
      </template>
    </section>

    <section v-if="popularAuthors.length" class="panel-section">
      <div class="panel-section__head">
        <div>
          <h4>UP 主工作台</h4>
        </div>
      </div>

      <div class="author-workspace">
        <div class="workspace-column workspace-column--list custom-scrollbar">
          <button
            v-for="author in popularAuthors"
            :key="authorKey(author)"
            type="button"
            class="author-list-card"
            :class="{ 'is-active': selectedAuthorKey === authorKey(author) }"
            @click="openAuthorWorkspaceCard(author)"
          >
            <div class="author-list-card__head">
              <div>
                <strong>{{ author.author_name }}</strong>
                <small>{{ author.dominant_topics.slice(0, 2).join(' / ') || '多主题覆盖' }}</small>
              </div>
              <span class="author-list-card__score">{{ formatScore(author.popularity_score, 2) }}</span>
            </div>

            <div class="author-list-card__metrics">
              <span>热点 {{ formatNumber(author.source_video_count) }}</span>
              <span>补抓 {{ formatNumber(author.fetched_video_count) }}</span>
              <span>活跃 {{ formatNumber(author.recent_publish_count) }}</span>
            </div>

            <InsightText
              tag="p"
              :text="author.ai_creator_profile || author.summary_text || '暂无创作者简介。'"
            />

            <div class="tag-cluster">
              <el-tag
                v-for="keyword in author.content_keywords.slice(0, 4)"
                :key="`${authorKey(author)}-${keyword}`"
                effect="plain"
                size="small"
              >
                {{ keyword }}
              </el-tag>
            </div>
          </button>
        </div>

        <div class="workspace-column workspace-column--detail custom-scrollbar">
          <EmptyState
            v-if="!selectedAuthor"
            title="请选择一位 UP 主"
            description="左侧卡片用于快速切换不同创作者，右侧会同步更新该创作者的详细分析和二次抓取视频可视化。"
          />

          <template v-else>
            <section class="detail-hero">
              <div>
                <p class="detail-hero__eyebrow">当前查看</p>
                <h4>{{ selectedAuthor.author_name }}</h4>
                <InsightText
                  tag="p"
                  :text="selectedAuthor.ai_creator_profile || selectedAuthor.summary_text || '暂无创作者画像摘要。'"
                />
              </div>
              <div class="detail-hero__score">
                <span>综合热度</span>
                <strong>{{ formatScore(selectedAuthor.popularity_score, 2) }}</strong>
              </div>
            </section>

            <section class="signal-grid">
              <article class="signal-item">
                <span>热点样本</span>
                <strong>{{ formatNumber(selectedAuthor.source_video_count) }}</strong>
              </article>
              <article class="signal-item">
                <span>二次抓取</span>
                <strong>{{ formatNumber(selectedAuthor.fetched_video_count) }}</strong>
              </article>
              <article class="signal-item">
                <span>近 30 天活跃</span>
                <strong>{{ formatNumber(selectedAuthor.recent_publish_count) }}</strong>
              </article>
              <article class="signal-item">
                <span>平均互动率</span>
                <strong>{{ formatPercent(selectedAuthor.fetched_average_engagement_rate, 2) }}</strong>
              </article>
            </section>

            <section class="detail-grid">
              <article class="detail-card">
                <div class="detail-card__head">
                  <h5>近期内容总结</h5>
                  <small>{{ summaryBasisLabel(selectedAuthor.summary_basis) }}</small>
                </div>
                <InsightText
                  class="detail-card__body"
                  tag="p"
                  :text="selectedAuthor.ai_recent_content_summary || selectedAuthor.summary_text || '暂无近期内容总结。'"
                />
                <div class="tag-cluster">
                  <el-tag
                    v-for="topic in selectedAuthor.dominant_topics"
                    :key="`${authorKey(selectedAuthor)}-topic-${topic}`"
                    type="success"
                    effect="plain"
                  >
                    {{ topic }}
                  </el-tag>
                  <el-tag
                    v-for="tag in selectedAuthor.style_tags"
                    :key="`${authorKey(selectedAuthor)}-style-${tag}`"
                    type="warning"
                    effect="plain"
                  >
                    {{ tag }}
                  </el-tag>
                </div>
              </article>

              <article class="detail-card">
                <div class="detail-card__head">
                  <h5>相关主题与入选原因</h5>
                  <small>{{ relatedTopicNames.length }} 个主题关联</small>
                </div>
                <div class="tag-cluster">
                  <el-tag
                    v-for="topic in relatedTopicNames"
                    :key="`${authorKey(selectedAuthor)}-related-${topic}`"
                    effect="plain"
                  >
                    {{ topic }}
                  </el-tag>
                </div>
                <div class="compact-list compact-list--dense">
                  <InsightText
                    v-for="point in compactStrategyPoints"
                    :key="point"
                    tag="p"
                    :text="point"
                  />
                </div>
              </article>
            </section>

            <section class="detail-grid">
              <article class="chart-card">
                <div class="detail-card__head">
                  <h5>二次抓取视频表现</h5>
                  <small>播放量与互动率</small>
                </div>
                <AuthorVideoMetricsChart :videos="selectedAuthor.videos" />
              </article>

              <article class="chart-card">
                <div class="detail-card__head">
                  <h5>内容重心分布</h5>
                  <small>AI 聚焦词与标签频次</small>
                </div>
                <div v-if="focusEntries.length" class="focus-bars">
                  <div
                    v-for="entry in focusEntries"
                    :key="`${authorKey(selectedAuthor)}-focus-${entry.label}`"
                    class="focus-bar"
                  >
                    <div class="focus-bar__label">
                      <strong>{{ entry.label }}</strong>
                      <small>{{ entry.count }}</small>
                    </div>
                    <div class="focus-bar__track">
                      <span :style="{ width: `${entry.ratio}%` }"></span>
                    </div>
                  </div>
                  <small>{{ selectedAuthor.videos.length }} 条样本</small>
                </div>
                <EmptyState
                  v-else
                  title="暂无内容重心数据"
                  description="当前 UP 主的二次抓取视频还没有足够的 AI 聚焦词或标签。"
                />
              </article>
            </section>

            <section class="detail-card">
              <div class="detail-card__head">
                <h5>近期视频列表</h5>
                <small>{{ selectedAuthor.videos.length }} 条样本</small>
              </div>
              <div class="video-grid">
                <article
                  v-for="video in selectedAuthor.videos"
                  :key="`${authorKey(selectedAuthor)}-${video.bvid}`"
                  class="video-card"
                >
                  <div class="video-card__head">
                    <a :href="video.url" target="_blank" rel="noreferrer">{{ video.title }}</a>
                    <small>{{ formatDateTime(video.published_at) }}</small>
                  </div>
                  <div class="video-card__meta">
                    <span>播放 {{ formatCompactNumber(video.view_count) }}</span>
                    <span>互动率 {{ formatPercent(video.engagement_rate, 2) }}</span>
                    <span>点赞率 {{ formatPercent(video.like_view_ratio, 2) }}</span>
                  </div>
                  <InsightText
                    class="video-card__summary"
                    tag="p"
                    :text="video.ai_summary || video.summary || '暂无视频摘要。'"
                  />
                  <div class="tag-cluster">
                    <el-tag
                      v-for="focus in video.content_focus.slice(0, 3)"
                      :key="`${video.bvid}-${focus}`"
                      size="small"
                      effect="plain"
                    >
                      {{ focus }}
                    </el-tag>
                  </div>
                </article>
              </div>
            </section>
          </template>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { getErrorMessage, isRequestCanceled } from '@/api/client'
import { getTaskAnalysis, getTaskProgress } from '@/api/tasks'
import type {
  TaskAnalysisPayload,
  TaskAnalysisPopularAuthor,
  TaskAnalysisTopicHotAuthor,
  TaskProgressPayload,
  TaskStatus,
} from '@/api/types'
import AuthorComparisonChart from '@/components/charts/AuthorComparisonChart.vue'
import AuthorVideoMetricsChart from '@/components/charts/AuthorVideoMetricsChart.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import InsightText from '@/components/common/InsightText.vue'
import StatCard from '@/components/common/StatCard.vue'
import TaskLifecycleNotice from '@/components/tasks/TaskLifecycleNotice.vue'
import { useTaskWorkspaceStore } from '@/stores/taskWorkspace'
import {
  formatCompactNumber,
  formatDateTime,
  formatNumber,
  formatPercent,
  formatScore,
} from '@/utils/format'
import { isActiveTaskStatus } from '@/utils/taskStatus'

const route = useRoute()
const workspaceStore = useTaskWorkspaceStore()

const taskId = computed(() => String(route.params.taskId))
const analysis = ref<TaskAnalysisPayload | null>(null)
const taskProgress = ref<TaskProgressPayload | null>(null)
const loading = ref(false)
const latestProgressLogId = ref('')
const selectedAuthorKey = ref('')

let timer: number | null = null
let pollInFlight = false
let progressController: AbortController | null = null
let analysisController: AbortController | null = null

const popularAuthors = computed<TaskAnalysisPopularAuthor[]>(
  () => analysis.value?.advanced.popular_authors ?? [],
)
const topicHotGroups = computed<TaskAnalysisTopicHotAuthor[]>(
  () => analysis.value?.advanced.topic_hot_authors ?? [],
)
const authorAnalysisNotes = computed(() => analysis.value?.advanced.author_analysis_notes ?? [])
const totalFetchedVideos = computed(() =>
  popularAuthors.value.reduce((total, author) => total + author.fetched_video_count, 0),
)
const recentlyActiveCount = computed(
  () => popularAuthors.value.filter((author) => author.recent_publish_count > 0).length,
)
const taskOptions = computed<Record<string, unknown>>(() => {
  const extraParams = taskProgress.value?.extra_params
  if (!extraParams || typeof extraParams !== 'object') {
    return {}
  }
  const raw = extraParams.task_options
  return raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {}
})
const taskScopeLabel = computed(() => {
  if (String(taskOptions.value.search_scope || 'site') === 'partition') {
    return String(taskOptions.value.partition_name || taskOptions.value.partition_tid || '指定分区')
  }
  return 'B 站全站'
})
const keywordEntries = computed(() => {
  const counts = new Map<string, number>()
  popularAuthors.value.forEach((author) => {
    author.content_keywords.forEach((keyword) => {
      counts.set(keyword, (counts.get(keyword) ?? 0) + 1)
    })
  })
  return Array.from(counts.entries())
    .map(([label, count]) => ({ label, count }))
    .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label, 'zh-CN'))
    .slice(0, 8)
})
const selectedAuthor = computed(() =>
  popularAuthors.value.find((author) => authorKey(author) === selectedAuthorKey.value) ?? null,
)
const relatedTopicNames = computed(() => {
  if (!selectedAuthor.value) {
    return []
  }
  return topicHotGroups.value
    .filter((group) =>
      group.authors.some((author) => authorKey(author) === authorKey(selectedAuthor.value!)),
    )
    .map((group) => group.topic_name)
})
const compactStrategyPoints = computed(() => {
  if (!selectedAuthor.value) {
    return []
  }
  const source =
    selectedAuthor.value.ai_content_strategy.length > 0
      ? selectedAuthor.value.ai_content_strategy
      : selectedAuthor.value.analysis_points
  return source.slice(0, 4)
})
const focusEntries = computed(() => {
  if (!selectedAuthor.value) {
    return []
  }
  const counts = new Map<string, number>()
  selectedAuthor.value.videos.forEach((video) => {
    const values =
      video.content_focus.length > 0 ? video.content_focus : video.tags.slice(0, 3)
    values.forEach((value) => {
      const label = value.trim()
      if (!label) {
        return
      }
      counts.set(label, (counts.get(label) ?? 0) + 1)
    })
  })
  const max = Math.max(...counts.values(), 1)
  return Array.from(counts.entries())
    .map(([label, count]) => ({
      label,
      count,
      ratio: Math.max(18, Math.round((count / max) * 100)),
    }))
    .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label, 'zh-CN'))
    .slice(0, 8)
})

function authorKey(author: Pick<TaskAnalysisPopularAuthor, 'author_mid' | 'author_name'>) {
  return author.author_mid || author.author_name
}

function authorHomepageUrl(author: Pick<TaskAnalysisPopularAuthor, 'author_mid'>) {
  return author.author_mid ? `https://space.bilibili.com/${author.author_mid}` : ''
}

function openAuthorWorkspaceCard(author: TaskAnalysisPopularAuthor) {
  selectedAuthorKey.value = authorKey(author)
  const homepageUrl = authorHomepageUrl(author)
  if (!homepageUrl) {
    return
  }
  window.open(homepageUrl, '_blank', 'noopener,noreferrer')
}

function shouldPoll(status: TaskStatus | undefined): boolean {
  return isActiveTaskStatus(status)
}

function summaryBasisLabel(value: string) {
  return value === 'heat' ? '按热度补抓' : '按时间补抓'
}

function syncSelectedAuthor() {
  if (!popularAuthors.value.length) {
    selectedAuthorKey.value = ''
    return
  }
  const exists = popularAuthors.value.some((author) => authorKey(author) === selectedAuthorKey.value)
  if (!exists) {
    selectedAuthorKey.value = authorKey(popularAuthors.value[0])
  }
}

function clearTimer() {
  if (timer !== null) {
    window.clearInterval(timer)
    timer = null
  }
}

function replaceController(current: AbortController | null): AbortController {
  current?.abort()
  return new AbortController()
}

function abortPendingRequests() {
  progressController?.abort()
  analysisController?.abort()
  progressController = null
  analysisController = null
}

function syncPolling() {
  clearTimer()
  if (!shouldPoll(taskProgress.value?.status)) {
    return
  }
  timer = window.setInterval(() => {
    void pollAuthorAnalysis()
  }, 8000)
}

async function fetchAnalysis() {
  const controller = replaceController(analysisController)
  analysisController = controller
  if (!analysis.value) {
    loading.value = true
  }
  try {
    workspaceStore.setCurrentTaskId(taskId.value)
    const response = await getTaskAnalysis(taskId.value, { signal: controller.signal })
    if (analysisController !== controller) {
      return
    }
    analysis.value = response
    syncSelectedAuthor()
  } catch (error) {
    if (!isRequestCanceled(error)) {
      ElMessage.error(getErrorMessage(error, '加载 UP 主分析失败。'))
    }
  } finally {
    if (analysisController === controller) {
      analysisController = null
      loading.value = false
    }
  }
}

async function fetchTaskProgress() {
  const controller = replaceController(progressController)
  progressController = controller
  try {
    const response = await getTaskProgress(taskId.value, { signal: controller.signal })
    if (progressController !== controller) {
      return
    }
    taskProgress.value = response
    latestProgressLogId.value = response.latest_log?.id ?? latestProgressLogId.value
    syncPolling()
  } catch (error) {
    if (isRequestCanceled(error)) {
      return
    }
    throw error
  } finally {
    if (progressController === controller) {
      progressController = null
    }
  }
}

async function pollAuthorAnalysis() {
  if (pollInFlight) {
    return
  }
  pollInFlight = true
  try {
    const previousStatus = taskProgress.value?.status
    const previousLogId = latestProgressLogId.value
    await fetchTaskProgress()
    const currentStatus = taskProgress.value?.status
    const currentLogId = taskProgress.value?.latest_log?.id ?? ''
    if (currentStatus !== previousStatus || currentLogId !== previousLogId) {
      await fetchAnalysis()
    }
  } catch (error) {
    if (!isRequestCanceled(error)) {
      ElMessage.error(getErrorMessage(error, '更新 UP 主分析失败。'))
    }
    clearTimer()
  } finally {
    pollInFlight = false
  }
}

async function refreshAll() {
  await Promise.all([fetchTaskProgress(), fetchAnalysis()])
}

watch(taskId, () => {
  abortPendingRequests()
  analysis.value = null
  taskProgress.value = null
  latestProgressLogId.value = ''
  selectedAuthorKey.value = ''
  void refreshAll()
})

watch(popularAuthors, () => {
  syncSelectedAuthor()
})

onMounted(() => {
  analysis.value = null
  taskProgress.value = null
  latestProgressLogId.value = ''
  selectedAuthorKey.value = ''
  void refreshAll()
})

onBeforeUnmount(() => {
  clearTimer()
  abortPendingRequests()
})
</script>

<style scoped>
.overview-grid,
.keyword-grid,
.author-workspace,
.signal-grid,
.detail-grid,
.video-grid {
  display: grid;
  gap: 16px;
}

.overview-grid {
  margin-top: 16px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.overview-card,
.detail-card,
.chart-card,
.author-list-card,
.keyword-card,
.signal-item,
.video-card {
  border: 1px solid rgba(100, 72, 46, 0.12);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.58);
}

.overview-card,
.detail-card,
.chart-card,
.keyword-card,
.video-card {
  padding: 16px 18px;
}

.overview-card h5,
.detail-card h5,
.detail-hero h4 {
  margin: 0;
}

.compact-list,
.focus-bars {
  display: grid;
  gap: 10px;
}

.compact-list p,
.detail-card__body,
.detail-hero p,
.author-list-card p,
.video-card__summary,
.video-card small,
.focus-bar small,
.overview-card small,
.keyword-card small {
  margin: 0;
  color: var(--muted);
}

.keyword-grid--compact {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.keyword-card strong,
.video-card__head a,
.author-list-card strong {
  font-weight: 700;
}

.author-workspace {
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  align-items: stretch;
}

.workspace-column {
  min-width: 0;
  min-height: 960px;
  max-height: 960px;
  padding-right: 6px;
  overflow-y: auto;
}

.workspace-column--list {
  display: grid;
  align-content: start;
  gap: 14px;
}

.workspace-column--detail {
  display: grid;
  align-content: start;
  gap: 16px;
}

.author-list-card {
  width: 100%;
  padding: 16px;
  text-align: left;
  cursor: pointer;
  transition:
    transform 160ms ease,
    border-color 160ms ease,
    box-shadow 160ms ease;
}

.author-list-card:hover,
.author-list-card.is-active {
  border-color: rgba(202, 92, 31, 0.36);
  box-shadow: 0 16px 30px rgba(81, 50, 28, 0.12);
  transform: translateY(-2px);
}

.author-list-card__head,
.detail-hero,
.detail-card__head,
.video-card__head,
.focus-bar__label {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.author-list-card__head small,
.author-list-card__metrics,
.detail-card__head small,
.detail-hero__eyebrow,
.detail-hero__score span {
  color: var(--muted);
}

.author-list-card__score {
  min-width: 52px;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(202, 92, 31, 0.12);
  color: var(--accent);
  text-align: center;
  font-weight: 700;
}

.author-list-card__metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  margin: 10px 0;
  font-size: 12px;
}

.author-list-card p {
  display: -webkit-box;
  overflow: hidden;
  line-height: 1.7;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
}

.detail-hero {
  padding: 18px 20px;
  border-radius: 24px;
  background:
    linear-gradient(135deg, rgba(255, 247, 238, 0.96), rgba(247, 236, 225, 0.88)),
    rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(100, 72, 46, 0.12);
}

.detail-hero__eyebrow {
  margin: 0 0 6px;
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.detail-hero p {
  margin-top: 8px;
  line-height: 1.8;
}

.detail-hero__score {
  min-width: 110px;
  padding: 12px 14px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.72);
  text-align: right;
}

.detail-hero__score strong,
.signal-item strong {
  display: block;
  margin-top: 6px;
}

.signal-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.signal-item {
  padding: 12px 14px;
}

.signal-item span {
  color: var(--muted);
  font-size: 12px;
}

.detail-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.detail-card__body {
  margin: 12px 0;
  line-height: 1.8;
}

.tag-cluster {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.compact-list--dense {
  margin-top: 12px;
}

.compact-list--dense p {
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(255, 248, 241, 0.72);
  line-height: 1.7;
}

.chart-card :deep(.chart-surface) {
  min-height: 320px;
}

.focus-bar {
  display: grid;
  gap: 8px;
}

.focus-bar__track {
  height: 10px;
  border-radius: 999px;
  background: rgba(202, 92, 31, 0.08);
  overflow: hidden;
}

.focus-bar__track span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #d6a06f, #ca5c1f);
}

.video-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin-top: 14px;
}

.video-card {
  display: grid;
  gap: 10px;
}

.video-card__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  color: var(--muted);
  font-size: 12px;
}

.video-card__summary {
  display: -webkit-box;
  overflow: hidden;
  line-height: 1.8;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
}

.custom-scrollbar {
  scrollbar-width: thin;
  scrollbar-color: rgba(202, 92, 31, 0.4) rgba(202, 92, 31, 0.08);
}

.custom-scrollbar::-webkit-scrollbar {
  width: 10px;
}

.custom-scrollbar::-webkit-scrollbar-track {
  border-radius: 999px;
  background: rgba(202, 92, 31, 0.08);
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: rgba(202, 92, 31, 0.4);
}

@media (max-width: 1280px) {
  .signal-grid,
  .detail-grid,
  .video-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .overview-grid,
  .author-workspace,
  .keyword-grid--compact {
    grid-template-columns: 1fr;
  }

  .workspace-column {
    min-height: auto;
    max-height: none;
    overflow: visible;
    padding-right: 0;
  }
}
</style>

