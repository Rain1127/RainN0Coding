import { describe, expect, it } from 'vitest'
import {
  buildLoginRedirect,
  decideRouteAccess,
  safeRouterRedirect,
  shouldRedirectToLogin,
} from './guards'
import type { RouteAccessMeta } from './guards'

describe('decideRouteAccess', () => {
  it('redirects a guest from a protected route with the full destination', () => {
    expect(
      decideRouteAccess(
        { requiresAuth: true },
        false,
        false,
        '/projects?tab=recent#activity',
      ),
    ).toEqual({
      name: 'Login',
      query: { redirect: '/projects?tab=recent#activity' },
    })
  })

  it('keeps an authenticated user away from a guest page', () => {
    expect(decideRouteAccess({ guest: true }, true, false, '/login')).toEqual({
      name: 'Home',
    })
  })

  it('blocks an authenticated non-admin from an admin route', () => {
    expect(
      decideRouteAccess(
        { requiresAuth: true, requiresAdmin: true },
        true,
        false,
        '/admin/apps',
      ),
    ).toEqual({ name: 'Forbidden' })
  })

  it('allows an authenticated admin to access an admin route', () => {
    expect(
      decideRouteAccess(
        { requiresAuth: true, requiresAdmin: true },
        true,
        true,
        '/admin/apps',
      ),
    ).toBe(true)
  })

  it.each([
    ['requiresAuth', { requiresAuth: 'true' }, false, false],
    ['guest', { guest: 'true' }, true, false],
    ['requiresAdmin', { requiresAdmin: 'true' }, true, false],
  ] as const)(
    'does not enable %s when malformed runtime metadata is non-boolean',
    (_field, meta, authenticated, admin) => {
      expect(
        decideRouteAccess(
          meta as unknown as RouteAccessMeta,
          authenticated,
          admin,
          '/chat/42',
        ),
      ).toBe(true)
    },
  )

  it('allows an authenticated user to access a protected route', () => {
    expect(decideRouteAccess({ requiresAuth: true }, true, false, '/projects')).toBe(true)
  })
})

describe('buildLoginRedirect', () => {
  it('preserves the destination path and search exactly', () => {
    expect(buildLoginRedirect('/projects', '?tab=mine&sort=updated%20desc')).toBe(
      '/login?redirect=%2Fprojects%3Ftab%3Dmine%26sort%3Dupdated%2520desc',
    )
  })

  it('uses the production base for login but stores a router-internal destination', () => {
    expect(buildLoginRedirect('/api/projects', '?x=1', '', '/api/')).toBe(
      '/api/login?redirect=%2Fprojects%3Fx%3D1',
    )
  })

  it('preserves query and hash while removing only one exact base segment', () => {
    expect(buildLoginRedirect('/api/api/projects', '?x=1', '#preview', '/api/')).toBe(
      '/api/login?redirect=%2Fapi%2Fprojects%3Fx%3D1%23preview',
    )
  })

  it('does not strip a partial base-segment match', () => {
    expect(buildLoginRedirect('/api2/projects?x=1', '', '', '/api/')).toBe(
      '/api/login?redirect=%2Fapi2%2Fprojects%3Fx%3D1',
    )
  })

  it.each([
    ['/projects', '?x=1', '#preview', '/', '/login?redirect=%2Fprojects%3Fx%3D1%23preview'],
    ['/api', '', '', '/api/', '/api/login?redirect=%2F'],
    ['/api/', '', '', '/api', '/api/login?redirect=%2F'],
  ] as const)(
    'normalizes pathname %s with base %s',
    (pathname, search, hash, base, expected) => {
      expect(buildLoginRedirect(pathname, search, hash, base)).toBe(expected)
    },
  )
})

describe('shouldRedirectToLogin', () => {
  it.each([
    { pathname: '/login', expected: false },
    { pathname: '/register', expected: false },
    { pathname: '/chat/42', expected: true },
  ] as const)('returns $expected for pathname $pathname', ({ pathname, expected }) => {
    expect(shouldRedirectToLogin(pathname)).toBe(expected)
  })

  it.each([
    ['/api/login', '/api/', false],
    ['/api/login/', '/api/', false],
    ['/api/register', '/api/', false],
    ['/api/register/', '/api/', false],
    ['/api/projects', '/api/', true],
    ['/api2/login', '/api/', true],
  ] as const)(
    'returns $expected for production pathname $pathname',
    (pathname, base, expected) => {
      expect(shouldRedirectToLogin(pathname, base)).toBe(expected)
    },
  )
})

describe('safeRouterRedirect', () => {
  it('converts a production-base redirect into a Vue Router internal path', () => {
    expect(safeRouterRedirect('/api/chat/42?tab=files#preview', '/api/')).toBe(
      '/chat/42?tab=files#preview',
    )
  })

  it.each(['//evil.example', 'https://evil.example', '/\\evil.example', '/api//evil.example'])(
    'rejects %s',
    (value) => {
      expect(safeRouterRedirect(value, '/api/')).toBe('/')
    },
  )
})
