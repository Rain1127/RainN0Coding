import { nextTick, onBeforeUnmount, type Ref } from 'vue'

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

interface ModalDrawerOptions {
  open: Ref<boolean>
  trigger: Ref<HTMLElement | null>
  dialog: Ref<HTMLElement | null>
  background: () => Array<HTMLElement | null>
}

function setElementInert(element: HTMLElement | null, inert: boolean) {
  if (!element) return

  if (inert) {
    element.setAttribute('inert', '')
  } else {
    element.removeAttribute('inert')
  }

  if ('inert' in element) {
    element.inert = inert
  }
}

export function useModalDrawer(options: ModalDrawerOptions) {
  function setBackgroundInert(inert: boolean) {
    options.background().forEach((element) => setElementInert(element, inert))
  }

  function focusableElements() {
    return Array.from(options.dialog.value?.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR) ?? [])
  }

  function openDrawer() {
    if (options.open.value) return
    options.open.value = true
    nextTick(() => {
      const [first] = focusableElements()
      first?.focus()
      setBackgroundInert(true)
    })
  }

  function closeDrawer() {
    if (!options.open.value) return
    setBackgroundInert(false)
    options.open.value = false
    nextTick(() => options.trigger.value?.focus())
  }

  function handleDrawerKeydown(event: KeyboardEvent) {
    if (!options.open.value) return

    if (event.key === 'Escape') {
      event.preventDefault()
      closeDrawer()
      return
    }

    if (event.key !== 'Tab') return
    const focusable = focusableElements()
    if (focusable.length === 0) {
      event.preventDefault()
      options.dialog.value?.focus()
      return
    }

    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    const active = document.activeElement
    if (event.shiftKey && (active === first || !options.dialog.value?.contains(active))) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && (active === last || !options.dialog.value?.contains(active))) {
      event.preventDefault()
      first.focus()
    }
  }

  function cleanupDrawer() {
    setBackgroundInert(false)
  }

  onBeforeUnmount(cleanupDrawer)

  return { closeDrawer, handleDrawerKeydown, openDrawer }
}
