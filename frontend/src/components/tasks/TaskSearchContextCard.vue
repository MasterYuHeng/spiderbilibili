<template>
  <article class="search-context-card" :class="{ 'search-context-card--compact': compact }">
    <div class="search-context-card__head">
      <div>
        <h5>{{ title }}</h5>
        <p v-if="description">{{ description }}</p>
      </div>
      <el-tag :type="enabled ? 'warning' : 'info'" effect="dark">
        {{ cardTagLabel }}
      </el-tag>
    </div>

    <dl class="search-context-card__meta">
      <div>
        <dt>原始关键词</dt>
        <dd>{{ sourceKeyword }}</dd>
      </div>
      <div>
        <dt>扩词状态</dt>
        <dd>{{ statusLabel }}</dd>
      </div>
      <div>
        <dt>新增同义词数量</dt>
        <dd>{{ expandedKeywordCount }}</dd>
      </div>
      <div>
        <dt>请求补充数量</dt>
        <dd>{{ requestedCountLabel }}</dd>
      </div>
    </dl>

    <div class="search-context-card__group">
      <span class="search-context-card__label">生成的同义词</span>
      <div class="tag-cluster">
        <el-tag
          v-for="keyword in generatedSynonyms"
          :key="`synonym-${keyword}`"
          effect="plain"
          type="warning"
        >
          {{ keyword }}
        </el-tag>
        <span v-if="!generatedSynonyms.length" class="search-context-card__empty">无</span>
      </div>
    </div>

    <div class="search-context-card__group">
      <span class="search-context-card__label">实际搜索词</span>
      <div class="tag-cluster">
        <el-tag
          v-for="keyword in searchKeywords"
          :key="`search-${keyword}`"
          effect="plain"
        >
          {{ keyword }}
        </el-tag>
        <span v-if="!searchKeywords.length" class="search-context-card__empty">无</span>
      </div>
    </div>

    <p v-if="noticeText" class="search-context-card__notice">
      {{ noticeText }}
    </p>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import type { KeywordExpansionPayload } from '@/api/types'

const props = withDefaults(
  defineProps<{
    taskKeyword?: string | null
    keywordExpansion?: KeywordExpansionPayload | null
    searchKeywordsUsed?: string[]
    expandedKeywordCount?: number
    crawlMode?: 'keyword' | 'hot' | null
    title?: string
    description?: string | null
    compact?: boolean
  }>(),
  {
    taskKeyword: null,
    keywordExpansion: null,
    searchKeywordsUsed: () => [],
    expandedKeywordCount: 0,
    crawlMode: 'keyword',
    title: '搜索口径',
    description: null,
    compact: false,
  },
)

const isHotMode = computed(() => props.crawlMode === 'hot')
const enabled = computed(() => props.keywordExpansion?.enabled ?? false)

const cardTagLabel = computed(() => {
  if (isHotMode.value) {
    return '热榜模式'
  }
  return enabled.value ? '已启用扩词' : '未启用扩词'
})

const sourceKeyword = computed(() => {
  if (isHotMode.value) {
    return '--'
  }
  return props.keywordExpansion?.source_keyword || props.taskKeyword || '--'
})

const generatedSynonyms = computed(() => {
  if (isHotMode.value) {
    return []
  }
  return props.keywordExpansion?.generated_synonyms ?? []
})

const searchKeywords = computed(() => {
  if (isHotMode.value) {
    return []
  }
  if (props.searchKeywordsUsed.length) {
    return props.searchKeywordsUsed
  }
  if (props.keywordExpansion?.expanded_keywords?.length) {
    return props.keywordExpansion.expanded_keywords
  }
  return sourceKeyword.value === '--' ? [] : [sourceKeyword.value]
})

const requestedCountLabel = computed(() => {
  if (isHotMode.value || !enabled.value) {
    return '--'
  }
  return String(props.keywordExpansion?.requested_synonym_count ?? '--')
})

const statusLabel = computed(() => {
  if (isHotMode.value) {
    return '热榜模式无需扩词'
  }

  const labels: Record<string, string> = {
    skipped: '未启用',
    pending: '待生成',
    success: '已生成',
    fallback: '已回退到原关键词',
    failed: '生成失败',
  }
  const status = props.keywordExpansion?.status ?? 'skipped'
  return labels[status] ?? status
})

const noticeText = computed(() => {
  if (isHotMode.value) {
    return '热榜模式不会执行关键词搜索，也不会进行关键词同义补充。'
  }

  const status = props.keywordExpansion?.status
  const errorMessage = props.keywordExpansion?.error_message
  if (status === 'fallback') {
    return errorMessage || '扩词未得到可用结果，当前任务已自动回退为原关键词搜索。'
  }
  if (status === 'failed') {
    return errorMessage || '扩词执行失败，当前任务已自动回退为原关键词搜索。'
  }
  return ''
})
</script>

<style scoped>
.search-context-card {
  padding: 16px 18px;
  border-radius: 18px;
  border: 1px solid rgba(100, 72, 46, 0.12);
  background: rgba(255, 255, 255, 0.72);
  display: grid;
  gap: 14px;
}

.search-context-card--compact {
  gap: 12px;
}

.search-context-card__head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.search-context-card__head h5 {
  margin: 0;
}

.search-context-card__head p,
.search-context-card__notice,
.search-context-card__empty,
.search-context-card__meta dt {
  color: var(--muted);
}

.search-context-card__head p {
  margin: 6px 0 0;
}

.search-context-card__meta {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin: 0;
}

.search-context-card__meta div {
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(255, 248, 241, 0.72);
}

.search-context-card__meta dt,
.search-context-card__meta dd {
  margin: 0;
}

.search-context-card__meta dd {
  margin-top: 6px;
  color: var(--text);
  font-weight: 700;
}

.search-context-card__group {
  display: grid;
  gap: 8px;
}

.search-context-card__label {
  font-size: 13px;
  font-weight: 700;
  color: var(--text);
}

.search-context-card__notice {
  margin: 0;
  line-height: 1.7;
}

@media (max-width: 900px) {
  .search-context-card__meta {
    grid-template-columns: 1fr;
  }

  .search-context-card__head {
    flex-direction: column;
  }
}
</style>
