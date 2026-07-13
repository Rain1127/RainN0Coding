import { defineStore } from 'pinia'
import { ref } from 'vue'
import { createSseParser } from '@/services/sseParser'
import type {
  GeneratedFile,
  GenerationEvent,
  GenerationState,
  GenerationStatus,
} from '@/types/generation'

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

  let activeController: AbortController | null = null
  let currentAppId: number | null = null

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

  async function start(
    appId: number,
    prompt: string,
    options: StartGenerationOptions = {},
  ): Promise<void> {
    const currentRunId = ++runId.value
    activeController?.abort()

    const controller = new AbortController()
    activeController = controller

    const preserve = options.preserve === true && currentAppId === appId
    currentAppId = appId
    replaceState({
      ...initialState(),
      status: 'connecting',
      events: preserve ? events.value : [],
      files: preserve ? files.value : [],
    })

    const baseUrl = import.meta.env.VITE_API_BASE ?? ''
    const url =
      `${baseUrl}/app/chat/gen/code` +
      `?appId=${encodeURIComponent(String(appId))}` +
      `&message=${encodeURIComponent(prompt)}`

    try {
      const response = await fetch(url, {
        method: 'GET',
        signal: controller.signal,
        credentials: 'include',
        headers: { Accept: 'text/event-stream' },
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
      const parser = createSseParser((event) => {
        if (currentRunId !== runId.value || controller.signal.aborted) return
        if (!isTransportCompletion(event)) validEventCount += 1
        replaceState(applyGenerationEvent(snapshot(), event))
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
      }
    } catch (caught) {
      if (currentRunId !== runId.value) return
      if (controller.signal.aborted || isAbortError(caught)) {
        if (status.value !== 'cancelled') status.value = 'cancelled'
        return
      }
      if (status.value !== 'failed') {
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

  function cancel() {
    if (!activeController) return
    status.value = 'cancelled'
    error.value = null
    const controller = activeController
    activeController = null
    controller.abort()
  }

  function reset() {
    runId.value += 1
    activeController?.abort()
    activeController = null
    currentAppId = null
    replaceState(initialState())
  }

  return {
    status,
    phase,
    events,
    files,
    error,
    runId,
    start,
    cancel,
    reset,
  }
})
