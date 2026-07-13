<template>
  <ChatLayout>
    <div class="flex-1 flex flex-col h-full">
      <!-- Header -->
      <div class="flex items-center justify-between px-4 py-3 border-b border-gpt-border">
        <h2 class="text-base font-medium text-gpt-text truncate">{{ chatStore.currentApp?.appName || '加载中...' }}</h2>
        <div class="flex items-center gap-1">
          <a-button type="text" size="small"><StarOutlined class="text-gpt-text-muted" /></a-button>
          <a-dropdown>
            <a-button type="text" size="small"><MoreOutlined class="text-gpt-text-muted" /></a-button>
            <template #overlay>
              <a-menu>
                <a-menu-item @click="showRename = true"><EditOutlined /> 重命名</a-menu-item>
                <a-menu-item danger @click="handleDelete"><DeleteOutlined /> 删除</a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
        </div>
      </div>

      <!-- Messages -->
      <div ref="msgContainer" class="flex-1 overflow-y-auto">
        <div v-if="chatStore.messages.length === 0 && !chatStore.isStreaming" class="flex items-center justify-center h-full">
          <div class="text-center text-gpt-text-muted">
            <p class="text-lg mb-2">开始对话</p>
            <p class="text-sm">输入你的需求，AI 将为你生成代码</p>
          </div>
        </div>
        <div v-for="msg in chatStore.messages" :key="msg.id" class="py-6" :class="msg.role === 'user' ? 'bg-gpt-bg' : 'bg-gpt-bg-alt'">
          <div class="max-w-[768px] mx-auto px-4 flex gap-4">
            <div class="w-7 h-7 rounded-full flex items-center justify-center shrink-0 text-xs font-medium" :class="msg.role === 'user' ? 'bg-gpt-accent text-white' : 'bg-purple-500 text-white'">
              {{ msg.role === 'user' ? auth.userName?.charAt(0) : 'AI' }}
            </div>
            <div class="flex-1 min-w-0">
              <div v-if="msg.role === 'ai'" class="markdown-body" v-html="renderMarkdown(msg.content)" />
              <div v-else class="text-gpt-text leading-relaxed whitespace-pre-wrap">{{ msg.content }}</div>
              <div v-if="msg.isStreaming" class="inline-block w-2 h-4 bg-gpt-accent animate-pulse ml-0.5 align-middle" />
            </div>
          </div>
          <div v-if="msg.role === 'ai' && !msg.isStreaming" class="max-w-[768px] mx-auto px-4 flex gap-4 mt-2">
            <div class="w-7 shrink-0" />
            <div class="flex items-center gap-2">
              <a-button type="text" size="small" @click="handleCopy(msg.content)"><CopyOutlined class="text-gpt-text-muted" /></a-button>
              <a-button type="text" size="small"><LikeOutlined class="text-gpt-text-muted" /></a-button>
              <a-button type="text" size="small"><DislikeOutlined class="text-gpt-text-muted" /></a-button>
            </div>
          </div>
        </div>
        <div v-if="chatStore.streamError" class="text-center py-4">
          <span class="text-red-500 text-sm">{{ chatStore.streamError }}</span>
          <a-button type="link" size="small" @click="handleRetry">重试</a-button>
        </div>
      </div>

      <!-- Input -->
      <div class="px-4 py-3 border-t border-gpt-border">
        <div class="max-w-[768px] mx-auto">
          <div class="relative bg-gpt-bg border border-gpt-border rounded-xl shadow-sm">
            <a-textarea
              v-model:value="inputText"
              :auto-size="{ minRows: 1, maxRows: 6 }"
              placeholder="输入你的问题..."
              class="chat-input"
              :disabled="chatStore.isStreaming"
              @press-enter="handleSend"
            />
            <div class="flex items-center justify-between px-3 pb-3">
              <a-button type="text" size="small" class="text-gpt-text-muted">
                <ThunderboltOutlined /> 深度思考
              </a-button>
              <a-button type="primary" shape="circle" size="small" :disabled="!inputText.trim() || chatStore.isStreaming" @click="handleSend">
                <SendOutlined v-if="!chatStore.isStreaming" />
                <span v-else class="inline-block w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
              </a-button>
            </div>
          </div>
          <p class="text-xs text-gpt-text-muted text-center mt-2">Enter 发送，Shift + Enter 换行</p>
        </div>
      </div>
    </div>

    <!-- Rename Modal -->
    <a-modal v-model:open="showRename" title="重命名应用" @ok="handleRename" :confirm-loading="renaming">
      <a-input v-model:value="newAppName" placeholder="输入新名称" />
    </a-modal>
  </ChatLayout>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { StarOutlined, MoreOutlined, EditOutlined, DeleteOutlined, CopyOutlined, LikeOutlined, DislikeOutlined, ThunderboltOutlined, SendOutlined } from '@ant-design/icons-vue'
