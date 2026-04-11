import { describe, expect, it } from 'vitest'

import { normalizeBaseUrl } from '@/api/client'

describe('normalizeBaseUrl', () => {
  it('falls back to the local api prefix when the value is empty', () => {
    expect(normalizeBaseUrl('')).toBe('/api')
  })

  it('keeps an existing api suffix without duplicating it', () => {
    expect(normalizeBaseUrl('http://localhost:8014/api')).toBe('http://localhost:8014/api')
    expect(normalizeBaseUrl('http://localhost:8014/api/')).toBe('http://localhost:8014/api')
  })

  it('appends the api suffix after trimming trailing slashes', () => {
    expect(normalizeBaseUrl('http://localhost:8014/')).toBe('http://localhost:8014/api')
  })
})
