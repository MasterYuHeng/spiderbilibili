import { describe, expect, it } from 'vitest'

import { formatInsightHtml } from '@/utils/aiText'

describe('formatInsightHtml', () => {
  it('highlights leading labels, trend words, and numeric signals', () => {
    const html = formatInsightHtml('核心结论：A 主题最近30天持续升温，互动率提升 18%。')

    expect(html).toContain('<strong>核心结论：</strong>')
    expect(html).toContain('<strong>最近30天持续升温</strong>')
    expect(html).toContain('<strong>互动率</strong>')
    expect(html).toContain('<strong>18%</strong>')
  })

  it('supports markdown-style emphasis from AI output', () => {
    const html = formatInsightHtml('建议优先关注 **热点迁移** 和 **内容重心** 的变化。')

    expect(html).toContain('<strong>热点迁移</strong>')
    expect(html).toContain('<strong>内容重心</strong>')
  })

  it('removes repeated leading titles before highlighting', () => {
    const html = formatInsightHtml('热点判断：热点判断：B 主题播放量增长最快。', {
      stripLeadingTitle: '热点判断',
    })

    expect(html.startsWith('热点判断')).toBe(false)
    expect(html).toContain('<strong>播放量增长最快</strong>')
  })

  it('escapes html while preserving emphasis', () => {
    const html = formatInsightHtml('重点提醒：<script>alert(1)</script> 转化率达到 12%。')

    expect(html).toContain('&lt;script&gt;alert(1)&lt;/script&gt;')
    expect(html).toContain('<strong>重点提醒：</strong>')
    expect(html).toContain('<strong>转化率</strong>')
    expect(html).toContain('<strong>12%</strong>')
  })
})
