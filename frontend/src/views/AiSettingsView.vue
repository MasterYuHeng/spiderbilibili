<template>
  <div class="page-stack">
    <section class="page-hero">
      <div>
        <h3>系统设置</h3>
      </div>
      <div class="page-hero__aside">
        <span>当前登录状态</span>
        <strong>{{ bilibiliStatusLabel }}</strong>
      </div>
    </section>

    <section class="stats-grid">
      <StatCard label="AI 提供方" :value="effectiveProviderLabel" />
      <StatCard label="AI 密钥来源" :value="deepSeekKeySourceLabel" />
      <StatCard label="B站登录态" :value="bilibiliStatusLabel" />
      <StatCard label="B站配置来源" :value="bilibiliKeySourceLabel" />
    </section>

    <section class="panel-section">
      <div class="panel-section__head">
        <div>
          <h4>DeepSeek API</h4>
        </div>
        <div class="toolbar__actions">
          <el-button :loading="loading" @click="loadSettings">刷新</el-button>
        </div>
      </div>

      <div class="settings-grid">
        <article class="detail-card">
          <div class="detail-card__head">
            <h5>运行时密钥</h5>
            <small>{{ deepSeekUpdatedAtLabel }}</small>
          </div>

          <el-form label-position="top" @submit.prevent="handleSaveDeepSeek">
            <el-form-item label="DeepSeek API Key">
              <el-input
                v-model="deepSeekForm.apiKey"
                type="password"
                show-password
                clearable
                placeholder="输入 DeepSeek API Key"
              />
            </el-form-item>

            <div class="task-form__actions">
              <el-button :loading="savingDeepSeek" type="primary" @click="handleSaveDeepSeek">
                保存
              </el-button>
              <el-button :loading="savingDeepSeek" @click="handleClearDeepSeek">
                清空
              </el-button>
            </div>
          </el-form>
        </article>

        <article class="detail-card">
          <div class="detail-card__head">
            <h5>当前配置</h5>
          </div>

          <dl class="detail-list">
            <div>
              <dt>Base URL</dt>
              <dd>{{ settingsPayload?.deepseek.base_url || '--' }}</dd>
            </div>
            <div>
              <dt>模型</dt>
              <dd>{{ settingsPayload?.deepseek.model || '--' }}</dd>
            </div>
            <div>
              <dt>后备模型</dt>
              <dd>{{ settingsPayload?.deepseek.fallback_model || '--' }}</dd>
            </div>
            <div>
              <dt>超时</dt>
              <dd>{{ deepSeekTimeoutLabel }}</dd>
            </div>
            <div>
              <dt>密钥来源</dt>
              <dd>{{ deepSeekKeySourceLabel }}</dd>
            </div>
            <div>
              <dt>生效提供方</dt>
              <dd>{{ effectiveProviderLabel }}</dd>
            </div>
          </dl>
        </article>
      </div>
    </section>

    <section class="panel-section">
      <div class="panel-section__head">
        <div>
          <h4>B站登录配置</h4>
        </div>
      </div>

      <div class="settings-grid">
        <article class="detail-card">
          <div class="detail-card__head">
            <h5>手动填写</h5>
            <small>{{ bilibiliUpdatedAtLabel }}</small>
          </div>

          <el-form label-position="top" @submit.prevent="handleSaveBilibili">
            <el-form-item label="Bilibili Cookie">
              <el-input
                v-model="bilibiliForm.cookie"
                type="textarea"
                :rows="7"
                placeholder="粘贴完整的 Bilibili Cookie，或使用右侧一键读取"
              />
            </el-form-item>

            <div class="task-form__actions">
              <el-button :loading="savingBilibili" type="primary" @click="handleSaveBilibili">
                保存 Cookie
              </el-button>
              <el-button :loading="savingBilibili" @click="handleClearBilibili">
                清空
              </el-button>
            </div>
          </el-form>
        </article>

        <article class="detail-card">
          <div class="detail-card__head">
            <h5>一键读取本机配置</h5>
          </div>

          <el-form label-position="top" @submit.prevent="handleImportBrowserCookie">
            <div class="settings-grid settings-grid--compact">
              <el-form-item label="浏览器">
                <el-select v-model="bilibiliImportForm.browser" placeholder="自动选择">
                  <el-option
                    v-for="source in browserSources"
                    :key="source.browser"
                    :label="source.label"
                    :value="source.browser"
                  />
                </el-select>
              </el-form-item>

              <el-form-item label="配置目录">
                <el-select
                  v-model="bilibiliImportForm.profileDirectory"
                  placeholder="自动选择"
                  :disabled="availableProfiles.length === 0"
                >
                  <el-option
                    v-for="profile in availableProfiles"
                    :key="profile.id"
                    :label="profile.label"
                    :value="profile.directory_name"
                  />
                </el-select>
              </el-form-item>
            </div>

            <el-form-item label="自定义用户数据目录">
              <el-input
                v-model="bilibiliImportForm.userDataDir"
                clearable
                placeholder="可选，不填则自动检测"
              />
            </el-form-item>

            <p class="ai-settings-note">
              如果本机 Cookie 文件被浏览器占用，系统会自动打开一个登录窗口，完成 B站登录后再回填配置。
            </p>

            <div class="task-form__actions">
              <el-button :loading="importingBrowserCookie" type="primary" @click="handleImportBrowserCookie">
                一键读取
              </el-button>
            </div>
          </el-form>

          <dl class="detail-list detail-list--single">
            <div>
              <dt>当前账号</dt>
              <dd>{{ bilibiliAccountLabel }}</dd>
            </div>
            <div>
              <dt>B站 UID</dt>
              <dd>{{ settingsPayload?.bilibili.account_profile?.mid || '--' }}</dd>
            </div>
            <div>
              <dt>来源</dt>
              <dd>{{ bilibiliImportSummary }}</dd>
            </div>
            <div>
              <dt>配置状态</dt>
              <dd>{{ bilibiliStatusLabel }}</dd>
            </div>
            <div v-if="settingsPayload?.bilibili.validation_message">
              <dt>验证结果</dt>
              <dd>{{ settingsPayload?.bilibili.validation_message }}</dd>
            </div>
          </dl>
        </article>
      </div>

      <article class="detail-card">
        <div class="detail-card__head">
          <h5>已解析出的关键字段</h5>
        </div>
        <dl class="detail-list">
          <div>
            <dt>SESSDATA</dt>
            <dd>{{ maskSecret(settingsPayload?.bilibili.sessdata) }}</dd>
          </div>
          <div>
            <dt>bili_jct</dt>
            <dd>{{ maskSecret(settingsPayload?.bilibili.bili_jct) }}</dd>
          </div>
          <div>
            <dt>DedeUserID</dt>
            <dd>{{ settingsPayload?.bilibili.dede_user_id || '--' }}</dd>
          </div>
          <div>
            <dt>buvid3</dt>
            <dd>{{ maskSecret(settingsPayload?.bilibili.buvid3) }}</dd>
          </div>
          <div>
            <dt>buvid4</dt>
            <dd>{{ maskSecret(settingsPayload?.bilibili.buvid4) }}</dd>
          </div>
          <div>
            <dt>Cookie 来源</dt>
            <dd>{{ bilibiliKeySourceLabel }}</dd>
          </div>
        </dl>
      </article>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { getErrorMessage } from '@/api/client'
