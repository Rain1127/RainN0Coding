import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { useLegacyGenerationStore, applyGenerationEvent } from './generationLegacy'

function stream(...events: Record<string, unknown>[]) {
  return new Response(events.map(event => `data: ${JSON.stringify({ d: JSON.stringify(event) })}\n\n`).join(''), {
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

describe('persistent generation pause and resume', () => {
  beforeEach(() => { setActivePinia(createPinia()); localStorage.clear(); vi.stubEnv('VITE_API_BASE', '/api') })
  afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs() })

  it('can start on an HTTP public IP without crypto.randomUUID', async () => {
    const getRandomValues = crypto.getRandomValues.bind(crypto)
    vi.stubGlobal('crypto', { getRandomValues })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(stream({ type: 'done', status: 'paused' })))
    const store = useLegacyGenerationStore()
    await store.start(7, 'build')
    expect(store.requestId).toMatch(/^[\da-f]{8}-[\da-f]{4}-4[\da-f]{3}-[89ab][\da-f]{3}-[\da-f]{12}$/i)
  })

  it('keeps the saved run if a concurrent resume is rejected through SSE', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(stream({ type: 'done', status: 'paused' }))
      .mockResolvedValueOnce(stream({ type: 'error', status: 'run_control_error', message: 'busy' }, { type: 'done', status: 'error' }))
    vi.stubGlobal('fetch', fetchMock)
    const store = useLegacyGenerationStore()
    await store.start(7, 'build')
    const id = store.requestId
    await store.resume()
    expect(store.status).toBe('paused')
    expect(localStorage.getItem('generation-run:7')).toBe(id)
    expect(store.controlError).toBe('busy')
    store.reset()
  })

  it('keeps pausing while the current node finishes and treats paused as nonterminal progress', () => {
    const state = { status: 'pausing' as const, phase: 'coder', events: [], files: [], error: null }
    const progress = applyGenerationEvent(state, { type: 'phase_end', phase: 'coder' })
    expect(progress.status).toBe('pausing')
    const paused = applyGenerationEvent(progress, { type: 'done', status: 'paused' })
    expect(paused.status).toBe('paused')
    expect(paused.phase).toBe('coder')
    expect(paused.error).toBeNull()
  })

  it('resumes with the original UUID and retains files and events without resending prompt', async () => {
    const fetchMock = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(stream({ type: 'code_file', path: 'main.py' }, { type: 'done', status: 'paused' }))
      .mockResolvedValueOnce(stream({ type: 'workflow_resumed' }, { type: 'done', status: 'success' }))
    vi.stubGlobal('fetch', fetchMock)
    const store = useLegacyGenerationStore()
    await store.start(7, 'build')
    const requestId = store.requestId
    expect(requestId).toMatch(/^[\da-f]{8}-[\da-f]{4}-4[\da-f]{3}-[89ab][\da-f]{3}-[\da-f]{12}$/i)
    expect(fetchMock.mock.calls[0][1]?.headers).toMatchObject({ 'Idempotency-Key': requestId })
    expect(store.status).toBe('paused')
    await Promise.all([store.resume(), store.resume()])
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(fetchMock.mock.calls[1][0]).toBe(`/api/app/chat/gen/resume?appId=7&runId=${requestId}`)
    expect(store.requestId).toBe(requestId)
    expect(store.files).toHaveLength(1)
    expect(store.events).toHaveLength(4)
    expect(store.status).toBe('success')
  })

  it('does not abort SSE on pause and recovers from control failure without failing generation', async () => {
    let end!: () => void
    const body = new ReadableStream({ start(controller) { end = () => controller.close() } })
    const fetchMock = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(body, { headers: { 'Content-Type': 'text/event-stream' } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ code: 50000, message: 'try again' })))
    vi.stubGlobal('fetch', fetchMock)
    const store = useLegacyGenerationStore()
    const running = store.start(7, 'build')
    await Promise.all([store.pause(), store.pause()])
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(fetchMock.mock.calls[1][0]).toBe('/api/app/chat/gen/pause')
    expect(JSON.parse(fetchMock.mock.calls[1][1]?.body as string)).toEqual({ appId: 7, runId: store.requestId })
    expect(fetchMock.mock.calls[0][1]?.signal?.aborted).toBe(false)
    expect(store.status).toBe('connecting')
    expect(store.error).toBeNull()
    expect(store.controlError).toBe('try again')
    store.cancel(); end(); await running
  })

  it('restores a paused run after a fresh store using the retained pointer and server status', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValueOnce(stream({ type: 'done', status: 'paused' }))
    vi.stubGlobal('fetch', fetchMock)
    const first = useLegacyGenerationStore()
    await first.start('7', 'build')
    const originalId = first.requestId
    setActivePinia(createPinia())
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ code: 0, data: { run_id: originalId, status: 'paused' } })))
    const restored = useLegacyGenerationStore()
    await restored.restore(7)
    expect(fetchMock.mock.calls[1][0]).toBe(`/api/app/chat/gen/status?appId=7&runId=${originalId}`)
    expect(restored.status).toBe('paused')
    expect(restored.requestId).toBe(originalId)
  })

  it('allows interrupted runs to resume and keeps their identity if reconnect fails', async () => {
    localStorage.setItem('generation-run:7', 'saved-run')
    const fetchMock = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(JSON.stringify({ code: 0, data: { run_id: 'saved-run', status: 'interrupted' } })))
      .mockRejectedValueOnce(new Error('network unavailable'))
    vi.stubGlobal('fetch', fetchMock)
    const store = useLegacyGenerationStore()
    await store.restore(7)
    expect(store.status).toBe('paused')
    store.phase = 'coder'
    await store.resume()
    expect(store.status).toBe('paused')
    expect(store.phase).toBe('coder')
    expect(store.requestId).toBe('saved-run')
    expect(store.error).toBeNull()
    expect(store.controlError).toBe('network unavailable')
  })

  it('keeps pause acknowledgement pending until the streamed checkpoint confirmation', async () => {
    let controller!: ReadableStreamDefaultController<Uint8Array>
    const fetchMock = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(new ReadableStream({ start(value) { controller = value } }), { headers: { 'Content-Type': 'text/event-stream' } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ code: 0, data: { run_id: 'run', status: 'pausing' } })))
    vi.stubGlobal('fetch', fetchMock)
    const store = useLegacyGenerationStore()
    const running = store.start(7, 'build')
    await store.pause()
    expect(store.status).toBe('pausing')
    await store.resume()
    expect(fetchMock).toHaveBeenCalledTimes(2)
    controller.enqueue(new TextEncoder().encode('data: {"type":"done","status":"paused"}\n\n'))
    controller.close()
    await running
    expect(store.status).toBe('paused')
    expect(store.error).toBeNull()
  })

  it('creates a UUID when a plain HTTP deployment has no crypto.randomUUID', async () => {
    const getRandomValues = crypto.getRandomValues.bind(crypto)
    vi.stubGlobal('crypto', { getRandomValues })
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockResolvedValueOnce(stream({ type: 'done', status: 'success' })))
    const store = useLegacyGenerationStore()
    await store.start(7, 'build')
    expect(store.requestId).toMatch(/^[\da-f]{8}-[\da-f]{4}-4[\da-f]{3}-[89ab][\da-f]{3}-[\da-f]{12}$/i)
  })
})
