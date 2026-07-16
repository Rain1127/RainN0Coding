import { nextTick, onBeforeUnmount, ref, type Ref } from 'vue'

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

interface InertSnapshot {
  element: HTMLElement
  hadInert: boolean
  ariaHidden: string | null
}

interface DialogEntry {
  id: symbol
  isOpen: Ref<boolean>
  overlayRef: Ref<HTMLElement | null>
  dialogRef: Ref<HTMLElement | null>
  canClose: () => boolean
  trigger: HTMLElement | null
  active: boolean
  close: () => Promise<boolean>
}

const dialogStack: DialogEntry[] = []
let inertSnapshots: InertSnapshot[] = []
let globalListenerInstalled = false

function topDialog() {
  return dialogStack[dialogStack.length - 1]
}

function focusableElements(entry: DialogEntry) {
  if (!entry.dialogRef.value) return []
  return Array.from(entry.dialogRef.value.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR))
    .filter(element => !element.hasAttribute('disabled') && element.getAttribute('aria-hidden') !== 'true')
}

function focusInitial(entry: DialogEntry) {
  const initial = entry.dialogRef.value?.querySelector<HTMLElement>('[data-dialog-initial-focus]')
  if (initial && !initial.hasAttribute('disabled')) initial.focus()
  else focusableElements(entry)[0]?.focus()
}

function restoreBackground() {
  for (const snapshot of inertSnapshots) {
    if (!snapshot.hadInert) snapshot.element.removeAttribute('inert')
    if (snapshot.ariaHidden === null) snapshot.element.removeAttribute('aria-hidden')
    else snapshot.element.setAttribute('aria-hidden', snapshot.ariaHidden)
  }
  inertSnapshots = []
}

function isolateTopDialog() {
  restoreBackground()
  const overlay = topDialog()?.overlayRef.value
  if (!overlay) return
  const seen = new Set<HTMLElement>()
  let branch: HTMLElement | null = overlay
  while (branch.parentElement && branch.parentElement !== document.documentElement) {
    const parent: HTMLElement = branch.parentElement
    for (const sibling of Array.from(parent.children)) {
      if (sibling === branch || !(sibling instanceof HTMLElement) || seen.has(sibling)) continue
      seen.add(sibling)
      inertSnapshots.push({
        element: sibling,
        hadInert: sibling.hasAttribute('inert'),
        ariaHidden: sibling.getAttribute('aria-hidden'),
      })
      sibling.setAttribute('inert', '')
      sibling.setAttribute('aria-hidden', 'true')
    }
    if (parent === document.body) break
    branch = parent
  }
}

function handleGlobalKeydown(event: KeyboardEvent) {
  const entry = topDialog()
  if (!entry?.isOpen.value) return
  if (event.key === 'Escape') {
    event.preventDefault()
    void entry.close()
    return
  }
  if (event.key !== 'Tab') return
  const focusable = focusableElements(entry)
  if (focusable.length === 0) {
    event.preventDefault()
    entry.dialogRef.value?.focus()
    return
  }
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && (document.activeElement === first || !entry.dialogRef.value?.contains(document.activeElement))) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

function syncGlobalListener() {
  if (dialogStack.length > 0 && !globalListenerInstalled) {
    window.addEventListener('keydown', handleGlobalKeydown)
    globalListenerInstalled = true
  } else if (dialogStack.length === 0 && globalListenerInstalled) {
    window.removeEventListener('keydown', handleGlobalKeydown)
    globalListenerInstalled = false
  }
}

function removeEntry(entry: DialogEntry) {
  const index = dialogStack.findIndex(item => item.id === entry.id)
  const wasTop = index === dialogStack.length - 1
  if (index >= 0) dialogStack.splice(index, 1)
  syncGlobalListener()
  return wasTop
}

export function useAccessibleDialog(canClose: () => boolean = () => true) {
  const entry: DialogEntry = {
    id: Symbol('dialog'),
    isOpen: ref(false),
    overlayRef: ref<HTMLElement | null>(null),
    dialogRef: ref<HTMLElement | null>(null),
    canClose,
    trigger: null,
    active: true,
    close: closeDialog,
  }

  async function openDialog(opener: EventTarget | null) {
    if (!entry.active || entry.isOpen.value) return
    entry.trigger = opener instanceof HTMLElement ? opener : null
    entry.isOpen.value = true
    await nextTick()
    if (!entry.active || !entry.isOpen.value) return
    dialogStack.push(entry)
    syncGlobalListener()
    isolateTopDialog()
    focusInitial(entry)
  }

  async function closeDialog() {
    if (!entry.active || !entry.isOpen.value || !entry.canClose()) return false
    const opener = entry.trigger
    const wasTop = removeEntry(entry)
    entry.isOpen.value = false
    await nextTick()
    isolateTopDialog()
    if (wasTop) {
      if (opener?.isConnected && !opener.hasAttribute('inert') && !opener.closest('[inert]')) opener.focus()
      else if (topDialog()) focusInitial(topDialog()!)
    } else if (topDialog() && !topDialog()!.dialogRef.value?.contains(document.activeElement)) {
      focusInitial(topDialog()!)
    }
    return true
  }

  onBeforeUnmount(() => {
    entry.active = false
    removeEntry(entry)
    restoreBackground()
    isolateTopDialog()
  })

  return {
    isOpen: entry.isOpen,
    overlayRef: entry.overlayRef,
    dialogRef: entry.dialogRef,
    openDialog,
    closeDialog,
  }
}