import {
  getAiSettings,
  importBilibiliCookieFromBrowser,
  updateBilibiliCookie,
  updateDeepSeekApiKey,
} from '@/api/system'
import type { AiSettingsPayload, BrowserProfile, BrowserSource } from '@/api/types'
import StatCard from '@/components/common/StatCard.vue'
import { formatDateTime } from '@/utils/format'

const loading = ref(false)
const savingDeepSeek = ref(false)
const savingBilibili = ref(false)
const importingBrowserCookie = ref(false)
const settingsPayload = ref<AiSettingsPayload | null>(null)

const deepSeekForm = reactive({
  apiKey: '',
})

const bilibiliForm = reactive({
  cookie: '',
})

const bilibiliImportForm = reactive({
  browser: '',
  profileDirectory: '',
  userDataDir: '',
})

const browserSources = computed<BrowserSource[]>(() => settingsPayload.value?.bilibili.browser_sources || [])
const currentBrowserSource = computed<BrowserSource | null>(() => {
  if (!browserSources.value.length) {
    return null
  }
  return (
    browserSources.value.find((item) => item.browser === bilibiliImportForm.browser) ||
    browserSources.value[0]
  )
})
const availableProfiles = computed<BrowserProfile[]>(() => currentBrowserSource.value?.profiles || [])

const effectiveProviderLabel = computed(() => {
  const provider = settingsPayload.value?.deepseek.effective_provider || ''
  if (provider === 'deepseek') {
    return 'DeepSeek'
  }
  if (provider === 'openai') {
    return 'OpenAI'
  }
  if (provider === 'openai_compatible') {
    return '兼容接口'
  }
  return '--'
})

const deepSeekKeySourceLabel = computed(() => {
  const source = settingsPayload.value?.deepseek.key_source
  if (source === 'runtime') {
    return '前端设置'
  }
  if (source === 'environment') {
    return '环境变量'
  }
  return '未设置'
})

const bilibiliKeySourceLabel = computed(() => {
  const source = settingsPayload.value?.bilibili.key_source
  if (source === 'runtime') {
    return '前端设置'
  }
  if (source === 'environment') {
    return '环境变量'
  }
  return '未设置'
})

const bilibiliStatusLabel = computed(() =>
  settingsPayload.value?.bilibili.cookie_configured ? '已配置' : '未配置',
)

const bilibiliAccountLabel = computed(() => {
  const profile = settingsPayload.value?.bilibili.account_profile
  if (!profile?.is_login) {
    return '--'
  }
  return profile.username || '已登录'
})

const bilibiliImportSummary = computed(
  () => settingsPayload.value?.bilibili.import_summary || '手动填写 / 环境变量',
)

const deepSeekUpdatedAtLabel = computed(() =>
  settingsPayload.value?.deepseek.updated_at
    ? `更新于 ${formatDateTime(settingsPayload.value.deepseek.updated_at)}`
    : '尚未保存',
)