import ChatLayout from '@/layouts/ChatLayout.vue'
import { useChatStore } from '@/stores/chat'
import { useAuthStore } from '@/stores/auth'
import { useSSE } from '@/composables/useSSE'
import { useMarkdown } from '@/composables/useMarkdown'
import { updateApp, deleteApp as deleteAppApi } from '@/api/app'

const route = useRoute()
const router = useRouter()
const chatStore = useChatStore()
const auth = useAuthStore()
const { isStreaming, startStream, stop } = useSSE()
const { render: renderMarkdown } = useMarkdown()

const inputText = ref('')
const msgContainer = ref<HTMLElement>()
const showRename = ref(false)
const newAppName = ref('')
const renaming = ref(false)

const appId = Number(route.params.appId)

onMounted(async () => {
  chatStore.clearMessages()
  await chatStore.loadAppDetail(appId)
  await chatStore.loadHistory(appId)
  await nextTick()
  scrollToBottom()

  const sendMsg = route.query.send as string
  if (sendMsg) {
    inputText.value = sendMsg
    await nextTick()
    doSend(sendMsg)
    router.replace({ path: route.path, query: {} })
  }
})

watch(() => chatStore.messages.length, () => {
  nextTick(() => scrollToBottom())
})

function scrollToBottom() {
  if (msgContainer.value) {
    msgContainer.value.scrollTop = msgContainer.value.scrollHeight
  }
}

async function handleSend(e: KeyboardEvent) {
  if (e.shiftKey) return
  e.preventDefault()
  const text = inputText.value.trim()
  if (!text || chatStore.isStreaming) return
  doSend(text)
}

async function doSend(text: string) {
  inputText.value = ''

  chatStore.addMessage({
    id: `user-${Date.now()}`,
    role: 'user',
    content: text,
    timestamp: Date.now(),
  })
  await nextTick()
  scrollToBottom()

  const aiMsgId = `ai-${Date.now()}`
  chatStore.addMessage({
    id: aiMsgId,
    role: 'ai',
    content: '',
    timestamp: Date.now(),
    isStreaming: true,
  })
  chatStore.setStreaming(true)

  await startStream(
    appId,
    text,
    (chunk) => {
      chatStore.updateLastAiMessage(
        chatStore.messages[chatStore.messages.length - 1].content + chunk
      )
      nextTick(() => scrollToBottom())
    },
    () => {
      const lastMsg = chatStore.messages[chatStore.messages.length - 1]
      if (lastMsg) lastMsg.isStreaming = false
      chatStore.setStreaming(false)
    },
    (err) => {
      chatStore.setStreamError(err)
      const lastMsg = chatStore.messages[chatStore.messages.length - 1]
      if (lastMsg) lastMsg.isStreaming = false
    }
  )
}

function handleRetry() {
  chatStore.setStreamError(null)
  const lastUserMsg = [...chatStore.messages].reverse().find(m => m.role === 'user')
  if (lastUserMsg) {
    chatStore.messages.pop()
    doSend(lastUserMsg.content)
  }
}

async function handleCopy(content: string) {
  try {
    await navigator.clipboard.writeText(content)
    message.success('已复制')
  } catch {
    message.error('复制失败')
  }
}

async function handleRename() {
  if (!newAppName.value.trim()) return
  renaming.value = true
  try {
    await updateApp({ id: appId, appName: newAppName.value.trim() })
    chatStore.currentApp!.appName = newAppName.value.trim()
    showRename.value = false
    message.success('已重命名')
  } finally {
    renaming.value = false
  }
}

async function handleDelete() {
  try {
    await deleteAppApi({ id: appId })
    message.success('已删除')
    router.push('/')
  } catch { /* handled */ }
}
</script>

<style scoped>
.chat-input :deep(textarea) {
  border: none !important;
  box-shadow: none !important;
  resize: none;
  font-size: 16px;
  line-height: 1.6;
  background: transparent;
}
</style>
