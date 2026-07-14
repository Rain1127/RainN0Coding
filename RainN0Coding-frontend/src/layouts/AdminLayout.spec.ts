import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it } from 'vitest'
import AdminLayout from './AdminLayout.vue'

async function mountLayout() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/admin/apps', component: { template: '<div />' } },
      { path: '/admin/users', component: { template: '<div />' } },
      { path: '/admin/intent-tree', component: { template: '<div />' } },
    ],
  })
  await router.push('/admin/apps')
  await router.isReady()

  const wrapper = mount(AdminLayout, {
    attachTo: document.body,
    slots: { default: '<p>管理内容</p>' },
    global: {
      plugins: [pinia, router],
      stubs: {
        'a-avatar': { template: '<span><slot /></span>' },
        'a-dropdown': { template: '<div><slot /><slot name="overlay" /></div>' },
        'a-menu': { template: '<div><slot /></div>' },
        'a-menu-item': { template: '<button><slot /></button>' },
      },
    },
  })

  return { wrapper }
}

describe('AdminLayout', () => {
  it('traps focus inside the mobile drawer in both directions', async () => {
    const { wrapper } = await mountLayout()
    await wrapper.get('button[aria-controls="admin-mobile-navigation"]').trigger('click')
    await nextTick()

    const close = wrapper.get('#admin-mobile-navigation .mobile-drawer__header button')
    const logout = wrapper.get('#admin-mobile-navigation .sidebar-footer button')
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

  it('removes inert background state when the drawer closes', async () => {
    const { wrapper } = await mountLayout()
    const sidebar = wrapper.get('.desktop-sidebar').element
    const mainColumn = wrapper.get('.shell-main-column').element
    const trigger = wrapper.get('button[aria-controls="admin-mobile-navigation"]')

    await trigger.trigger('click')
    await nextTick()
    expect(sidebar.hasAttribute('inert')).toBe(true)
    expect(mainColumn.hasAttribute('inert')).toBe(true)

    await wrapper.get('#admin-mobile-navigation .mobile-drawer__header button').trigger('click')
    await nextTick()
    await nextTick()
    expect(sidebar.hasAttribute('inert')).toBe(false)
    expect(mainColumn.hasAttribute('inert')).toBe(false)
    expect(document.activeElement).toBe(trigger.element)

    wrapper.unmount()
  })
})
