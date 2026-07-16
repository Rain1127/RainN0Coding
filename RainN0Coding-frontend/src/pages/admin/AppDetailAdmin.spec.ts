import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { adminDeleteApp, adminGetAppVO, deployApp, downloadApp } from '@/api/app'
import { useAuthStore } from '@/stores/auth'
import AppDetailAdmin from './AppDetailAdmin.vue'

const routerMocks = vi.hoisted(() => ({ routerReplace: vi.fn(), route: null as any }))

vi.mock('vue-router', async () => {
  const { reactive } = await import('vue')
  routerMocks.route = reactive({ params: { appId: '42' } })
  return { useRoute: () => routerMocks.route, useRouter: () => ({ replace: routerMocks.routerReplace }) }
})
vi.mock('@/api/app', () => ({
  adminDeleteApp: vi.fn(),
  adminGetAppVO: vi.fn(),
  deployApp: vi.fn(),
  downloadApp: vi.fn(() => '/api/app/download/42'),
}))
vi.mock('@/api/auth', () => ({ getLoginUser: vi.fn(), login: vi.fn(), logout: vi.fn(), register: vi.fn() }))

const app = {
  id: 42,
  appName: '运营看板',
  initPrompt: '创建运营看板',
  codeGenType: 'vue_project',
  deployKey: '',
  priority: 0,
  userId: 8,
  currentVersion: 3,
  createTime: '2026-07-15',
  updateTime: '2026-07-16',
  editTime: '2026-07-16',
  userVO: { id: 8, userName: '项目所有者' },
} as any

function mountPage(userId = 8) {
  const pinia = createPinia()
  setActivePinia(pinia)
  useAuthStore().user = { id: userId, userAccount: 'admin', userName: 'Admin', userAvatar: '', userProfile: '', userRole: 'admin', createTime: '', updateTime: '' }
  return mount(AppDetailAdmin, {
    attachTo: document.body,
    global: {
      plugins: [pinia], stubs: {
        AdminLayout: { template: '<main><slot /></main>' },
        PageHeader: { template: '<header><h1>{{ title }}</h1><slot name="actions" /></header>', props: ['title'] },
        RouterLink: { template: '<a href="/admin/apps"><slot /></a>' },
      },
    },
  })
}

