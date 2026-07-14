import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { listMyApps } from '@/api/app'
import ProjectCard from '@/components/projects/ProjectCard.vue'
import ProjectListToolbar from '@/components/projects/ProjectListToolbar.vue'
import { useAppsStore } from '@/stores/apps'
import type { AppVO } from '@/types/app'
import ProjectsPage from './ProjectsPage.vue'

vi.mock('@/api/app', () => ({
  deleteApp: vi.fn(),
  listMyApps: vi.fn(),
}))

function project(id = 1, deployKey = ''): AppVO {
  return {
    id,
    appName: `项目 ${id}`,
    cover: '',
    initPrompt: '生成一个项目',
    codeGenType: 'vue_project',
    deployKey,
    deployedTime: deployKey ? '2026-07-14T10:00:00' : '',
    priority: 0,
    userId: 1,
    currentVersion: 1,
    createTime: '2026-07-13T10:00:00',
    updateTime: '2026-07-14T10:00:00',
    editTime: '2026-07-14T10:00:00',
  }
}

async function mountPage(
  configure?: (store: ReturnType<typeof useAppsStore>) => void,
  initialPath = '/projects',
  stubFetch = true,
) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useAppsStore()
  configure?.(store)
  const fetchMyApps = vi.spyOn(store, 'fetchMyApps')
  if (stubFetch) fetchMyApps.mockResolvedValue()
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/projects', component: ProjectsPage },
      { path: '/chat/:appId', component: { template: '<div />' } },
    ],
  })
  await router.push(initialPath)
  await router.isReady()
  const wrapper = mount(ProjectsPage, {
    global: {
      plugins: [pinia, router],
      stubs: { ChatLayout: { template: '<div><slot /></div>' } },
    },
  })
  await flushPromises()
  return { fetchMyApps, router, store, wrapper }
}

