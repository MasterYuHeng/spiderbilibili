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
            <el-select v-model="form.crawl_mode" placeholder="选择抓取方式" :clearable="false">
              <el-option label="关键词抓取" value="keyword" />
              <el-option label="当前热榜抓取" value="hot" />
            </el-select>
            <small class="task-form__field-hint">
              关键词模式适合跟踪某个领域，热榜模式适合直接观察当下热门内容。
            </small>
          </el-form-item>

          <el-form-item label="抓取范围" prop="search_scope">
            <el-select v-model="form.search_scope" placeholder="选择范围" :clearable="false">
              <el-option label="B 站全站" value="site" />
              <el-option label="固定分区" value="partition" />
            </el-select>
            <small class="task-form__field-hint">
              全站更适合看大盘热点，固定分区更适合研究垂类内容。
            </small>
          </el-form-item>

          <el-form-item
            v-if="form.crawl_mode === 'keyword'"
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

          <div v-else class="task-form__info-card">
            <strong>当前模式不需要输入关键词</strong>
            <p>
              系统会直接抓取 {{ scopeLabel }} 下的热门视频，并继续做主题、热门 UP 主和内容特点分析。
            </p>
          </div>

          <el-form-item
            v-if="form.search_scope === 'partition'"
            label="固定分区"
            prop="partition_tid"
          >
            <el-select v-model="form.partition_tid" placeholder="选择分区" filterable>
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
              :disabled="form.crawl_mode === 'hot' && form.search_scope === 'partition'"
            />
            <small class="task-form__field-hint">
              控制向前翻多少页找候选视频；分区热榜模式下会自动固定为 1。
            </small>
          </el-form-item>

          <el-form-item label="发布时间限制">
            <el-select v-model="form.published_within_days" clearable placeholder="不限发布时间">
              <el-option
                v-for="option in publishedWithinOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
            <small class="task-form__field-hint">
              只保留最近一段时间发布的视频，适合做阶段性热点追踪。
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
              <small class="task-form__field-hint">网络不稳定或触发限流时再开启。</small>
            </el-form-item>

            <el-form-item label="最小休眠秒数">
              <el-input-number v-model="form.min_sleep_seconds" :min="0.1" :step="0.1" />
              <small class="task-form__field-hint">每次请求之间的最短等待时间。</small>
            </el-form-item>

            <el-form-item label="最大休眠秒数">
              <el-input-number v-model="form.max_sleep_seconds" :min="0.1" :step="0.1" />
              <small class="task-form__field-hint">系统会在该区间内随机等待。</small>
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
              <small class="task-form__field-hint">一般保持默认即可。</small>
            </el-form-item>
          </div>
        </section>

        <div class="task-form__actions">
          <el-button @click="resetForm">重置</el-button>
          <el-button type="primary" :loading="submitting" @click="handleSubmit">
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
]

const publishedWithinOptions = [
  { label: '最近 1 天', value: 1 },
  { label: '最近 3 天', value: 3 },
  { label: '最近 7 天', value: 7 },
  { label: '最近 30 天', value: 30 },
  { label: '最近 90 天', value: 90 },
]

const router = useRouter()
const workspaceStore = useTaskWorkspaceStore()
const formRef = ref<FormInstance>()
const submitting = ref(false)
const advancedOpen = ref(false)

const form = reactive<TaskCreateRequest>({
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

const selectedPartition = computed(
  () => partitionOptions.find((item) => item.tid === form.partition_tid) ?? null,
)

const scopeLabel = computed(() => {
  if (form.search_scope === 'partition') {
    return selectedPartition.value?.label ?? '指定分区'
  }
  return 'B 站全站'
})

const rules: FormRules<TaskCreateRequest> = {
  keyword: [
    {
      validator: (_rule, value, callback) => {
        if (form.crawl_mode === 'keyword' && !String(value ?? '').trim()) {
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
        if (form.search_scope === 'partition' && !value) {
          callback(new Error('固定分区模式下请选择一个分区'))
          return
        }
        callback()
      },
      trigger: 'change',
    },
  ],
}

function resetForm() {
  form.keyword = ''
  form.crawl_mode = 'keyword'
  form.search_scope = 'site'
  form.partition_tid = null
  form.partition_name = null
  form.published_within_days = null
  form.requested_video_limit = 50
  form.max_pages = 5
  form.hot_author_total_count = 5
  form.topic_hot_author_count = 1
  form.hot_author_video_limit = 10
  form.hot_author_summary_basis = 'time'
  form.enable_proxy = false
  form.min_sleep_seconds = 1
  form.max_sleep_seconds = 3
  form.source_ip_strategy = 'local_sleep'
  advancedOpen.value = false
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
    form.partition_name = partitionOptions.find((item) => item.tid === tid)?.label ?? null
  },
)

watch(
  () => form.crawl_mode,
  (mode) => {
    if (mode === 'hot') {
      form.keyword = ''
    }
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
    const payload = await createTask({
      ...form,
      keyword: form.crawl_mode === 'keyword' ? form.keyword.trim() : '',
      partition_name:
        form.search_scope === 'partition'
          ? partitionOptions.find((item) => item.tid === form.partition_tid)?.label ?? null
          : null,
      max_pages:
        form.crawl_mode === 'hot' && form.search_scope === 'partition'
          ? 1
          : form.max_pages,
    })
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

@media (max-width: 900px) {
  .task-form__advanced-grid {
    grid-template-columns: 1fr;
  }
}
</style>
