import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ErrorState from './ErrorState.vue'

describe('ErrorState', () => {
  it('announces the error and emits retry', async () => {
    const wrapper = mount(ErrorState, {
      props: {
        title: '加载失败',
        description: '请检查网络后重试',
        retryable: true,
      },
    })

    expect(wrapper.get('[role="alert"]').text()).toContain('请检查网络后重试')
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })
})
