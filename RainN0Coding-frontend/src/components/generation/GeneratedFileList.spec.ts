import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import GeneratedFileList from './GeneratedFileList.vue'

describe('GeneratedFileList', () => {
  it('renders semantic file metadata without source content', () => {
    const wrapper = mount(GeneratedFileList, {
      props: {
        files: [{ path: 'src/App.vue', language: 'vue', size: 2048 }],
        status: 'success',
      },
    })

    expect(wrapper.get('ul[aria-label="生成文件"]').element.tagName).toBe('UL')
    expect(wrapper.get('code').text()).toBe('src/App.vue')
    expect(wrapper.text()).toContain('Vue')
    expect(wrapper.text()).toContain('2 KB')
    expect(wrapper.text()).toContain('已生成')
    expect(wrapper.html()).not.toContain('content')
    expect(wrapper.html()).not.toContain('source')
  })

  it('has a useful empty state', () => {
    const wrapper = mount(GeneratedFileList, { props: { files: [], status: 'running' } })

    expect(wrapper.get('[data-empty-files]').text()).toContain('文件将在生成后显示')
  })
})
