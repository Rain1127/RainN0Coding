import { describe, expect, it } from 'vitest'
import { MAX_SSE_BUFFER_SIZE, createSseParser } from './sseParser'

describe('createSseParser', () => {
  it('reassembles a frame split across arbitrary chunks', () => {
    const events: unknown[] = []
    const parser = createSseParser((event) => events.push(event))

    parser.push('da')
    parser.push('ta: {"type":"phase","phase":"arch')
    parser.push('itect","message":"designing"}\n')
    parser.push('\n')

    expect(events).toEqual([
      { type: 'phase', phase: 'architect', message: 'designing' },
    ])
  })

  it('parses multiple LF-delimited frames from one chunk', () => {
    const events: unknown[] = []
    const parser = createSseParser((event) => events.push(event))

    parser.push(
      'data: {"type":"code_file","path":"src/App.vue","language":"vue","size":42}\n\n' +
        'data: {"type":"done","status":"success"}\n\n',
    )

    expect(events).toEqual([
      {
        type: 'code_file',
        path: 'src/App.vue',
        language: 'vue',
        size: 42,
      },
      { type: 'done', status: 'success' },
    ])
  })

  it('supports CRLF boundaries and joins multiple data fields with newlines', () => {
    const events: unknown[] = []
    const parser = createSseParser((event) => events.push(event))

    parser.push('data: {"type":"phase",\r\ndata: "phase":"coder"}\r\n\r\n')

    expect(events).toEqual([{ type: 'phase', phase: 'coder' }])
  })

  it('supports CR-only lines and blank-frame boundaries', () => {
    const events: unknown[] = []
    const parser = createSseParser((event) => events.push(event))

    parser.push('data: {"type":"phase",\rdata: "phase":"reviewer"}\r\r')

    expect(events).toEqual([{ type: 'phase', phase: 'reviewer' }])
  })

  it('ignores comments, empty frames, and unknown non-data fields', () => {
    const events: unknown[] = []
    const malformed: string[] = []
    const parser = createSseParser(
      (event) => events.push(event),
      (payload) => malformed.push(payload),
    )

    parser.push(
      ': keepalive\n\n\n\nevent: progress\nid: 7\nretry: 1000\n' +
        'data: {"type":"phase","phase":"pm"}\n\n',
    )

    expect(events).toEqual([
      { type: 'phase', phase: 'pm', sse_event: 'progress' },
    ])
    expect(malformed).toEqual([])
  })

  it('unwraps a JSON event from a string d property', () => {
    const events: unknown[] = []
    const parser = createSseParser((event) => events.push(event))

    parser.push(
      'data: {"d":"{\\"type\\":\\"done\\",\\"status\\":\\"success\\"}"}\n\n',
    )

    expect(events).toEqual([{ type: 'done', status: 'success' }])
  })

  it('preserves named business errors and transport completion frames', () => {
    const events: unknown[] = []
    const parser = createSseParser((event) => events.push(event))

    parser.push(
      'event: business-error\n' +
        'data: {"error":true,"code":40100,"message":"未登录"}\n\n' +
        'event: done\n' +
        'data: {}\n\n',
    )

    expect(events).toEqual([
      {
        error: true,
        code: 40100,
        message: '未登录',
        sse_event: 'business-error',
      },
      { sse_event: 'done' },
    ])
  })

  it('preserves a named transport completion frame with empty data', () => {
    const events: unknown[] = []
    const parser = createSseParser((event) => events.push(event))

    parser.push('event: done\ndata: \n\n')

    expect(events).toEqual([{ sse_event: 'done' }])
  })

  it('ignores named frames that contain no data field', () => {
    const events: unknown[] = []
    const parser = createSseParser((event) => events.push(event))

    parser.push('event: progress\nid: 7\n\n')

    expect(events).toEqual([])
  })

  it('reports malformed payloads and continues with later valid frames', () => {
    const events: unknown[] = []
    const malformed: string[] = []
    const parser = createSseParser(
      (event) => events.push(event),
      (payload) => malformed.push(payload),
    )

    parser.push('data: nope\n\ndata: {"type":"done","status":"success"}\n\n')

    expect(malformed).toEqual(['nope'])
    expect(events).toEqual([{ type: 'done', status: 'success' }])
  })

  it('propagates consumer callback errors without reporting malformed input', () => {
    const malformed: string[] = []
    const consumerError = new Error('consumer failed')
    const parser = createSseParser(
      () => {
        throw consumerError
      },
      (payload) => malformed.push(payload),
    )

    expect(() =>
      parser.push('data: {"type":"phase_start","phase":"coder"}\n\n'),
    ).toThrow(consumerError)
    expect(malformed).toEqual([])
  })

  it('rejects non-object events and non-string discriminators, then recovers', () => {
    const events: unknown[] = []
    const malformed: string[] = []
    const parser = createSseParser(
      (event) => events.push(event),
      (payload) => malformed.push(payload),
    )

    parser.push(
      'data: []\n\n' +
        'data: null\n\n' +
        'data: "text"\n\n' +
        'data: {"type":7}\n\n' +
        'data: {"phase":false}\n\n' +
        'data: {"status":{}}\n\n' +
        'data: {"sse_event":9}\n\n' +
        'data: {}\n\n' +
        'data: {"foo":"bar"}\n\n' +
        'data: {"type":"phase","message":7}\n\n' +
        'data: {"type":"phase","phase":"builder"}\n\n',
    )

    expect(malformed).toHaveLength(10)
    expect(events).toEqual([{ type: 'phase', phase: 'builder' }])
  })

  it('rejects a complete frame whose payload exceeds the limit', () => {
    const events: unknown[] = []
    const malformed: string[] = []
    const parser = createSseParser(
      (event) => events.push(event),
      (payload) => malformed.push(payload),
    )

    expect(() =>
      parser.push(
        `data: {"type":"progress","message":"${'x'.repeat(MAX_SSE_BUFFER_SIZE)}"}\n\n`,
      ),
    ).toThrow('maximum buffer size')

    expect(malformed).toEqual([
      expect.stringContaining('maximum buffer size'),
    ])
    expect(events).toEqual([])
  })

  it('drains many complete frames in order', () => {
    const events: unknown[] = []
    const parser = createSseParser((event) => events.push(event))
    const frameCount = 2_000

    parser.push(
      Array.from(
        { length: frameCount },
        (_, index) => `data: {"type":"progress","index":${index}}\n\n`,
      ).join(''),
    )

    expect(events).toHaveLength(frameCount)
    expect(events.map((event) => (event as { index: number }).index)).toEqual(
      Array.from({ length: frameCount }, (_, index) => index),
    )
  })

  it('fails closed when an unframed buffer exceeds the limit', () => {
    const events: unknown[] = []
    const malformed: string[] = []
    const parser = createSseParser(
      (event) => events.push(event),
      (payload) => malformed.push(payload),
    )

    expect(() => parser.push('x'.repeat(MAX_SSE_BUFFER_SIZE + 1))).toThrow(
      'maximum buffer size',
    )

    expect(malformed).toEqual([
      expect.stringContaining('maximum buffer size'),
    ])
    expect(events).toEqual([])
  })

  it('flushes one final non-blank frame and clears the buffer', () => {
    const events: unknown[] = []
    const parser = createSseParser((event) => events.push(event))

    parser.push('data: {"type":"phase","phase":"reviewer"}')
    parser.flush()
    parser.flush()

    expect(events).toEqual([{ type: 'phase', phase: 'reviewer' }])
  })
})
