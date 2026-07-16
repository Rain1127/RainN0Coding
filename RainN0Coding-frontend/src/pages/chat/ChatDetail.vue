<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  CloudDownloadOutlined,
  CloudUploadOutlined,
  PauseCircleOutlined,
  SendOutlined,
} from '@ant-design/icons-vue'
import { deployApp, downloadApp } from '@/api/app'
import AgentProgress from '@/components/generation/AgentProgress.vue'
import GeneratedFileList from '@/components/generation/GeneratedFileList.vue'
import ChatLayout from '@/layouts/ChatLayout.vue'
import { useAppsStore } from '@/stores/apps'
import { useChatStore } from '@/stores/chat'
import { useGenerationStore } from '@/stores/generation'
import type { EntityId } from '@/types/entity'
import { normalizeEntityId, sameEntityId } from '@/utils/entityId'

const route = useRoute()
const router = useRouter()
const chat = useChatStore()
const apps = useAppsStore()
const generation = useGenerationStore()

const appId = computed(() => {
  const raw = Array.isArray(route.params.appId) ? route.params.appId[0] : route.params.appId
  return normalizeEntityId(raw)
})
const input = ref('')
const messageFeed = ref<HTMLElement | null>(null)
const deployPending = ref(false)
const downloadPending = ref(false)
const deployUrl = ref('')
const deployError = ref('')
const downloadError = ref('')
const lastPrompt = ref('')
let viewActive = true
let navigationSequence = 0
let consumedPromptNavigation = -1
let deployOperationSequence = 0
let downloadOperationSequence = 0

const hasCurrentApp = computed(() => (
  appId.value !== null && sameEntityId(chat.currentApp?.id, appId.value)
))

const isGenerating = computed(() => (
  generation.status === 'connecting' || generation.status === 'running'
))

const safeEventMessages = computed(() => generation.events
  .filter((event) => event.type !== 'code_file' && typeof event.message === 'string' && event.message.trim())
  .map((event, index) => ({
    id: `${event.type ?? 'event'}-${index}`,
    type: event.type ?? 'event',
    phase: typeof event.phase === 'string' ? event.phase : '',
    message: event.message!.trim(),
  })))

const safeDeploymentUrl = computed(() => {
  if (!deployUrl.value) return null
  try {
    const parsed = new URL(deployUrl.value)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? parsed.href : null
  } catch {
    return null
  }
})

function responseMediaType(response: Response) {
  return response.headers.get('content-type')?.split(';', 1)[0].trim().toLowerCase() ?? ''
}

async function downloadFailureMessage(response: Response) {
  if (responseMediaType(response) === 'application/json') {
    try {
      const body = await response.json() as { message?: unknown }
      if (typeof body.message === 'string' && body.message.trim()) return body.message.trim()
    } catch {
      // Fall through to a non-sensitive local error.
    }
  }
  return response.ok
    ? '下载响应格式不正确，请稍后重试。'
    : `项目下载失败（HTTP ${response.status}）。`
}

function routeInitialPrompt() {
  const state = router.options.history.state as Record<string, unknown>
  return typeof state.initialPrompt === 'string' ? state.initialPrompt.trim() : ''
}

async function consumeInitialPrompt(targetAppId: EntityId, requestSequence: number) {
  if (
    consumedPromptNavigation === requestSequence ||
    requestSequence !== navigationSequence ||
    !sameEntityId(appId.value, targetAppId) ||
    !sameEntityId(chat.currentApp?.id, targetAppId)
  ) return ''
  const prompt = routeInitialPrompt()
  consumedPromptNavigation = requestSequence
  if (!prompt) return ''
  const state = router.options.history.state as Record<string, unknown>
  router.options.history.replace(route.fullPath, {
    ...state,
    initialPrompt: undefined,
  })
  return prompt
}

function scrollToBottom() {
  nextTick(() => {
    if (messageFeed.value) messageFeed.value.scrollTop = messageFeed.value.scrollHeight
  })
}

async function maybeConsumeInitialPrompt(targetAppId: EntityId, requestSequence: number) {
  const prompt = await consumeInitialPrompt(targetAppId, requestSequence)
  if (prompt && viewActive && requestSequence === navigationSequence) {
    void startGeneration(prompt, false, true, targetAppId, requestSequence)
  }
}

