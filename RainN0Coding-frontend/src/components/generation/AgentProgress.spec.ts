import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AgentProgress from './AgentProgress.vue'

describe('AgentProgress', () => {
  it('renders every agent in workflow order with explicit text status', () => {
    const wrapper = mount(AgentProgress, { props: { phase: 'code', status: 'running' } })

    expect(wrapper.findAll('[data-agent]').map((item) => item.attributes('data-agent'))).toEqual([
      'intent',
      'pm',
      'architect',
      'image_collector',
      'coder',
      'reviewer',
      'builder',
    ])
    expect(wrapper.get('[data-agent="intent"]').text()).toContain('已完成')
    expect(wrapper.get('[data-agent="coder"]').text()).toContain('进行中')
    expect(wrapper.get('[data-agent="builder"]').text()).toContain('待处理')
    expect(wrapper.get('[data-agent="coder"]').attributes('aria-current')).toBe('step')
  })

  it('handles an unknown phase without falsely marking a known step current', () => {
    const wrapper = mount(AgentProgress, { props: { phase: 'future_agent', status: 'running' } })

    expect(wrapper.find('[aria-current="step"]').exists()).toBe(false)
    expect(wrapper.get('[data-unknown-phase]').text()).toContain('future_agent')
  })

  it('marks all agents complete after a successful run', () => {
    const wrapper = mount(AgentProgress, { props: { phase: 'done', status: 'success' } })

    expect(wrapper.findAll('[data-step-status="complete"]')).toHaveLength(7)
  })

  it.each([
    ['arch', 'architect'],
    ['code', 'coder'],
    ['code_retry', 'coder'],
    ['review', 'reviewer'],
    ['build', 'builder'],
    ['intent', 'intent'],
    ['pm', 'pm'],
    ['image_collector', 'image_collector'],
  ])('normalizes backend phase %s to the %s agent', (phase, agent) => {
    const wrapper = mount(AgentProgress, { props: { phase, status: 'running' } })

    expect(wrapper.get(`[data-agent="${agent}"]`).attributes('aria-current')).toBe('step')
    expect(wrapper.find('[data-unknown-phase]').exists()).toBe(false)
  })

  it('does not mark the workflow complete when a done phase failed', () => {
    const wrapper = mount(AgentProgress, { props: { phase: 'done', status: 'failed' } })

    expect(wrapper.findAll('[data-step-status="complete"]')).toHaveLength(0)
    expect(wrapper.findAll('[data-agent]').every((step) => step.text().includes('未完成'))).toBe(true)
  })
})
