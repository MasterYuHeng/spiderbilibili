<template>
  <div class="page-stack">
    <section class="page-hero">
      <div>
        <h3>{{ report?.title ?? '任务热点分析报告' }}</h3>
      </div>
      <div class="page-hero__aside">
        <span>最新热点主题</span>
        <strong>{{ report?.latest_hot_topic_name || '--' }}</strong>
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

    <TaskSearchContextCard
      v-if="report && taskProgress"
      :task-keyword="report.task_keyword"
      :keyword-expansion="report.keyword_expansion"
      :search-keywords-used="report.search_keywords_used"
      :expanded-keyword-count="report.expanded_keyword_count"
      :crawl-mode="reportCrawlMode"
      title="报告搜索口径"
      description="报告不会按同义词拆成多份，但这里会明确说明这次分析样本是由哪些搜索词召回的。"
    />

    <section class="stats-grid">
      <StatCard label="报告章节" :value="String(report?.sections.length ?? 0)" />
      <StatCard label="AI 解读" :value="String(report?.ai_outputs.length ?? 0)" />
      <StatCard label="重点视频" :value="String(report?.featured_videos.length ?? 0)" />
      <StatCard label="热门 UP 主" :value="String(report?.popular_authors.length ?? 0)" />
    </section>

    <section class="panel-section">
      <div class="panel-section__head">
        <div>
          <h4>执行摘要</h4>
        </div>
        <div class="toolbar__actions">
          <el-button @click="refreshAll">刷新报告</el-button>
          <RouterLink class="toolbar__link" :to="`/tasks/${taskId}`">返回任务详情</RouterLink>
          <RouterLink class="toolbar__link" :to="`/tasks/${taskId}/topics`">查看主题分析</RouterLink>
          <RouterLink class="toolbar__link" :to="`/tasks/${taskId}/authors`">查看 UP 主分析</RouterLink>
        </div>
      </div>

      <EmptyState
        v-if="!loading && !report"
        title="报告尚未生成"
        description="任务分析完成后，这里会展示当前任务的热点内容分析报告。"
      />

      <div v-else-if="report" class="report-summary">
        <InsightText tag="p" :text="report.executive_summary" />
      </div>
    </section>

    <section v-if="report?.popular_authors.length" class="panel-section">
      <div class="panel-section__head">
        <div>
          <h4>热门 UP 主对比</h4>
        </div>
      </div>

      <AuthorComparisonChart :authors="report.popular_authors" />

      <div v-if="report.topic_hot_authors.length" class="topic-author-grid">
        <article
          v-for="group in report.topic_hot_authors"
          :key="group.topic_id"
          class="topic-author-card"
        >
          <h5>{{ group.topic_name }}</h5>
          <div class="tag-cluster">
            <el-tag
              v-for="author in group.authors"
              :key="`${group.topic_id}-${author.author_mid ?? author.author_name}`"
              effect="plain"
            >
              {{ author.author_name }}
            </el-tag>
          </div>
        </article>
      </div>

      <div class="author-grid">
        <article
          v-for="author in report.popular_authors"
          :key="author.author_mid ?? author.author_name"
          class="author-card"
        >
          <div class="author-card__head">
            <div>
              <h5>{{ author.author_name }}</h5>
              <InsightText
                tag="p"
                :text="author.ai_recent_content_summary || author.summary_text || '当前还没有生成该 up 主的补充总结。'"
              />
            </div>
            <div class="author-card__score">
              <span>综合热度</span>
              <strong>{{ formatScore(author.popularity_score, 2) }}</strong>
            </div>
          </div>

          <div class="signal-grid">
            <div class="signal-item">
              <span>热点样本数</span>
              <strong>{{ formatNumber(author.source_video_count) }}</strong>
            </div>
            <div class="signal-item">
              <span>热点贡献值</span>
              <strong>{{ formatScore(author.source_total_heat_score, 2) }}</strong>
            </div>
            <div class="signal-item">
              <span>补抓视频数</span>
              <strong>{{ formatNumber(author.fetched_video_count) }}</strong>
            </div>
            <div class="signal-item">
              <span>补抓平均互动率</span>
              <strong>{{ formatPercent(author.fetched_average_engagement_rate, 2) }}</strong>
            </div>
          </div>

          <div class="tag-cluster">
            <el-tag
              v-for="keyword in author.content_keywords"
              :key="`${author.author_name}-keyword-${keyword}`"
              effect="plain"
            >
              {{ keyword }}
            </el-tag>
            <el-tag
              v-for="topic in author.dominant_topics"
              :key="`${author.author_name}-${topic}`"
              effect="plain"
            >
              {{ topic }}
            </el-tag>
            <el-tag
              v-for="tag in author.style_tags"
              :key="`${author.author_name}-${tag}`"
              type="success"
              effect="plain"
            >
              {{ tag }}
            </el-tag>
          </div>

          <ul class="report-list">
            <InsightText
              v-for="point in author.ai_content_strategy.length ? author.ai_content_strategy : author.analysis_points"
              :key="point"
              tag="li"
              :text="point"
            />
          </ul>

          <div v-if="author.videos.length" class="mini-list">
            <div
              v-for="video in author.videos.slice(0, 3)"
              :key="`${author.author_name}-${video.bvid}`"
              class="mini-list__item"
            >
              <a :href="video.url" target="_blank" rel="noreferrer">{{ video.title }}</a>
              <small>
                播放 {{ formatCompactNumber(video.view_count) }} / 互动率 {{ formatPercent(video.engagement_rate, 2) }}
              </small>
              <InsightText
                tag="p"
                :text="video.ai_summary || video.summary || '暂无视频摘要。'"
              />
            </div>
          </div>

          <small class="author-card__foot">
            入选原因：{{ author.selection_reasons.map(formatSelectionReason).join('、') || '热点样本突出' }}
          </small>
        </article>
      </div>
    </section>

    <section v-if="report?.ai_outputs.length" class="panel-section">
      <div class="panel-section__head">
        <div>
          <h4>多视角解读</h4>
        </div>
      </div>
      <div class="report-grid">
        <article v-for="output in report.ai_outputs" :key="output.key" class="prompt-card">
          <h5>{{ output.title }}</h5>
          <div class="prompt-card__meta">
            <span>{{ output.audience }}</span>
            <small>{{ output.generation_mode }}</small>
          </div>
          <div class="prompt-card__content" v-html="formatAiOutputContent(output.title, output.content)"></div>
        </article>
      </div>
    </section>

    <section v-if="report?.featured_videos.length" class="panel-section">
      <div class="panel-section__head">
        <div>
          <h4>重点视频</h4>
        </div>
      </div>
      <div class="feature-grid">
        <article
          v-for="video in report.featured_videos"
          :key="video.video_id"
          class="feature-card"
        >
          <a :href="video.url" target="_blank" rel="noreferrer">{{ video.title }}</a>
          <small>{{ video.topic_name || '未归类主题' }}</small>
          <p>
            爆发 {{ formatScore(video.burst_score, 2) }} / 深度 {{ formatScore(video.depth_score, 2) }} /
            扩散 {{ formatScore(video.community_score, 2) }}
          </p>
        </article>
      </div>
    </section>

    <section v-if="report?.sections.length" class="panel-section">
      <div class="panel-section__head">
        <div>
          <h4>结构化报告</h4>
        </div>
      </div>
      <div class="report-grid">
        <article v-for="section in report.sections" :key="section.key" class="report-card">
          <h5>{{ section.title }}</h5>
          <InsightText tag="p" :text="section.summary" />
          <ul class="report-list">
            <InsightText
              v-for="bullet in section.bullets"
              :key="bullet"
              tag="li"
              :text="bullet"
            />
            <InsightText
              v-for="evidence in section.evidence"
              :key="evidence"
              tag="li"
              :text="`证据：${evidence}`"
            />
          </ul>
        </article>
      </div>
    </section>

    <section v-if="report" class="panel-section">
      <div class="panel-section__head">
        <div>
          <h4>Markdown 报告</h4>
        </div>
        <div class="toolbar__actions">
          <el-button @click="showMarkdown = !showMarkdown">
            {{ showMarkdown ? '收起 Markdown' : '展开 Markdown' }}
          </el-button>
        </div>
      </div>
      <pre v-if="showMarkdown" class="markdown-report">{{ report.report_markdown }}</pre>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { getErrorMessage, isRequestCanceled } from '@/api/client'