const bilibiliUpdatedAtLabel = computed(() =>
  settingsPayload.value?.bilibili.updated_at
    ? `更新于 ${formatDateTime(settingsPayload.value.bilibili.updated_at)}`
    : '尚未保存',
)

const deepSeekTimeoutLabel = computed(() => {
  const seconds = settingsPayload.value?.deepseek.timeout_seconds
  return typeof seconds === 'number' ? `${seconds} 秒` : '--'
})

watch(
  currentBrowserSource,
  (source) => {
    if (!source) {
      bilibiliImportForm.profileDirectory = ''
      return
    }
    const matchedProfile = source.profiles.find(
      (profile) => profile.id === source.default_profile_id,
    )
    if (!bilibiliImportForm.profileDirectory) {
      bilibiliImportForm.profileDirectory =
        matchedProfile?.directory_name || source.profiles[0]?.directory_name || ''
    }
  },
  { immediate: true },
)

async function loadSettings() {
  loading.value = true
  try {
    const response = await getAiSettings()
    settingsPayload.value = response
    deepSeekForm.apiKey = response.deepseek.api_key || ''
    bilibiliForm.cookie = response.bilibili.cookie || ''
    initializeImportSelection(response)
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '加载系统设置失败。'))
  } finally {
    loading.value = false
  }
}

function initializeImportSelection(response: AiSettingsPayload) {
  const sources = response.bilibili.browser_sources || []
  if (!sources.length) {
    bilibiliImportForm.browser = ''
    bilibiliImportForm.profileDirectory = ''
    return
  }
  if (!bilibiliImportForm.browser) {
    bilibiliImportForm.browser = sources[0].browser
  }
  const source = sources.find((item) => item.browser === bilibiliImportForm.browser) || sources[0]
  const matchedProfile = source.profiles.find((profile) => profile.id === source.default_profile_id)
  if (!bilibiliImportForm.profileDirectory) {
    bilibiliImportForm.profileDirectory =
      matchedProfile?.directory_name || source.profiles[0]?.directory_name || ''
  }
}

async function handleSaveDeepSeek() {
  savingDeepSeek.value = true
  try {
    const response = await updateDeepSeekApiKey(deepSeekForm.apiKey)
    if (settingsPayload.value) {
      settingsPayload.value = {
        ...settingsPayload.value,
        deepseek: response,
      }
    }
    ElMessage.success(response.api_key ? 'DeepSeek 密钥已保存。' : 'DeepSeek 密钥已清空。')
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '保存 DeepSeek 密钥失败。'))
  } finally {
    savingDeepSeek.value = false
  }
}

async function handleClearDeepSeek() {
  deepSeekForm.apiKey = ''
  await handleSaveDeepSeek()
}

async function handleSaveBilibili() {
  savingBilibili.value = true
  try {
    const response = await updateBilibiliCookie(bilibiliForm.cookie)
    if (settingsPayload.value) {
      settingsPayload.value = {
        ...settingsPayload.value,
        bilibili: response,
      }
    }
    bilibiliForm.cookie = response.cookie || ''
    if (settingsPayload.value) {
      initializeImportSelection(settingsPayload.value)
    }
    ElMessage.success(response.cookie ? 'B站登录态已保存。' : 'B站登录态已清空。')
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '保存 B站 Cookie 失败。'))
  } finally {
    savingBilibili.value = false
  }
}

async function handleClearBilibili() {
  bilibiliForm.cookie = ''
  await handleSaveBilibili()
}

async function handleImportBrowserCookie() {
  importingBrowserCookie.value = true
  try {
    const response = await importBilibiliCookieFromBrowser({
      browser: bilibiliImportForm.browser || null,
      profile_directory: bilibiliImportForm.profileDirectory || null,
      user_data_dir: bilibiliImportForm.userDataDir || null,
    })
    if (settingsPayload.value) {
      settingsPayload.value = {
        ...settingsPayload.value,
        bilibili: response,
      }
    }
    bilibiliForm.cookie = response.cookie || ''
    if (settingsPayload.value) {
      initializeImportSelection(settingsPayload.value)
    }
    ElMessage.success('已从本机浏览器读取 B站登录态。')
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '读取本机浏览器 Cookie 失败。'))
  } finally {
    importingBrowserCookie.value = false
  }
}

function maskSecret(value: string | null | undefined): string {
  const normalized = String(value || '').trim()
  if (!normalized) {
    return '--'
  }
  if (normalized.length <= 10) {
    return normalized
  }
  return `${normalized.slice(0, 4)}...${normalized.slice(-4)}`
}

onMounted(() => {
  void loadSettings()
})
</script>

<style scoped>
.settings-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.settings-grid--compact {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.detail-list--single {
  grid-template-columns: 1fr;
  margin-top: 16px;
}

.ai-settings-note {
  margin: 0;
  color: var(--muted);
  line-height: 1.6;
}

@media (max-width: 960px) {
  .settings-grid,
  .settings-grid--compact {
    grid-template-columns: 1fr;
  }
}
</style>
