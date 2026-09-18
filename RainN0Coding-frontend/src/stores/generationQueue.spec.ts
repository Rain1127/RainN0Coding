import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useGenerationStore } from './generation'

function json(data: unknown, code = 0) {
  return new Response(JSON.stringify({ code, data, message: code ? '无权访问' : 'ok' }), {
    headers: { 'Content-Type': 'application/json' },
  })
}
function task(status = 'QUEUED', overrides = {}) {
  return { taskId: '9007199254740993123', appId: '7', status, errorMessage: null,
    lastEventId: '0', retryAllowed: false, ...overrides }
}
function stream(frames: string) {
  return new Response(frames, { headers: { 'Content-Type': 'text/event-stream' } })
}
const frame = (id: string, event: object) => `id: ${id}\ndata: ${JSON.stringify(event)}\n\n`

describe('durable generation task lifecycle', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.stubEnv('VITE_API_BASE', '/api')
  })
  afterEach(() => {
    useGenerationStore().reset()
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
    vi.useRealTimers()
  })

  it('submits a JSON task once and confirms success from the persisted task after EOF', async () => {
    const fetchMock = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(json(task()))
      .mockResolvedValueOnce(stream(frame('1', { type: 'queued', phase: 'queued' }) +
        frame('2', { type: 'code_file', path: 'src/App.vue', language: 'vue' })))
      .mockResolvedValueOnce(json(task('SUCCEEDED', { lastEventId: '2' })))
    vi.stubGlobal('fetch', fetchMock)
    const store = useGenerationStore()
    await store.start(7, 'build & test')
    const [url, init] = fetchMock.mock.calls[0]!
    expect(url).toBe('/api/app/generation/tasks')
    expect(init?.method).toBe('POST')
    expect(JSON.parse(init!.body as string)).toEqual({ appId: '7', message: 'build & test', idempotencyKey: expect.any(String) })
    expect(fetchMock.mock.calls[1]![0]).toBe('/api/app/generation/tasks/9007199254740993123/events?after=0')
    expect(store.status).toBe('success')
    expect(store.files).toEqual([{ path: 'src/App.vue', language: 'vue' }])
  })

  it('restores from event zero and deduplicates replayed cursors without submitting', async () => {
    const event = { type: 'phase_start', phase: 'coder', message: '编写代码' }
    const fetchMock = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(json(task('RUNNING', { lastEventId: '99' })))
      .mockResolvedValueOnce(stream(frame('9007199254740993123', event) + frame('9007199254740993123', event)))
      .mockResolvedValueOnce(json(task('SUCCEEDED')))
    vi.stubGlobal('fetch', fetchMock)
    const store = useGenerationStore()
    await store.restore(7)
    expect(fetchMock.mock.calls[0]![0]).toBe('/api/app/generation/tasks/latest?appId=7')
    expect(fetchMock.mock.calls[1]![0]).toContain('after=0')
    expect(fetchMock.mock.calls.every(([, init]) => init?.method !== 'POST')).toBe(true)
    expect(store.events).toHaveLength(1)
    expect(store.lastEventId).toBe('9007199254740993123')
    expect(store.status).toBe('success')
  })

  it.each(['SUCCEEDED', 'FAILED', 'INTERRUPTED'])('restores %s from snapshot when retained events expired', async (status) => {
    const snapshot = task(status, { errorMessage: 'worker interrupted', retryAllowed: status === 'INTERRUPTED', lastEventId: '42' })
    const fetchMock = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(json(snapshot))
      .mockResolvedValueOnce(stream(''))
      .mockResolvedValueOnce(json(snapshot))
    vi.stubGlobal('fetch', fetchMock)
    const store = useGenerationStore()
    await store.restore(7)
    expect(store.status).toBe(status === 'SUCCEEDED' ? 'success' : 'failed')
    expect(store.retryAllowed).toBe(status === 'INTERRUPTED')
    expect(store.error).toBe(status === 'SUCCEEDED' ? null : 'worker interrupted')
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('disconnects only the subscription and reopens the existing queued task', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValueOnce(json(task()))
      .mockImplementationOnce(async (_url, init) => new Response(new ReadableStream({
        start(controller) {
          controller.enqueue(new TextEncoder().encode(frame('1', { type: 'queued', phase: 'queued' })))
          init!.signal!.addEventListener('abort', () => controller.error(new DOMException('Aborted', 'AbortError')))
        },
      }), { headers: { 'Content-Type': 'text/event-stream' } }))
      .mockResolvedValueOnce(json(task('SUCCEEDED')))
      .mockResolvedValueOnce(stream(''))
      .mockResolvedValueOnce(json(task('SUCCEEDED')))
    vi.stubGlobal('fetch', fetchMock)
    const store = useGenerationStore()
    const run = store.start(7, 'hello')
    await vi.waitFor(() => expect(store.status).toBe('queued'))
    store.cancel()
    await run
    expect(store.status).toBe('queued')
    await store.restore(7)
    expect(store.status).toBe('success')
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1)
  })

  it('reconnects after an incomplete stream using the last cursor without creating another task', async () => {
    vi.useFakeTimers()
    const fetchMock = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(json(task()))
      .mockResolvedValueOnce(stream(frame('12', { type: 'phase_start', phase: 'coder' })))
      .mockResolvedValueOnce(json(task('RUNNING')))
      .mockResolvedValueOnce(stream(frame('13', { type: 'done', status: 'success' })))
      .mockResolvedValueOnce(json(task('SUCCEEDED')))
    vi.stubGlobal('fetch', fetchMock)
    const store = useGenerationStore()
    const run = store.start(7, 'hello')
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))
    expect(store.status).not.toBe('success')
    await vi.advanceTimersByTimeAsync(3000)
    await run
    expect(fetchMock.mock.calls[3]![0]).toContain('/events?after=12')
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1)
    expect(store.status).toBe('success')
  })

  it('rejects ownership errors without subscribing or retrying', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValueOnce(json(null, 40101))
    vi.stubGlobal('fetch', fetchMock)
    const store = useGenerationStore()
    await store.restore(7)
    expect(store.status).toBe('failed')
    expect(store.error).toBe('无权访问')
    expect(store.retryAllowed).toBe(false)
    expect(fetchMock).toHaveBeenCalledOnce()
  })

  it('does not claim success for an early done when the final save failed', async () => {
    const fetchMock = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(json(task()))
      .mockResolvedValueOnce(stream(frame('1', { type: 'done', status: 'success' })))
      .mockResolvedValueOnce(json(task('FAILED', { errorMessage: '文件保存失败', retryAllowed: true })))
    vi.stubGlobal('fetch', fetchMock)
    const store = useGenerationStore()
    await store.start(7, 'hello')
    expect(store.status).toBe('failed')
    expect(store.error).toBe('文件保存失败')
    expect(store.retryAllowed).toBe(true)
  })
  it('pauses a queued task without cancelling its progress subscription', async () => {
    let finish!: () => void
    const fetchMock = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(json(task()))
      .mockImplementationOnce(async () => new Response(new ReadableStream({ start(controller) {
        controller.enqueue(new TextEncoder().encode(frame('1', { type: 'queued' })))
        finish = () => controller.close()
      } }), { headers: { 'Content-Type': 'text/event-stream' } }))
      .mockResolvedValueOnce(json(task('PAUSED', { lastEventId: '2' })))
      .mockResolvedValueOnce(json(task('PAUSED', { lastEventId: '2' })))
    vi.stubGlobal('fetch', fetchMock)
    const store = useGenerationStore()
    const running = store.start(7, 'pause me')
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    await store.pause()
    expect(store.status).toBe('paused')
    expect(fetchMock.mock.calls[1]![1]?.signal?.aborted).toBe(false)
    expect(fetchMock.mock.calls[2]![0]).toContain('/pause')
    finish(); await running
  })

  it('resumes the same paused task once and skips its previous paused terminal', async () => {
    const fetchMock = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(json(task('PAUSED', { lastEventId: '2' })))
      .mockResolvedValueOnce(stream(frame('1', { type: 'queued' }) + frame('2', { type: 'done', status: 'paused' })))
      .mockResolvedValueOnce(json(task('PAUSED', { lastEventId: '2' })))
      .mockResolvedValueOnce(json(task('QUEUED', { lastEventId: '3' })))
      .mockResolvedValueOnce(stream(frame('3', { type: 'queued' }) + frame('4', { type: 'done', status: 'success' })))
      .mockResolvedValueOnce(json(task('SUCCEEDED', { lastEventId: '4' })))
    vi.stubGlobal('fetch', fetchMock)
    const store = useGenerationStore()
    await store.restore(7)
    expect(store.status).toBe('paused')
    await Promise.all([store.resume(), store.resume()])
    expect(store.status).toBe('success')
    expect(fetchMock.mock.calls[3]![0]).toContain('/9007199254740993123/resume')
    expect(fetchMock.mock.calls[4]![0]).toContain('after=2')
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1)
  })

  it('falls back to the legacy transport only for a missing queue endpoint', async () => {
    const fetchMock = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(new Response('', { status: 404 }))
      .mockResolvedValueOnce(stream('data: {"type":"done","status":"success"}\n\n'))
    vi.stubGlobal('fetch', fetchMock)
    const store = useGenerationStore()
    await store.start(7, 'legacy')
    expect(fetchMock.mock.calls[1]![0]).toContain('/app/chat/gen/code')
    expect(store.status).toBe('success')
  })

  it.each([500, 503])('never resubmits via legacy after HTTP %s', async (code) => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(new Response('', { status: code }))
    vi.stubGlobal('fetch', fetchMock)
    await useGenerationStore().start(7, 'uncertain response')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('restores a pre-upgrade paused run when no queue record exists', async () => {
    localStorage.setItem('generation-run:7', 'legacy-id')
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValueOnce(json(null))
      .mockResolvedValueOnce(json({ run_id: 'legacy-id', status: 'paused' }))
    vi.stubGlobal('fetch', fetchMock)
    const store = useGenerationStore()
    await store.restore(7)
    expect(store.status).toBe('paused')
    expect(store.requestId).toBe('legacy-id')
    expect(fetchMock.mock.calls[1]![0]).toContain('/chat/gen/status')
  })

})
