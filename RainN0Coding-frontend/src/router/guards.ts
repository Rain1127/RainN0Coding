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

export function buildLoginRedirect(pathname: string, search: string): string {
  return `/login?redirect=${encodeURIComponent(pathname + search)}`
}

export function shouldRedirectToLogin(pathname: string): boolean {
  return pathname !== '/login' && pathname !== '/register'
}
