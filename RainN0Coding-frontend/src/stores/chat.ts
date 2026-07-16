import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { ChatMessage } from '@/types/chat'
import { getChatHistory } from '@/api/chatHistory'
import { getAppVO } from '@/api/app'
import type { AppVO } from '@/types/app'
import type { EntityId } from '@/types/entity'
import { sameEntityId } from '@/utils/entityId'

export const useChatStore = defineStore('chat', () => {
  const currentAppId = ref<EntityId | null>(null)
  const currentApp = ref<AppVO | null>(null)
  const messages = ref<ChatMessage[]>([])
  const isStreaming = ref(false)
  const streamError = ref<string | null>(null)
  const appLoading = ref(false)
  const historyLoading = ref(false)
  const appError = ref<string | null>(null)
  const historyError = ref<string | null>(null)
  let appRequestSequence = 0
  let historyRequestSequence = 0

  function errorMessage(error: unknown, fallback: string) {
    return error instanceof Error && error.message ? error.message : fallback
  }

  function resetForApp(appId: EntityId) {
    if (sameEntityId(currentAppId.value, appId)) return
    appRequestSequence += 1
    historyRequestSequence += 1
    currentAppId.value = appId
    currentApp.value = null
    messages.value = []
    isStreaming.value = false
    streamError.value = null
    appLoading.value = false
    historyLoading.value = false
    appError.value = null
    historyError.value = null
  }

  function setAppId(appId: EntityId) {
    resetForApp(appId)
  }

  function ensureAppContext(appId: EntityId) {
    if (currentAppId.value === null) {
      currentAppId.value = appId
    } else {
      resetForApp(appId)
    }
  }

  async function loadAppDetail(appId: EntityId) {
    ensureAppContext(appId)
    const requestSequence = ++appRequestSequence
    appLoading.value = true
    appError.value = null
    try {
      const app = await getAppVO(appId)
      if (requestSequence !== appRequestSequence || !sameEntityId(currentAppId.value, appId)) return
      currentApp.value = app
    } catch (error) {
      if (requestSequence === appRequestSequence && sameEntityId(currentAppId.value, appId)) {
        appError.value = errorMessage(error, '应用详情加载失败')
      }
      throw error
    } finally {
      if (requestSequence === appRequestSequence && sameEntityId(currentAppId.value, appId)) {
        appLoading.value = false
      }
    }
  }

  async function loadHistory(appId: EntityId) {
    ensureAppContext(appId)
    const requestSequence = ++historyRequestSequence
    const messageIdsAtRequestStart = new Set(messages.value.map(message => message.id))
    historyLoading.value = true
    historyError.value = null
    try {
      const res = await getChatHistory(appId, 50)
      const msgs: ChatMessage[] = (res.records || [])
        .sort((a, b) => new Date(a.createTime).getTime() - new Date(b.createTime).getTime())
        .map(h => ({
          id: String(h.id),
          role: h.messageType as 'user' | 'ai',
          content: h.message,
          timestamp: new Date(h.createTime).getTime(),
        }))
      if (requestSequence !== historyRequestSequence || !sameEntityId(currentAppId.value, appId)) return
      const messagesAddedDuringRequest = messages.value.filter(
        message => !messageIdsAtRequestStart.has(message.id),
      )
      messages.value = [...msgs, ...messagesAddedDuringRequest]
    } catch (error) {
      if (requestSequence === historyRequestSequence && sameEntityId(currentAppId.value, appId)) {
        historyError.value = errorMessage(error, '对话历史加载失败')
      }
      throw error
    } finally {
      if (requestSequence === historyRequestSequence && sameEntityId(currentAppId.value, appId)) {
        historyLoading.value = false
      }
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
    appLoading,
    historyLoading,
    appError,
    historyError,
    resetForApp,
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
