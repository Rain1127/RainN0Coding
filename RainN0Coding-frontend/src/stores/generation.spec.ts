import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { marked } from 'marked'
import { useSSE } from '@/composables/useSSE'
import { MAX_SSE_BUFFER_SIZE } from '@/services/sseParser'
import type { GenerationState } from '@/types/generation'
import {
  MAX_GENERATION_EVENTS,
  applyGenerationEvent,
  useGenerationStore,
} from './generation'

function generationState(
  overrides: Partial<GenerationState> = {},
): GenerationState {
  return {
    status: 'idle',
    phase: null,
    events: [],
    files: [],
    error: null,
    ...overrides,
  }
}

function streamResponse(chunks: string[]): Response {
  const encoder = new TextEncoder()
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)))
      controller.close()
    },
  })
  return new Response(body, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream; charset=utf-8' },
  })
}

function proxyFrame(event: Record<string, unknown>): string {
  return `data: ${JSON.stringify({ d: JSON.stringify(event) })}\n\n`
}

function controllableStreamResponse(initialChunks: string[]) {
  const encoder = new TextEncoder()
  let streamController: ReadableStreamDefaultController<Uint8Array> | null = null
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      streamController = controller
      initialChunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)))
    },
  })

  return {
    response: new Response(body, {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    }),
    close() {
      streamController?.close()
    },
  }
}

function abortError() {
  const error = new Error('The operation was aborted')
  error.name = 'AbortError'
  return error
}