async function loadApp(
  targetAppId: EntityId | null = appId.value,
  requestSequence = navigationSequence,
) {
  if (targetAppId === null) return false
  try {
    await chat.loadAppDetail(targetAppId)
    if (
      viewActive &&
      requestSequence === navigationSequence &&
      sameEntityId(appId.value, targetAppId) &&
      sameEntityId(chat.currentApp?.id, targetAppId)
    ) {
      await maybeConsumeInitialPrompt(targetAppId, requestSequence)
    }
    return true
  } catch {
    return false
  }
}

async function loadHistory(targetAppId: EntityId | null = appId.value) {
  if (targetAppId === null) return
  try {
    await chat.loadHistory(targetAppId)
  } catch {
    // The store exposes a targeted error while retaining existing messages.
  }
}

async function refreshAfterSuccess(targetAppId: EntityId) {
  await Promise.allSettled([
    chat.loadAppDetail(targetAppId),
    chat.loadHistory(targetAppId),
    apps.fetchRecentApps(),
  ])
}

async function startGeneration(
  prompt: string,
  preserve: boolean,
  addUserMessage: boolean,
  targetAppId: EntityId | null = appId.value,
  requestSequence = navigationSequence,
) {
  const normalized = prompt.trim()
  if (
    !normalized ||
    targetAppId === null ||
    !sameEntityId(chat.currentApp?.id, targetAppId) ||
    !sameEntityId(appId.value, targetAppId) ||
    requestSequence !== navigationSequence ||
    isGenerating.value
  ) return
  lastPrompt.value = normalized
  chat.setStreamError(null)
  if (addUserMessage) {
    chat.addMessage({
      id: `local-user-${Date.now()}`,
      role: 'user',
      content: normalized,
      timestamp: Date.now(),
    })
  }
  input.value = ''
  scrollToBottom()
  await generation.start(targetAppId, normalized, { preserve })
  if (
    !viewActive ||
    requestSequence !== navigationSequence ||
    !sameEntityId(appId.value, targetAppId) ||
    !sameEntityId(chat.currentApp?.id, targetAppId)
  ) return
  if (generation.status === 'success') {
    await refreshAfterSuccess(targetAppId)
    scrollToBottom()
  } else if (generation.status === 'failed') {
    chat.setStreamError(generation.error ?? '生成失败，请稍后重试。')
  }
}

function submit() {
  void startGeneration(input.value, false, true)
}

function handleComposerKeydown(event: KeyboardEvent) {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return
  event.preventDefault()
  submit()
}

function cancelGeneration() {
  generation.cancel()
}

function retryGeneration() {
  const prompt = lastPrompt.value || [...chat.messages].reverse().find((message) => message.role === 'user')?.content || ''
  if (prompt) void startGeneration(prompt, true, false)
}

async function handleDeploy() {
  const targetAppId = appId.value
  if (targetAppId === null || !sameEntityId(chat.currentApp?.id, targetAppId) || deployPending.value) return
  const requestNavigation = navigationSequence
  const operationSequence = ++deployOperationSequence
  const isCurrentOperation = () => (
    viewActive &&
    operationSequence === deployOperationSequence &&
    requestNavigation === navigationSequence &&
    sameEntityId(appId.value, targetAppId) &&
    sameEntityId(chat.currentApp?.id, targetAppId)
  )
  deployPending.value = true
  deployError.value = ''
  deployUrl.value = ''
  try {
    const result = await deployApp(targetAppId)
    if (!isCurrentOperation()) return
    deployUrl.value = result.trim()
    if (!safeDeploymentUrl.value) deployError.value = '服务返回了不安全的部署地址，已阻止打开。'
    await Promise.allSettled([chat.loadAppDetail(targetAppId)])
  } catch (caught) {
    if (isCurrentOperation()) {
      deployError.value = caught instanceof Error && caught.message
        ? caught.message
        : '部署失败，请稍后重试。'
    }
  } finally {
    if (isCurrentOperation()) deployPending.value = false
  }
}

