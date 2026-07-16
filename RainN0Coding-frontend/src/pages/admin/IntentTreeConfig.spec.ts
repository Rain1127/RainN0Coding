import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getIntentTree, resetIntentTree, saveIntentTree } from '@/api/intentConfig'
import IntentTreeConfig from './IntentTreeConfig.vue'

const routeLeave = vi.hoisted(() => ({ guard: undefined as undefined | (() => boolean) }))
vi.mock('vue-router', () => ({ onBeforeRouteLeave: (guard: () => boolean) => { routeLeave.guard = guard } }))
vi.mock('@/api/intentConfig', () => ({ getIntentTree: vi.fn(), resetIntentTree: vi.fn(), saveIntentTree: vi.fn() }))

function mountPage() {
  return mount(IntentTreeConfig, {
    attachTo: document.body,
    global: {
      stubs: {
        AdminLayout: { template: '<main><slot /></main>' },
        PageHeader: { template: '<header><h1>{{ title }}</h1><slot name="actions" /></header>', props: ['title'] },
      },
    },
  })
}

describe('IntentTreeConfig', () => {
  let wrapper: ReturnType<typeof mountPage> | undefined

  beforeEach(() => {
    document.body.innerHTML = ''
    routeLeave.guard = undefined
    vi.clearAllMocks()
    vi.mocked(getIntentTree).mockResolvedValue({ customized: true, treeJson: '[{"key":"root","title":"根节点"}]' })
    vi.mocked(saveIntentTree).mockResolvedValue(true)
    vi.mocked(resetIntentTree).mockResolvedValue(true)
  })
  afterEach(() => wrapper?.unmount())

  it('loads editable JSON and keeps save disabled until it changes', async () => {
    wrapper = mountPage()
    await flushPromises()

    expect((wrapper.get('textarea[aria-label="意图树 JSON"]').element as HTMLTextAreaElement).value).toContain('根节点')
    expect(wrapper.get('[data-action="save-intent-tree"]').attributes('disabled')).toBeDefined()
    await wrapper.get('textarea').setValue('[{"key":"new","title":"新节点"}]')
    expect(wrapper.get('[data-action="save-intent-tree"]').attributes('disabled')).toBeUndefined()
  })

  it('normalizes the backend empty default tree to an editable array', async () => {
    vi.mocked(getIntentTree).mockResolvedValueOnce({ customized: false, treeJson: '' })
    wrapper = mountPage()
    await flushPromises()

    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('[]')
    expect(wrapper.get('[data-action="save-intent-tree"]').attributes('disabled')).toBeDefined()
  })

  it('validates malformed and structurally invalid JSON locally without calling save', async () => {
    wrapper = mountPage()
    await flushPromises()

    await wrapper.get('textarea').setValue('{bad json')
    await wrapper.get('[data-action="save-intent-tree"]').trigger('click')
    expect(wrapper.get('[data-validation-error]').text()).toContain('JSON')
    expect(saveIntentTree).not.toHaveBeenCalled()
    await wrapper.get('textarea').setValue('[{"title":"缺少 key"}]')
    await wrapper.get('[data-action="save-intent-tree"]').trigger('click')
    expect(wrapper.get('[data-validation-error]').text()).toContain('key')
    expect(saveIntentTree).not.toHaveBeenCalled()
  })

  it('rejects duplicate keys and invalid optional DTO fields recursively', async () => {
    wrapper = mountPage()
    await flushPromises()
    const invalidTrees = [
      '[{"key":"same","title":"A"},{"key":"same","title":"B"}]',
      '[{"key":"a","title":"A","enabled":"yes"}]',
      '[{"key":"a","title":"A","examples":["ok",1]}]',
      '[{"key":"a","title":"A","sortOrder":"1"}]',
      '[{"key":"a","title":"A","children":[{"key":"b","title":"B","parentKey":2}]}]',
    ]
    for (const value of invalidTrees) {
      await wrapper.get('textarea').setValue(value)
      await wrapper.get('[data-action="save-intent-tree"]').trigger('click')
      expect(wrapper.get('[data-validation-error]').text()).not.toBe('')
    }
    expect(saveIntentTree).not.toHaveBeenCalled()
  })

  it('keeps edited JSON and exposes an error when saving fails', async () => {
    vi.mocked(saveIntentTree).mockRejectedValue(new Error('save failed'))
    wrapper = mountPage()
    await flushPromises()
    const edited = '[{"key":"edited","title":"保留内容"}]'

    await wrapper.get('textarea').setValue(edited)
    await wrapper.get('[data-action="save-intent-tree"]').trigger('click')
    await flushPromises()
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe(edited)
    expect(wrapper.get('[role="alert"]').text()).toContain('保存失败')
  })

  it('keeps only the newest load response', async () => {
    let resolveFirst!: (value: { customized: boolean; treeJson: string }) => void
    vi.mocked(getIntentTree)
      .mockReturnValueOnce(new Promise(resolve => { resolveFirst = resolve }))
      .mockResolvedValueOnce({ customized: false, treeJson: '[{"key":"new","title":"最新"}]' })
    wrapper = mountPage()
    ;(wrapper.vm as any).fetchTree()
    await flushPromises()
    resolveFirst({ customized: true, treeJson: '[{"key":"old","title":"旧数据"}]' })
    await flushPromises()
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toContain('最新')
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).not.toContain('旧数据')
  })

  it('confirms reset, closes with Escape, and refetches after success', async () => {
    wrapper = mountPage()
    await flushPromises()

    const trigger = wrapper.get('[data-action="request-reset"]')
    await trigger.trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('重置意图树')
    expect(document.activeElement).toBe(wrapper.get('[data-action="confirm-reset"]').element)
    expect(wrapper.get('header').attributes('inert')).toBeDefined()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.get('header').attributes('inert')).toBeUndefined()
    expect(document.activeElement).toBe(trigger.element)
    await trigger.trigger('click')
    await wrapper.get('[data-action="confirm-reset"]').trigger('click')
    await flushPromises()
    expect(resetIntentTree).toHaveBeenCalledTimes(1)
    expect(getIntentTree).toHaveBeenCalledTimes(2)
    expect(document.activeElement).toBe(trigger.element)
  })

  it('does not refetch or write reset results after unmount', async () => {
    let resolveReset!: (value: boolean) => void
    vi.mocked(resetIntentTree).mockReturnValue(new Promise(resolve => { resolveReset = resolve }))
    wrapper = mountPage()
    await flushPromises()
    await wrapper.get('[data-action="request-reset"]').trigger('click')
    await wrapper.get('[data-action="confirm-reset"]').trigger('click')
    expect(resetIntentTree).toHaveBeenCalledTimes(1)
    wrapper.unmount()
    wrapper = undefined
    resolveReset(true)
    await flushPromises()
    expect(getIntentTree).toHaveBeenCalledTimes(1)
  })

  it('warns before unloading or leaving only while JSON is dirty', async () => {
    wrapper = mountPage()
    await flushPromises()
    const cleanEvent = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(cleanEvent)
    expect(cleanEvent.defaultPrevented).toBe(false)
    expect(routeLeave.guard?.()).toBe(true)

    await wrapper.get('textarea').setValue('[{"key":"dirty","title":"未保存"}]')
    const dirtyEvent = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(dirtyEvent)
    expect(dirtyEvent.defaultPrevented).toBe(true)
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true)
    expect(routeLeave.guard?.()).toBe(false)
    expect(routeLeave.guard?.()).toBe(true)
    expect(confirm).toHaveBeenCalledTimes(2)
    confirm.mockRestore()
  })
})
