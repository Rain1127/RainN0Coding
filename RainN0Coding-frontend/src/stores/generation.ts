import { defineStore } from 'pinia'
import { ref } from 'vue'
import { createSseParser } from '@/services/sseParser'
import type {
  GeneratedFile,
  GenerationEvent,
  GenerationState,
  GenerationStatus,
} from '@/types/generation'
import type { EntityId } from '@/types/entity'
import { sameEntityId } from '@/utils/entityId'

export const MAX_GENERATION_EVENTS = 200
const SUCCESSFUL_DONE_STATUSES = new Set([
  'success',
  'partial_success',
  'degraded_success',
  'duplicate_completed',
])

export interface StartGenerationOptions {
  preserve?: boolean
}

function newRequestId(): string {
  // Public IP deployments use HTTP, where randomUUID may be unavailable.
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6]! & 0x0f) | 0x40
  bytes[8] = (bytes[8]! & 0x3f) | 0x80
  const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

function eventError(event: GenerationEvent): string {
  if (event.message) return event.message
  if (event.detail) return event.detail
  if (event.status) return `Generation ended with status: ${event.status}`
  return 'Generation failed'
}

function generatedFile(event: GenerationEvent): GeneratedFile | null {
  if (event.type !== 'code_file') return null

  const path =
    typeof event.file_path === 'string'
      ? event.file_path
      : typeof event.path === 'string'
        ? event.path
        : null

  if (!path) return null

  const file: GeneratedFile = {
    path,
    language: typeof event.language === 'string' ? event.language : '',
  }
  if (typeof event.size === 'number') {
    file.size = event.size
  } else if (typeof event.size === 'string' && event.size.trim()) {
    file.size = event.size.trim()
  }
  return file
}

function retainedEvent(event: GenerationEvent): GenerationEvent {
  if (
    event.type !== 'code_file' ||
    (event.content === undefined && event.source === undefined)
  ) {
    return event
  }
  const retained = { ...event }
  delete retained.content
  delete retained.source
  return retained
}

function mergedFile(existing: GeneratedFile, incoming: GeneratedFile): GeneratedFile {
  const language = incoming.language.trim() ? incoming.language : existing.language
  const incomingHasSize =
    typeof incoming.size === 'number' ||
    (typeof incoming.size === 'string' && incoming.size.trim().length > 0)
  const size = incomingHasSize ? incoming.size : existing.size
  return size === undefined
    ? { path: existing.path, language }
    : { path: existing.path, language, size }
}

export function applyGenerationEvent(
  state: GenerationState,
  event: GenerationEvent,
): GenerationState {
  const retainedEvents = [...state.events, retainedEvent(event)]
  const next: GenerationState = {
    ...state,
    events: retainedEvents.slice(-MAX_GENERATION_EVENTS),
  }

  if (typeof event.phase === 'string') {
    next.phase = event.phase
    if (!['failed', 'cancelled', 'pausing', 'paused'].includes(state.status)) {
      next.status = 'running'
    }
  }

  const file = generatedFile(event)
  if (file) {
    const existingIndex = state.files.findIndex(
      (existing) => existing.path === file.path,
    )
    if (existingIndex === -1) {
      next.files = [...state.files, file]
    } else {
      next.files = state.files.map((existing, index) =>
        index === existingIndex ? mergedFile(existing, file) : existing,
      )
    }
  }

  if (
    event.type === 'error' ||
    event.sse_event === 'business-error' ||
    event.error === true
  ) {
    next.status = 'failed'
    next.error = eventError(event)
  }

  if (event.type === 'done') {
    if (event.status === 'paused' && next.status !== 'failed' && next.status !== 'cancelled') {
      next.status = 'paused'
      next.phase = state.phase
      next.error = null
      return next
    }
    next.phase = 'done'
    if (event.status && SUCCESSFUL_DONE_STATUSES.has(event.status)) {
      if (next.status !== 'failed' && next.status !== 'cancelled') {
        next.status = 'success'
        next.error = null
      }
    } else if (next.status !== 'failed' && next.status !== 'cancelled') {
      next.status = 'failed'
      next.error = eventError(event)
    }
  }

  return next
}

function initialState(): GenerationState {
  return {
    status: 'idle',
    phase: null,
    events: [],
    files: [],
    error: null,
  }
}

function errorMessage(error: unknown): string {
  return error instanceof Error && error.message
    ? error.message
    : 'Generation stream failed'
}

function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === 'AbortError'
}

function isEventStreamResponse(response: Response): boolean {
  const contentType = response.headers.get('content-type')
  const mediaType = contentType?.split(';', 1)[0].trim().toLowerCase()
  return mediaType === 'text/event-stream'
}

