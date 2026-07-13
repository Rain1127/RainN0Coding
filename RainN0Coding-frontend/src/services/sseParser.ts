import type { GenerationEvent } from '@/types/generation'

export const MAX_SSE_BUFFER_SIZE = 1024 * 1024

export interface SseParser {
  push(chunk: string): void
  flush(): void
}

const OPTIONAL_STRING_FIELDS = [
  'phase',
  'status',
  'sse_event',
  'message',
  'text',
  'detail',
  'content',
  'source',
  'file_path',
  'path',
  'name',
  'language',
] as const

function isGenerationEvent(
  value: unknown,
  namedEvent?: string,
): value is GenerationEvent {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return false
  }

  const event = value as Record<string, unknown>
  if (
    !OPTIONAL_STRING_FIELDS.every(
      (field) => event[field] === undefined || typeof event[field] === 'string',
    ) ||
    (event.error !== undefined && typeof event.error !== 'boolean') ||
    (event.code !== undefined &&
      typeof event.code !== 'number' &&
      typeof event.code !== 'string') ||
    (event.size !== undefined &&
      typeof event.size !== 'number' &&
      typeof event.size !== 'string')
  ) {
    return false
  }

  if (typeof event.type === 'string') return true
  if (event.type !== undefined) return false

  if (namedEvent === 'done') return Object.keys(event).length === 0
  return namedEvent === 'business-error' && event.error === true
}

function lineEndingLengthAt(value: string, index: number): number {
  if (value[index] === '\r') return value[index + 1] === '\n' ? 2 : 1
  return value[index] === '\n' ? 1 : 0
}

function findFrameBoundary(value: string, start: number) {
  for (let index = start; index < value.length; index += 1) {
    const firstLength = lineEndingLengthAt(value, index)
    if (firstLength === 0) continue

    const secondLength = lineEndingLengthAt(value, index + firstLength)
    if (secondLength > 0) {
      return { index, length: firstLength + secondLength }
    }

    index += firstLength - 1
  }
  return null
}

export function createSseParser(
  onEvent: (event: GenerationEvent) => void,
  onMalformed: (payload: string) => void = () => undefined,
): SseParser {
  let buffer = ''
  let cursor = 0
  let scanFrom = 0

  function failOversizedFrame(): never {
    const message =
      `SSE frame exceeded maximum buffer size of ${MAX_SSE_BUFFER_SIZE}`
    buffer = ''
    cursor = 0
    scanFrom = 0
    onMalformed(message)
    throw new Error(message)
  }

  function parseFrame(frame: string) {
    const data: string[] = []
    let hasDataField = false
    let sseEvent: string | undefined

    for (const line of frame.split(/\r\n|\r|\n/)) {
      if (!line || line.startsWith(':')) continue

      const colonIndex = line.indexOf(':')
      const field = colonIndex === -1 ? line : line.slice(0, colonIndex)
      let value = colonIndex === -1 ? '' : line.slice(colonIndex + 1)
      if (value.startsWith(' ')) value = value.slice(1)

      if (field === 'data') {
        hasDataField = true
        data.push(value)
      }
      if (field === 'event') sseEvent = value
    }

    if (!hasDataField) return
    const payload = data.join('\n')

    let event: GenerationEvent
    try {
      const outer: unknown = payload ? JSON.parse(payload) : {}
      const isProxyWrapper =
        typeof outer === 'object' &&
        outer !== null &&
        !Array.isArray(outer) &&
        typeof (outer as Record<string, unknown>).d === 'string' &&
        Object.keys(outer).every((field) => field === 'd')
      const parsedEvent: unknown = isProxyWrapper
        ? JSON.parse((outer as Record<string, string>).d)
        : outer
      if (!isGenerationEvent(parsedEvent, sseEvent)) {
        throw new Error('SSE event does not match the generation protocol')
      }
      event = parsedEvent
    } catch {
      onMalformed(payload)
      return
    }

    onEvent(sseEvent ? { ...event, sse_event: sseEvent } : event)
  }

  function drainFrames() {
    while (true) {
      const boundary = findFrameBoundary(buffer, scanFrom)

      if (!boundary) {
        scanFrom = Math.max(cursor, buffer.length - 3)
        if (buffer.length - cursor > MAX_SSE_BUFFER_SIZE) failOversizedFrame()

        if (cursor > 0) {
          buffer = buffer.slice(cursor)
          scanFrom = Math.max(0, scanFrom - cursor)
          cursor = 0
        }
        return
      }

      if (boundary.index - cursor > MAX_SSE_BUFFER_SIZE) failOversizedFrame()

      const frame = buffer.slice(cursor, boundary.index)
      cursor = boundary.index + boundary.length
      scanFrom = cursor
      parseFrame(frame)
    }
  }

  return {
    push(chunk) {
      buffer += chunk
      drainFrames()
    },
    flush() {
      const finalFrame = buffer.slice(cursor)
      buffer = ''
      cursor = 0
      scanFrom = 0
      if (finalFrame.length > MAX_SSE_BUFFER_SIZE) failOversizedFrame()
      if (finalFrame.trim()) parseFrame(finalFrame)
    },
  }
}
