import { defineStore } from 'pinia'
import { ref } from 'vue'
import { createSseParser } from '@/services/sseParser'
import { createGenerationTask, getGenerationTask, getLatestGenerationTask, generationTaskUrl, GenerationRequestError } from '@/api/generation'
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
    if (state.status !== 'failed' && state.status !== 'cancelled') {
      next.status = 'running'
    }
  }

  if (event.type === 'queued') next.status = 'queued'

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
  return task.status === 'SUCCEEDED' || task.status === 'FAILED' || task.status === 'INTERRUPTED'
}

export const useGenerationStore = defineStore('generation', () => {
  const status = ref<GenerationStatus>('idle')
  const phase = ref<GenerationState['phase']>(null)
  const events = ref<GenerationEvent[]>([])
  const files = ref<GeneratedFile[]>([])
  const error = ref<string | null>(null)
  const runId = ref(0)
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

  function applyTask(next: GenerationTask) {
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
      status.value = next.status === 'QUEUED' ? 'queued' : 'running'
      if (next.status === 'QUEUED') phase.value = 'queued'
      error.value = null
    }
  }

  function begin(appId: EntityId, preserve = false) {
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
      if (!next) { replaceState(initialState()); return }
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
      pendingSubmission = { appId: String(appId), prompt, key: crypto.randomUUID() }
    }
    const submission = pendingSubmission
    await runTask(context, async () => {
      const next = await createGenerationTask(appId, prompt, submission.key, context.controller.signal)
      if (pendingSubmission === submission) pendingSubmission = null
      return next
    })
  }

  async function restore(appId: EntityId): Promise<void> {
    const context = begin(appId)
    await runTask(context, () => getLatestGenerationTask(appId, context.controller.signal))
  }

  // Compatibility name: this cancels the local subscription, never the server task.
  function cancel() {
    activeController?.abort()
    activeController = null
  }

  function reset() {
    runId.value += 1
    cancel()
    currentAppId = null
    task.value = null
    lastEventId.value = '0'
    retryAllowed.value = false
    connectionMessage.value = ''
    replaceState(initialState())
  }

  return { status, phase, events, files, error, runId, task, lastEventId, retryAllowed, connectionMessage, start, restore, cancel, reset }
})