describe('AppDetailAdmin', () => {
  let wrapper: ReturnType<typeof mountPage> | undefined

  beforeEach(() => {
    document.body.innerHTML = ''
    vi.clearAllMocks()
    routerMocks.route.params.appId = '42'
    vi.mocked(adminGetAppVO).mockResolvedValue(app)
  })
  afterEach(() => wrapper?.unmount())

  it('loads the real app id and labels application fields', async () => {
    wrapper = mountPage()
    await flushPromises()
    expect(adminGetAppVO).toHaveBeenCalledWith(42)
    expect(wrapper.text()).toContain('代码生成类型')
    expect(wrapper.text()).toContain('创建者')
    expect(wrapper.text()).toContain('项目所有者')
    expect(wrapper.text()).toContain('初始需求')
  })

  it('shows the deployment URL returned by the string API contract', async () => {
    vi.mocked(deployApp).mockResolvedValue('https://deploy.example/board')
    wrapper = mountPage()
    await flushPromises()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(deployApp).toHaveBeenCalledWith(42)
    expect(wrapper.text()).toContain('https://deploy.example/board')
  })

  it('traps focus, restores the delete trigger on Escape, and safely returns after deletion', async () => {
    let resolveDelete!: (value: boolean) => void
    vi.mocked(adminDeleteApp).mockReturnValue(new Promise(resolve => { resolveDelete = resolve }))
    wrapper = mountPage()
    await flushPromises()
    const trigger = wrapper.get('[data-action="request-delete-app"]')

    await trigger.trigger('click')
    await flushPromises()
    const confirm = wrapper.get('[data-action="confirm-delete-app"]')
    const cancel = wrapper.get('[data-action="cancel-delete-app"]')
    expect(document.activeElement).toBe(confirm.element)
    expect(wrapper.get('header').attributes('inert')).toBeDefined()

    await confirm.trigger('keydown', { key: 'Tab' })
    expect(document.activeElement).toBe(cancel.element)
    await cancel.trigger('keydown', { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(confirm.element)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.get('header').attributes('inert')).toBeUndefined()
    expect(document.activeElement).toBe(trigger.element)

    await trigger.trigger('click')
    await wrapper.get('[data-action="confirm-delete-app"]').trigger('click')
    await wrapper.get('[data-action="confirm-delete-app"]').trigger('click')
    expect(adminDeleteApp).toHaveBeenCalledTimes(1)
    expect(adminDeleteApp).toHaveBeenCalledWith({ id: 42 })
    resolveDelete(true)
    await flushPromises()
    expect(routerMocks.routerReplace).toHaveBeenCalledWith('/admin/apps')
  })

  it('keeps app details visible and restores focus when deletion fails', async () => {
    vi.mocked(adminDeleteApp).mockRejectedValue(new Error('delete failed'))
    wrapper = mountPage()
    await flushPromises()
    const trigger = wrapper.get('[data-action="request-delete-app"]')

    await trigger.trigger('click')
    await wrapper.get('[data-action="confirm-delete-app"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(document.activeElement).toBe(trigger.element)
    expect(wrapper.get('[role="alert"]').text()).toContain('删除失败')
    expect(wrapper.text()).toContain('运营看板')
    expect(routerMocks.routerReplace).not.toHaveBeenCalled()
  })

  it('reloads on route reuse and ignores the older app response', async () => {
    let resolveOld!: (value: any) => void
    vi.mocked(adminGetAppVO)
      .mockReturnValueOnce(new Promise(resolve => { resolveOld = resolve }))
      .mockResolvedValueOnce({ ...app, id: 43, appName: '新应用', userId: 8 })
    wrapper = mountPage()
    routerMocks.route.params.appId = '43'
    await flushPromises()
    resolveOld(app)
    await flushPromises()
    expect(adminGetAppVO).toHaveBeenLastCalledWith(43)
    expect(wrapper.get('h1').text()).toBe('新应用')
    expect(wrapper.text()).toContain('应用 ID43')
  })

  it('blocks non-owner operations and rejects unsafe deployment URLs', async () => {
    wrapper = mountPage(7)
    await flushPromises()
    expect(wrapper.text()).toContain('仅应用所有者可部署或下载此应用')
    expect(wrapper.get('[data-action="request-delete-app"]').attributes('disabled')).toBeUndefined()
    await wrapper.get('.primary-button').trigger('click')
    await wrapper.get('.detail-actions .secondary-button').trigger('click')
    expect(deployApp).not.toHaveBeenCalled()
    expect(downloadApp).not.toHaveBeenCalled()
    vi.mocked(adminDeleteApp).mockResolvedValueOnce(true)
    await wrapper.get('[data-action="request-delete-app"]').trigger('click')
    await wrapper.get('[data-action="confirm-delete-app"]').trigger('click')
    await flushPromises()
    expect(adminDeleteApp).toHaveBeenCalledWith({ id: 42 })

    wrapper.unmount()
    wrapper = mountPage(8)
    await flushPromises()
    vi.mocked(deployApp).mockResolvedValueOnce('data:text/html,unsafe')
    await wrapper.get('.primary-button').trigger('click')
    await flushPromises()
    expect(wrapper.find('.deployment-result').exists()).toBe(false)
    expect(wrapper.get('[role="alert"]').text()).toContain('部署失败')
  })

  it('invalidates an in-flight deployment when the route changes', async () => {
    let resolveDeploy!: (value: string) => void
    vi.mocked(deployApp).mockReturnValue(new Promise(resolve => { resolveDeploy = resolve }))
    wrapper = mountPage()
    await flushPromises()
    await wrapper.get('.primary-button').trigger('click')
    vi.mocked(adminGetAppVO).mockResolvedValueOnce({ ...app, id: 43, appName: '路由新应用' })
    routerMocks.route.params.appId = '43'
    await flushPromises()
    resolveDeploy('https://deploy.example/stale')
    await flushPromises()
    expect(wrapper.get('h1').text()).toBe('路由新应用')
    expect(wrapper.find('.deployment-result').exists()).toBe(false)
  })

  it('clears a valid pending app immediately when the reused route becomes invalid', async () => {
    let resolveOld!: (value: any) => void
    vi.mocked(adminGetAppVO).mockReturnValueOnce(new Promise(resolve => { resolveOld = resolve }))
    wrapper = mountPage()
    routerMocks.route.params.appId = 'invalid'
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('应用编号无效')
    expect(wrapper.text()).not.toContain('运营看板')
    resolveOld(app)
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('应用编号无效')
    expect(wrapper.text()).not.toContain('运营看板')
  })
})
