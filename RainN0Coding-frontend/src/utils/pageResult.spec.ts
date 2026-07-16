import { describe, expect, it } from 'vitest'
import { normalizePageResult } from './pageResult'

describe('normalizePageResult', () => {
  it('normalizes the MyBatis-Flex pagination contract returned by Java', () => {
    const result = normalizePageResult({
      records: [{ id: 1 }],
      pageNumber: 2,
      pageSize: 10,
      totalPage: 3,
      totalRow: 21,
    }, 1, 20)

    expect(result).toEqual({
      records: [{ id: 1 }],
      current: 2,
      size: 10,
      pages: 3,
      total: 21,
    })
  })

  it('keeps the conventional pagination contract and safe fallbacks', () => {
    expect(normalizePageResult({ records: [], total: 4, current: 1, size: 20, pages: 1 }, 3, 50)).toEqual({
      records: [], total: 4, current: 1, size: 20, pages: 1,
    })
    expect(normalizePageResult({ records: [] }, 3, 50)).toEqual({
      records: [], total: 0, current: 3, size: 50, pages: 1,
    })
  })
})