async function handleDownload() {
  const targetAppId = appId.value
  if (targetAppId === null) return
  const currentApp = sameEntityId(chat.currentApp?.id, targetAppId) ? chat.currentApp : null
  if (!currentApp || downloadPending.value) return
  const requestNavigation = navigationSequence
  const operationSequence = ++downloadOperationSequence
  const isCurrentOperation = () => (
    viewActive &&
    operationSequence === downloadOperationSequence &&
    requestNavigation === navigationSequence &&
    sameEntityId(appId.value, targetAppId) &&
    sameEntityId(chat.currentApp?.id, targetAppId)
  )
  const appName = currentApp.appName
  downloadPending.value = true
  downloadError.value = ''
  let objectUrl = ''
  try {
    const response = await fetch(downloadApp(targetAppId), { credentials: 'include' })
    if (!isCurrentOperation()) return
    if (!response.ok || responseMediaType(response) !== 'application/zip') {
      throw new Error(await downloadFailureMessage(response))
    }
    if (!isCurrentOperation()) return
    const blob = await response.blob()
    if (!isCurrentOperation()) return
    objectUrl = URL.createObjectURL(blob)
    if (!isCurrentOperation()) return
    const anchor = document.createElement('a')
    anchor.href = objectUrl
    anchor.download = `${appName || `app-${targetAppId}`}.zip`
    if (!isCurrentOperation()) return
    anchor.click()
  } catch (caught) {
    if (isCurrentOperation()) {
      downloadError.value = caught instanceof Error && caught.message
        ? caught.message
        : '项目下载失败，请稍后重试。'
    }
  } finally {
    if (objectUrl) URL.revokeObjectURL(objectUrl)
    if (isCurrentOperation()) downloadPending.value = false
  }
}

async function loadRouteApp(targetAppId: EntityId | null) {
  const requestSequence = ++navigationSequence
  consumedPromptNavigation = -1
  deployOperationSequence += 1
  downloadOperationSequence += 1
  lastPrompt.value = ''
  input.value = ''
  deployPending.value = false
  downloadPending.value = false
  deployUrl.value = ''
  deployError.value = ''
  downloadError.value = ''

  if (isGenerating.value) generation.cancel()
  generation.reset()

  if (targetAppId === null) {
    await router.replace('/404')
    return
  }
  chat.resetForApp(targetAppId)
  void loadHistory(targetAppId)
  await loadApp(targetAppId, requestSequence)
}

watch(() => chat.messages.length, scrollToBottom)
watch(() => generation.events.length, scrollToBottom)
watch(appId, (targetAppId) => {
  void loadRouteApp(targetAppId)
}, { immediate: true })

onBeforeUnmount(() => {
  viewActive = false
  deployOperationSequence += 1
  downloadOperationSequence += 1
  if (isGenerating.value) generation.cancel()
  generation.reset()
})
</script>

