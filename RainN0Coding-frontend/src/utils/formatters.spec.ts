import { describe, expect, it } from 'vitest'
import { formatDateTime, formatInteger } from './formatters'

describe('shared localized formatters', () => {
  it('formats valid dates with Intl and returns an em dash for empty or invalid values', () => {
    expect(formatDateTime('2026-07-15T08:30:00Z')).not.toBe('2026-07-15T08:30:00Z')
    expect(formatDateTime('')).toBe('—')
    expect(formatDateTime('not-a-date')).toBe('—')
    expect(formatDateTime(null)).toBe('—')
  })

  it('formats finite integers with Intl and handles invalid values safely', () => {
    expect(formatInteger(1234567)).toMatch(/1.*234.*567/)
    expect(formatInteger(Number.NaN)).toBe('—')
    expect(formatInteger(null)).toBe('—')
  })
})