function abortableStreamResponse(
  signal: AbortSignal,
  initialChunks: string[] = [],
): Response {
  const encoder = new TextEncoder()
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      initialChunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)))
      signal.addEventListener(
        'abort',
        () => controller.error(abortError()),
        { once: true },
      )
    },
  })
  return new Response(body, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

function failingStreamResponse(firstChunk: string, error: Error): Response {
  const encoder = new TextEncoder()
  let sentFirstChunk = false
  const body = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (!sentFirstChunk) {
        sentFirstChunk = true
        controller.enqueue(encoder.encode(firstChunk))
        return
      }
      controller.error(error)
    },
  })
  return new Response(body, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

describe('applyGenerationEvent', () => {
  it('immutably appends a phase event and enters running', () => {
    const priorEvent = { type: 'queued' }
    const prior = generationState({ events: [priorEvent] })

    const next = applyGenerationEvent(prior, {
      type: 'phase_start',
      phase: 'architect',
    })

    expect(next).not.toBe(prior)
    expect(next.events).not.toBe(prior.events)
    expect(next.events).toEqual([
      priorEvent,
      { type: 'phase_start', phase: 'architect' },
    ])
    expect(next.phase).toBe('architect')
    expect(next.status).toBe('running')
    expect(prior).toEqual(generationState({ events: [priorEvent] }))
  })

  it('enriches duplicate file metadata without erasing richer values', () => {
    const sparse = applyGenerationEvent(generationState(), {
      type: 'code_file',
      path: 'src/App.vue',
    })
    const enriched = applyGenerationEvent(sparse, {
      type: 'code_file',
      file_path: 'src/App.vue',
      language: 'vue',
      size: 42,
    })
    const withSecondPath = applyGenerationEvent(enriched, {
      type: 'code_file',
      file_path: 'src/main.ts',
      language: 'typescript',
    })
    const laterSparse = applyGenerationEvent(withSecondPath, {
      type: 'code_file',
      path: 'src/App.vue',
    })

    expect(laterSparse.files).toEqual([
      { path: 'src/App.vue', language: 'vue', size: 42 },
      { path: 'src/main.ts', language: 'typescript' },
    ])
    expect(sparse.files).toEqual([{ path: 'src/App.vue', language: '' }])
  })

  it('retains file metadata without keeping code content in event history', () => {
    const codeFile = {
      type: 'code_file',
      path: 'src/App.vue',
      language: 'vue',
      size: 42,
      content: '<template>private source</template>',
      source: '<template>another source field</template>',
    }

    const next = applyGenerationEvent(generationState(), codeFile)

    expect(next.events).toEqual([
      {
        type: 'code_file',
        path: 'src/App.vue',
        language: 'vue',
        size: 42,
      },
    ])
    expect(next.files).toEqual([
      { path: 'src/App.vue', language: 'vue', size: 42 },
    ])
    expect(codeFile.content).toBe('<template>private source</template>')
  })

  it('collects only code_file events and ignores incidental paths', () => {
    const progress = applyGenerationEvent(generationState(), {
      type: 'progress',
      path: 'not-a-generated-file.ts',
      message: 'working',
    })
    const legacyFile = applyGenerationEvent(progress, {
      type: 'file',
      file_path: 'also-not-collected.ts',
    })

    expect(legacyFile.files).toEqual([])
  })

  it('does not replace a known numeric size with whitespace', () => {
    const initial = applyGenerationEvent(generationState(), {
      type: 'code_file',
      path: 'src/App.vue',
      size: 42,
    })
    const next = applyGenerationEvent(initial, {
      type: 'code_file',
      path: 'src/App.vue',
      size: '   ',
    })

    expect(next.files).toEqual([{ path: 'src/App.vue', language: '', size: 42 }])
  })

  it('keeps only the most recent bounded event history', () => {
    expect(MAX_GENERATION_EVENTS).toBe(200)
    let state = generationState()

    for (let index = 0; index < MAX_GENERATION_EVENTS + 5; index += 1) {
      state = applyGenerationEvent(state, {
        type: 'progress',
        message: String(index),
      })
    }

    expect(state.events).toHaveLength(MAX_GENERATION_EVENTS)
    expect(state.events[0]?.message).toBe('5')
    expect(state.events.at(-1)?.message).toBe('204')
  })

  it('marks error events failed without losing accumulated data', () => {
    const prior = generationState({
      status: 'running',
      events: [{ type: 'phase', phase: 'coder' }],
      files: [{ path: 'src/App.vue', language: 'vue' }],
    })

    const next = applyGenerationEvent(prior, {
      type: 'error',
      message: 'review failed',
    })

    expect(next.status).toBe('failed')
    expect(next.error).toBe('review failed')
    expect(next.events).toHaveLength(2)
    expect(next.files).toEqual(prior.files)
    expect(prior.status).toBe('running')
  })

  it('treats an error flag as a failure even without a type discriminator', () => {
    const next = applyGenerationEvent(generationState({ status: 'running' }), {
      error: true,
      code: 40100,
      message: '未登录',
    })

    expect(next.status).toBe('failed')
    expect(next.error).toBe('未登录')
    expect(next.events).toEqual([
      { error: true, code: 40100, message: '未登录' },
    ])
  })

  it.each([
    'success',
    'partial_success',
    'degraded_success',
    'duplicate_completed',
  ])('treats done status %s as successful', (status) => {
    const success = applyGenerationEvent(generationState({ status: 'running' }), {
      type: 'done',
      status,
    })

    expect(success.status).toBe('success')
    expect(success.phase).toBe('done')
    expect(success.error).toBeNull()
  })

  it('fails a done event with a real failure status', () => {
    const failure = applyGenerationEvent(generationState({ status: 'running' }), {
      type: 'done',
      status: 'failed',
    })

    expect(failure.status).toBe('failed')
    expect(failure.phase).toBe('done')
    expect(failure.error).toContain('failed')
  })

  it('does not let a later successful done event erase an earlier failure', () => {
    const failed = applyGenerationEvent(generationState({ status: 'running' }), {
      type: 'error',
      detail: 'unsafe output',
    })

    const next = applyGenerationEvent(failed, {
      type: 'done',
      status: 'success',
    })

    expect(next.status).toBe('failed')
    expect(next.error).toBe('unsafe output')
    expect(next.events).toHaveLength(2)
  })

  it('tolerates unknown event types and phases', () => {
    const next = applyGenerationEvent(generationState(), {
      type: 'future_progress_shape',
      phase: 'custom_agent',
      percent: 37,
    })

    expect(next.status).toBe('running')
    expect(next.phase).toBe('custom_agent')
    expect(next.events).toEqual([
      { type: 'future_progress_shape', phase: 'custom_agent', percent: 37 },
    ])
  })
})

describe('generation store stream lifecycle', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.stubEnv('VITE_API_BASE', '/api')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it('requests the SSE endpoint and makes a clean stream end successful', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      streamResponse([
        'data: {"type":"phase_start","phase":"co',
        'der"}\n\ndata: {"type":"code_file","path":"src/App.vue","language":"vue"}\n\n',
      ]),
    )
    vi.stubGlobal('fetch', fetchMock)
    const store = useGenerationStore()

    const run = store.start(7, 'build a dashboard & tests')

    expect(store.status).toBe('connecting')
    await run

    expect(fetchMock).toHaveBeenCalledOnce()
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe(
      '/api/app/chat/gen/code?appId=7&message=build%20a%20dashboard%20%26%20tests',
    )
    expect(init).toMatchObject({
      method: 'GET',
      credentials: 'include',
      headers: { Accept: 'text/event-stream' },
    })
    expect(init?.signal).toBeInstanceOf(AbortSignal)
    expect(store.status).toBe('success')
    expect(store.phase).toBe('coder')
    expect(store.events).toHaveLength(2)
    expect(store.files).toEqual([{ path: 'src/App.vue', language: 'vue' }])
    expect(store.error).toBeNull()
  })

  it('keeps files and events when a done event reports failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(
        streamResponse([
          'data: {"type":"code_file","path":"main.py","language":"python"}\n\n',
          'data: {"type":"done","status":"failed","message":"build failed"}\n\n',
        ]),
      ),
    )
    const store = useGenerationStore()

    await store.start(8, 'build a service')

    expect(store.status).toBe('failed')
    expect(store.phase).toBe('done')
    expect(store.error).toBe('build failed')
    expect(store.events).toHaveLength(2)
    expect(store.files).toEqual([{ path: 'main.py', language: 'python' }])
  })

  it('keeps a gateway business error failed through named done and EOF', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(
        streamResponse([
          'event: business-error\n' +
            'data: {"error":true,"code":40100,"message":"未登录"}\n\n' +
            'event: done\n' +
            'data: {}\n\n',
        ]),
      ),
    )
    const store = useGenerationStore()

    await store.start(8, 'requires login')

    expect(store.status).toBe('failed')
    expect(store.error).toBe('未登录')
    expect(store.events).toEqual([
      {
        error: true,
        code: 40100,
        message: '未登录',
        sse_event: 'business-error',
      },
      { sse_event: 'done' },
    ])
  })

  it('reports meaningful HTTP and missing-stream failures', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response('unavailable', {
          status: 503,
          statusText: 'Service Unavailable',
        }),
      )
      .mockResolvedValueOnce(
        new Response(null, {
          status: 200,
          headers: { 'Content-Type': 'text/event-stream' },
        }),
      )
    vi.stubGlobal('fetch', fetchMock)
    const store = useGenerationStore()

    await store.start(9, 'first')
    expect(store.status).toBe('failed')
    expect(store.error).toContain('HTTP 503')

    await store.start(9, 'second')
    expect(store.status).toBe('failed')
    expect(store.error).toContain('readable stream')
  })

  it('rejects an HTTP 200 response that is not an event stream', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(
        new Response('<html>login</html>', {
          status: 200,
          headers: { 'Content-Type': 'text/html; charset=utf-8' },
        }),
      ),
    )
    const store = useGenerationStore()

    await store.start(9, 'wrong response type')

    expect(store.status).toBe('failed')
    expect(store.error).toContain('text/event-stream')
    expect(store.events).toEqual([])
  })

  it('fails when every SSE frame is malformed', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(
        streamResponse([
          'data: nope\n\n' +
            'data: still-nope\n\n' +
            'event: done\n' +
            'data: \n\n',
        ]),
      ),
    )
    const store = useGenerationStore()

    await store.start(9, 'malformed response')

    expect(store.status).toBe('failed')
    expect(store.error).toContain('2 malformed')
    expect(store.events).toEqual([{ sse_event: 'done' }])
  })

  it('does not count named transport completion as a valid event', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(
        streamResponse(['event: done\ndata: {}\n\n']),
      ),
    )
    const store = useGenerationStore()

    await store.start(9, 'transport only')

    expect(store.status).toBe('failed')
    expect(store.error).toContain('without any valid events')
    expect(store.events).toEqual([{ sse_event: 'done' }])
  })

  it('fails when an SSE response ends without any event frames', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(streamResponse([])),
    )
    const store = useGenerationStore()

    await store.start(9, 'empty response')

    expect(store.status).toBe('failed')
    expect(store.error).toContain('without any valid events')
    expect(store.events).toEqual([])
  })

  it('fails closed and aborts when an SSE frame exceeds the buffer limit', async () => {
    let requestSignal: AbortSignal | undefined
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockImplementation((_url, init) => {
        requestSignal = init?.signal as AbortSignal
        return Promise.resolve(
          streamResponse(['x'.repeat(MAX_SSE_BUFFER_SIZE + 1)]),
        )
      }),
    )
    const store = useGenerationStore()

    await store.start(9, 'oversized response')

    expect(store.status).toBe('failed')
    expect(store.error).toContain('maximum buffer size')
    expect(requestSignal?.aborted).toBe(true)
    expect(store.events).toEqual([])
  })

  it('preserves received data when reading the stream throws', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(
        failingStreamResponse(
          'data: {"type":"code_file","path":"main.go","language":"go"}\n\n',
          new Error('connection lost'),
        ),
      ),
    )
    const store = useGenerationStore()

    await store.start(10, 'build a CLI')

    expect(store.status).toBe('failed')
    expect(store.error).toBe('connection lost')
    expect(store.events).toHaveLength(1)
    expect(store.files).toEqual([{ path: 'main.go', language: 'go' }])
  })

  it('cancels an active stream without clearing received data', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockImplementation((_url, init) =>
      Promise.resolve(
        abortableStreamResponse(init?.signal as AbortSignal, [
          'data: {"type":"code_file","path":"main.rs","language":"rust"}\n\n',
        ]),
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    const store = useGenerationStore()

    const run = store.start(11, 'build a parser')
    await vi.waitFor(() => expect(store.files).toHaveLength(1))
    store.cancel()
    await run

    expect(store.status).toBe('cancelled')
    expect(store.error).toBeNull()
    expect(store.events).toHaveLength(1)
    expect(store.files).toEqual([{ path: 'main.rs', language: 'rust' }])
  })

  it('preserves same-app retry data only when explicitly requested', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        streamResponse([
          'data: {"type":"code_file","path":"src/App.vue","language":"vue"}\n\n',
        ]),
      )
      .mockImplementationOnce((_url, init) =>
        Promise.resolve(abortableStreamResponse(init?.signal as AbortSignal)),
      )
    vi.stubGlobal('fetch', fetchMock)
    const store = useGenerationStore()

    await store.start(12, 'first attempt')
    const retry = store.start(12, 'retry', { preserve: true })

    expect(store.status).toBe('connecting')
    expect(store.events).toHaveLength(1)
    expect(store.files).toEqual([{ path: 'src/App.vue', language: 'vue' }])

    store.cancel()
    await retry
    expect(store.status).toBe('cancelled')
    expect(store.files).toHaveLength(1)
  })

  it('resets accumulated data for a normal run or a different app', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        streamResponse([
          'data: {"type":"code_file","path":"old.ts","language":"typescript"}\n\n',
        ]),
      )
      .mockResolvedValueOnce(
        streamResponse(['data: {"type":"done","status":"success"}\n\n']),
      )
    vi.stubGlobal('fetch', fetchMock)
    const store = useGenerationStore()

    await store.start(13, 'old run')
    await store.start(14, 'new run', { preserve: true })

    expect(store.status).toBe('success')
    expect(store.events).toEqual([{ type: 'done', status: 'success' }])
    expect(store.files).toEqual([])
  })

  it('prevents an older aborted run from overwriting a newer run', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockImplementationOnce((_url, init) =>
        Promise.resolve(
          abortableStreamResponse(init?.signal as AbortSignal, [
            'data: {"type":"phase_start","phase":"old_agent"}\n\n',
          ]),
        ),
      )
      .mockResolvedValueOnce(
        streamResponse(['data: {"type":"done","status":"success"}\n\n']),
      )
    vi.stubGlobal('fetch', fetchMock)
    const store = useGenerationStore()

    const olderRun = store.start(15, 'old')
    await vi.waitFor(() => expect(store.phase).toBe('old_agent'))
    const newerRun = store.start(16, 'new')
    await Promise.all([olderRun, newerRun])

    expect(store.status).toBe('success')
    expect(store.phase).toBe('done')
    expect(store.events).toEqual([{ type: 'done', status: 'success' }])
    expect(store.error).toBeNull()
  })

  it('reset aborts the active run and returns to idle', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockImplementation((_url, init) =>
      Promise.resolve(
        abortableStreamResponse(init?.signal as AbortSignal, [
          'data: {"type":"phase_start","phase":"builder"}\n\n',
        ]),
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    const store = useGenerationStore()

    const run = store.start(17, 'active run')
    await vi.waitFor(() => expect(store.events).toHaveLength(1))
    store.reset()
    await run

    expect(store.status).toBe('idle')
    expect(store.phase).toBeNull()
    expect(store.events).toEqual([])
    expect(store.files).toEqual([])
    expect(store.error).toBeNull()
  })
})

