import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp } from '@/api/app'
import { useAppsStore } from '@/stores/apps'
import ChatLayout from './ChatLayout.vue'

vi.mock('@/api/app', () => ({ createApp: vi.fn() }))

async function mountLayout() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const fetchMyApps = vi.spyOn(useAppsStore(), 'fetchMyApps').mockResolvedValue()

  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/chat/:appId', component: { template: '<div />' } },
      { path: '/admin/apps', component: { template: '<div />' } },
    ],
  })
  await router.push('/')
  await router.isReady()

  const wrapper = mount(ChatLayout, {
    attachTo: document.body,
    slots: { default: '<p>工作区内容</p>' },
    global: {
      plugins: [pinia, router],
      stubs: {
        'a-input': { template: '<input />' },
        'a-avatar': { template: '<span><slot /></span>' },
        'a-dropdown': { template: '<div><slot /><slot name="overlay" /></div>' },
        'a-menu': { template: '<div><slot /></div>' },
        'a-menu-item': { template: '<button><slot /></button>' },
      },
    },
  })

  return { fetchMyApps, router, wrapper }
}

describe('ChatLayout', () => {
  beforeEach(() => {
    vi.mocked(createApp).mockReset()
  })

  it('provides a semantic navigation landmark and skip target', async () => {
    const { wrapper } = await mountLayout()

    expect(wrapper.get('.skip-link').attributes('href')).toBe('#main-content')
    expect(wrapper.find('nav[aria-label="主导航"]').exists()).toBe(true)
    expect(wrapper.get('main#main-content').text()).toContain('工作区内容')

    wrapper.unmount()
  })

  it('closes the mobile menu with Escape and restores trigger focus', async () => {
    const { wrapper } = await mountLayout()
    const trigger = wrapper.get('button[aria-label="打开主导航"]')

    expect(trigger.attributes('aria-expanded')).toBe('false')
    await trigger.trigger('click')
    expect(trigger.attributes('aria-expanded')).toBe('true')

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()
    await nextTick()

    expect(trigger.attributes('aria-expanded')).toBe('false')
    expect(document.activeElement).toBe(trigger.element)

    wrapper.unmount()
  })

  it('restores the mobile trigger focus when navigation closes the drawer', async () => {
    const { router, wrapper } = await mountLayout()
    const trigger = wrapper.get('button[aria-label="打开主导航"]')

    await trigger.trigger('click')
    expect(trigger.attributes('aria-expanded')).toBe('true')

    await router.push('/admin/apps')
    await nextTick()
    await nextTick()

    expect(trigger.attributes('aria-expanded')).toBe('false')
    expect(document.activeElement).toBe(trigger.element)

    wrapper.unmount()
  })

  it('marks the compact mobile brand link as a full-size touch target', async () => {
    const { wrapper } = await mountLayout()

    expect(wrapper.get('.mobile-header .mobile-brand-link').attributes('aria-label')).toBe('返回生成首页')

    wrapper.unmount()
  })

  it('does not render navigation to a route that is not registered yet', async () => {
    const { wrapper } = await mountLayout()

    expect(wrapper.find('a[href="/projects"]').exists()).toBe(false)

    wrapper.unmount()
  })

  it('navigates to a newly created app even when refreshing the app list fails', async () => {
    vi.mocked(createApp).mockResolvedValue(42)
    const { fetchMyApps, router, wrapper } = await mountLayout()
    fetchMyApps.mockClear()
    fetchMyApps.mockRejectedValueOnce(new Error('refresh failed'))

    await wrapper.get('.shell-primary-button--sidebar').trigger('click')
    await flushPromises()

    expect(createApp).toHaveBeenCalledTimes(1)
    expect(router.currentRoute.value.fullPath).toBe('/chat/42')
    expect(fetchMyApps).toHaveBeenCalledTimes(1)

    wrapper.unmount()
  })

  it('traps focus inside the mobile drawer in both directions', async () => {
    const { wrapper } = await mountLayout()
    await wrapper.get('button[aria-controls="chat-mobile-navigation"]').trigger('click')
    await nextTick()

    const close = wrapper.get('#chat-mobile-navigation .mobile-drawer__header button')
    const logout = wrapper.get('#chat-mobile-navigation .sidebar-footer button')
    const closeElement = close.element as HTMLElement
    const logoutElement = logout.element as HTMLElement
    expect(document.activeElement).toBe(closeElement)

    logoutElement.focus()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }))
    expect(document.activeElement).toBe(closeElement)

    closeElement.focus()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true }))
    expect(document.activeElement).toBe(logoutElement)

    wrapper.unmount()
  })

  it('makes background regions inert and removes the boundary during cleanup', async () => {
    const { wrapper } = await mountLayout()
    const sidebar = wrapper.get('.desktop-sidebar').element
    const mainColumn = wrapper.get('.shell-main-column').element

    await wrapper.get('button[aria-controls="chat-mobile-navigation"]').trigger('click')
    await nextTick()
    expect(sidebar.hasAttribute('inert')).toBe(true)
    expect(mainColumn.hasAttribute('inert')).toBe(true)

    wrapper.unmount()
    expect(sidebar.hasAttribute('inert')).toBe(false)
    expect(mainColumn.hasAttribute('inert')).toBe(false)
  })
})
