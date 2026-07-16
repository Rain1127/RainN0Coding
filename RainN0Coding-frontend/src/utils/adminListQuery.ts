export const ADMIN_PAGE_SIZES = [10, 20, 50] as const

export interface AdminListQueryState {
  page: number
  pageSize: number
  search: string
  role?: '' | 'user' | 'admin'
}

function stringValue(value: unknown) {
  return typeof value === 'string' ? value : ''
}

export function parseAdminListQuery(query: Record<string, unknown>, withRole = false): AdminListQueryState {
  const parsedPage = Number(stringValue(query.page))
  const parsedPageSize = Number(stringValue(query.pageSize))
  const role = stringValue(query.role)
  return {
    page: Number.isSafeInteger(parsedPage) && parsedPage > 0 ? parsedPage : 1,
    pageSize: ADMIN_PAGE_SIZES.includes(parsedPageSize as typeof ADMIN_PAGE_SIZES[number]) ? parsedPageSize : 10,
    search: stringValue(query.search).trim(),
    ...(withRole ? { role: role === 'user' || role === 'admin' ? role : '' } : {}),
  }
}

export function buildAdminListQuery(state: AdminListQueryState): Record<string, string> {
  const query: Record<string, string> = {}
  if (state.page > 1) query.page = String(state.page)
  if (state.pageSize !== 10) query.pageSize = String(state.pageSize)
  if (state.search) query.search = state.search
  if (state.role) query.role = state.role
  return query
}

export function isCanonicalAdminListQuery(current: Record<string, unknown>, canonical: Record<string, string>) {
  const keys = Object.keys(current)
  const canonicalKeys = Object.keys(canonical)
  return keys.length === canonicalKeys.length
    && canonicalKeys.every((key) => stringValue(current[key]) === canonical[key])
}
