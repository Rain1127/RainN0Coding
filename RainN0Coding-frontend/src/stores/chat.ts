import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { ChatMessage } from '@/types/chat'
import { getChatHistory } from '@/api/chatHistory'
import { getAppVO } from '@/api/app'
import type { AppVO } from '@/types/app'

export const useChatStore = defineStore('chat', () => {
  const currentAppId = ref<number | null>(null)
  const currentApp = ref<AppVO | null>(null)
  const messages = ref<ChatMessage[]>([])
  const isStreaming = ref(false)
  const streamError = ref<string | null>(null)

  function setAppId(appId: number) {
    currentAppId.value = appId
  }

  async function loadAppDetail(appId: number) {
    const app = await getAppVO(appId)
    currentApp.value = app
    currentAppId.value = appId
  }

  async function loadHistory(appId: number) {
    try {
      const res = await getChatHistory(appId, 100)
      const msgs: ChatMessage[] = (res.records || [])
        .sort((a, b) => new Date(a.createTime).getTime() - new Date(b.createTime).getTime())
        .map(h => ({
          id: String(h.id),
          role: h.messageType as 'user' | 'ai',
          content: h.message,
          timestamp: new Date(h.createTime).getTime(),
        }))
      messages.value = msgs
    } catch {
      messages.value = []
    }
  }

  function addMessage(msg: ChatMessage) {
    messages.value.push(msg)
  }

  function updateLastAiMessage(content: string) {
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'ai') {
      last.content = content
    }
  }

  function setStreaming(val: boolean) {
    isStreaming.value = val
  }

  function setStreamError(err: string | null) {
    streamError.value = err
  }

  function clearMessages() {
    messages.value = []
    streamError.value = null
  }

  return {
    currentAppId,
    currentApp,
    messages,
    isStreaming,
    streamError,
    setAppId,
    loadAppDetail,
    loadHistory,
    addMessage,
    updateLastAiMessage,
    setStreaming,
    setStreamError,
    clearMessages,
  }
})
