import { describe, expect, it } from 'vitest'
import {
  buildLoginRedirect,
  decideRouteAccess,
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
})

describe('shouldRedirectToLogin', () => {
  it.each([
    { pathname: '/login', expected: false },
    { pathname: '/register', expected: false },
    { pathname: '/chat/42', expected: true },
  ] as const)('returns $expected for pathname $pathname', ({ pathname, expected }) => {
    expect(shouldRedirectToLogin(pathname)).toBe(expected)
  })
})
