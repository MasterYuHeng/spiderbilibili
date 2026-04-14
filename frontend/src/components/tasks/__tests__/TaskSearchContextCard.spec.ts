import { mount } from '@vue/test-utils'

import TaskSearchContextCard from '@/components/tasks/TaskSearchContextCard.vue'

describe('TaskSearchContextCard', () => {
  it('renders keyword expansion details for keyword mode', () => {
    const wrapper = mount(TaskSearchContextCard, {
      props: {
        taskKeyword: 'AI',
        crawlMode: 'keyword',
        expandedKeywordCount: 1,
        searchKeywordsUsed: ['AI', 'AIGC'],
        keywordExpansion: {
          source_keyword: 'AI',
          enabled: true,
          requested_synonym_count: 1,
          generated_synonyms: ['AIGC'],
          expanded_keywords: ['AI', 'AIGC'],
          status: 'success',
          model_name: 'gpt-expand',
          error_message: null,
          generated_at: '2026-04-14T00:00:00Z',
        },
      },
      global: {
        stubs: {
          ElTag: {
            template: '<span><slot /></span>',
          },
        },
      },
    })

    expect(wrapper.text()).toContain('已启用扩词')
    expect(wrapper.text()).toContain('已生成')
    expect(wrapper.text()).toContain('AI')
    expect(wrapper.text()).toContain('AIGC')
  })

  it('does not fabricate keyword search context for hot mode', () => {
    const wrapper = mount(TaskSearchContextCard, {
      props: {
        taskKeyword: '当前热度',
        crawlMode: 'hot',
        expandedKeywordCount: 0,
        searchKeywordsUsed: [],
        keywordExpansion: {
          source_keyword: '当前热度',
          enabled: false,
          requested_synonym_count: null,
          generated_synonyms: [],
          expanded_keywords: ['当前热度'],
          status: 'skipped',
          model_name: null,
          error_message: null,
          generated_at: null,
        },
      },
      global: {
        stubs: {
          ElTag: {
            template: '<span><slot /></span>',
          },
        },
      },
    })

    expect(wrapper.text()).toContain('热榜模式')
    expect(wrapper.text()).toContain('热榜模式无需扩词')
    expect(wrapper.text()).toContain('热榜模式不会执行关键词搜索')
    expect(wrapper.text()).not.toContain('当前热度')
  })
})
