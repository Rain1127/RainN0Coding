import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import PromptComposer from './PromptComposer.vue'

const examples = [
  { title: '项目看板', prompt: '生成一个项目管理看板' },
  { title: '数据工具', prompt: '创建一个 CSV 数据分析工具' },
  { title: '接口服务', prompt: '生成一个 Spring Boot 用户接口' },
]

describe('PromptComposer', () => {
  it('keeps whitespace-only prompts disabled', async () => {
    const wrapper = mount(PromptComposer, { props: { examples } })

    await wrapper.get('textarea').setValue('   ')

    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    expect(wrapper.emitted('submit')).toBeUndefined()
  })

  it('submits a trimmed prompt with Ctrl+Enter or Command+Enter', async () => {
    const wrapper = mount(PromptComposer, { props: { examples } })
    const textarea = wrapper.get('textarea')

    await textarea.setValue('  生成一个项目管理看板  ')
    await textarea.trigger('keydown', { key: 'Enter', ctrlKey: true })
    await textarea.trigger('keydown', { key: 'Enter', metaKey: true })

    expect(wrapper.emitted('submit')).toEqual([
      ['生成一个项目管理看板'],
      ['生成一个项目管理看板'],
    ])
  })

  it('does not submit while an IME composition is active', async () => {
    const wrapper = mount(PromptComposer, { props: { examples } })
    const textarea = wrapper.get('textarea')

    await textarea.setValue('生成中文项目')
    await textarea.trigger('compositionstart')
    await textarea.trigger('keydown', { key: 'Enter', ctrlKey: true })
    await textarea.trigger('compositionend')

    expect(wrapper.emitted('submit')).toBeUndefined()
  })

  it('announces loading and blocks repeated submission', async () => {
    const wrapper = mount(PromptComposer, { props: { examples, loading: true } })

    await wrapper.get('textarea').setValue('生成一个项目')

    expect(wrapper.get('form').attributes('aria-busy')).toBe('true')
    expect(wrapper.get('textarea').attributes('disabled')).toBeDefined()
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('button[type="submit"]').text()).toContain('正在创建')
  })

  it('uses a visible label and copies an example into the textarea without submitting', async () => {
    const wrapper = mount(PromptComposer, { props: { examples } })

    expect(wrapper.get('label').isVisible()).toBe(true)
    expect(wrapper.get('[id="prompt-description"]').text()).toContain('Ctrl')
    await wrapper.get('[data-example="项目看板"]').trigger('click')

    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('生成一个项目管理看板')
    expect(wrapper.emitted('submit')).toBeUndefined()
  })
})
