import { ref } from 'vue'

export function useSSE() {
  const isStreaming = ref(false)
  const content = ref('')
  const error = ref<string | null>(null)
  let abortController: AbortController | null = null

  async function startStream(
    appId: number,
    message: string,
    onChunk: (text: string) => void,
    onDone: () => void,
    onError: (err: string) => void
  ) {
    abortController = new AbortController()
    isStreaming.value = true
    content.value = ''
    error.value = null

    const baseUrl = import.meta.env.VITE_API_BASE
    const url = `${baseUrl}/app/chat/gen/code?appId=${appId}&message=${encodeURIComponent(message)}`

    try {
      const response = await fetch(url, {
        signal: abortController.signal,
        credentials: 'include',
        headers: { 'Accept': 'text/event-stream' },
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const reader = response.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          const trimmed = line.trim()
          if (trimmed.startsWith('data:')) {
            const jsonStr = trimmed.slice(5).trim()
            if (!jsonStr) continue
            try {
              const parsed = JSON.parse(jsonStr)
              if (parsed.d) {
                content.value += parsed.d
                onChunk(parsed.d)
              }
            } catch {
              // skip malformed data
            }
          }
          if (trimmed.startsWith('event:done') || trimmed.startsWith('event: done')) {
            isStreaming.value = false
            onDone()
            return
          }
          if (trimmed.startsWith('event:business-error') || trimmed.startsWith('event: business-error')) {
            // next data line will contain error message
          }
        }
      }

      // Stream ended
      isStreaming.value = false
      onDone()
    } catch (e: any) {
      if (e.name !== 'AbortError') {
        const errMsg = e.message || '流式请求失败'
        error.value = errMsg
        onError(errMsg)
      }
      isStreaming.value = false
    }
  }

  function stop() {
    abortController?.abort()
    isStreaming.value = false
  }

  return { isStreaming, content, error, startStream, stop }
}