<template>
  <ChatLayout>
    <div class="workbench">
      <header class="workbench__header">
        <div class="workbench__identity">
          <p class="workbench__eyebrow">Project workbench</p>
          <h1>{{ hasCurrentApp ? chat.currentApp?.appName : (chat.appLoading ? '正在加载项目…' : '项目工作台') }}</h1>
          <p v-if="hasCurrentApp && chat.currentApp" class="workbench__meta">
            <span class="mono">#{{ chat.currentApp.id }}</span>
            <span>{{ chat.currentApp.codeGenType }}</span>
            <span>版本 {{ chat.currentApp.currentVersion }}</span>
          </p>
        </div>
        <div v-if="hasCurrentApp" class="workbench__actions">
          <button type="button" class="button button--secondary" data-action="download" :disabled="downloadPending" @click="handleDownload">
            <CloudDownloadOutlined aria-hidden="true" />
            {{ downloadPending ? '正在准备…' : '下载代码' }}
          </button>
          <button type="button" class="button" data-action="deploy" :disabled="deployPending" @click="handleDeploy">
            <CloudUploadOutlined aria-hidden="true" />
            {{ deployPending ? '正在部署…' : '部署应用' }}
          </button>
        </div>
      </header>

      <div v-if="chat.appError" class="workbench-alert" data-error="app" role="alert">
        <span>应用详情加载失败：{{ chat.appError }}</span>
        <button type="button" data-retry="app" :disabled="chat.appLoading" @click="loadApp()">重试应用详情</button>
      </div>
      <div v-if="chat.historyError" class="workbench-alert" data-error="history" role="alert">
        <span>对话历史加载失败：{{ chat.historyError }}</span>
        <button type="button" data-retry="history" :disabled="chat.historyLoading" @click="loadHistory()">重试对话历史</button>
      </div>
      <div v-if="downloadError" class="workbench-alert" role="alert">{{ downloadError }}</div>
      <div v-if="deployUrl || deployError" class="workbench-alert" data-deploy-url :class="{ 'workbench-alert--success': safeDeploymentUrl }" role="status">
        <a v-if="safeDeploymentUrl" :href="safeDeploymentUrl" target="_blank" rel="noopener noreferrer">打开已部署应用</a>
        <span v-else>{{ deployError }}</span>
      </div>

      <div class="workbench__grid">
        <section class="conversation" aria-labelledby="conversation-title">
          <div class="panel-heading">
            <div>
              <p class="panel-heading__eyebrow">Conversation</p>
              <h2 id="conversation-title">需求与生成反馈</h2>
            </div>
            <span v-if="chat.historyLoading" role="status">正在加载历史…</span>
          </div>

          <div ref="messageFeed" class="conversation__feed" aria-live="polite">
            <div v-if="!chat.messages.length && !safeEventMessages.length && !chat.historyLoading" class="conversation__empty">
              <strong>描述下一步要构建的功能</strong>
              <span>生成反馈、Agent 进度和文件元数据会实时显示。</span>
            </div>
            <article v-for="message in chat.messages" :key="message.id" class="message" :class="`message--${message.role}`">
              <p class="message__role">{{ message.role === 'user' ? '你' : 'AI' }}</p>
              <p class="message__content">{{ message.content }}</p>
            </article>
            <article v-for="event in safeEventMessages" :key="event.id" class="message message--event">
              <p class="message__role">{{ event.phase || event.type }}</p>
              <p class="message__content">{{ event.message }}</p>
            </article>
          </div>

          <div v-if="generation.error || chat.streamError" class="generation-error" role="alert">
            <span>{{ generation.error || chat.streamError }}</span>
            <button type="button" data-action="retry-generation" @click="retryGeneration">保留进度并重试</button>
          </div>

          <form class="composer" @submit.prevent="submit">
            <label for="workbench-prompt">继续描述需求</label>
            <textarea
              id="workbench-prompt"
              name="workbench-prompt"
              v-model="input"
              rows="4"
              autocomplete="off"
              required
              :disabled="!hasCurrentApp || isGenerating"
              placeholder="例如：增加项目筛选、空状态和移动端布局…"
              @keydown="handleComposerKeydown"
            />
            <div class="composer__footer">
              <span>Enter 发送，Shift + Enter 换行</span>
              <button v-if="isGenerating" type="button" class="button button--danger" data-action="cancel-generation" @click="cancelGeneration">
                <PauseCircleOutlined aria-hidden="true" />取消生成
              </button>
              <button v-else type="submit" class="button" :disabled="!input.trim() || !hasCurrentApp">
                <SendOutlined aria-hidden="true" />发送需求
              </button>
            </div>
          </form>
        </section>

        <aside class="workbench__inspector" aria-label="生成详情">
          <AgentProgress :phase="generation.phase" :status="generation.status" />

          <section class="event-log" aria-labelledby="event-log-title">
            <div class="panel-heading panel-heading--compact">
              <h2 id="event-log-title">事件详情</h2>
              <span>{{ generation.events.length }} 条</span>
            </div>
            <ol v-if="safeEventMessages.length" class="event-log__list">
              <li v-for="event in safeEventMessages.slice(-8)" :key="`detail-${event.id}`">
                <code>{{ event.phase || event.type }}</code>
                <span>{{ event.message }}</span>
              </li>
            </ol>
            <p v-else class="event-log__empty">生成开始后显示安全的文本事件；源码内容不会在此渲染。</p>
          </section>

          <GeneratedFileList :files="generation.files" :status="generation.status" />
        </aside>
      </div>
    </div>
  </ChatLayout>
</template>

<style scoped>
.workbench {
  width: 100%;
  min-width: 0;
  padding: var(--space-6);
}

.workbench__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-6);
  max-width: 1440px;
  margin: 0 auto var(--space-5);
}

.workbench__eyebrow,
.panel-heading__eyebrow {
  margin: 0 0 var(--space-1);
  color: var(--color-primary);
  font-family: var(--font-mono);
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.workbench h1 { margin: 0; font-size: clamp(1.45rem, 3vw, 2rem); letter-spacing: -0.025em; }
.workbench__meta { display: flex; flex-wrap: wrap; gap: var(--space-3); margin: var(--space-2) 0 0; color: var(--color-text-muted); font-size: 0.78rem; }
.mono { font-family: var(--font-mono); }
.workbench__actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: var(--space-2); }

.button {
  display: inline-flex;
  min-height: 44px;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  padding: 0 var(--space-4);
  color: #fff;
  background: var(--color-primary);
  font-weight: 800;
}
.button:hover { background: var(--color-primary-hover); }
.button--secondary { border-color: var(--color-border); color: var(--color-text); background: var(--color-surface); }
.button--secondary:hover { border-color: var(--color-primary); color: var(--color-primary); background: var(--color-primary-soft); }
.button--danger { background: var(--color-danger); }

