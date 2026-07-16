import { describe, expect, it } from 'vitest'
import { normalizeEntityId, sameEntityId } from './entityId'

describe('entityId', () => {
  it('keeps Snowflake IDs as lossless strings', () => {
    const id = '429149380495425536'
    expect(normalizeEntityId(id)).toBe(id)
    expect(sameEntityId(id, '429149380495425536')).toBe(true)
  })

  it('retains compatibility for safe numeric IDs and rejects invalid values', () => {
    expect(normalizeEntityId('42')).toBe(42)
    expect(sameEntityId('42', 42)).toBe(true)
    expect(normalizeEntityId('0')).toBeNull()
    expect(normalizeEntityId('12x')).toBeNull()
    expect(normalizeEntityId(9_007_199_254_740_992)).toBeNull()
  })
})
