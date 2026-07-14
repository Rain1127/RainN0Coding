import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { getAppVO } from '@/api/app'
import { getChatHistory } from '@/api/chatHistory'
import { useChatStore } from './chat'

vi.mock('@/api/app', () => ({ getAppVO: vi.fn() }))
vi.mock('@/api/chatHistory', () => ({ getChatHistory: vi.fn() }))

const app = {
  id: 7,
  appName: '销售看板',
  cover: '',
  initPrompt: '',
  codeGenType: 'vue_project' as const,
  deployKey: '',
  deployedTime: '',
  priority: 0,
  userId: 1,
  currentVersion: 1,
  createTime: '',
  updateTime: '',
  editTime: '',
}

describe('chat store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('tracks application and history loading independently', async () => {
    let releaseApp!: () => void
    let releaseHistory!: () => void
    vi.mocked(getAppVO).mockImplementation(() => new Promise((resolve) => {
      releaseApp = () => resolve(app)
    }))
    vi.mocked(getChatHistory).mockImplementation(() => new Promise((resolve) => {
      releaseHistory = () => resolve({ records: [], total: 0, size: 100, current: 1, pages: 0 })
    }))
    const store = useChatStore()

    const appRequest = store.loadAppDetail(7)
    const historyRequest = store.loadHistory(7)
    expect(store.appLoading).toBe(true)
    expect(store.historyLoading).toBe(true)

    releaseApp()
    await appRequest
    expect(store.appLoading).toBe(false)
    expect(store.historyLoading).toBe(true)

    releaseHistory()
    await historyRequest
    expect(store.historyLoading).toBe(false)
  })

  it('retains existing messages when history refresh fails', async () => {
    vi.mocked(getChatHistory).mockRejectedValue(new Error('offline'))
    const store = useChatStore()
    store.addMessage({ id: 'existing', role: 'user', content: '保留我', timestamp: 1 })

    await expect(store.loadHistory(7)).rejects.toThrow('offline')

    expect(store.messages.map((message) => message.content)).toEqual(['保留我'])
    expect(store.historyError).toBeTruthy()
  })

  it('keeps app and history errors separate and supports targeted retry', async () => {
    vi.mocked(getAppVO).mockRejectedValueOnce(new Error('app failed')).mockResolvedValueOnce(app)
    vi.mocked(getChatHistory).mockResolvedValue({ records: [], total: 0, size: 100, current: 1, pages: 0 })
    const store = useChatStore()

    await expect(store.loadAppDetail(7)).rejects.toThrow('app failed')
    expect(store.appError).toBeTruthy()
    expect(store.historyError).toBeNull()

    await store.loadAppDetail(7)
    expect(store.currentApp).toEqual(app)
    expect(store.appError).toBeNull()
  })

  it('clears the previous app immediately and ignores stale app and history responses', async () => {
    const historyPage = (appId: number, message: string) => ({
      records: [{
        id: appId,
        appId,
        userId: 1,
        messageType: 'user' as const,
        message,
        createTime: '2026-07-14T01:00:00Z',
      }],
      total: 1,
      size: 100,
      current: 1,
      pages: 1,
    })
    let resolveAppA!: (value: typeof app) => void
    let resolveAppB!: (value: typeof app) => void
    let resolveHistoryA!: (value: ReturnType<typeof historyPage>) => void
    let resolveHistoryB!: (value: ReturnType<typeof historyPage>) => void
    const appB = { ...app, id: 8, appName: '项目 B' }
    vi.mocked(getAppVO).mockImplementation((id) => new Promise((resolve) => {
      if (id === 7) resolveAppA = resolve
      else resolveAppB = resolve
    }))
    vi.mocked(getChatHistory).mockImplementation((id) => new Promise((resolve) => {
      if (id === 7) resolveHistoryA = resolve
      else resolveHistoryB = resolve
    }))
    const store = useChatStore()

    store.resetForApp(7)
    const appRequestA = store.loadAppDetail(7)
    const historyRequestA = store.loadHistory(7)
    store.addMessage({ id: 'local-a', role: 'user', content: 'A local', timestamp: 1 })

    store.resetForApp(8)
    expect(store.currentApp).toBeNull()
    expect(store.messages).toEqual([])
    const appRequestB = store.loadAppDetail(8)
    const historyRequestB = store.loadHistory(8)

    resolveAppA(app)
    resolveHistoryA(historyPage(7, 'A history'))
    await Promise.all([appRequestA, historyRequestA])
    expect(store.currentApp).toBeNull()
    expect(store.messages).toEqual([])

    resolveAppB(appB)
    resolveHistoryB(historyPage(8, 'B history'))
    await Promise.all([appRequestB, historyRequestB])
    expect(store.currentApp?.id).toBe(8)
    expect(store.messages.map((message) => message.content)).toEqual(['B history'])
  })
})
