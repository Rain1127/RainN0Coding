import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { AppVO } from '@/types/app'
import ProjectCard from './ProjectCard.vue'

function project(overrides: Partial<AppVO> = {}): AppVO {
  return {
    id: 7,
    appName: '销售数据看板',
    cover: '',
    initPrompt: '',
    codeGenType: 'vue_project',
    deployKey: '',
    deployedTime: '',
    priority: 0,
    userId: 1,
    currentVersion: 1,
    createTime: '2026-07-13T09:00:00',
    updateTime: '2026-07-14T09:00:00',
    editTime: '2026-07-14T09:00:00',
    ...overrides,
  }
}

describe('ProjectCard', () => {
  it('shows the real project summary and an explicit open action', () => {
    const wrapper = mount(ProjectCard, {
      props: { project: project() },
      global: {
        stubs: {
          RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
        },
      },
    })

    expect(wrapper.get('h2').text()).toBe('销售数据看板')
    expect(wrapper.text()).toContain('Vue 项目')
    expect(wrapper.text()).toContain('未部署')
    expect(wrapper.get('a').text()).toContain('打开项目')
    expect(wrapper.get('a').attributes('href')).toBe('/chat/7')
  })

  it('uses deployment metadata to show a text status', () => {
    const wrapper = mount(ProjectCard, {
      props: { project: project({ deployKey: 'release-key', deployedTime: '2026-07-14T10:00:00' }) },
      global: { stubs: { RouterLink: true } },
    })

    expect(wrapper.text()).toContain('已部署')
  })

  it('requires confirmation before emitting delete', async () => {
    const wrapper = mount(ProjectCard, {
      props: { project: project() },
      global: { stubs: { RouterLink: true } },
    })

    await wrapper.get('[data-action="request-delete"]').trigger('click')
    expect(wrapper.get('[role="alertdialog"]').text()).toContain('删除“销售数据看板”')
    expect(wrapper.emitted('delete')).toBeUndefined()
    await wrapper.get('[data-action="confirm-delete"]').trigger('click')

    expect(wrapper.emitted('delete')).toEqual([[7]])
  })

  it('moves focus into confirmation and restores it when Escape cancels', async () => {
    const wrapper = mount(ProjectCard, {
      attachTo: document.body,
      props: { project: project() },
      global: { stubs: { RouterLink: true } },
    })
    const trigger = wrapper.get('[data-action="request-delete"]')

    await trigger.trigger('click')
    const cancel = wrapper.get('[data-action="cancel-delete"]')
    const confirm = wrapper.get('[data-action="confirm-delete"]')
    expect(document.activeElement).toBe(cancel.element)
    await cancel.trigger('keydown', { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(confirm.element)
    await confirm.trigger('keydown', { key: 'Tab' })
    expect(document.activeElement).toBe(cancel.element)
    await wrapper.get('[role="alertdialog"]').trigger('keydown', { key: 'Escape' })

    expect(wrapper.find('[role="alertdialog"]').exists()).toBe(false)
    expect(document.activeElement).toBe(trigger.element)
    wrapper.unmount()
  })
})
