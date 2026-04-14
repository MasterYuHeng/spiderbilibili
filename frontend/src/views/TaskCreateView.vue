<template>
  <div class="page-stack">
    <section class="panel-section">
      <div class="panel-section__head">
        <div>
          <h4>任务配置</h4>
        </div>
      </div>
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        class="task-form"
        label-position="top"
        @submit.prevent="handleSubmit"
      >
        <div class="task-form__grid">
          <el-form-item label="抓取方式" prop="crawl_mode">
            <el-select
              v-model="form.crawl_mode"
              data-testid="crawl-mode-select"
              placeholder="选择抓取方式"
              :clearable="false"
            >
              <el-option label="关键词抓取" value="keyword" />
              <el-option label="当前热榜抓取" value="hot" />
            </el-select>
            <small class="task-form__field-hint">
              关键词模式适合跟踪某个领域，热榜模式适合直接观察当下热门内容。
            </small>
          </el-form-item>

          <el-form-item label="抓取范围" prop="search_scope">
            <el-select
              v-model="form.search_scope"
              data-testid="search-scope-select"
              placeholder="选择范围"
              :clearable="false"
            >
              <el-option label="B 站全站" value="site" />
              <el-option label="固定分区" value="partition" />
            </el-select>
            <small class="task-form__field-hint">
              全站更适合看大盘热点，固定分区更适合研究垂类内容。
            </small>
          </el-form-item>

          <el-form-item
            v-if="isKeywordMode"
            label="搜索关键词"
            prop="keyword"
          >
            <el-input
              v-model="form.keyword"
              data-testid="keyword-input"
              placeholder="例如：AI 编程、AIGC 工作流、OpenAI"
              clearable
            />
            <small class="task-form__field-hint">
              建议输入一个聚焦主题，这样后续主题与 UP 主分析会更稳定。
            </small>
          </el-form-item>

          <template v-if="isKeywordMode">
            <el-form-item label="关键词同义补充">
              <el-switch
                v-model="keywordExpansionEnabled"
                data-testid="keyword-expansion-switch"
              />
              <small class="task-form__field-hint">
                只增强搜索召回范围，不会把后续分析拆成多条任务链路。
              </small>
            </el-form-item>

            <el-form-item
              v-if="keywordExpansionEnabled"
              label="补充个数"
              prop="keyword_synonym_count"
            >
              <el-select
                v-model="form.keyword_synonym_count"
                data-testid="keyword-expansion-count"
                placeholder="选择补充个数"
                :clearable="false"
              >
                <el-option
                  v-for="count in keywordSynonymCountOptions"
                  :key="count"
                  :label="`补充 ${count} 个同义词`"
                  :value="count"
                />
              </el-select>
              <small class="task-form__field-hint">
                例如搜索“和平精英”并补充 1 个同义词，后续会按“和平精英 + 吃鸡”共同搜索，再统一去重进入原链路。
              </small>
            </el-form-item>
          </template>

          <div v-else class="task-form__info-card">
            <strong>当前模式无需输入关键词</strong>
            <p>
              系统会直接抓取 {{ scopeLabel }} 下的热门视频，并继续做主题、热门 UP 主和内容特点分析。
            </p>
          </div>

          <el-form-item
            v-if="isPartitionScope"
            label="固定分区"
            prop="partition_tid"
          >
            <el-select
              v-model="form.partition_tid"
              data-testid="partition-select"
              placeholder="选择分区"
              filterable
            >
              <el-option
                v-for="item in partitionOptions"
                :key="item.tid"
                :label="item.label"
                :value="item.tid"
              />
            </el-select>
          </el-form-item>

          <el-form-item label="目标视频数">
            <el-input-number v-model="form.requested_video_limit" :min="1" :step="10" />
            <small class="task-form__field-hint">
              控制当前任务最终保留多少条热点视频作为样本。
            </small>
          </el-form-item>

          <el-form-item label="最大页数">
            <el-input-number
              v-model="form.max_pages"
              :min="1"
              :step="1"
              :disabled="isHotPartitionMode"
            />
            <small class="task-form__field-hint">
              控制向前翻多少页找候选视频；分区热榜模式下会自动固定为 1。
            </small>
          </el-form-item>

          <el-form-item label="发布时间限制">
            <el-select
              v-model="publishedWithinMode"
              data-testid="published-within-select"
              clearable
              placeholder="不限发布时间"
            >
              <el-option
                v-for="option in publishedWithinOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
              <el-option
                :label="publishedWithinCustomOption.label"
                :value="publishedWithinCustomOption.value"
              />
            </el-select>
            <el-input-number
              v-if="isCustomPublishedWithinMode"
              v-model="publishedWithinCustomDays"
              data-testid="published-within-custom-input"
              :min="1"
              :max="3650"
              :step="1"
              class="task-form__inline-number"
            />
            <small class="task-form__field-hint">
              只保留最近一段时间发布的视频；除了常用预设，也可以自定义最近多少天。
            </small>
          </el-form-item>

          <el-form-item label="总热门 UP 主数">
            <el-input-number v-model="form.hot_author_total_count" :min="0" :step="1" />
            <small class="task-form__field-hint">
              先从热点视频中汇总全局最值得关注的热门 UP 主。
            </small>
          </el-form-item>

          <el-form-item label="各主题热门 UP 主数">
            <el-input-number v-model="form.topic_hot_author_count" :min="0" :step="1" />
            <small class="task-form__field-hint">
              每个主题再补充若干位代表性 UP 主，用来做主题视角对比。
            </small>
          </el-form-item>

          <el-form-item label="UP 主总结视频数">
            <el-input-number v-model="form.hot_author_video_limit" :min="1" :step="1" />
            <small class="task-form__field-hint">
              对每位入选的热门 UP 主，再补抓多少条视频做二次总结。
            </small>
          </el-form-item>

          <el-form-item label="UP 主总结依据">
            <el-select
              v-model="form.hot_author_summary_basis"
              placeholder="选择总结依据"
              :clearable="false"
            >
              <el-option label="按时间" value="time" />
              <el-option label="按热度" value="heat" />
            </el-select>
            <small class="task-form__field-hint">
              按时间会抓最近发布的视频；按热度会优先抓代表性更强的热门视频。
            </small>
          </el-form-item>
        </div>

        <section class="task-form__advanced">
          <button
            type="button"
            class="task-form__advanced-toggle"
            @click="advancedOpen = !advancedOpen"
          >
            <div>
              <strong>{{ advancedOpen ? '收起进阶设置' : '展开进阶设置' }}</strong>
            </div>
            <span>{{ advancedOpen ? '收起' : '展开' }}</span>
          </button>

          <div v-if="advancedOpen" class="task-form__advanced-grid">
            <el-form-item label="启用代理">
              <el-switch v-model="proxyEnabled" />
              <small class="task-form__field-hint">
                网络不稳定或触发限流时再开启。
              </small>
            </el-form-item>

            <el-form-item label="最小休眠秒数">
              <el-input-number v-model="form.min_sleep_seconds" :min="0.1" :step="0.1" />
              <small class="task-form__field-hint">
                每次请求之间的最短等待时间。
              </small>
            </el-form-item>

            <el-form-item label="最大休眠秒数">
              <el-input-number v-model="form.max_sleep_seconds" :min="0.1" :step="0.1" />
              <small class="task-form__field-hint">
                系统会在该区间内随机等待。
              </small>
            </el-form-item>

            <el-form-item v-if="form.enable_proxy" label="代理策略">
              <el-select
                v-model="form.source_ip_strategy"
                placeholder="选择策略"
                :clearable="false"
              >
                <el-option
                  v-for="item in availableIpStrategies"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
              <small class="task-form__field-hint">
                一般保持默认即可。
              </small>
            </el-form-item>
          </div>
        </section>

        <div class="task-form__actions">
          <el-button @click="resetForm">重置</el-button>
          <el-button
            type="primary"
            data-testid="submit-button"
            :loading="submitting"
            @click="handleSubmit"
          >
            创建任务
          </el-button>
        </div>
      </el-form>
    </section>
  </div>
