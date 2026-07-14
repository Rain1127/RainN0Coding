import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { deployApp, getAppVO } from '@/api/app'
import { getChatHistory } from '@/api/chatHistory'
import { useGenerationStore } from '@/stores/generation'
import type { ChatHistory } from '@/types/chat'
import ChatDetail from './ChatDetail.vue'

const generationState = vi.hoisted(() => ({
  status: 'idle' as string,
  phase: null as string | null,
  events: [] as Array<Record<string, unknown>>,
  files: [] as Array<{ path: string; language: string; size?: number | string }>,
  error: null as string | null,
  start: vi.fn(),
  cancel: vi.fn(),
  reset: vi.fn(),
}))

vi.mock('@/api/app', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/app')>()
  return { ...actual, getAppVO: vi.fn(), deployApp: vi.fn() }
})
vi.mock('@/api/chatHistory', () => ({ getChatHistory: vi.fn() }))
vi.mock('@/stores/generation', async () => {
  const { reactive } = await import('vue')
  const state = reactive(generationState)
  return { useGenerationStore: () => state }
})

const mockedGeneration = useGenerationStore()
const mountedWrappers: Array<{ unmount: () => void; exists: () => boolean }> = []
const originalCreateObjectURL = URL.createObjectURL
const originalRevokeObjectURL = URL.revokeObjectURL

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
const appB = { ...app, id: 8, appName: '项目 B' }

function page(records: ChatHistory[] = []) {
  return { records, total: records.length, size: 100, current: 1, pages: records.length ? 1 : 0 }
}

async function mountPage(initialPrompt?: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/chat/:appId', name: 'ChatDetail', component: ChatDetail }],
  })
  await router.push({
    name: 'ChatDetail',
    params: { appId: 7 },
    state: initialPrompt ? { initialPrompt } : {},
  })
  await router.isReady()
  const wrapper = mount(ChatDetail, {
    global: {
      plugins: [createPinia(), router],
      stubs: { ChatLayout: { template: '<main><slot /></main>' } },
    },
  })
  mountedWrappers.push(wrapper)
  return { router, wrapper }
}

