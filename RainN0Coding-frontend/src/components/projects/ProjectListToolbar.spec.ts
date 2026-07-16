import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ProjectListToolbar from './ProjectListToolbar.vue'

describe('ProjectListToolbar', () => {
  it('submits a trimmed search explicitly instead of on every keystroke', async () => {
    const wrapper = mount(ProjectListToolbar, { props: { keyword: '', status: 'all', codeGenType: 'all' } })

    await wrapper.get('input').setValue('  数据看板  ')
    expect(wrapper.emitted('search')).toBeUndefined()
    await wrapper.get('form').trigger('submit')

    expect(wrapper.emitted('search')).toEqual([['数据看板']])
  })

  it('labels deployment filtering as current-page behavior', async () => {
    const wrapper = mount(ProjectListToolbar, { props: { keyword: '', status: 'all', codeGenType: 'all' } })

    expect(wrapper.text()).toContain('部署状态（当前页）')
    await wrapper.get('#project-deployment-status').setValue('deployed')

    expect(wrapper.emitted('status-change')).toEqual([['deployed']])
  })

  it('offers the backend-supported code types and emits a server filter', async () => {
    const wrapper = mount(ProjectListToolbar, { props: { keyword: '', status: 'all', codeGenType: 'all' } })

    expect(wrapper.text()).toContain('代码类型')
    expect(wrapper.get('#project-code-type').find('option[value="vue_project"]').exists()).toBe(true)
    expect(wrapper.get('#project-code-type').find('option[value="python"]').exists()).toBe(true)
    await wrapper.get('#project-code-type').setValue('java')

    expect(wrapper.emitted('type-change')).toEqual([['java']])
  })
})