</template>

<script setup lang="ts">
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { getErrorMessage } from '@/api/client'
import { createTask } from '@/api/tasks'
import type { TaskCreateRequest } from '@/api/types'
import { useTaskWorkspaceStore } from '@/stores/taskWorkspace'

const partitionOptions = [
  { tid: 1, label: '动画区' },
  { tid: 3, label: '音乐区' },
  { tid: 129, label: '舞蹈区' },
  { tid: 4, label: '游戏区' },
  { tid: 36, label: '知识区' },
  { tid: 188, label: '科技区' },
  { tid: 234, label: '运动区' },
  { tid: 223, label: '汽车区' },
  { tid: 160, label: '生活区' },
  { tid: 211, label: '美食区' },
  { tid: 217, label: '动物圈' },
  { tid: 119, label: '鬼畜区' },
  { tid: 155, label: '时尚区' },
  { tid: 5, label: '娱乐区' },
  { tid: 181, label: '影视区' },
] as const

const publishedWithinOptions = [
  { label: '最近 1 天', value: 1 },
  { label: '最近 3 天', value: 3 },
  { label: '最近 7 天', value: 7 },
  { label: '最近 30 天', value: 30 },
  { label: '最近 90 天', value: 90 },
] as const
const publishedWithinCustomOption = {
  label: '自定义最近天数',
  value: 'custom',
} as const

