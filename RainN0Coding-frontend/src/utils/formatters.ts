const dateTimeFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
  timeStyle: 'short',
})

const integerFormatter = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 })

export function formatDateTime(value: unknown): string {
  if (typeof value !== 'string' && typeof value !== 'number' && !(value instanceof Date)) return '—'
  if (typeof value === 'string' && !value.trim()) return '—'
  const date = value instanceof Date ? value : new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : dateTimeFormatter.format(date)
}

export function formatInteger(value: unknown): string {
  if (typeof value === 'number' && Number.isFinite(value)) return integerFormatter.format(value)
  if (typeof value === 'string' && /^-?\d+$/.test(value.trim())) {
    try {
      return integerFormatter.format(BigInt(value.trim()))
    } catch {
      return '—'
    }
  }
  return '—'
}