import { getTaskProgress, getTaskReport } from '@/api/tasks'
import type { TaskProgressPayload, TaskReportPayload, TaskStatus } from '@/api/types'
import EmptyState from '@/components/common/EmptyState.vue'
import InsightText from '@/components/common/InsightText.vue'
import StatCard from '@/components/common/StatCard.vue'
import TaskLifecycleNotice from '@/components/tasks/TaskLifecycleNotice.vue'
import TaskSearchContextCard from '@/components/tasks/TaskSearchContextCard.vue'
import { useTaskWorkspaceStore } from '@/stores/taskWorkspace'
import { formatInsightHtml } from '@/utils/aiText'
import { formatCompactNumber, formatNumber, formatPercent, formatScore } from '@/utils/format'
import { isActiveTaskStatus } from '@/utils/taskStatus'

const AuthorComparisonChart = defineAsyncComponent(
  () => import('@/components/charts/AuthorComparisonChart.vue'),
)

const route = useRoute()
const workspaceStore = useTaskWorkspaceStore()

const taskId = computed(() => String(route.params.taskId))
const report = ref<TaskReportPayload | null>(null)
const taskProgress = ref<TaskProgressPayload | null>(null)
const loading = ref(false)
const showMarkdown = ref(false)
const latestProgressLogId = ref('')
const reportCrawlMode = computed<'keyword' | 'hot'>(() => {
  const taskOptions = taskProgress.value?.extra_params?.task_options
  if (taskOptions && typeof taskOptions === 'object') {
    return String((taskOptions as Record<string, unknown>).crawl_mode || 'keyword') === 'hot'
      ? 'hot'
      : 'keyword'
  }
  return 'keyword'
})