describe('ProjectsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('distinguishes an empty account from an empty server search', async () => {
    const empty = await mountPage(store => {
      store.total = 0
      store.keyword = ''
    })
    expect(empty.wrapper.text()).toContain('还没有项目')
    empty.wrapper.unmount()

    const noSearchResult = await mountPage(store => {
      store.total = 0
    }, '/projects?keyword=数据看板')
    expect(noSearchResult.wrapper.text()).toContain('没有找到匹配项目')
    expect(noSearchResult.wrapper.text()).not.toContain('还没有项目')
  })

  it('does not present a current-page deployment mismatch as a globally empty account', async () => {
    const { store, wrapper } = await mountPage(store => {
      store.appList = [project(1)]
      store.total = 24
    }, '/projects?status=deployed')

    expect(store.visibleApps).toHaveLength(0)
    expect(wrapper.text()).toContain('当前页没有已部署项目')
    expect(wrapper.text()).not.toContain('还没有项目')
  })

  it('shows loading skeletons and a retryable request error', async () => {
    const loading = await mountPage(store => { store.loading = true })
    expect(loading.wrapper.get('[aria-busy="true"]').findAll('.project-card-skeleton')).toHaveLength(6)
    loading.wrapper.unmount()

    const failed = await mountPage(store => { store.error = '项目加载失败，请稍后重试。' })
    failed.fetchMyApps.mockClear()
    expect(failed.wrapper.get('[role="alert"]').text()).toContain('项目加载失败')
    await failed.wrapper.get('[role="alert"] button').trigger('click')
    expect(failed.fetchMyApps).toHaveBeenCalledTimes(1)
  })

  it('keeps the last successful page visible when refresh fails and clears the error after retry', async () => {
    vi.mocked(listMyApps)
      .mockResolvedValueOnce({
        records: [project(8)],
        current: 1,
        size: 12,
        total: 25,
        pages: 3,
      })
      .mockRejectedValueOnce(new Error('refresh failed'))
      .mockResolvedValueOnce({
        records: [project(8)],
        current: 1,
        size: 12,
        total: 25,
        pages: 3,
      })
    const { store, wrapper } = await mountPage(undefined, '/projects?keyword=项目', false)
    await flushPromises()

    await expect(store.fetchMyApps()).rejects.toThrow('refresh failed')
    await flushPromises()

    expect(wrapper.findAllComponents(ProjectCard)).toHaveLength(1)
    expect(wrapper.get('[role="alert"]').text()).toContain('项目加载失败')
    expect(wrapper.find('[data-action="next-page"]').exists()).toBe(true)
    await wrapper.get('[data-action="retry-projects"]').trigger('click')
    await flushPromises()

    expect(wrapper.findAllComponents(ProjectCard)).toHaveLength(1)
    expect(store.error).toBe('')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('requests a server page and preserves the current keyword', async () => {
    const { fetchMyApps, wrapper } = await mountPage(store => {
      store.appList = [project(1)]
      store.total = 25
      store.pageNum = 1
      store.pageSize = 12
    }, '/projects?keyword=看板')
    fetchMyApps.mockClear()

    await wrapper.get('[data-action="next-page"]').trigger('click')
    await flushPromises()

    expect(fetchMyApps).toHaveBeenCalledWith({ pageNum: 2, keyword: '看板' })
  })

  it('restores filters from the URL and keeps new searches deep-linkable', async () => {
    const { fetchMyApps, router, store, wrapper } = await mountPage(
      current => {
        current.appList = [project(1, 'deployed-key')]
        current.total = 25
      },
      '/projects?page=2&keyword=数据看板&type=java&status=deployed',
    )

    expect(store.pageNum).toBe(2)
    expect(store.keyword).toBe('数据看板')
    expect(store.codeGenType).toBe('java')
    expect(store.status).toBe('deployed')
    expect(fetchMyApps).toHaveBeenCalledWith({ pageNum: 2, keyword: '数据看板', codeGenType: 'java' })

    wrapper.getComponent(ProjectListToolbar).vm.$emit('search', '任务中心')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ keyword: '任务中心', type: 'java', status: 'deployed' })
  })

  it('clears the current-page status through URL synchronization', async () => {
    const { fetchMyApps, router, store, wrapper } = await mountPage(current => {
      current.appList = [project(1)]
      current.total = 12
    }, '/projects?status=deployed')
    fetchMyApps.mockClear()

    await wrapper.get('[data-action="clear-status"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.query).toEqual({})
    expect(store.status).toBe('all')
    expect(fetchMyApps).toHaveBeenCalledTimes(1)
  })

  it('replays browser query changes into the store and fetches exactly once', async () => {
    const { fetchMyApps, router, store } = await mountPage(current => {
      current.appList = [project(1)]
      current.total = 60
    })
    fetchMyApps.mockClear()

    await router.push('/projects?page=3&keyword=API&type=python&status=undeployed')
    await flushPromises()

    expect(store.pageNum).toBe(3)
    expect(store.keyword).toBe('API')
    expect(store.codeGenType).toBe('python')
    expect(store.status).toBe('undeployed')
    expect(fetchMyApps).toHaveBeenCalledTimes(1)
    expect(fetchMyApps).toHaveBeenCalledWith({ pageNum: 3, keyword: 'API', codeGenType: 'python' })
  })

  it('resets the page when the server-backed code type changes', async () => {
    const { fetchMyApps, router, store, wrapper } = await mountPage(current => {
      current.appList = [project(1)]
      current.total = 60
    }, '/projects?page=3')
    fetchMyApps.mockClear()

    wrapper.getComponent(ProjectListToolbar).vm.$emit('type-change', 'vue_project')
    await flushPromises()

    expect(router.currentRoute.value.query).toEqual({ type: 'vue_project' })
    expect(store.pageNum).toBe(1)
    expect(store.codeGenType).toBe('vue_project')
    expect(fetchMyApps).toHaveBeenCalledTimes(1)
    expect(fetchMyApps).toHaveBeenCalledWith({ pageNum: 1, keyword: '', codeGenType: 'vue_project' })
  })

  it('delegates a confirmed card deletion to the store once', async () => {
    const { store, wrapper } = await mountPage(store => {
      store.appList = [project(7)]
      store.total = 1
    })
    const deleteProject = vi.spyOn(store, 'deleteProject').mockResolvedValue()

    wrapper.getComponent(ProjectCard).vm.$emit('delete', 7)
    await flushPromises()

    expect(deleteProject).toHaveBeenCalledWith(7)
  })
})