const keywordSynonymCountOptions = [1, 2, 3, 5] as const
type KeywordSynonymCount = (typeof keywordSynonymCountOptions)[number]
const allowedKeywordSynonymCounts = new Set<KeywordSynonymCount>(keywordSynonymCountOptions)
type PublishedWithinPresetValue = (typeof publishedWithinOptions)[number]['value']
type PublishedWithinMode =
  | PublishedWithinPresetValue
  | typeof publishedWithinCustomOption.value
  | null
const allowedPublishedWithinPresetValues = new Set<PublishedWithinPresetValue>(
  publishedWithinOptions.map((item) => item.value),
)
const partitionLabelByTid = new Map<number, string>(
  partitionOptions.map((item) => [item.tid, item.label]),
)

function createDefaultForm(): TaskCreateRequest {
  return {
    keyword: '',
    crawl_mode: 'keyword',
    search_scope: 'site',
    partition_tid: null,
    partition_name: null,
    published_within_days: null,
    requested_video_limit: 50,
    max_pages: 5,
    hot_author_total_count: 5,
    topic_hot_author_count: 1,
    hot_author_video_limit: 10,
    hot_author_summary_basis: 'time',
    enable_proxy: false,
    min_sleep_seconds: 1,
    max_sleep_seconds: 3,
    source_ip_strategy: 'local_sleep',
    enable_keyword_synonym_expansion: false,
    keyword_synonym_count: null,
  }
}

function resolvePartitionName(tid: number | null | undefined): string | null {
  if (!tid) {
    return null
  }
  return partitionLabelByTid.get(tid) ?? null
}

function normalizeKeywordSynonymCount(value: unknown): KeywordSynonymCount | null {
  const numericValue = Number(value)
  if (!Number.isInteger(numericValue)) {
    return null
  }
  return allowedKeywordSynonymCounts.has(numericValue as KeywordSynonymCount)
    ? (numericValue as KeywordSynonymCount)
    : null
}

function normalizePublishedWithinDays(value: unknown): number | null {
  const numericValue = Number(value)
  if (!Number.isInteger(numericValue)) {
    return null
  }
  if (numericValue < 1 || numericValue > 3650) {
    return null
  }
  return numericValue
}

const router = useRouter()
const workspaceStore = useTaskWorkspaceStore()
const formRef = ref<FormInstance>()
const submitting = ref(false)
const advancedOpen = ref(false)

const form = reactive<TaskCreateRequest>(createDefaultForm())

