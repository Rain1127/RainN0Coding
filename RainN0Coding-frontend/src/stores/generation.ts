import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { useLegacyGenerationStore } from './generationLegacy'
import { createSseParser } from '@/services/sseParser'
import { createGenerationTask, getGenerationTask, getLatestGenerationTask, generationTaskUrl, GenerationRequestError, controlGenerationTask } from '@/api/generation'
import type {
  GeneratedFile,
  GenerationEvent,
  GenerationState,
  GenerationStatus,
  GenerationTask,
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

  if (event.type === 'queued') { next.status = 'queued'; next.error = null }

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

function reconnectDelay(signal: AbortSignal, delay: number): Promise<void> {
  return new Promise((resolve) => {
    const finish = () => {
      clearTimeout(timer)
      signal.removeEventListener('abort', finish)
      resolve()
    }
    const timer = setTimeout(finish, delay)
    signal.addEventListener('abort', finish, { once: true })
    if (signal.aborted) finish()
  })
}

function isTerminal(task: GenerationTask) {
  return task.status === 'PAUSED' || task.status === 'SUCCEEDED' || task.status === 'FAILED' || task.status === 'INTERRUPTED'
}

export const useGenerationStore = defineStore('generation', () => {
  const status = ref<GenerationStatus>('idle')
  const phase = ref<GenerationState['phase']>(null)
  const events = ref<GenerationEvent[]>([])
  const files = ref<GeneratedFile[]>([])
  const error = ref<string | null>(null)
  const runId = ref(0)
  const legacy = useLegacyGenerationStore()
  const legacyMode = ref(false)
  const requestId = ref<string | null>(null)
  const controlError = ref<string | null>(null)
  const task = ref<GenerationTask | null>(null)
  const lastEventId = ref('0')
  const retryAllowed = ref(false)
  const connectionMessage = ref('')
  let activeController: AbortController | null = null
  let currentAppId: EntityId | null = null
  // Keep the same key after an uncertain POST response, so a manual resubmit
  // cannot charge for the same request twice. Prompts are never persisted locally.
  let pendingSubmission: { appId: string; prompt: string; key: string } | null = null

  function snapshot(): GenerationState {
    return { status: status.value, phase: phase.value, events: events.value, files: files.value, error: error.value }
  }

  function replaceState(next: GenerationState) {
    status.value = next.status
    phase.value = next.phase
    events.value = next.events
    files.value = next.files
    error.value = next.error
  }

  watch(() => [legacy.status, legacy.phase, legacy.events, legacy.files, legacy.error, legacy.controlError, legacy.requestId], () => {
    if (!legacyMode.value) return
    replaceState({ status: legacy.status, phase: legacy.phase, events: legacy.events, files: legacy.files, error: legacy.error })
    requestId.value = legacy.requestId
    controlError.value = legacy.controlError
    retryAllowed.value = legacy.status === 'failed'
  }, { flush: 'sync' })

  function applyTask(next: GenerationTask) {
    requestId.value = next.taskId
    task.value = next
    retryAllowed.value = next.retryAllowed
    if (next.status === 'SUCCEEDED') {
      status.value = 'success'
      phase.value = 'done'
      error.value = null
    } else if (next.status === 'FAILED' || next.status === 'INTERRUPTED') {
      status.value = 'failed'
      error.value = next.errorMessage || (next.status === 'INTERRUPTED' ? '生成任务已中断' : '生成失败')
    } else {
      status.value = next.status === 'QUEUED' ? 'queued' : next.status === 'PAUSING' ? 'pausing' : next.status === 'PAUSED' ? 'paused' : 'running'
      if (next.status === 'QUEUED') phase.value = 'queued'
      error.value = null
    }
  }

  function begin(appId: EntityId, preserve = false) {
    legacyMode.value = false
    legacy.reset()
    controlError.value = null
    requestId.value = null
    const id = ++runId.value
    activeController?.abort()
    const controller = new AbortController()
    activeController = controller
    const keep = preserve && sameEntityId(currentAppId, appId)
    currentAppId = appId
    replaceState({ ...initialState(), status: 'connecting', events: keep ? events.value : [], files: keep ? files.value : [] })
    task.value = null
    lastEventId.value = '0'
    retryAllowed.value = false
    connectionMessage.value = ''
    return { id, controller, current: () => id === runId.value && !controller.signal.aborted }
  }

  async function subscribe(initialTask: GenerationTask, context: ReturnType<typeof begin>) {
    const { controller, current } = context
    let delay = 1000
    while (current()) {
      let streamError: unknown
      try {
        const response = await fetch(generationTaskUrl(`/${encodeURIComponent(initialTask.taskId)}/events?after=${encodeURIComponent(lastEventId.value)}`), {
          method: 'GET', signal: controller.signal, credentials: 'include', headers: { Accept: 'text/event-stream' },
        })
        if (!current()) return
        if (!response.ok) {
          throw new GenerationRequestError(`进度订阅失败（HTTP ${response.status}）`, response.status >= 500 || response.status === 429)
        }
        if (!isEventStreamResponse(response)) {
          // Gateway ownership/login failures may use the normal JSON envelope.
          if (response.headers.get('content-type')?.includes('application/json')) {
            const body = await response.json() as { message?: string }
            throw new GenerationRequestError(body.message || '无权订阅此任务')
          }
          throw new GenerationRequestError('Generation response must use Content-Type text/event-stream')
        }
        if (!response.body) throw new GenerationRequestError('Generation response did not include a readable stream')
        connectionMessage.value = ''
        const parser = createSseParser((event) => {
          if (!current()) return
          if (event.sse_event === 'business-error') throw new GenerationRequestError(eventError(event))
          if (event.id !== undefined) {
            if (!/^\d+$/.test(event.id)) throw new GenerationRequestError('进度事件编号无效')
            if (BigInt(event.id) <= BigInt(lastEventId.value)) return
            lastEventId.value = event.id
          }
          replaceState(applyGenerationEvent(snapshot(), event))
          // Only the durable task snapshot can confirm all file/history saves.
          if (event.type === 'done' && status.value === 'success') status.value = 'running'
          delay = 1000
        }, () => { throw new GenerationRequestError('Generation stream contained a malformed SSE frame') })
        const decoder = new TextDecoder()
        const reader = response.body.getReader()
        const abortReader = () => { void reader.cancel().catch(() => undefined) }
        controller.signal.addEventListener('abort', abortReader, { once: true })
        try {
          while (current()) {
            const { done, value } = await reader.read()
            if (!current()) return
            if (done) break
            parser.push(decoder.decode(value, { stream: true }))
          }
          parser.push(decoder.decode())
          parser.flush()
        } finally {
          controller.signal.removeEventListener('abort', abortReader)
          await reader.cancel().catch(() => undefined)
          reader.releaseLock()
        }
      } catch (caught) {
        if (!current() || isAbortError(caught)) return
        if (caught instanceof GenerationRequestError && !caught.retryable) throw caught
        streamError = caught
      }
      if (!current()) return
      try {
        const latest = await getGenerationTask(initialTask.taskId, controller.signal)
        if (!current()) return
        applyTask(latest)
        if (isTerminal(latest)) return
      } catch (caught) {
        if (!current() || isAbortError(caught)) return
        if (caught instanceof GenerationRequestError && !caught.retryable) throw caught
        streamError = caught
      }
      connectionMessage.value = streamError ? '连接暂时中断，正在恢复进度；任务继续执行。' : '正在恢复进度；任务继续执行。'
      await reconnectDelay(controller.signal, delay)
      delay = Math.min(delay * 2, 15000)
    }
  }

  async function runTask(context: ReturnType<typeof begin>, load: () => Promise<GenerationTask | null>) {
    try {
      const next = await load()
      if (!context.current()) return
      if (!next) { if (!legacyMode.value) replaceState(initialState()); return }
      applyTask(next)
      await subscribe(next, context)
    } catch (caught) {
      if (!context.current() || isAbortError(caught)) return
      status.value = 'failed'
      error.value = errorMessage(caught)
      retryAllowed.value = false
    } finally {
      if (context.id === runId.value && activeController === context.controller) activeController = null
    }
  }

  async function start(appId: EntityId, prompt: string, options: StartGenerationOptions = {}): Promise<void> {
    const context = begin(appId, options.preserve)
    if (!pendingSubmission || pendingSubmission.appId !== String(appId) || pendingSubmission.prompt !== prompt) {
      pendingSubmission = { appId: String(appId), prompt, key: newRequestId() }
    }
    const submission = pendingSubmission
    await runTask(context, async () => {
      let next: GenerationTask
      try {
        next = await createGenerationTask(appId, prompt, submission.key, context.controller.signal)
      } catch (caught) {
        if (!(caught instanceof GenerationRequestError) || caught.httpStatus !== 404 || !context.current()) throw caught
        legacyMode.value = true
        await legacy.start(appId, prompt, options)
        return null
      }
      if (pendingSubmission === submission) pendingSubmission = null
      return next
    })
  }

  async function restore(appId: EntityId): Promise<void> {
    const context = begin(appId)
    await runTask(context, async () => {
      let next: GenerationTask | null
      try { next = await getLatestGenerationTask(appId, context.controller.signal) }
      catch (caught) {
        if (!(caught instanceof GenerationRequestError) || caught.httpStatus !== 404) throw caught
        next = null
      }
      if (!context.current()) return null
      if (!next) {
        replaceState(initialState())
        legacyMode.value = true
        await legacy.restore(appId)
      }
      return next
    })
  }

  async function pause() {
    if (legacyMode.value) return legacy.pause()
    if (!task.value || !['queued', 'running'].includes(status.value)) return
    const epoch = runId.value
    const previous = status.value
    status.value = 'pausing'
    controlError.value = null
    try {
      const next = await controlGenerationTask(task.value.taskId, 'pause', new AbortController().signal)
      if (epoch === runId.value) applyTask(next)
    } catch (caught) {
      if (epoch === runId.value) {
        if (status.value === 'pausing') status.value = previous
        controlError.value = errorMessage(caught)
      }
    }
  }

  async function refreshStatus() {
    if (legacyMode.value) return legacy.refreshStatus()
    if (currentAppId === null) return
    return restore(currentAppId)
  }

  async function resume() {
    if (legacyMode.value) {
      await legacy.resume()
      return
    }
    if (!task.value || currentAppId === null || !['PAUSED', 'INTERRUPTED'].includes(task.value.status)) return
    const previousTask = task.value
    const previousState = snapshot()
    const context = begin(currentAppId, true)
    try {
      const next = await controlGenerationTask(previousTask.taskId, 'resume', context.controller.signal)
      if (!context.current()) return
      // Replay the newly appended queued event, never an older paused terminal.
      lastEventId.value = String(BigInt(next.lastEventId) > 0n ? BigInt(next.lastEventId) - 1n : 0n)
      applyTask(next)
      await subscribe(next, context)
    } catch (caught) {
      if (context.current()) {
        task.value = previousTask
        replaceState(previousState)
        controlError.value = errorMessage(caught)
      }
    } finally {
      if (context.id === runId.value) activeController = null
    }
  }

  // Compatibility name: this cancels the local subscription, never the server task.
  function cancel() {
    if (legacyMode.value) legacy.cancel()
    activeController?.abort()
    activeController = null
  }

  function reset() {
    legacyMode.value = false
    legacy.reset()
    requestId.value = null
    controlError.value = null
    runId.value += 1
    cancel()
    currentAppId = null
    task.value = null
    lastEventId.value = '0'
    retryAllowed.value = false
    connectionMessage.value = ''
    replaceState(initialState())
  }

  return { requestId, controlError, pause, resume, refreshStatus, status, phase, events, files, error, runId, task, lastEventId, retryAllowed, connectionMessage, start, restore, cancel, reset }
})