function isTransportCompletion(event: GenerationEvent): boolean {
  return (
    event.sse_event === 'done' &&
    event.type === undefined &&
    Object.keys(event).every((field) => field === 'sse_event')
  )
}

export const useGenerationStore = defineStore('generation', () => {
  const status = ref<GenerationStatus>('idle')
  const phase = ref<GenerationState['phase']>(null)
  const events = ref<GenerationEvent[]>([])
  const files = ref<GeneratedFile[]>([])
  const error = ref<string | null>(null)
  const runId = ref(0)
  const requestId = ref<string | null>(null)
  const controlError = ref<string | null>(null)

  let activeController: AbortController | null = null
  let currentAppId: EntityId | null = null
  let statusTimer: ReturnType<typeof setTimeout> | undefined
  const pointerKey = (appId: EntityId) => `generation-run:${appId}`

  function retainRun() {
    if (currentAppId === null || !requestId.value) return
    try { localStorage.setItem(pointerKey(currentAppId), requestId.value) } catch { /* Storage is optional. */ }
  }

  function forgetRun() {
    if (currentAppId === null) return
    try { localStorage.removeItem(pointerKey(currentAppId)) } catch { /* Storage is optional. */ }
  }

  function snapshot(): GenerationState {
    return {
      status: status.value,
      phase: phase.value,
      events: events.value,
      files: files.value,
      error: error.value,
    }
  }

  function replaceState(next: GenerationState) {
    status.value = next.status
    phase.value = next.phase
    events.value = next.events
    files.value = next.files
    error.value = next.error
  }

  async function stream(
    appId: EntityId,
    prompt: string,
    options: StartGenerationOptions = {},
    resuming = false,
  ): Promise<void> {
    const currentRunId = ++runId.value
    clearTimeout(statusTimer)
    activeController?.abort()

    const controller = new AbortController()
    activeController = controller

    const preserve = options.preserve === true && sameEntityId(currentAppId, appId)
    currentAppId = appId
    if (!resuming) requestId.value = newRequestId()
    controlError.value = null
    retainRun()
    replaceState({
      ...initialState(),
      status: 'connecting',
      phase: resuming ? phase.value : null,
      events: preserve ? events.value : [],
      files: preserve ? files.value : [],
    })

    const baseUrl = import.meta.env.VITE_API_BASE ?? ''
    const url = resuming
      ? `${baseUrl}/app/chat/gen/resume?appId=${encodeURIComponent(String(appId))}&runId=${encodeURIComponent(requestId.value!)}`
      :
      `${baseUrl}/app/chat/gen/code` +
      `?appId=${encodeURIComponent(String(appId))}` +
      `&message=${encodeURIComponent(prompt)}`

    try {
      const response = await fetch(url, {
        method: 'GET',
        signal: controller.signal,
        credentials: 'include',
        headers: { Accept: 'text/event-stream', 'Idempotency-Key': requestId.value! },
      })

      if (!response.ok) {
        const statusText = response.statusText ? ` ${response.statusText}` : ''
        throw new Error(`Generation request failed: HTTP ${response.status}${statusText}`)
      }
      if (!isEventStreamResponse(response)) {
        throw new Error('Generation response must use Content-Type text/event-stream')
      }
      if (!response.body) {
        throw new Error('Generation response did not include a readable stream')
      }

      let validEventCount = 0
      let malformedFrameCount = 0
      let resumeRejected = false
      const parser = createSseParser((event) => {
        if (currentRunId !== runId.value || controller.signal.aborted) return
        if (!isTransportCompletion(event)) validEventCount += 1
        if (typeof event.request_id === 'string' && event.request_id) {
          requestId.value = event.request_id
          retainRun()
        }
        if (resuming && event.type === 'error') {
          resumeRejected = true
          controlError.value = eventError(event)
          status.value = 'paused'
          return
        }
        if (resumeRejected) return
        replaceState(applyGenerationEvent(snapshot(), event))
        if (event.type === 'done' && event.status !== 'paused') forgetRun()
      }, () => {
        if (currentRunId === runId.value && !controller.signal.aborted) {
          malformedFrameCount += 1
        }
      })
      const reader = response.body.getReader()
      const decoder = new TextDecoder()

      while (true) {
        const { done, value } = await reader.read()
        if (currentRunId !== runId.value || controller.signal.aborted) return
        if (done) break
        parser.push(decoder.decode(value, { stream: true }))
      }

      const finalChunk = decoder.decode()
      if (finalChunk) parser.push(finalChunk)
      parser.flush()

      if (currentRunId !== runId.value || controller.signal.aborted) return
      if (resumeRejected) {
        scheduleStatus()
        return
      }
      if (validEventCount === 0) {
        if (malformedFrameCount > 0) {
          throw new Error(
            `Generation stream contained ${malformedFrameCount} malformed SSE frame(s) and no valid events`,
          )
        }
        throw new Error('Generation stream ended without any valid events')
      }
      if (status.value === 'connecting' || status.value === 'running') {
        status.value = 'success'
        error.value = null
        forgetRun()
      } else if (status.value === 'pausing') {
        scheduleStatus()
      }
    } catch (caught) {
      if (currentRunId !== runId.value) return
      if (controller.signal.aborted || isAbortError(caught)) {
        if (status.value !== 'cancelled') status.value = 'cancelled'
        return
      }
      if (resuming && status.value !== 'failed') {
        status.value = 'paused'
        controlError.value = errorMessage(caught)
      } else if (status.value !== 'failed') {
        status.value = 'failed'
        error.value = errorMessage(caught)
      }
      controller.abort()
    } finally {
      if (currentRunId === runId.value && activeController === controller) {
        activeController = null
      }
    }
  }

  async function start(appId: EntityId, prompt: string, options: StartGenerationOptions = {}) {
    if (['connecting', 'running', 'pausing', 'paused'].includes(status.value) && sameEntityId(currentAppId, appId)) return
    return stream(appId, prompt, options)
  }

  async function control(action: 'pause' | 'status', appId: EntityId, id: string) {
    const base = import.meta.env.VITE_API_BASE ?? ''
    const response = await fetch(action === 'pause'
      ? `${base}/app/chat/gen/pause`
      : `${base}/app/chat/gen/status?appId=${encodeURIComponent(String(appId))}&runId=${encodeURIComponent(id)}`, {
      method: action === 'pause' ? 'POST' : 'GET',
      credentials: 'include',
      ...(action === 'pause' ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ appId, runId: id }) } : {}),
    })
    const body = await response.json() as { code?: number; message?: string; data?: { run_id: string; status: string } }
    if (!response.ok || body.code !== 0 || !body.data) throw new Error(body.message || '暂停状态查询失败，请重试。')
    return body.data
  }

  function scheduleStatus() {
    clearTimeout(statusTimer)
    statusTimer = setTimeout(() => { void refreshStatus() }, 2000)
  }

  async function refreshStatus() {
    if (currentAppId === null || !requestId.value) return
    const epoch = runId.value
    try {
      const result = await control('status', currentAppId, requestId.value)
      if (epoch !== runId.value) return
      controlError.value = null
      if (result.status === 'paused' || result.status === 'interrupted') status.value = 'paused'
      else if (result.status === 'running' || result.status === 'pausing') {
        status.value = result.status
        scheduleStatus()
      } else {
        status.value = SUCCESSFUL_DONE_STATUSES.has(result.status) || result.status === 'completed' ? 'success' : 'failed'
        if (status.value === 'failed') error.value = '此任务已结束，无法继续。'
        forgetRun()
      }
    } catch (caught) {
      if (epoch === runId.value) controlError.value = errorMessage(caught)
    }
  }

  async function restore(appId: EntityId) {
    let saved: string | null = null
    try { saved = localStorage.getItem(pointerKey(appId)) } catch { return }
    if (!saved) return
    currentAppId = appId
    requestId.value = saved
    status.value = 'connecting'
    await refreshStatus()
  }

  async function pause() {
    if (currentAppId === null || !requestId.value || !['connecting', 'running'].includes(status.value)) return
    const previousStatus = status.value
    const epoch = runId.value
    status.value = 'pausing'
    controlError.value = null
    try {
      await control('pause', currentAppId, requestId.value)
      if (epoch === runId.value && !activeController && status.value === 'pausing') scheduleStatus()
    } catch (caught) {
      if (epoch !== runId.value) return
      if (status.value === 'pausing') status.value = previousStatus
      controlError.value = errorMessage(caught)
    }
  }

  async function resume() {
    if (status.value !== 'paused' || currentAppId === null || !requestId.value) return
    return stream(currentAppId, '', { preserve: true }, true)
  }

  function cancel() {
    if (!activeController) return
    status.value = 'cancelled'
    error.value = null
    const controller = activeController
    activeController = null
    controller.abort()
  }

  function reset() {
    clearTimeout(statusTimer)
    runId.value += 1
    activeController?.abort()
    activeController = null
    currentAppId = null
    requestId.value = null
    controlError.value = null
    replaceState(initialState())
  }

  return {
    status,
    phase,
    events,
    files,
    error,
    runId,
    requestId,
    controlError,
    pause,
    resume,
    restore,
    refreshStatus,
    start,
    cancel,
    reset,
  }
})
