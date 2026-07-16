import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp } from '@/api/app'
import PromptComposer from '@/components/generation/PromptComposer.vue'
import { useAppsStore } from '@/stores/apps'
import ChatHome from './ChatHome.vue'

vi.mock('@/api/app', () => ({ createApp: vi.fn() }))

function healthResponse(ok = true) {
  return Promise.resolve({ ok, json: async () => ({ code: ok ? 0 : 500 }) } as Response)
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(res => { resolve = res })
  return { promise, resolve }
}

async function mountHome() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const apps = useAppsStore()
  vi.spyOn(apps, 'fetchRecentApps').mockResolvedValue()

  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'Home', component: ChatHome },
      { path: '/chat/:appId', name: 'ChatDetail', component: { template: '<div />' } },
      { path: '/projects', name: 'Projects', component: { template: '<div />' } },
    ],
  })
  await router.push('/')
  await router.isReady()
  const wrapper = mount(ChatHome, {
    global: {
      plugins: [pinia, router],
      stubs: { ChatLayout: { template: '<div><slot /></div>' } },
    },
  })
  await flushPromises()
  return { apps, router, wrapper }
}

describe('ChatHome', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(() => healthResponse()))
  })

  it('creates once and carries only the initial prompt in navigation state', async () => {
    let resolveCreate!: (value: number) => void
    vi.mocked(createApp).mockReturnValue(new Promise(resolve => { resolveCreate = resolve }))
    const { router, wrapper } = await mountHome()
    const push = vi.spyOn(router, 'push')
    const composer = wrapper.getComponent(PromptComposer)

    composer.vm.$emit('submit', '生成销售看板')
    composer.vm.$emit('submit', '生成销售看板')
    await flushPromises()
    expect(createApp).toHaveBeenCalledTimes(1)
    resolveCreate(42)
    await flushPromises()

    expect(createApp).toHaveBeenCalledWith({ initPrompt: '生成销售看板' })
    expect(push).toHaveBeenCalledWith({
      name: 'ChatDetail',
      params: { appId: 42 },
      state: { initialPrompt: '生成销售看板' },
    })
  })

  it('retries navigation after a route failure without creating a duplicate app', async () => {
    vi.mocked(createApp).mockResolvedValue(42)
    const { router, wrapper } = await mountHome()
    const push = vi.spyOn(router, 'push')
      .mockRejectedValueOnce(new Error('route failed'))
      .mockResolvedValueOnce(undefined as never)

    wrapper.getComponent(PromptComposer).vm.$emit('submit', '生成销售看板')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('项目已创建，但工作台暂时无法打开')
    await wrapper.get('[data-action="retry-create"]').trigger('click')
    await flushPromises()

    expect(createApp).toHaveBeenCalledTimes(1)
    expect(push).toHaveBeenCalledTimes(2)
  })

  it('keeps prompt entry available when either health check fails', async () => {
    vi.mocked(fetch)
      .mockRejectedValueOnce(new Error('java offline'))
      .mockRejectedValueOnce(new Error('python offline'))
    const { wrapper } = await mountHome()

    expect(wrapper.text()).toContain('Java 服务')
    expect(wrapper.text()).toContain('Python 服务')
    expect(wrapper.findAll('.service-status--offline')).toHaveLength(2)
    expect(wrapper.getComponent(PromptComposer).props('loading')).toBe(false)
  })

  it('keeps the newest health result when an older check finishes last', async () => {
    const oldJava = deferred<Response>()
    const oldPython = deferred<Response>()
    vi.mocked(fetch)
      .mockReturnValueOnce(oldJava.promise)
      .mockReturnValueOnce(oldPython.promise)
      .mockResolvedValueOnce({ ok: true } as Response)
      .mockResolvedValueOnce({ ok: false } as Response)
    const { wrapper } = await mountHome()

    await wrapper.get('.home-section__link--button').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.service-status--online')).toHaveLength(1)
    expect(wrapper.findAll('.service-status--offline')).toHaveLength(1)

    oldJava.resolve({ ok: false } as Response)
    oldPython.resolve({ ok: true } as Response)
    await flushPromises()

    const statuses = wrapper.findAll('.service-status')
    expect(statuses[0]?.classes()).toContain('service-status--online')
    expect(statuses[1]?.classes()).toContain('service-status--offline')
  })

  it('does not commit a pending health result after unmount', async () => {
    const java = deferred<Response>()
    const python = deferred<Response>()
    vi.mocked(fetch)
      .mockReturnValueOnce(java.promise)
      .mockReturnValueOnce(python.promise)
    const { wrapper } = await mountHome()
    const viewModel = wrapper.vm as unknown as { javaStatus: string; pythonStatus: string }

    expect(viewModel.javaStatus).toBe('checking')
    wrapper.unmount()
    java.resolve({ ok: true } as Response)
    python.resolve({ ok: true } as Response)
    await flushPromises()

    expect(viewModel.javaStatus).toBe('checking')
    expect(viewModel.pythonStatus).toBe('checking')
  })
})
