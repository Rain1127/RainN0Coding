import type { EntityId } from '@/types/entity'

export function normalizeEntityId(value: unknown): EntityId | null {
  if (typeof value === 'number') {
    return Number.isSafeInteger(value) && value > 0 ? value : null
  }
  if (typeof value !== 'string') return null
  const normalized = value.trim()
  if (!/^\d+$/.test(normalized)) return null
  try {
    if (BigInt(normalized) <= 0n) return null
  } catch {
    return null
  }
  const numeric = Number(normalized)
  return Number.isSafeInteger(numeric) ? numeric : normalized
}

export function sameEntityId(left: EntityId | null | undefined, right: EntityId | null | undefined) {
  return left != null && right != null && String(left) === String(right)
}