const isKeywordMode = computed(() => form.crawl_mode === 'keyword')
const isPartitionScope = computed(() => form.search_scope === 'partition')
const isHotPartitionMode = computed(() => form.crawl_mode === 'hot' && form.search_scope === 'partition')
const publishedWithinMode = computed<PublishedWithinMode>({
  get: () => {
    const normalizedDays = normalizePublishedWithinDays(form.published_within_days)
    if (normalizedDays === null) {
      return null
    }
    return allowedPublishedWithinPresetValues.has(normalizedDays as PublishedWithinPresetValue)
      ? (normalizedDays as PublishedWithinPresetValue)
      : publishedWithinCustomOption.value
  },
  set: (value) => {
    if (value === null) {
      form.published_within_days = null
      return
    }
    if (value === publishedWithinCustomOption.value) {
      form.published_within_days = normalizePublishedWithinDays(form.published_within_days) ?? 14
      return
    }
    form.published_within_days = value
  },
})
const isCustomPublishedWithinMode = computed(
  () => publishedWithinMode.value === publishedWithinCustomOption.value,
)
const publishedWithinCustomDays = computed<number | null>({
  get: () => normalizePublishedWithinDays(form.published_within_days) ?? 14,
  set: (value) => {
    form.published_within_days = normalizePublishedWithinDays(value)
  },
})

const keywordExpansionEnabled = computed({
  get: () => Boolean(form.enable_keyword_synonym_expansion),
  set: (value: boolean) => {
    form.enable_keyword_synonym_expansion = value
  },
})

const proxyEnabled = computed({
  get: () => Boolean(form.enable_proxy),
  set: (value: boolean) => {
    form.enable_proxy = value
  },
})

const availableIpStrategies = computed(() =>
  form.enable_proxy
    ? [
        { label: '本机节流', value: 'local_sleep' },
        { label: '代理池轮换', value: 'proxy_pool' },
        { label: '自定义代理', value: 'custom_proxy' },
      ]
    : [{ label: '本机节流', value: 'local_sleep' }],
)

const scopeLabel = computed(() => {
  if (isPartitionScope.value) {
    return resolvePartitionName(form.partition_tid) ?? '指定分区'
  }
  return 'B 站全站'
})

const rules: FormRules<TaskCreateRequest> = {
  keyword: [
    {
      validator: (_rule, value, callback) => {
        if (isKeywordMode.value && !String(value ?? '').trim()) {
          callback(new Error('关键词抓取模式下请输入搜索关键词'))
          return
        }
        callback()
      },
      trigger: 'blur',
    },
  ],
  partition_tid: [
    {
      validator: (_rule, value, callback) => {
        if (isPartitionScope.value && !value) {
          callback(new Error('固定分区模式下请选择一个分区'))
          return
        }
        callback()
      },
      trigger: 'change',
    },
  ],
  published_within_days: [
    {
      validator: (_rule, value, callback) => {
        if (!isCustomPublishedWithinMode.value) {
          callback()
          return
        }
        if (normalizePublishedWithinDays(value) === null) {
          callback(new Error('自定义发布时间限制需填写 1 到 3650 之间的整数天数'))
          return
        }
        callback()
      },
      trigger: 'change',
    },
  ],
  keyword_synonym_count: [
    {
      validator: (_rule, value, callback) => {
        if (!isKeywordMode.value || !keywordExpansionEnabled.value) {
          callback()
          return
        }
        if (!normalizeKeywordSynonymCount(value)) {
          callback(new Error('补充个数仅允许 1、2、3、5'))
          return
        }
        callback()
      },
      trigger: 'change',
    },
  ],
}

function resetForm() {
  Object.assign(form, createDefaultForm())
  advancedOpen.value = false
  formRef.value?.clearValidate()
}

