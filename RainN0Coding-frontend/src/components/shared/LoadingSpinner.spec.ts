import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import LoadingSpinner from './LoadingSpinner.vue'

describe('LoadingSpinner', () => {
  it('announces the default loading state with an ellipsis', () => {
    const wrapper = mount(LoadingSpinner, {
      global: {
        stubs: { 'a-spin': { template: '<span />' } },
      },
    })

    expect(wrapper.get('[role="status"]').text()).toBe('正在加载…')
  })
})