describe('useSSE compatibility wrapper', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.stubEnv('VITE_API_BASE', '/api')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it('forwards safe messages from real proxy events without exposing source', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(
        streamResponse([
          proxyFrame({
            type: 'phase_start',
            phase: 'coder',
            message: 'generating source',
          }),
          proxyFrame({
            type: 'code_file',
            path: 'src/App.vue',
            content: '<template>source must stay out of chat</template>',
          }),
          proxyFrame({ type: 'text_delta', text: 'hello ' }),
          proxyFrame({ type: 'message_delta', message: 'world' }),
          proxyFrame({ type: 'content_delta', content: '!' }),
          proxyFrame({ type: 'done', status: 'success' }),
          'event: done\ndata: \n\n',
        ]),
      ),
    )
    const chunks: string[] = []
    const onDone = vi.fn()
    const onError = vi.fn()
    const { content, isStreaming, startStream } = useSSE()

    const run = startStream(18, 'legacy page', (chunk) => chunks.push(chunk), onDone, onError)
    expect(isStreaming.value).toBe(true)
    await run

    expect(chunks).toEqual(['generating source', 'hello ', 'world', '\\!'])
    expect(content.value).toBe('generating sourcehello world\\!')
    expect(isStreaming.value).toBe(false)
    expect(onDone).toHaveBeenCalledOnce()
    expect(onError).not.toHaveBeenCalled()
  })

  it('escapes HTML metacharacters in every compatibility chunk', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(
        streamResponse([
          proxyFrame({
            type: 'workflow_start',
            message: `<script>alert("x")</script> & 'hello'`,
          }),
          proxyFrame({
            type: 'text_delta',
            text: `<img src=x onerror='boom'>`,
          }),
          proxyFrame({
            type: 'content_delta',
            content: `& < > " '`,
          }),
          proxyFrame({ type: 'done', status: 'success' }),
        ]),
      ),
    )
    const chunks: string[] = []
    const { content, startStream } = useSSE()

    await startStream(24, 'unsafe input', (chunk) => chunks.push(chunk), vi.fn(), vi.fn())

    expect(chunks).toEqual([
      '&lt;script&gt;alert\\(&quot;x&quot;\\)&lt;/script&gt; &amp; &#39;hello&#39;',
      '&lt;img src=x onerror=&#39;boom&#39;&gt;',
      '&amp; &lt; &gt; &quot; &#39;',
    ])
    expect(content.value).toBe(chunks.join(''))
    expect(content.value).not.toContain('<script>')
    expect(content.value).not.toContain('<img')
  })

  it('renders projected backend text as inert Markdown text', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(
        streamResponse([
          proxyFrame({
            type: 'workflow_start',
            message: [
              '你好，第一行 C:\\temp',
              '第二行 [click](javascript:alert(1)) ' +
                '![x](data:image/svg+xml,<svg onload=alert(1)>) ' +
                '<javascript:alert(1)> <script>alert(1)</script>',
            ].join('\n'),
          }),
          proxyFrame({ type: 'done', status: 'success' }),
        ]),
      ),
    )
    const { content, startStream } = useSSE()

    await startStream(27, 'markdown injection', vi.fn(), vi.fn(), vi.fn())

    const rendered = marked.parse(content.value) as string
    expect(content.value).toContain('你好，第一行')
    expect(content.value).toContain('\n第二行')
    expect(rendered).not.toMatch(/<(?:a|img|script)\b/i)
    expect(rendered).not.toMatch(/(?:href|src)=["'](?:javascript|data):/i)
    expect(rendered).toContain('[click](javascript:alert(1))')
    expect(rendered).toContain('![x](data:image/svg+xml,')
  })

  it('continues forwarding deltas after retained history reaches its cap', async () => {
    const frames = Array.from(
      { length: MAX_GENERATION_EVENTS + 5 },
      (_, index) => proxyFrame({ type: 'progress', percent: index }),
    )
    frames.push(
      proxyFrame({ type: 'content_delta', content: 'tail' }),
      proxyFrame({ type: 'done', status: 'success' }),
    )
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(streamResponse(frames)),
    )

    const chunks: string[] = []
    const onDone = vi.fn()
    const { content, startStream } = useSSE()

    await startStream(18, 'long run', (chunk) => chunks.push(chunk), onDone, vi.fn())

    expect(chunks).toEqual(['tail'])
    expect(content.value).toBe('tail')
    expect(onDone).toHaveBeenCalledOnce()
  })

  it('isolates callbacks and content across overlapping wrapper runs', async () => {
    const firstStream = controllableStreamResponse([
      proxyFrame({ type: 'content_delta', content: 'old' }),
    ])
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(firstStream.response)
      .mockResolvedValueOnce(
        streamResponse([
          proxyFrame({ type: 'content_delta', content: 'new' }),
          proxyFrame({ type: 'done', status: 'success' }),
        ]),
      )
    vi.stubGlobal('fetch', fetchMock)

    const firstChunks: string[] = []
    const secondChunks: string[] = []
    const firstDone = vi.fn()
    const firstError = vi.fn()
    const secondDone = vi.fn()
    const secondError = vi.fn()
    const { content, startStream } = useSSE()

    const firstRun = startStream(
      19,
      'old run',
      (chunk) => firstChunks.push(chunk),
      firstDone,
      firstError,
    )
    await vi.waitFor(() => expect(firstChunks).toEqual(['old']))

    const secondRun = startStream(
      20,
      'new run',
      (chunk) => secondChunks.push(chunk),
      secondDone,
      secondError,
    )
    await secondRun
    firstStream.close()
    await firstRun

    expect(firstChunks).toEqual(['old'])
    expect(firstDone).not.toHaveBeenCalled()
    expect(firstError).not.toHaveBeenCalled()
    expect(secondChunks).toEqual(['new'])
    expect(secondDone).toHaveBeenCalledOnce()
    expect(secondError).not.toHaveBeenCalled()
    expect(content.value).toBe('new')
  })

  it('isolates overlapping runs across separate wrapper instances', async () => {
    const firstStream = controllableStreamResponse([
      proxyFrame({ type: 'phase_start', message: 'old' }),
    ])
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(firstStream.response)
      .mockResolvedValueOnce(
        streamResponse([
          proxyFrame({ type: 'phase_start', message: 'new' }),
          proxyFrame({ type: 'done', status: 'success' }),
        ]),
      )
    vi.stubGlobal('fetch', fetchMock)

    const firstChunks: string[] = []
    const secondChunks: string[] = []
    const firstDone = vi.fn()
    const firstError = vi.fn()
    const secondDone = vi.fn()
    const first = useSSE()
    const second = useSSE()

    const firstRun = first.startStream(
      21,
      'old',
      (chunk) => firstChunks.push(chunk),
      firstDone,
      firstError,
    )
    await vi.waitFor(() => expect(firstChunks).toEqual(['old']))

    const secondRun = second.startStream(
      22,
      'new',
      (chunk) => secondChunks.push(chunk),
      secondDone,
      vi.fn(),
    )
    await secondRun
    firstStream.close()
    await firstRun

    expect(firstChunks).toEqual(['old'])
    expect(firstDone).not.toHaveBeenCalled()
    expect(firstError).not.toHaveBeenCalled()
    expect(first.isStreaming.value).toBe(false)
    expect(secondChunks).toEqual(['new'])
    expect(second.content.value).toBe('new')
    expect(secondDone).toHaveBeenCalledOnce()
  })

  it('does not expose a newer run error through an older wrapper instance', async () => {
    const firstStream = controllableStreamResponse([
      proxyFrame({ type: 'phase_start', message: 'old' }),
    ])
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(firstStream.response)
      .mockResolvedValueOnce(
        streamResponse([
          proxyFrame({ type: 'error', message: 'new run failed' }),
        ]),
      )
    vi.stubGlobal('fetch', fetchMock)
    const first = useSSE()
    const second = useSSE()

    const firstRun = first.startStream(25, 'old', vi.fn(), vi.fn(), vi.fn())
    await vi.waitFor(() => expect(first.content.value).toBe('old'))
    await second.startStream(26, 'new', vi.fn(), vi.fn(), vi.fn())

    expect(first.error.value).toBeNull()
    expect(second.error.value).toBe('new run failed')

    firstStream.close()
    await firstRun
  })

  it('passes preserve through the compatibility wrapper for same-app retries', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        streamResponse([
          proxyFrame({ type: 'code_file', path: 'src/App.vue', language: 'vue' }),
        ]),
      )
      .mockResolvedValueOnce(
        streamResponse([
          proxyFrame({ type: 'done', status: 'duplicate_completed' }),
        ]),
      )
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = useSSE()
    const store = useGenerationStore()

    await wrapper.startStream(23, 'first', vi.fn(), vi.fn(), vi.fn())
    await wrapper.startStream(23, 'retry', vi.fn(), vi.fn(), vi.fn(), {
      preserve: true,
    })

    expect(store.files).toEqual([{ path: 'src/App.vue', language: 'vue' }])
    expect(store.status).toBe('success')
  })
})
