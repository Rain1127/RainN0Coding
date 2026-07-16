import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'
import { useAppsStore } from '@/stores/apps'
import { useAuthStore } from '@/stores/auth'
import ChatLayout from './ChatLayout.vue'

async function mountLayout() {
  const pinia = createPinia()
  setActivePinia(pinia)
  useAuthStore().user = {
    id: 1, userAccount: 'admin', userName: 'Admin', userAvatar: '', userProfile: '',
    userRole: 'admin', createTime: '', updateTime: '',
  }
  const fetchRecentApps = vi.spyOn(useAppsStore(), 'fetchRecentApps').mockResolvedValue()

  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/projects', component: { template: '<div />' } },
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

  return { fetchRecentApps, router, wrapper }
}

describe('ChatLayout', () => {
  it('provides a semantic navigation landmark and skip target', async () => {
    const { wrapper } = await mountLayout()

    expect(wrapper.get('.skip-link').attributes('href')).toBe('#main-content')
    expect(wrapper.find('nav[aria-label="主导航"]').exists()).toBe(true)
    expect(wrapper.get('main#main-content').text()).toContain('工作区内容')
    wrapper.unmount()
  })

  it('links to the real project route and returns new-project work to the composer', async () => {
    const { wrapper } = await mountLayout()

    expect(wrapper.find('a[href="/projects"]').exists()).toBe(true)
    expect(wrapper.get('.shell-primary-button--sidebar').attributes('href')).toBe('/')
    wrapper.unmount()
  })

  it('renders administration navigation as a real link', async () => {
    const { wrapper } = await mountLayout()

    expect(wrapper.find('a[href="/admin/apps"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('loads recent projects for the sidebar without mutating the project browser page', async () => {
    const { fetchRecentApps, wrapper } = await mountLayout()

    expect(fetchRecentApps).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('closes the mobile menu with Escape and restores trigger focus', async () => {
    const { wrapper } = await mountLayout()
    const trigger = wrapper.get('button[aria-label="打开主导航"]')

    await trigger.trigger('click')
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()
    await nextTick()

    expect(trigger.attributes('aria-expanded')).toBe('false')
    expect(document.activeElement).toBe(trigger.element)
    wrapper.unmount()
  })

  it('restores mobile trigger focus when route navigation closes the drawer', async () => {
    const { router, wrapper } = await mountLayout()
    const trigger = wrapper.get('button[aria-label="打开主导航"]')

    await trigger.trigger('click')
    await router.push('/projects')
    await nextTick()
    await nextTick()

    expect(trigger.attributes('aria-expanded')).toBe('false')
    expect(document.activeElement).toBe(trigger.element)
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
