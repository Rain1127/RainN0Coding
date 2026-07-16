import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { listUsers, updateUser } from '@/api/user'
import { useAuthStore } from '@/stores/auth'
import UserManagement from './UserManagement.vue'

const routeState = vi.hoisted(() => ({ route: null as any, replace: vi.fn() }))

vi.mock('vue-router', async () => {
  const { reactive } = await import('vue')
  routeState.route = reactive({ query: {} as Record<string, unknown> })
  return {
    useRoute: () => routeState.route,
    useRouter: () => ({ replace: routeState.replace }),
  }
})

vi.mock('@/api/user', () => ({ addUser: vi.fn(), deleteUser: vi.fn(), listUsers: vi.fn(), updateUser: vi.fn() }))
vi.mock('@/api/auth', () => ({ getLoginUser: vi.fn(), login: vi.fn(), logout: vi.fn(), register: vi.fn() }))

function mountPage() {
  const pinia = createPinia()
  setActivePinia(pinia)
  useAuthStore().user = {
    id: 7,
    userAccount: 'me',
    userName: '我',
    userAvatar: '',
    userProfile: '',
    userRole: 'admin',
    createTime: '',
    updateTime: '',
  }
  const wrapper = mount(UserManagement, {
    global: {
      plugins: [pinia],
      stubs: {
        AdminLayout: { template: '<main><slot /></main>' },
        PageHeader: { template: '<header><h1>{{ title }}</h1><slot name="actions" /></header>', props: ['title'] },
      },
    },
  })
  mountedWrappers.push(wrapper)
  return wrapper
}

const mountedWrappers: Array<ReturnType<typeof mount>> = []