function buildCreateTaskPayload(): TaskCreateRequest {
  const normalizedKeyword = isKeywordMode.value ? form.keyword.trim() : ''
  const normalizedPartitionName = isPartitionScope.value
    ? resolvePartitionName(form.partition_tid)
    : null
  const publishedWithinDays = normalizePublishedWithinDays(form.published_within_days)
  const enableKeywordSynonymExpansion = isKeywordMode.value
    ? Boolean(form.enable_keyword_synonym_expansion)
    : false
  const keywordSynonymCount = enableKeywordSynonymExpansion
    ? (normalizeKeywordSynonymCount(form.keyword_synonym_count) ?? 1)
    : null

  return {
    ...form,
    keyword: normalizedKeyword,
    partition_name: normalizedPartitionName,
    published_within_days: publishedWithinDays,
    max_pages: isHotPartitionMode.value ? 1 : form.max_pages,
    enable_keyword_synonym_expansion: enableKeywordSynonymExpansion,
    keyword_synonym_count: keywordSynonymCount,
  }
}

watch(
  () => form.enable_proxy,
  (enabled) => {
    if (!enabled) {
      form.source_ip_strategy = 'local_sleep'
    }
  },
)

watch(
  () => form.search_scope,
  (scope) => {
    if (scope !== 'partition') {
      form.partition_tid = null
      form.partition_name = null
    }
  },
)

watch(
  () => form.partition_tid,
  (tid) => {
    form.partition_name = resolvePartitionName(tid) ?? null
  },
)

watch(
  () => form.crawl_mode,
  (mode) => {
    if (mode === 'hot') {
      form.keyword = ''
      form.enable_keyword_synonym_expansion = false
      form.keyword_synonym_count = null
      return
    }

    if (form.enable_keyword_synonym_expansion) {
      form.keyword_synonym_count = normalizeKeywordSynonymCount(form.keyword_synonym_count) ?? 1
    }
  },
)

watch(
  () => form.enable_keyword_synonym_expansion,
  (enabled) => {
    if (!isKeywordMode.value) {
      form.enable_keyword_synonym_expansion = false
      form.keyword_synonym_count = null
      return
    }

    form.keyword_synonym_count = enabled
      ? (normalizeKeywordSynonymCount(form.keyword_synonym_count) ?? 1)
      : null
  },
)

watch(
  [() => form.crawl_mode, () => form.search_scope],
  ([mode, scope]) => {
    if (mode === 'hot' && scope === 'partition') {
      form.max_pages = 1
    } else if ((form.max_pages ?? 0) < 1) {
      form.max_pages = 1
    }
  },
)

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) {
    return
  }

  if ((form.min_sleep_seconds ?? 0) > (form.max_sleep_seconds ?? 0)) {
    ElMessage.error('最小休眠时间不能大于最大休眠时间。')
    return
  }

  submitting.value = true
  try {
    const payload = await createTask(buildCreateTaskPayload())
    workspaceStore.setCurrentTaskContext(payload.task.id, payload.task.keyword)
    ElMessage.success('任务已创建，正在跳转详情页。')
    await router.push(`/tasks/${payload.task.id}`)
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '创建任务失败，请稍后重试。'))
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.task-form__info-card p {
  color: var(--muted);
}

.task-form__info-card strong {
  display: block;
  color: var(--text);
}

.task-form__info-card {
  padding: 16px 18px;
  border-radius: 18px;
  background: rgba(255, 248, 241, 0.75);
  border: 1px solid rgba(189, 91, 32, 0.12);
}

.task-form__info-card p {
  margin: 8px 0 0;
  line-height: 1.7;
}

.task-form__advanced {
  margin-top: 8px;
}

.task-form__advanced-toggle {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 18px;
  border: 1px solid rgba(100, 72, 46, 0.12);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.6);
  text-align: left;
  cursor: pointer;
}

.task-form__advanced-toggle strong {
  display: block;
}

.task-form__advanced-toggle span {
  color: var(--accent);
  font-weight: 700;
  white-space: nowrap;
}

.task-form__advanced-grid {
  margin-top: 16px;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.task-form__field-hint {
  display: block;
  margin-top: 6px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.5;
}

.task-form__inline-number {
  margin-top: 12px;
}

@media (max-width: 900px) {
  .task-form__advanced-grid {
    grid-template-columns: 1fr;
  }
}
</style>