describe('ChatDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Object.assign(generationState, {
      status: 'idle',
      phase: null,
      events: [],
      files: [],
      error: null,
    })
    vi.mocked(getAppVO).mockResolvedValue(app)
    vi.mocked(getChatHistory).mockResolvedValue(page())
    generationState.start.mockResolvedValue(undefined)
    generationState.cancel.mockImplementation(() => {
      mockedGeneration.status = 'cancelled'
    })
    generationState.reset.mockImplementation(() => {
      Object.assign(mockedGeneration, {
        status: 'idle',
        phase: null,
        events: [],
        files: [],
        error: null,
      })
    })
  })

  afterEach(() => {
    for (const wrapper of mountedWrappers.splice(0)) {
      if (wrapper.exists()) wrapper.unmount()
    }
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    Object.defineProperties(URL, {
      createObjectURL: { configurable: true, value: originalCreateObjectURL },
      revokeObjectURL: { configurable: true, value: originalRevokeObjectURL },
    })
  })

  it('loads app and history in parallel and starts a route-state prompt once after app loads', async () => {
    let resolveApp!: (value: typeof app) => void
    let resolveHistory!: (value: ReturnType<typeof page>) => void
    vi.mocked(getAppVO).mockImplementation(() => new Promise((resolve) => { resolveApp = resolve }))
    vi.mocked(getChatHistory).mockImplementation(() => new Promise((resolve) => { resolveHistory = resolve }))

    const { router, wrapper } = await mountPage('  生成销售看板  ')
    expect(getAppVO).toHaveBeenCalledWith(7)
    expect(getChatHistory).toHaveBeenCalledWith(7, 100)
    expect(generationState.start).not.toHaveBeenCalled()

    resolveApp(app)
    await flushPromises()
    expect(generationState.start).toHaveBeenCalledTimes(1)
    expect(generationState.start).toHaveBeenCalledWith(7, '生成销售看板', { preserve: false })
    expect(router.options.history.state.initialPrompt).toBeUndefined()

    await wrapper.vm.$forceUpdate()
    expect(generationState.start).toHaveBeenCalledTimes(1)
    resolveHistory(page())
    await flushPromises()
    expect(router.currentRoute.value.params.appId).toBe('7')
  })

  it('renders history and event messages as escaped plain text', async () => {
    vi.mocked(getChatHistory).mockResolvedValue(page([{
      id: 1,
      appId: 7,
      userId: 1,
      messageType: 'user',
      message: '<img src=x onerror=alert(1)>',
      createTime: '2026-07-14T01:00:00Z',
    }]))
    const { wrapper } = await mountPage()
    await flushPromises()
    mockedGeneration.events = [{ type: 'phase_start', phase: 'coder', message: '<script>alert(1)</script>' }]
    await flushPromises()

    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.text()).toContain('<img src=x onerror=alert(1)>')
    expect(wrapper.text()).toContain('<script>alert(1)</script>')
  })

  it('keeps successful history visible when the app request fails and retries only that request', async () => {
    vi.mocked(getAppVO).mockRejectedValueOnce(new Error('app offline')).mockResolvedValueOnce(app)
    vi.mocked(getChatHistory).mockResolvedValue(page([{
      id: 1,
      appId: 7,
      userId: 1,
      messageType: 'user',
      message: '保留的需求',
      createTime: '2026-07-14T01:00:00Z',
    }]))

    const { wrapper } = await mountPage()
    await flushPromises()
    expect(wrapper.text()).toContain('保留的需求')
    expect(wrapper.get('[data-error="app"]').attributes('role')).toBe('alert')

    await wrapper.get('[data-retry="app"]').trigger('click')
    await flushPromises()
    expect(getAppVO).toHaveBeenCalledTimes(2)
    expect(getChatHistory).toHaveBeenCalledTimes(1)
  })

  it('consumes the initial prompt after an app retry succeeds and only starts once', async () => {
    vi.mocked(getAppVO).mockRejectedValueOnce(new Error('app offline')).mockResolvedValueOnce(app)
    const { router, wrapper } = await mountPage('  retry this prompt  ')
    await flushPromises()

    expect(generationState.start).not.toHaveBeenCalled()
    expect(router.options.history.state.initialPrompt).toBe('  retry this prompt  ')

    await wrapper.get('[data-retry="app"]').trigger('click')
    await flushPromises()

    expect(generationState.start).toHaveBeenCalledTimes(1)
    expect(generationState.start).toHaveBeenCalledWith(7, 'retry this prompt', { preserve: false })
    expect(router.options.history.state.initialPrompt).toBeUndefined()
    await wrapper.vm.$forceUpdate()
    await flushPromises()
    expect(generationState.start).toHaveBeenCalledTimes(1)
  })

  it('reloads isolated state when the reused route changes and consumes the new route prompt', async () => {
    vi.mocked(getAppVO).mockImplementation(async (id) => id === 7 ? app : appB)
    const { router, wrapper } = await mountPage()
    await flushPromises()
    vi.clearAllMocks()
    vi.mocked(getAppVO).mockImplementation(async (id) => id === 7 ? app : appB)
    vi.mocked(getChatHistory).mockResolvedValue(page())
    mockedGeneration.status = 'running'

    await router.push({
      name: 'ChatDetail',
      params: { appId: 8 },
      state: { initialPrompt: 'build project B' },
    })
    await flushPromises()

    expect(generationState.cancel).toHaveBeenCalledTimes(1)
    expect(generationState.reset).toHaveBeenCalledTimes(1)
    expect(getAppVO).toHaveBeenCalledWith(8)
    expect(getChatHistory).toHaveBeenCalledWith(8, 100)
    expect(wrapper.text()).toContain('项目 B')
    expect(wrapper.text()).not.toContain('销售看板')
    expect(generationState.start).toHaveBeenCalledWith(8, 'build project B', { preserve: false })
    expect(router.options.history.state.initialPrompt).toBeUndefined()
  })

  it('cancels and clears a global generation immediately on first entry', async () => {
    Object.assign(mockedGeneration, {
      status: 'running',
      phase: 'code',
      events: [{ type: 'phase_start', phase: 'code', message: 'stale event' }],
      files: [{ path: 'stale.ts', language: 'typescript' }],
      error: 'stale error',
    })

    const { wrapper } = await mountPage()
    await flushPromises()

    expect(generationState.cancel).toHaveBeenCalledTimes(1)
    expect(generationState.reset).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).not.toContain('stale event')
    expect(mockedGeneration.events).toEqual([])
    expect(mockedGeneration.files).toEqual([])
    expect(mockedGeneration.error).toBeNull()
  })

  it('cancels active generation and retries the last prompt without clearing progress', async () => {
    vi.mocked(getChatHistory).mockResolvedValue(page([{
      id: 1,
      appId: 7,
      userId: 1,
      messageType: 'user',
      message: '创建看板',
      createTime: '2026-07-14T01:00:00Z',
    }]))
    const { wrapper } = await mountPage()
    await flushPromises()
    mockedGeneration.status = 'running'
    await flushPromises()
    vi.mocked(generationState.cancel).mockClear()

    await wrapper.get('[data-action="cancel-generation"]').trigger('click')
    expect(generationState.cancel).toHaveBeenCalledTimes(1)

    mockedGeneration.status = 'failed'
    mockedGeneration.error = '模型暂时不可用'
    await flushPromises()
    await wrapper.get('[data-action="retry-generation"]').trigger('click')
    expect(generationState.start).toHaveBeenLastCalledWith(7, '创建看板', { preserve: true })
  })

  it('only links safe deployment URLs and blocks repeated deploy requests', async () => {
    let resolveDeploy!: (value: string) => void
    vi.mocked(deployApp).mockImplementation(() => new Promise((resolve) => { resolveDeploy = resolve }))
    const { wrapper } = await mountPage()
    await flushPromises()

    const deploy = wrapper.get('[data-action="deploy"]')
    await Promise.all([deploy.trigger('click'), deploy.trigger('click')])
    expect(deployApp).toHaveBeenCalledTimes(1)
    resolveDeploy('javascript:alert(1)')
    await flushPromises()
    expect(wrapper.find('[data-deploy-url] a').exists()).toBe(false)
    expect(wrapper.get('[data-deploy-url]').text()).toContain('不安全')

    vi.mocked(deployApp).mockResolvedValue('https://preview.example/app')
    await deploy.trigger('click')
    await flushPromises()
    const link = wrapper.get('[data-deploy-url] a')
    expect(link.attributes()).toMatchObject({
      href: 'https://preview.example/app',
      target: '_blank',
      rel: 'noopener noreferrer',
    })
    expect(link.text()).toContain('打开已部署应用')
    expect(getAppVO).toHaveBeenCalledTimes(3)
  })

  it('keeps a new app deploy pending when the stale app deploy settles', async () => {
    let resolveDeployA!: (value: string) => void
    let resolveDeployB!: (value: string) => void
    vi.mocked(getAppVO).mockImplementation(async (id) => id === 7 ? app : appB)
    vi.mocked(deployApp)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveDeployA = resolve }))
      .mockImplementationOnce(() => new Promise((resolve) => { resolveDeployB = resolve }))
    const { router, wrapper } = await mountPage()
    await flushPromises()

    await wrapper.get('[data-action="deploy"]').trigger('click')
    await router.push({ name: 'ChatDetail', params: { appId: 8 } })
    await flushPromises()
    await wrapper.get('[data-action="deploy"]').trigger('click')

    resolveDeployA('https://preview.example/a')
    await flushPromises()
    expect((wrapper.get('[data-action="deploy"]').element as HTMLButtonElement).disabled).toBe(true)
    expect(wrapper.find('[data-deploy-url]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('preview.example/a')

    resolveDeployB('https://preview.example/b')
    await flushPromises()
    expect((wrapper.get('[data-action="deploy"]').element as HTMLButtonElement).disabled).toBe(false)
    expect(wrapper.get('[data-deploy-url] a').attributes('href')).toBe('https://preview.example/b')
  })

  it('downloads through the real endpoint once and revokes the object URL', async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const createObjectURL = vi.fn(() => 'blob:download')
    const revokeObjectURL = vi.fn()
    Object.defineProperties(URL, {
      createObjectURL: { configurable: true, value: createObjectURL },
      revokeObjectURL: { configurable: true, value: revokeObjectURL },
    })
    let resolveFetch!: (value: Response) => void
    vi.stubGlobal('fetch', vi.fn(() => new Promise((resolve) => { resolveFetch = resolve })))
    const { wrapper } = await mountPage()
    await flushPromises()

    const download = wrapper.get('[data-action="download"]')
    await Promise.all([download.trigger('click'), download.trigger('click')])
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(fetch).toHaveBeenCalledWith('/api/app/download/7', { credentials: 'include' })
    resolveFetch(new Response(new Blob(['zip']), {
      status: 200,
      headers: {
        'Content-Type': 'application/zip',
        'Content-Disposition': 'attachment; filename="7.zip"',
      },
    }))
    await flushPromises()
    expect(click).toHaveBeenCalledTimes(1)
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:download')
  })

  it('shows a JSON business error instead of downloading an HTTP 200 response', async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const createObjectURL = vi.fn(() => 'blob:should-not-exist')
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      code: 40000,
      message: '应用代码不存在，请先生成代码',
      data: null,
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json;charset=UTF-8' },
    })))
    const { wrapper } = await mountPage()
    await flushPromises()

    await wrapper.get('[data-action="download"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('应用代码不存在，请先生成代码')
    expect(createObjectURL).not.toHaveBeenCalled()
    expect(click).not.toHaveBeenCalled()
  })

  it('does not let a stale download blob clear or act on the new app download', async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const createObjectURL = vi.fn(() => 'blob:download-b')
    const revokeObjectURL = vi.fn()
    Object.defineProperties(URL, {
      createObjectURL: { configurable: true, value: createObjectURL },
      revokeObjectURL: { configurable: true, value: revokeObjectURL },
    })
    let resolveBlobA!: (value: Blob) => void
    let resolveBlobB!: (value: Blob) => void
    const blobA = vi.fn(() => new Promise<Blob>((resolve) => { resolveBlobA = resolve }))
    const blobB = vi.fn(() => new Promise<Blob>((resolve) => { resolveBlobB = resolve }))
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'Content-Type': 'application/zip' }),
        blob: blobA,
      })
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'Content-Type': 'application/zip' }),
        blob: blobB,
      }))
    vi.mocked(getAppVO).mockImplementation(async (id) => id === 7 ? app : appB)
    const { router, wrapper } = await mountPage()
    await flushPromises()

    await wrapper.get('[data-action="download"]').trigger('click')
    await flushPromises()
    expect(blobA).toHaveBeenCalledTimes(1)
    await router.push({ name: 'ChatDetail', params: { appId: 8 } })
    await flushPromises()
    await wrapper.get('[data-action="download"]').trigger('click')
    await flushPromises()
    expect(blobB).toHaveBeenCalledTimes(1)

    resolveBlobA(new Blob(['stale-a']))
    await flushPromises()
    expect(createObjectURL).not.toHaveBeenCalled()
    expect(click).not.toHaveBeenCalled()
    expect((wrapper.get('[data-action="download"]').element as HTMLButtonElement).disabled).toBe(true)

    resolveBlobB(new Blob(['current-b']))
    await flushPromises()
    expect(createObjectURL).toHaveBeenCalledTimes(1)
    expect(click).toHaveBeenCalledTimes(1)
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:download-b')
    expect((wrapper.get('[data-action="download"]').element as HTMLButtonElement).disabled).toBe(false)
  })

  it('invalidates pending operations and generation before unmount completes', async () => {
    let resolveDeploy!: (value: string) => void
    let resolveBlob!: (value: Blob) => void
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const createObjectURL = vi.fn(() => 'blob:stale-unmount')
    const revokeObjectURL = vi.fn()
    Object.defineProperties(URL, {
      createObjectURL: { configurable: true, value: createObjectURL },
      revokeObjectURL: { configurable: true, value: revokeObjectURL },
    })
    vi.mocked(deployApp).mockImplementation(() => new Promise((resolve) => { resolveDeploy = resolve }))
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      headers: new Headers({ 'Content-Type': 'application/zip' }),
      blob: () => new Promise<Blob>((resolve) => { resolveBlob = resolve }),
    }))
    const { wrapper } = await mountPage()
    await flushPromises()
    await wrapper.get('[data-action="deploy"]').trigger('click')
    await wrapper.get('[data-action="download"]').trigger('click')
    await flushPromises()
    mockedGeneration.status = 'running'
    vi.clearAllMocks()

    wrapper.unmount()
    resolveDeploy('https://preview.example/stale')
    resolveBlob(new Blob(['stale']))
    await flushPromises()

    expect(generationState.cancel).toHaveBeenCalledTimes(1)
    expect(generationState.reset).toHaveBeenCalledTimes(1)
    expect(createObjectURL).not.toHaveBeenCalled()
    expect(click).not.toHaveBeenCalled()
    expect(revokeObjectURL).not.toHaveBeenCalled()
  })
})