describe('UserManagement', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    routeState.route.query = {}
    routeState.replace.mockImplementation(async ({ query }: { query: Record<string, unknown> }) => {
      routeState.route.query = query
    })
    vi.mocked(listUsers).mockResolvedValue({
      records: [
        { id: 7, userAccount: 'me', userName: '我', userAvatar: '', userProfile: '', userRole: 'admin', createTime: '' },
        { id: 8, userAccount: 'other', userName: '其他', userAvatar: '', userProfile: '', userRole: 'user', createTime: '' },
      ],
      total: 2,
      size: 10,
      current: 1,
      pages: 1,
    })
    vi.mocked(updateUser).mockResolvedValue(true)
  })
  afterEach(() => {
    for (const wrapper of mountedWrappers.splice(0)) wrapper.unmount()
  })

  it('hydrates pagination and user filters from the URL and follows history changes once', async () => {
    routeState.route.query = { page: '2', pageSize: '20', search: 'operator', role: 'admin' }
    vi.mocked(listUsers).mockResolvedValue({
      records: [], total: 60, size: 20, current: 2, pages: 3,
    })

    const wrapper = mountPage()
    await flushPromises()

    expect(listUsers).toHaveBeenCalledTimes(1)
    expect(listUsers).toHaveBeenLastCalledWith(expect.objectContaining({
      pageNum: 2,
      pageSize: 20,
      userAccount: 'operator',
      userRole: 'admin',
    }))
    expect((wrapper.get('[name="user-role-filter"]').element as HTMLSelectElement).value).toBe('admin')

    routeState.route.query = { page: '3', pageSize: '20', role: 'user' }
    await flushPromises()
    expect(listUsers).toHaveBeenCalledTimes(2)
    expect(listUsers).toHaveBeenLastCalledWith(expect.objectContaining({ pageNum: 3, pageSize: 20, userRole: 'user' }))
  })

  it('canonicalizes invalid user list query values before one default fetch', async () => {
    routeState.route.query = { page: '0', pageSize: '200', role: 'owner', search: '  ' }
    const wrapper = mountPage()
    await flushPromises()

    expect(routeState.replace).toHaveBeenCalledWith({ query: {} })
    expect(listUsers).toHaveBeenCalledTimes(1)
    expect(listUsers).toHaveBeenCalledWith(expect.objectContaining({ pageNum: 1, pageSize: 10 }))
  })

  it('searches with real fields and prevents changing the signed-in account', async () => {
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('input[aria-label="搜索用户账号"]').setValue('other')
    await wrapper.get('[data-action="search-users"]').trigger('click')
    await flushPromises()
    expect(listUsers).toHaveBeenLastCalledWith(expect.objectContaining({ userAccount: 'other', pageNum: 1, pageSize: 10 }))
    expect(wrapper.get('[data-user-id="7"] [data-action="change-role"]').attributes('disabled')).toBeDefined()
  })

  it('updates a Snowflake user id without numeric conversion', async () => {
    const snowflake = '430474206606770176'
    vi.mocked(listUsers).mockResolvedValueOnce({
      records: [{ id: snowflake, userAccount: 'snowflake', userName: 'Snowflake', userAvatar: '', userProfile: '', userRole: 'user', createTime: '' }],
      pageNumber: 1,
      pageSize: 10,
      totalPage: 1,
      totalRow: 1,
    })
    const wrapper = mountPage()
    await flushPromises()

    const role = wrapper.get(`[data-user-id="${snowflake}"] [data-action="change-role"]`)
    await role.setValue('admin')
    await role.trigger('change')
    await flushPromises()

    expect(updateUser).toHaveBeenCalledWith({ id: snowflake, userRole: 'admin' })
  })

  it('prevents duplicate role mutations and keeps the row after an error', async () => {
    let reject!: (reason: unknown) => void
    vi.mocked(updateUser).mockReturnValue(new Promise((_resolve, rejectPromise) => { reject = rejectPromise }))
    const wrapper = mountPage()
    await flushPromises()
    const role = wrapper.get('[data-user-id="8"] [data-action="change-role"]')

    await role.setValue('admin')
    await role.trigger('change')
    await role.trigger('change')
    expect(updateUser).toHaveBeenCalledTimes(1)
    reject(new Error('failed'))
    await flushPromises()
    expect(wrapper.get('[data-user-id="8"]')).toBeTruthy()
    expect(wrapper.get('[role="alert"]').text()).toContain('角色更新失败')
  })

  it('keeps the desired role over a refresh and applies success to the replacement row', async () => {
    let resolveUpdate!: (value: boolean) => void
    vi.mocked(updateUser).mockReturnValue(new Promise(resolve => { resolveUpdate = resolve }))
    const wrapper = mountPage()
    await flushPromises()
    const role = wrapper.get('[data-user-id="8"] [data-action="change-role"]')
    await role.setValue('admin')

    vi.mocked(listUsers).mockResolvedValueOnce({
      records: [{ id: 8, userAccount: 'other', userName: '刷新后的用户', userAvatar: '', userProfile: '', userRole: 'user', createTime: '' }],
      total: 1, size: 10, current: 1, pages: 1,
    })
    await (wrapper.vm as any).fetchUsers()
    await flushPromises()
    expect((wrapper.get('[data-user-id="8"] select').element as HTMLSelectElement).value).toBe('admin')
    resolveUpdate(true)
    await flushPromises()
    expect((wrapper.get('[data-user-id="8"] select').element as HTMLSelectElement).value).toBe('admin')
    expect(wrapper.text()).toContain('刷新后的用户')
  })

  it('recovers an out-of-range empty page using server metadata', async () => {
    const wrapper = mountPage()
    await flushPromises()
    vi.mocked(listUsers)
      .mockResolvedValueOnce({ records: [], total: 11, size: 10, current: 3, pages: 2 })
      .mockResolvedValueOnce({ records: [{ id: 8, userAccount: 'last', userName: '末页', userAvatar: '', userProfile: '', userRole: 'user', createTime: '' }], total: 11, size: 10, current: 2, pages: 2 })
    ;(wrapper.vm as any).currentPage = 3
    await (wrapper.vm as any).fetchUsers()
    await flushPromises()
    expect(listUsers).toHaveBeenLastCalledWith(expect.objectContaining({ pageNum: 2 }))
    expect(wrapper.text()).toContain('第 2 / 2 页')
    expect(wrapper.text()).toContain('last')
  })
})
