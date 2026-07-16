import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { deleteApp, listMyApps } from '@/api/app'
import type { AppVO } from '@/types/app'
import { useAppsStore } from './apps'

vi.mock('@/api/app', () => ({
  deleteApp: vi.fn(),
  listMyApps: vi.fn(),
}))

function app(id: number, deployKey = ''): AppVO {
  return {
    id,
    appName: `项目 ${id}`,
    cover: '',
    initPrompt: '',
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

function page(records: AppVO[], current = 1, size = 12, total = records.length) {
  return { records, current, size, total, pages: Math.ceil(total / size) }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, reject, resolve }
}

describe('apps store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('loads a server-backed page using the trimmed app name', async () => {
    vi.mocked(listMyApps).mockResolvedValue(page([app(1)], 2, 12, 31))
    const store = useAppsStore()
    store.pageNum = 2
    store.keyword = '  看板  '

    await store.fetchMyApps()

    expect(listMyApps).toHaveBeenCalledWith({
      pageNum: 2,
      pageSize: 12,
      sortField: 'editTime',
      sortOrder: 'descend',
      appName: '看板',
    })
    expect(store.appList.map(item => item.id)).toEqual([1])
    expect(store.total).toBe(31)
    expect(store.error).toBe('')
  })

  it('sends the real code generation type as a server-side filter', async () => {
    vi.mocked(listMyApps).mockResolvedValue(page([app(3)]))
    const store = useAppsStore()

    await store.fetchMyApps({ codeGenType: 'java' })

    expect(store.codeGenType).toBe('java')
    expect(listMyApps).toHaveBeenCalledWith(expect.objectContaining({ codeGenType: 'java' }))
    expect(listMyApps).toHaveBeenCalledWith(expect.not.objectContaining({ status: expect.anything() }))
  })

  it('reads the real MyBatis-Flex Page field names returned by Java', async () => {
    vi.mocked(listMyApps).mockResolvedValue({
      records: [app(9)],
      pageNumber: 3,
      pageSize: 20,
      totalRow: 49,
      totalPage: 3,
    } as never)
    const store = useAppsStore()

    await store.fetchMyApps({ pageNum: 3, pageSize: 20 })

    expect(store.pageNum).toBe(3)
    expect(store.pageSize).toBe(20)
    expect(store.total).toBe(49)
    expect(store.appList.map(item => item.id)).toEqual([9])
  })

  it('keeps the latest request result when responses arrive out of order', async () => {
    const first = deferred<ReturnType<typeof page>>()
    const second = deferred<ReturnType<typeof page>>()
    vi.mocked(listMyApps)
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)
    const store = useAppsStore()

    const firstRequest = store.fetchMyApps({ keyword: '旧查询' })
    const secondRequest = store.fetchMyApps({ keyword: '新查询' })
    second.resolve(page([app(2)]))
    await secondRequest
    first.resolve(page([app(1)]))
    await firstRequest

    expect(store.keyword).toBe('新查询')
    expect(store.appList.map(item => item.id)).toEqual([2])
    expect(store.loading).toBe(false)
  })

  it('filters deployment status from real deploy metadata without inventing an API field', async () => {
    vi.mocked(listMyApps).mockResolvedValue(page([app(1, 'deployed-key'), app(2)]))
    const store = useAppsStore()
    await store.fetchMyApps()

    store.status = 'deployed'
    expect(store.visibleApps.map(item => item.id)).toEqual([1])
    store.status = 'undeployed'
    expect(store.visibleApps.map(item => item.id)).toEqual([2])
    expect(listMyApps).toHaveBeenLastCalledWith(expect.not.objectContaining({ status: expect.anything() }))
  })

  it('exposes a retryable error without replacing the last successful list', async () => {
    vi.mocked(listMyApps)
      .mockResolvedValueOnce(page([app(1)]))
      .mockRejectedValueOnce(new Error('offline'))
    const store = useAppsStore()
    await store.fetchMyApps()

    await expect(store.fetchMyApps()).rejects.toThrow('offline')

    expect(store.appList.map(item => item.id)).toEqual([1])
    expect(store.error).toBe('项目加载失败，请稍后重试。')
  })

  it('deletes through the real API and updates the current page summary', async () => {
    vi.mocked(listMyApps).mockResolvedValue(page([app(1), app(2)], 1, 12, 2))
    vi.mocked(deleteApp).mockResolvedValue(true)
    const store = useAppsStore()
    await store.fetchMyApps()

    await store.deleteProject(1)

    expect(deleteApp).toHaveBeenCalledWith({ id: 1 })
    expect(store.appList.map(item => item.id)).toEqual([2])
    expect(store.total).toBe(1)
  })
})