.workbench-alert {
  display: flex;
  max-width: 1440px;
  min-height: 44px;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin: 0 auto var(--space-3);
  padding: var(--space-3) var(--space-4);
  border: 1px solid #fecaca;
  border-radius: var(--radius-sm);
  color: var(--color-danger);
  background: var(--color-danger-soft);
}
.workbench-alert--success { border-color: #bbf7d0; color: var(--color-success); background: var(--color-success-soft); }
.workbench-alert button,
.workbench-alert a { border: 0; color: inherit; background: transparent; font-weight: 800; text-decoration: underline; }

.workbench__grid {
  display: grid;
  max-width: 1440px;
  grid-template-columns: minmax(0, 1fr) minmax(300px, 360px);
  gap: var(--space-5);
  margin: 0 auto;
  align-items: start;
}

.conversation,
.event-log {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
}

.conversation { min-width: 0; overflow: hidden; }
.panel-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--space-3); padding: var(--space-5); border-bottom: 1px solid var(--color-border); }
.panel-heading h2 { margin: 0; font-size: 1.05rem; }
.panel-heading > span { color: var(--color-text-muted); font-size: 0.78rem; }
.panel-heading--compact { padding: var(--space-4); }

.conversation__feed { min-height: 360px; max-height: 56vh; overflow-y: auto; padding: var(--space-5); }
.conversation__empty { display: grid; min-height: 260px; place-content: center; gap: var(--space-2); color: var(--color-text-muted); text-align: center; }
.conversation__empty strong { color: var(--color-text); font-size: 1.05rem; }
.message { max-width: 82%; margin-bottom: var(--space-4); }
.message--user { margin-left: auto; }
.message__role { margin: 0 0 var(--space-1); color: var(--color-text-muted); font-size: 0.7rem; font-weight: 800; text-transform: uppercase; }
.message__content { margin: 0; padding: var(--space-3) var(--space-4); border-radius: var(--radius-md); background: var(--color-surface-subtle); white-space: pre-wrap; overflow-wrap: anywhere; }
.message--user .message__content { color: #fff; background: var(--color-primary); }
.message--event .message__content { border-left: 3px solid var(--color-primary); border-radius: 0 var(--radius-sm) var(--radius-sm) 0; }

.generation-error { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); padding: var(--space-3) var(--space-5); color: var(--color-danger); background: var(--color-danger-soft); }
.generation-error button { min-height: 44px; border: 0; color: inherit; background: transparent; font-weight: 800; text-decoration: underline; }

.composer { display: grid; gap: var(--space-2); padding: var(--space-5); border-top: 1px solid var(--color-border); }
.composer label { font-weight: 800; }
.composer textarea { width: 100%; min-height: 108px; resize: vertical; border: 1px solid var(--color-border); border-radius: var(--radius-sm); padding: var(--space-3); color: var(--color-text); background: var(--color-surface); line-height: 1.55; }
.composer textarea:focus { border-color: var(--color-primary); outline: 3px solid rgb(79 70 229 / 18%); }
.composer__footer { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); }
.composer__footer > span { color: var(--color-text-muted); font-size: 0.75rem; }

.workbench__inspector { display: grid; gap: var(--space-4); min-width: 0; }
.event-log { padding: 0; }
.event-log__list { display: grid; gap: var(--space-3); margin: 0; padding: var(--space-4); list-style: none; }
.event-log__list li { display: grid; gap: var(--space-1); }
.event-log__list code { color: var(--color-primary); font-family: var(--font-mono); font-size: 0.7rem; font-weight: 800; }
.event-log__list span { color: var(--color-text-muted); font-size: 0.78rem; overflow-wrap: anywhere; }
.event-log__empty { margin: 0; padding: var(--space-4); color: var(--color-text-muted); font-size: 0.78rem; }

@media (max-width: 960px) {
  .workbench { padding: var(--space-4); }
  .workbench__header { display: grid; }
  .workbench__actions { justify-content: flex-start; }
  .workbench__grid { grid-template-columns: minmax(0, 1fr); }
  .workbench__inspector { order: 2; }
  .conversation { order: 1; }
}

@media (max-width: 560px) {
  .workbench { padding: var(--space-3); }
  .workbench__actions,
  .workbench__actions .button { width: 100%; }
  .message { max-width: 94%; }
  .composer__footer { align-items: stretch; flex-direction: column; }
  .composer__footer .button { width: 100%; }
  .workbench-alert { align-items: flex-start; flex-direction: column; }
}
</style>
