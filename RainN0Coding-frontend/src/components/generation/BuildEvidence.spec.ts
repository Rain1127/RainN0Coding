import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import BuildEvidence from './BuildEvidence.vue'
describe('BuildEvidence', () => {
  it('labels missing tools as unverified', () => {
    const wrapper = mount(BuildEvidence, { props: { events: [{ type: 'done', result: { build_status: 'unverified' } }] } })
    expect(wrapper.text()).toContain('未验证')
    expect(wrapper.text()).not.toContain('验证通过')
  })
  it('distinguishes no build from browser acceptance', () => {
    const wrapper = mount(BuildEvidence, { props: { events: [{ type: 'done', result: { build_status: 'not_required', runtime_result: { status: 'succeeded' } } }] } })
    expect(wrapper.text()).toContain('无需此项验证')
    expect(wrapper.text()).toContain('浏览器：验证通过')
  })
})