let timer: number | null = null
let pollInFlight = false
let progressController: AbortController | null = null
let reportController: AbortController | null = null

function hydrateCachedReport() {
  report.value = workspaceStore.taskReportsByTask[taskId.value] ?? null
}

function shouldPoll(status: TaskStatus | undefined): boolean {
  return isActiveTaskStatus(status)
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
  reportController?.abort()
  progressController = null
  reportController = null
}

function syncPolling() {
  clearTimer()
  if (!shouldPoll(taskProgress.value?.status)) {
    return
  }
  timer = window.setInterval(() => {
    void pollTaskReport()
  }, 8000)
}

async function fetchReport() {
  const controller = replaceController(reportController)
  reportController = controller
  if (!report.value) {
    loading.value = true
  }
  try {
    workspaceStore.setCurrentTaskId(taskId.value)
    const response = await getTaskReport(taskId.value, { signal: controller.signal })
    if (reportController !== controller) {
      return
    }
    report.value = response
    workspaceStore.cacheTaskReport(response)
  } catch (error) {
    if (!isRequestCanceled(error)) {
      ElMessage.error(getErrorMessage(error, '加载任务报告失败。'))
    }
  } finally {
    if (reportController === controller) {
      reportController = null
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

async function pollTaskReport() {
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
      await fetchReport()
    }
  } catch (error) {
    if (!isRequestCanceled(error)) {
      ElMessage.error(getErrorMessage(error, '更新任务报告失败。'))
    }
    clearTimer()
  } finally {
    pollInFlight = false
  }
}

async function refreshAll() {
  await Promise.all([fetchTaskProgress(), fetchReport()])
}

function formatAiOutputContent(title: string, content: string) {
  return formatInsightHtml(content, { stripLeadingTitle: title })
}

function formatSelectionReason(reason: string) {
  if (reason === 'overall_hot') {
    return '全局热门'
  }
  if (reason.startsWith('topic:')) {
    return `${reason.slice(6)} 主题代表`
  }
  return reason
}

watch(taskId, () => {
  clearTimer()
  abortPendingRequests()
  hydrateCachedReport()
  taskProgress.value = null
  latestProgressLogId.value = ''
  showMarkdown.value = false
  void refreshAll()
})

onMounted(() => {
  hydrateCachedReport()
  taskProgress.value = null
  latestProgressLogId.value = ''
  showMarkdown.value = false
  void refreshAll()
})

onBeforeUnmount(() => {
  clearTimer()
  abortPendingRequests()
})
</script>

<style scoped>
.report-summary,
.report-card,
.feature-card,
.prompt-card,
.author-card,
.topic-author-card {
  border: 1px solid rgba(100, 72, 46, 0.12);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.58);
}

.report-summary,
.report-card,
.prompt-card,
.author-card,
.topic-author-card {
  padding: 16px;
}

.report-summary p,
.report-card p,
.feature-card p,
.feature-card small,
.prompt-card small,
.author-card p,
.author-card small,
.topic-author-card p {
  color: var(--muted);
}

.feature-grid,
.report-grid,
.author-grid,
.topic-author-grid {
  display: grid;
  gap: 16px;
}

.feature-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.report-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.author-grid {
  margin-top: 16px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.topic-author-grid {
  margin-top: 16px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.feature-card {
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.feature-card a,
.report-card h5,
.prompt-card h5,
.author-card h5,
.topic-author-card h5 {
  font-weight: 700;
}

.report-card h5,
.prompt-card h5,
.author-card h5,
.topic-author-card h5 {
  margin: 0 0 8px;
}

.report-list {
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 8px;
}

.prompt-card__meta,
.author-card__head {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: 12px;
}

.prompt-card__content,
.markdown-report {
  margin: 12px 0 0;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.8;
  color: var(--text);
  background: rgba(255, 248, 241, 0.72);
  border-radius: 16px;
  padding: 14px 16px;
}

.prompt-card__content :deep(strong) {
  font-weight: 800;
}

.markdown-report {
  border: 1px solid rgba(100, 72, 46, 0.12);
}

.author-card__score {
  min-width: 92px;
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(255, 248, 241, 0.75);
  text-align: right;
}

.author-card__score span,
.signal-item span {
  color: var(--muted);
  font-size: 12px;
}

.author-card__score strong,
.signal-item strong {
  display: block;
  margin-top: 6px;
}

.signal-grid {
  margin: 14px 0;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.signal-item {
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(255, 248, 241, 0.72);
}

.tag-cluster {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.mini-list {
  display: grid;
  gap: 10px;
}

.mini-list__item {
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(255, 248, 241, 0.72);
}

.mini-list__item a {
  color: var(--text);
  font-weight: 700;
}

.author-card__foot {
  display: block;
  margin-top: 12px;
}

@media (max-width: 1080px) {
  .feature-grid,
  .report-grid,
  .author-grid,
  .topic-author-grid,
  .signal-grid {
    grid-template-columns: 1fr;
  }
}
</style>


