interface HighlightRange {
  start: number
  end: number
}

interface FormatInsightHtmlOptions {
  stripLeadingTitle?: string | null
}

const LABEL_PATTERN =
  /^\s*(?:[-*•]|(?:\d+[.)])|(?:其一|其二|其三|首先|其次|最后))?\s*([^\n：:]{2,18}[：:])/u

const HIGHLIGHT_PATTERNS = [
  /(?:核心|关键|主要|重点|优先|最新)?(?:结论|判断|建议|机会|风险|亮点|策略|趋势|信号|原因|总结|提醒|方向|变化|特征|优势|观察|发现)/gu,
  /(?:热度最高|增长最快|优先关注|重点主题|热点迁移|内容重心|高频关键词|创作策略|代表视频|播放量|互动率|转化率|爆发力|内容深度|社区扩散|综合热度)/gu,
  /(?:持续|明显|快速|显著|逐步)?(?:升温|回落|增长|下滑|领跑|领先|走强|走弱|爆发|承压|扩散|收缩|回暖|攀升|放缓)/gu,
  /(?:TOP|Top|top)\s?\d+/gu,
  /(?:近|过去|最近)\s?\d+\s*(?:天|周|个月|月|小时|分钟)/gu,
  /\d+(?:\.\d+)?\s*(?:%|倍|万|w|W|k|K|亿|条|次|人|小时|分钟|天)/gu,
  /[“"「『【][^”“"」』】\n]{2,24}[”"」』】]/gu,
]

export function escapeHtml(text: string) {
  return text
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

function escapeRegExp(text: string) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function mergeHighlightRanges(ranges: HighlightRange[]) {
  if (!ranges.length) {
    return []
  }

  const sorted = [...ranges].sort((left, right) => left.start - right.start || left.end - right.end)
  const merged: HighlightRange[] = [sorted[0]]

  for (const current of sorted.slice(1)) {
    const previous = merged[merged.length - 1]
    if (current.start <= previous.end) {
      previous.end = Math.max(previous.end, current.end)
      continue
    }
    merged.push({ ...current })
  }

  return merged
}

function normalizeExplicitHighlights(text: string) {
  let normalized = ''
  const explicitRanges: HighlightRange[] = []

  for (let cursor = 0; cursor < text.length; cursor += 1) {
    if (text.startsWith('**', cursor)) {
      const closingIndex = text.indexOf('**', cursor + 2)
      if (closingIndex > cursor + 2) {
        const content = text.slice(cursor + 2, closingIndex)
        const start = normalized.length
        normalized += content
        explicitRanges.push({
          start,
          end: start + content.length,
        })
        cursor = closingIndex + 1
        continue
      }
    }

    normalized += text[cursor]
  }

  return {
    text: normalized,
    explicitRanges,
  }
}

function collectLeadingLabelRange(text: string) {
  const match = LABEL_PATTERN.exec(text)
  if (!match || !match[1]) {
    return null
  }

  const fullMatch = match[0]
  const capture = match[1]
  const start = fullMatch.length - capture.length

  return {
    start,
    end: start + capture.length,
  }
}

function collectHighlightRanges(text: string) {
  const { text: normalizedText, explicitRanges } = normalizeExplicitHighlights(text)
  const ranges: HighlightRange[] = [...explicitRanges]
  const leadingLabelRange = collectLeadingLabelRange(normalizedText)

  if (leadingLabelRange) {
    ranges.push(leadingLabelRange)
  }

  for (const pattern of HIGHLIGHT_PATTERNS) {
    for (const match of normalizedText.matchAll(pattern)) {
      if (typeof match.index !== 'number') {
        continue
      }
      ranges.push({
        start: match.index,
        end: match.index + match[0].length,
      })
    }
  }

  return {
    text: normalizedText,
    ranges: mergeHighlightRanges(ranges),
  }
}

function stripLeadingTitle(text: string, title: string | null | undefined) {
  const normalizedTitle = title?.trim()
  if (!normalizedTitle) {
    return text.trim()
  }

  const titlePattern = new RegExp(`^\\s*${escapeRegExp(normalizedTitle)}\\s*[:：]?\\s*`, 'u')
  let current = text.trim()

  while (titlePattern.test(current)) {
    current = current.replace(titlePattern, '').trim()
  }

  return current
}

function renderWithHighlights(text: string, ranges: HighlightRange[]) {
  if (!text) {
    return ''
  }

  if (!ranges.length) {
    return escapeHtml(text)
  }

  let cursor = 0
  let html = ''

  for (const range of ranges) {
    if (range.start > cursor) {
      html += escapeHtml(text.slice(cursor, range.start))
    }

    html += `<strong>${escapeHtml(text.slice(range.start, range.end))}</strong>`
    cursor = range.end
  }

  if (cursor < text.length) {
    html += escapeHtml(text.slice(cursor))
  }

  return html
}

function formatInsightLine(line: string) {
  const { text, ranges } = collectHighlightRanges(line)
  return renderWithHighlights(text, ranges)
}

export function formatInsightHtml(
  text: string | null | undefined,
  options: FormatInsightHtmlOptions = {},
) {
  const source = stripLeadingTitle(String(text ?? ''), options.stripLeadingTitle)
  if (!source) {
    return ''
  }

  return source
    .split(/\n{2,}/)
    .map((block) => block.split('\n').map((line) => formatInsightLine(line)).join('<br />'))
    .join('<br /><br />')
}
