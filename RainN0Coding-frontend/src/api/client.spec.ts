import { describe, expect, it } from 'vitest'
import { unauthorizedRedirectForLocation } from './client'

describe('unauthorizedRedirectForLocation', () => {
  it('builds a production-base login URL with an internal redirect target', () => {
    expect(unauthorizedRedirectForLocation({
      pathname: '/api/projects',
      search: '?x=1',
      hash: '#recent',
    }, '/api/')).toBe(
      '/api/login?redirect=%2Fprojects%3Fx%3D1%23recent',
    )
  })

  it.each(['/api/login', '/api/register'])('does not redirect a guest page: %s', (pathname) => {
    expect(unauthorizedRedirectForLocation({ pathname, search: '', hash: '' }, '/api/')).toBeNull()
  })

  it('keeps the development-root behavior', () => {
    expect(unauthorizedRedirectForLocation({
      pathname: '/projects',
      search: '?tab=mine',
      hash: '',
    }, '/')).toBe('/login?redirect=%2Fprojects%3Ftab%3Dmine')
  })
})
