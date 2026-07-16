import { defineComponent, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import { useAccessibleDialog } from './useAccessibleDialog'

const Harness = defineComponent({
  setup() {
    const busy = ref(false)
    const dialog = useAccessibleDialog(() => !busy.value)
    return { busy, ...dialog }
  },
  template: `
    <main data-background><button data-trigger @click="openDialog($event.currentTarget)">open</button></main>
    <div v-if="isOpen" ref="overlayRef" data-overlay>
      <section ref="dialogRef" role="dialog">
        <button data-first>first</button>
        <button data-dialog-initial-focus>confirm</button>
      </section>
    </div>
  `,
})

const StackedHarness = defineComponent({
  setup() {
    const first = useAccessibleDialog()
    const second = useAccessibleDialog()
    return {
      firstOpen: first.isOpen,
      firstOverlay: first.overlayRef,
      firstDialog: first.dialogRef,
      openFirst: first.openDialog,
      closeFirst: first.closeDialog,
      secondOpen: second.isOpen,
      secondOverlay: second.overlayRef,
      secondDialog: second.dialogRef,
      openSecond: second.openDialog,
    }
  },
  template: `
    <main data-stack-background><button data-open-first @click="openFirst($event.currentTarget)">open first</button></main>
    <div v-if="firstOpen" ref="firstOverlay" data-first-overlay>
      <section ref="firstDialog" role="dialog" data-first-dialog>
        <button data-open-second data-dialog-initial-focus @click="openSecond($event.currentTarget)">open second</button>
      </section>
    </div>
    <div v-if="secondOpen" ref="secondOverlay" data-second-overlay>
      <section ref="secondDialog" role="dialog" data-second-dialog>
        <button data-second-confirm data-dialog-initial-focus>second confirm</button>
      </section>
    </div>
  `,
})

describe('useAccessibleDialog', () => {
  let wrapper: ReturnType<typeof mount> | undefined
  afterEach(() => {
    wrapper?.unmount()
    document.body.innerHTML = ''
  })

  it('traps focus, makes the background inert, and restores the trigger', async () => {
    wrapper = mount(Harness, { attachTo: document.body })
    const trigger = wrapper.get('[data-trigger]')
    await trigger.trigger('click')
    await nextTick()
    expect(wrapper.get('[data-background]').attributes('inert')).toBeDefined()
    const first = wrapper.get('[data-first]')
    const last = wrapper.get('[data-dialog-initial-focus]')
    expect(document.activeElement).toBe(last.element)
    await last.trigger('keydown', { key: 'Tab' })
    expect(document.activeElement).toBe(first.element)
    await first.trigger('keydown', { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(last.element)
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.get('[data-background]').attributes('inert')).toBeUndefined()
    expect(document.activeElement).toBe(trigger.element)
  })

  it('removes inert state and listeners when unmounted while open', async () => {
    wrapper = mount(Harness, { attachTo: document.body })
    await wrapper.get('[data-trigger]').trigger('click')
    await nextTick()
    const background = wrapper.get('[data-background]').element
    expect(background.hasAttribute('inert')).toBe(true)
    wrapper.unmount()
    wrapper = undefined
    expect(background.hasAttribute('inert')).toBe(false)
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
  })

  it('handles Escape only on the top dialog and preserves isolation when the lower dialog closes', async () => {
    wrapper = mount(StackedHarness, { attachTo: document.body })
    await wrapper.get('[data-open-first]').trigger('click')
    await wrapper.get('[data-open-second]').trigger('click')
    await nextTick()
    expect(wrapper.findAll('[role="dialog"]')).toHaveLength(2)
    expect(wrapper.get('[data-first-overlay]').attributes('inert')).toBeDefined()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()
    expect(wrapper.find('[data-second-dialog]').exists()).toBe(false)
    expect(wrapper.find('[data-first-dialog]').exists()).toBe(true)
    expect(document.activeElement).toBe(wrapper.get('[data-open-second]').element)

    await wrapper.get('[data-open-second]').trigger('click')
    await nextTick()
    await (wrapper.vm as any).closeFirst()
    await nextTick()
    expect(wrapper.find('[data-first-dialog]').exists()).toBe(false)
    expect(wrapper.find('[data-second-dialog]').exists()).toBe(true)
    expect(wrapper.get('[data-stack-background]').attributes('inert')).toBeDefined()
    expect(document.activeElement).toBe(wrapper.get('[data-second-confirm]').element)

    const background = wrapper.get('[data-stack-background]').element
    wrapper.unmount()
    wrapper = undefined
    expect(background.hasAttribute('inert')).toBe(false)
  })
})
