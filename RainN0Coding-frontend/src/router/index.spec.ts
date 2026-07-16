import { createWebHistory } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'
import router from './index'

async function routerSource() {
  const { readFileSync } = await vi.importActual<{
    readFileSync: (path: string, encoding: 'utf8') => string
  }>('node:fs')
  return readFileSync('src/router/index.ts', 'utf8')
}

describe('application routes', () => {
  it('registers the authenticated project browser route', () => {
    const projects = router.getRoutes().find(route => route.name === 'Projects')

    expect(projects?.path).toBe('/projects')
    expect(projects?.meta.requiresAuth).toBe(true)
  })

  it('binds web history to the Vite base URL used by production', async () => {
    expect(await routerSource()).toContain('createWebHistory(import.meta.env.BASE_URL)')
  })

  it('creates production home and deep-link hrefs inside /api/', () => {
    const history = createWebHistory('/api/')

    expect(history.base).toBe('/api')
    expect(history.createHref('/')).toBe('/api/')
    expect(history.createHref('/projects')).toBe('/api/projects')
    expect(history.createHref('/chat/42')).toBe('/api/chat/42')
  })
})
