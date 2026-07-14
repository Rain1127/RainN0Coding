import { describe, expect, it } from 'vitest'
import router from './index'

describe('application routes', () => {
  it('registers the authenticated project browser route', () => {
    const projects = router.getRoutes().find(route => route.name === 'Projects')

    expect(projects?.path).toBe('/projects')
    expect(projects?.meta.requiresAuth).toBe(true)
  })
})
