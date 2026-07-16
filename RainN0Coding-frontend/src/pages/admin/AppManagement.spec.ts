import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { adminDeleteApp, adminListApps, deployApp, downloadApp } from '@/api/app'
import { useAuthStore } from '@/stores/auth'
import AppManagement from './AppManagement.vue'

vi.mock('@/api/app', () => ({
  adminDeleteApp: vi.fn(),
  adminListApps: vi.fn(),
  deployApp: vi.fn(),
  downloadApp: vi.fn(() => '/download/1'),
}))
vi.mock('@/api/auth', () => ({ getLoginUser: vi.fn(), login: vi.fn(), logout: vi.fn(), register: vi.fn() }))

const page = (name: string, id = 1) => ({
  records: [{ id, appName: name, codeGenType: 'vue_project', deployKey: '', priority: 0, createTime: '2026-07-15', userId: 2 }],
  total: 1,
  size: 10,
  current: 1,
  pages: 1,
}) as any

function mountPage() {
  const pinia = createPinia()
  setActivePinia(pinia)
  useAuthStore().user = { id: 2, userAccount: 'owner', userName: 'Owner', userAvatar: '', userProfile: '', userRole: 'admin', createTime: '', updateTime: '' }
  return mount(AppManagement, {
    attachTo: document.body,
    global: {
      plugins: [pinia], stubs: {
        AdminLayout: { template: '<main><slot /></main>' },
        PageHeader: { template: '<header><h1>{{ title }}</h1><slot name="actions" /></header>', props: ['title'] },
        RouterLink: { template: '<a><slot /></a>' },
      },
    },
  })
}

