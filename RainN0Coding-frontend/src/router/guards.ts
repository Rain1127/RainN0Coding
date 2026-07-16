export type RouteAccessMeta = Readonly<{
  requiresAuth?: boolean
  guest?: boolean
  requiresAdmin?: boolean
}>

declare module 'vue-router' {
  interface RouteMeta {
    requiresAuth?: boolean
    guest?: boolean
    requiresAdmin?: boolean
  }
}

export type RouteAccessDecision =
  | true
  | { name: 'Login'; query: { redirect: string } }
  | { name: 'Home' | 'Forbidden' }

export function decideRouteAccess(
  meta: RouteAccessMeta,
  authenticated: boolean,
  admin: boolean,
  fullPath: string,
): RouteAccessDecision {
  if (meta.requiresAuth === true && !authenticated) {
    return { name: 'Login', query: { redirect: fullPath } }
  }
  if (meta.guest === true && authenticated) {
    return { name: 'Home' }
  }
  if (meta.requiresAdmin === true && !admin) {
    return { name: 'Forbidden' }
  }
  return true
}

function normalizeBasePath(baseUrl: string): string {
  const withLeadingSlash = baseUrl.startsWith('/') ? baseUrl : `/${baseUrl}`
  return withLeadingSlash.replace(/\/+$/, '') || '/'
}

function splitPathSuffix(routePath: string): [pathname: string, suffix: string] {
  const queryIndex = routePath.indexOf('?')
  const hashIndex = routePath.indexOf('#')
  const suffixIndex = [queryIndex, hashIndex]
    .filter((index) => index >= 0)
    .reduce((smallest, index) => Math.min(smallest, index), routePath.length)
  return [routePath.slice(0, suffixIndex), routePath.slice(suffixIndex)]
}

function stripBasePath(routePath: string, baseUrl: string): string {
  const basePath = normalizeBasePath(baseUrl)
  if (basePath === '/') return routePath

  const [pathname, suffix] = splitPathSuffix(routePath)
  if (pathname !== basePath && !pathname.startsWith(`${basePath}/`)) return routePath

  return (pathname.slice(basePath.length) || '/') + suffix
}

export function buildLoginRedirect(
  pathname: string,
  search: string,
  hash = '',
  baseUrl = '/',
): string {
  const basePath = normalizeBasePath(baseUrl)
  const loginPath = `${basePath === '/' ? '' : basePath}/login`
  const destination = stripBasePath(pathname, basePath) + search + hash
  return `${loginPath}?redirect=${encodeURIComponent(destination)}`
}

export function shouldRedirectToLogin(pathname: string, baseUrl = '/'): boolean {
  const [internalPathname] = splitPathSuffix(stripBasePath(pathname, baseUrl))
  const canonicalPathname = internalPathname.length > 1
    ? internalPathname.replace(/\/+$/, '')
    : internalPathname
  return canonicalPathname !== '/login' && canonicalPathname !== '/register'
}

function isUnsafeRouterRedirect(value: string): boolean {
  let decoded = value
  try {
    decoded = decodeURIComponent(value)
  } catch {
    return true
  }

  return [value, decoded].some((candidate) => (
    !candidate.startsWith('/')
    || candidate.startsWith('//')
    || candidate.includes('\\')
    || /[\u0000-\u001f\u007f]/.test(candidate)
  ))
}

export function safeRouterRedirect(value: unknown, baseUrl = '/'): string {
  if (typeof value !== 'string' || isUnsafeRouterRedirect(value)) return '/'

  const internalPath = stripBasePath(value, baseUrl)
  return isUnsafeRouterRedirect(internalPath) ? '/' : internalPath
}
