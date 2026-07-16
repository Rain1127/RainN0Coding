import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it } from 'vitest'
import Forbidden from './Forbidden.vue'
import NotFound from './NotFound.vue'

async function mountAt(component: any, path: string) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component }] })
  await router.push(path)
  await router.isReady()
  return mount(component, { global: { plugins: [router] } })
}

describe('error pages', () => {
  it('renders an accessible standalone 403 without administration navigation', async () => {
    const wrapper = await mountAt(Forbidden, '/403')
    expect(wrapper.get('main')).toBeTruthy()
    expect(wrapper.findAll('h1')).toHaveLength(1)
    expect(wrapper.get('h1').text()).toContain('403')
    expect(wrapper.text()).toContain('没有权限')
    expect(wrapper.text()).not.toContain('用户管理')
    expect(wrapper.get('a[href="/"]').text()).toContain('返回首页')
    expect(wrapper.get('.skip-link').attributes('href')).toBe('#main-content')
    expect(wrapper.get('main').attributes('id')).toBe('main-content')
  })

  it('renders the missing route as text and never injects markup', async () => {
    const wrapper = await mountAt(NotFound, '/missing/<img-src=x>')
    expect(wrapper.get('main')).toBeTruthy()
    expect(wrapper.findAll('h1')).toHaveLength(1)
    expect(wrapper.text()).toContain('/missing/<img-src=x>')
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.get('a[href="/"]').text()).toContain('返回首页')
    expect(wrapper.get('.skip-link').attributes('href')).toBe('#main-content')
    expect(wrapper.get('main').attributes('id')).toBe('main-content')
  })
})