describe('AppManagement', () => {
  let wrapper: ReturnType<typeof mountPage> | undefined

  beforeEach(() => {
    document.body.innerHTML = ''
    vi.clearAllMocks()
    vi.mocked(adminListApps).mockResolvedValue(page('应用一'))
  })
  afterEach(() => wrapper?.unmount())

  it('uses real server query fields and keeps only the latest response', async () => {
    let resolveOld!: (value: any) => void
    vi.mocked(adminListApps)
      .mockReturnValueOnce(new Promise(resolve => { resolveOld = resolve }))
      .mockResolvedValueOnce(page('最新应用', 2))
    wrapper = mountPage()

    await wrapper.get('input[aria-label="搜索应用名称"]').setValue('看板')
    await wrapper.get('[data-action="search-apps"]').trigger('click')
    await flushPromises()
    resolveOld(page('旧应用'))
    await flushPromises()

    expect(adminListApps).toHaveBeenLastCalledWith(expect.objectContaining({
      pageNum: 1,
      pageSize: 10,
      appName: '看板',
      sortField: 'createTime',
      sortOrder: 'descend',
    }))
    expect(wrapper.text()).toContain('最新应用')
    expect(wrapper.text()).not.toContain('旧应用')
  })

  it('shows retryable load errors and confirms destructive deletion', async () => {
    vi.mocked(adminListApps).mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(page('恢复'))
    vi.mocked(adminDeleteApp).mockResolvedValue(true)
    wrapper = mountPage()
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('加载失败')
    await wrapper.get('[data-action="retry-apps"]').trigger('click')
    await flushPromises()
    const trigger = wrapper.get('[data-action="request-delete-app"]')
    await trigger.trigger('click')
    expect(adminDeleteApp).not.toHaveBeenCalled()
    expect(wrapper.get('[role="dialog"]').attributes('aria-modal')).toBe('true')
    expect(document.activeElement).toBe(wrapper.get('[data-action="confirm-delete-app"]').element)
    expect(wrapper.get('header').attributes('inert')).toBeDefined()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.get('header').attributes('inert')).toBeUndefined()
    expect(document.activeElement).toBe(trigger.element)
    await trigger.trigger('click')
    await wrapper.get('[data-action="confirm-delete-app"]').trigger('click')
    await flushPromises()
    expect(adminDeleteApp).toHaveBeenCalledWith({ id: 1 })
  })

  it('renders a keyboard-scrollable table and deploys using the returned URL string', async () => {
    vi.mocked(deployApp).mockResolvedValue('https://deploy.example/app')
    wrapper = mountPage()
    await flushPromises()

    expect(wrapper.get('.admin-table-scroll').attributes('tabindex')).toBe('0')
    await wrapper.get('[data-action="deploy-app"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('https://deploy.example/app')
  })

  it('blocks non-owners and rejects unsafe deployment URLs', async () => {
    const foreign = page('foreign')
    foreign.records[0].userId = 99
    vi.mocked(adminListApps).mockResolvedValueOnce(foreign)
    wrapper = mountPage()
    await flushPromises()
    expect(wrapper.text()).toContain('仅应用所有者可部署或下载')
    expect(wrapper.get('[data-action="deploy-app"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-action="deploy-app"]').trigger('click')
    await wrapper.get('[data-action="download-app"]').trigger('click')
    expect(deployApp).not.toHaveBeenCalled()
    expect(downloadApp).not.toHaveBeenCalled()
    vi.mocked(adminDeleteApp).mockResolvedValueOnce(true)
    expect(wrapper.get('[data-action="request-delete-app"]').attributes('disabled')).toBeUndefined()
    await wrapper.get('[data-action="request-delete-app"]').trigger('click')
    await wrapper.get('[data-action="confirm-delete-app"]').trigger('click')
    await flushPromises()
    expect(adminDeleteApp).toHaveBeenCalledWith({ id: 1 })

    vi.mocked(adminListApps).mockResolvedValueOnce(page('owner'))
    await (wrapper.vm as any).fetchApps()
    vi.mocked(deployApp).mockResolvedValueOnce('javascript:alert(1)')
    await wrapper.get('[data-action="deploy-app"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('.deployment-result').exists()).toBe(false)
    expect(wrapper.get('[role="alert"]').text()).toContain('部署失败')
  })

  it('recovers an out-of-range empty page using server current/pages metadata', async () => {
    wrapper = mountPage()
    await flushPromises()
    vi.mocked(adminListApps)
      .mockResolvedValueOnce({ records: [], total: 11, size: 10, current: 3, pages: 2 } as any)
      .mockResolvedValueOnce({ ...page('last-page'), current: 2, pages: 2, total: 11 } as any)
    ;(wrapper.vm as any).currentPage = 3
    await (wrapper.vm as any).fetchApps()
    await flushPromises()
    expect(adminListApps).toHaveBeenLastCalledWith(expect.objectContaining({ pageNum: 2 }))
    expect(wrapper.text()).toContain('第 2 / 2 页')
    expect(wrapper.text()).toContain('last-page')
  })

  it('invalidates an in-flight deployment when the list refreshes', async () => {
    let resolveDeploy!: (value: string) => void
    vi.mocked(deployApp).mockReturnValue(new Promise(resolve => { resolveDeploy = resolve }))
    wrapper = mountPage()
    await flushPromises()
    await wrapper.get('[data-action="deploy-app"]').trigger('click')
    expect(wrapper.get('[data-action="deploy-app"]').attributes('disabled')).toBeDefined()
    vi.mocked(adminListApps).mockResolvedValueOnce(page('refreshed'))
    await (wrapper.vm as any).fetchApps()
    expect(wrapper.get('[data-action="deploy-app"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-action="deploy-app"]').trigger('click')
    expect(deployApp).toHaveBeenCalledTimes(1)
    resolveDeploy('https://deploy.example/stale')
    await flushPromises()
    expect(wrapper.text()).toContain('refreshed')
    expect(wrapper.find('.deployment-result').exists()).toBe(false)
  })

  it('closes a failed delete confirmation and restores its trigger', async () => {
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
  })
})
