import type { PageResult } from '@/types/api'

export interface NormalizedPageResult<T> {
  records: T[]
  total: number
  size: number
  current: number
  pages: number
}

function nonNegativeNumber(value: unknown, fallback: number) {
  const number = Number(value)
  return Number.isFinite(number) && number >= 0 ? number : fallback
}

function positiveNumber(value: unknown, fallback: number) {
  const number = Number(value)
  return Number.isFinite(number) && number > 0 ? number : fallback
}

export function normalizePageResult<T>(
  result: PageResult<T>,
  fallbackPage = 1,
  fallbackPageSize = 10,
): NormalizedPageResult<T> {
  const total = nonNegativeNumber(result.totalRow ?? result.total, 0)
  const size = positiveNumber(result.pageSize ?? result.size, fallbackPageSize)
  return {
    records: Array.isArray(result.records) ? result.records : [],
    total,
    size,
    current: positiveNumber(result.pageNumber ?? result.current, fallbackPage),
    pages: positiveNumber(result.totalPage ?? result.pages, Math.ceil(total / size) || 1),
  }
}
