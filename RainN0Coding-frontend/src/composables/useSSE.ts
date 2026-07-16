import { computed, ref, watch } from 'vue'
import {
  useGenerationStore,
  type StartGenerationOptions,
} from '@/stores/generation'
import type { GenerationEvent } from '@/types/generation'
import type { EntityId } from '@/types/entity'

const DISPLAY_DELTA_TYPES = new Set([
  'text_delta',
  'message_delta',
  'content_delta',
])

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => {
    switch (character) {
      case '&':
        return '&amp;'
      case '<':
        return '&lt;'
      case '>':
        return '&gt;'
      case '"':
        return '&quot;'
      default:
        return '&#39;'
    }
  })
}

function escapeMarkdownText(value: string): string {
  const escapedBackslashes = value.replace(/\\/g, '\\\\')
  const escapedMarkdown = escapedBackslashes.replace(
    /([`*_[\]{}()#+\-.!|~])/g,
    '\\$1',
  )
  return escapeHtml(escapedMarkdown)
}

function displayChunk(event: GenerationEvent): string | null {
  if (!event.type || event.type === 'code_file') return null
  if (typeof event.message === 'string') return escapeMarkdownText(event.message)
  if (!DISPLAY_DELTA_TYPES.has(event.type)) return null
  if (typeof event.content === 'string') return escapeMarkdownText(event.content)
  if (typeof event.text === 'string') return escapeMarkdownText(event.text)
  return null
}

export function useSSE() {
  const generation = useGenerationStore()
  const ownedRunId = ref<number | null>(null)
  const isStreaming = computed(() => {
    const ownsActiveRun = ownedRunId.value === generation.runId
    const streamIsActive =
      generation.status === 'connecting' || generation.status === 'running'
    return ownsActiveRun && streamIsActive
  })
  const content = ref('')
  const error = computed(() =>
    ownedRunId.value === generation.runId ? generation.error : null,
  )

  async function startStream(
    appId: EntityId,
    message: string,
    onChunk: (text: string) => void,
    onDone: () => void,
    onError: (err: string) => void,
    options: StartGenerationOptions = {},
  ) {
    content.value = ''
    let expectedRunId: number | null = null
    let lastObservedEvent = generation.events.at(-1)
    const stopWatching = watch(
      () => generation.events,
      (currentEvents) => {
        if (expectedRunId === null || generation.runId !== expectedRunId) return
        const previousIndex = lastObservedEvent
          ? currentEvents.indexOf(lastObservedEvent)
          : -1
        for (const event of currentEvents.slice(previousIndex + 1)) {
          if (generation.runId !== expectedRunId) break
          const chunk = displayChunk(event)
          if (chunk === null) continue
          content.value += chunk
          onChunk(chunk)
        }
        if (generation.runId === expectedRunId) {
          lastObservedEvent = currentEvents.at(-1)
        }
      },
      { flush: 'sync' },
    )

    try {
      const run = generation.start(appId, message, options)
      expectedRunId = generation.runId
      ownedRunId.value = expectedRunId
      await run
      if (generation.runId !== expectedRunId) return
      if (generation.status === 'success') {
        onDone()
      } else if (generation.status === 'failed') {
        onError(generation.error ?? 'Generation stream failed')
      }
    } finally {
      stopWatching()
    }
  }

  function stop() {
    if (ownedRunId.value === generation.runId) generation.cancel()
    ownedRunId.value = null
  }

  return { isStreaming, content, error, startStream, stop }
}
