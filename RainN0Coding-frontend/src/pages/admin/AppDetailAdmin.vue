<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AdminLayout from '@/layouts/AdminLayout.vue'
import PageHeader from '@/components/shared/PageHeader.vue'
import { adminDeleteApp, adminGetAppVO, deployApp, downloadApp } from '@/api/app'
import type { AppVO } from '@/types/app'
import { useAccessibleDialog } from '@/composables/useAccessibleDialog'
import { useAuthStore } from '@/stores/auth'
import { formatDateTime, formatInteger } from '@/utils/formatters'
import { normalizeEntityId, sameEntityId } from '@/utils/entityId'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const app = ref<AppVO | null>(null)
const loading = ref(false)
const error = ref('')
const actionError = ref('')
const actionFeedback = ref('')
const deploymentUrl = ref('')
const deploying = ref(false)
const deleting = ref(false)
const {
  isOpen: deleteDialogOpen,
  overlayRef: deleteOverlayRef,
  dialogRef: deleteDialogRef,
  openDialog: openDeleteDialog,
  closeDialog: closeDeleteDialog,
} = useAccessibleDialog(() => !deleting.value)
let requestSequence = 0
let deploySequence = 0
let deleteSequence = 0
let viewActive = true

const appId = computed(() => {
  const raw = Array.isArray(route.params.appId) ? route.params.appId[0] : route.params.appId
  return normalizeEntityId(raw)
})
const isOwner = computed(() => Boolean(app.value && sameEntityId(auth.userId, app.value.userId)))

watch(appId, (id) => {
  deploySequence += 1
  deleteSequence += 1
  deploying.value = false
  deleting.value = false
  void closeDeleteDialog()
  void fetchApp(id)
}, { immediate: true })
onBeforeUnmount(() => {
  viewActive = false
  requestSequence += 1
  deploySequence += 1
  deleteSequence += 1
})

async function fetchApp(id = appId.value) {
  const sequence = ++requestSequence
  error.value = ''
  app.value = null
  if (id === null) {
    loading.value = false
    error.value = '应用编号无效。'
    return
  }
  loading.value = true
  try {
    const result = await adminGetAppVO(id)
    if (viewActive && sequence === requestSequence && sameEntityId(id, appId.value)) app.value = result
  } catch {
    if (viewActive && sequence === requestSequence && sameEntityId(id, appId.value)) error.value = '应用详情加载失败，请稍后重试。'
  } finally {
    if (viewActive && sequence === requestSequence && sameEntityId(id, appId.value)) loading.value = false
  }
}

async function handleDeploy() {
  const currentApp = app.value
  if (!currentApp || !isOwner.value || deploying.value || !sameEntityId(currentApp.id, appId.value)) return
  const sequence = ++deploySequence
  deploying.value = true
  actionError.value = ''
  deploymentUrl.value = ''
  try {
    const url = await deployApp(currentApp.id)
    if (!viewActive || sequence !== deploySequence || !sameEntityId(currentApp.id, appId.value)) return
    deploymentUrl.value = normalizeHttpUrl(url)
  } catch {
    if (!viewActive || sequence !== deploySequence || !sameEntityId(currentApp.id, appId.value)) return
    actionError.value = '部署失败，请稍后重试。'
  } finally {
    if (viewActive && sequence === deploySequence) deploying.value = false
  }
}

function handleDownload() {
  if (app.value && isOwner.value && sameEntityId(app.value.id, appId.value)) {
    window.open(downloadApp(app.value.id), '_blank', 'noopener,noreferrer')
  }
}

function normalizeHttpUrl(value: unknown) {
  if (typeof value !== 'string') throw new Error('invalid deployment URL')
  const url = new URL(value)
  if (url.protocol !== 'http:' && url.protocol !== 'https:') throw new Error('invalid deployment URL')
  return url.toString()
}

async function requestDelete(event: Event) {
  if (!app.value || deleting.value || deploying.value || !sameEntityId(app.value.id, appId.value)) return
  actionError.value = ''
  await openDeleteDialog(event.currentTarget)
}

async function confirmDelete() {
  const currentApp = app.value
  if (!currentApp || deleting.value || !sameEntityId(currentApp.id, appId.value)) return
  const sequence = ++deleteSequence
  deleting.value = true
  actionError.value = ''
  try {
    const deleted = await adminDeleteApp({ id: currentApp.id })
    if (!viewActive || sequence !== deleteSequence || !sameEntityId(currentApp.id, appId.value)) return
    if (!deleted) throw new Error('delete rejected')
  } catch {
    if (!viewActive || sequence !== deleteSequence || !sameEntityId(currentApp.id, appId.value)) return
    actionError.value = '删除失败，应用详情仍然保留，请稍后重试。'
    deleting.value = false
    await closeDeleteDialog()
    return
  }
  actionFeedback.value = '应用已删除，正在返回应用列表…'
  deleting.value = false
  await closeDeleteDialog()
  if (!viewActive || sequence !== deleteSequence || !sameEntityId(currentApp.id, appId.value)) return
  try {
    await router.replace('/admin/apps')
  } catch {
    if (viewActive && sequence === deleteSequence && sameEntityId(currentApp.id, appId.value)) {
      actionError.value = '应用已删除，但自动返回失败，请使用“返回应用列表”。'
    }
  }
}
</script>

<template>
  <AdminLayout>
    <PageHeader :title="app?.appName || '应用详情'" description="查看应用的生成、部署和归属信息。" eyebrow="Application detail">
      <template #actions><router-link class="secondary-link" to="/admin/apps">返回应用列表</router-link></template>
    </PageHeader>

    <div v-if="loading" class="detail-state detail-card" role="status">正在加载应用详情…</div>
    <div v-else-if="error" class="detail-state detail-card" role="alert"><strong>无法显示应用</strong><span>{{ error }}</span><button type="button" class="secondary-button" @click="fetchApp()">重新加载</button></div>
    <section v-else-if="app" class="detail-card" aria-labelledby="app-information">
      <div class="detail-heading"><h2 id="app-information">基本信息</h2><span :class="['status-badge', app.deployKey && 'status-badge--success']">{{ app.deployKey ? '已部署' : '未部署' }}</span></div>
      <dl class="detail-grid">
        <div><dt>应用 ID</dt><dd class="tabular-nums">{{ formatInteger(app.id) }}</dd></div><div><dt>应用名称</dt><dd>{{ app.appName || '未命名应用' }}</dd></div>
        <div><dt>代码生成类型</dt><dd><code>{{ app.codeGenType || '未知' }}</code></dd></div><div><dt>创建者</dt><dd>{{ app.userVO?.userName || `用户 #${app.userId}` }}</dd></div>
        <div><dt>部署标识</dt><dd><code>{{ app.deployKey || '尚未部署' }}</code></dd></div><div><dt>当前版本</dt><dd class="tabular-nums">{{ formatInteger(app.currentVersion) }}</dd></div>
        <div><dt>优先级</dt><dd class="tabular-nums">{{ formatInteger(app.priority) }}</dd></div><div><dt>创建时间</dt><dd class="tabular-nums">{{ formatDateTime(app.createTime) }}</dd></div>
        <div><dt>更新时间</dt><dd class="tabular-nums">{{ formatDateTime(app.updateTime) }}</dd></div><div><dt>最近编辑</dt><dd class="tabular-nums">{{ formatDateTime(app.editTime) }}</dd></div>
        <div class="detail-grid__wide"><dt>初始需求</dt><dd>{{ app.initPrompt || '未记录' }}</dd></div>
      </dl>
      <p v-if="deploymentUrl" class="deployment-result" role="status">部署地址：<a :href="deploymentUrl" target="_blank" rel="noopener noreferrer">{{ deploymentUrl }}</a></p>
      <p v-if="actionFeedback" class="inline-feedback" role="status">{{ actionFeedback }}</p>
      <p v-if="actionError" class="inline-alert" role="alert">{{ actionError }}</p>
      <p v-if="!isOwner" class="owner-notice">仅应用所有者可部署或下载此应用；管理员仍可执行删除。</p>
      <div class="detail-actions">
        <button type="button" class="primary-button" :disabled="deploying || !isOwner" :title="!isOwner ? '仅应用所有者可操作' : undefined" @click="handleDeploy">{{ deploying ? '正在部署…' : '部署应用' }}</button>
        <button type="button" class="secondary-button" :disabled="!isOwner" :title="!isOwner ? '仅应用所有者可操作' : undefined" @click="handleDownload">下载代码</button>
        <button type="button" class="danger-button" data-action="request-delete-app" :disabled="deleting || deploying" :title="deploying ? '请等待部署请求完成' : undefined" @click="requestDelete">删除应用</button>
      </div>
    </section>
    <div v-else class="detail-state detail-card"><strong>未找到应用</strong><span>该应用可能已被删除。</span></div>

    <div v-if="deleteDialogOpen" ref="deleteOverlayRef" class="dialog-backdrop" @mousedown.self="closeDeleteDialog">
      <section ref="deleteDialogRef" class="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="detail-delete-title" tabindex="-1">
        <p class="dialog-kicker">不可撤销操作</p>
        <h2 id="detail-delete-title">删除这个应用？</h2>
        <p>将永久删除“{{ app?.appName || `应用 #${app?.id}` }}”，此操作无法撤销。</p>
        <div class="dialog-actions">
          <button type="button" class="secondary-button" data-action="cancel-delete-app" :disabled="deleting" @click="closeDeleteDialog">取消</button>
          <button type="button" class="danger-button" data-action="confirm-delete-app" data-dialog-initial-focus :disabled="deleting" @click="confirmDelete">{{ deleting ? '正在删除…' : '确认删除' }}</button>
        </div>
      </section>
    </div>
  </AdminLayout>
</template>

<style scoped>
.tabular-nums{font-variant-numeric:tabular-nums}
.detail-card{border:1px solid var(--color-border);border-radius:var(--radius-lg);background:var(--color-surface);box-shadow:var(--shadow-card)}.detail-state{display:flex;min-height:320px;align-items:center;justify-content:center;flex-direction:column;gap:var(--space-2);padding:var(--space-6);text-align:center}.detail-state span{color:var(--color-text-muted)}.detail-heading{display:flex;align-items:center;justify-content:space-between;padding:var(--space-5);border-bottom:1px solid var(--color-border)}.detail-heading h2{margin:0}.status-badge{border-radius:999px;padding:.3rem .7rem;color:#475569;background:#e2e8f0;font-size:.8rem;font-weight:800}.status-badge--success{color:#166534;background:#dcfce7}.detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));margin:0}.detail-grid>div{min-width:0;padding:var(--space-4) var(--space-5);border-bottom:1px solid var(--color-border)}.detail-grid>div:nth-child(odd){border-right:1px solid var(--color-border)}.detail-grid .detail-grid__wide{grid-column:1/-1;border-right:0}.detail-grid dt{color:var(--color-text-muted);font-size:.8rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase}.detail-grid dd{margin:var(--space-1) 0 0;overflow-wrap:anywhere;font-weight:600}.detail-grid code{font-family:var(--font-mono)}.detail-actions{display:flex;gap:var(--space-2);padding:var(--space-5)}.primary-button,.secondary-button,.secondary-link,.danger-button{display:inline-flex;min-height:44px;align-items:center;justify-content:center;border-radius:var(--radius-sm);padding:0 var(--space-4);font-weight:700}.primary-button{border:1px solid var(--color-primary);color:#fff;background:var(--color-primary)}.secondary-button,.secondary-link{border:1px solid var(--color-border);color:var(--color-text);background:#fff;text-decoration:none}.danger-button{border:1px solid var(--color-danger);color:#fff;background:var(--color-danger)}.deployment-result,.inline-alert{margin:var(--space-4) var(--space-5) 0;border-radius:var(--radius-sm);padding:var(--space-3) var(--space-4);overflow-wrap:anywhere}.deployment-result{background:var(--color-primary-soft)}.deployment-result a{color:var(--color-primary);font-weight:700}.inline-alert{color:#991b1b;background:var(--color-danger-soft)}
.inline-feedback{margin:var(--space-4) var(--space-5) 0;border-radius:var(--radius-sm);padding:var(--space-3) var(--space-4);color:#166534;background:#ecfdf3}
.owner-notice{margin:var(--space-4) var(--space-5) 0;color:var(--color-text-muted);font-weight:600}
.dialog-backdrop{position:fixed;z-index:1100;inset:0;display:grid;place-items:center;padding:var(--space-4);background:rgb(15 23 42 / 55%)}.confirm-dialog{width:min(100%,480px);max-height:calc(100dvh - 32px);overflow-y:auto;overscroll-behavior:contain;border-radius:var(--radius-lg);padding:var(--space-6);background:#fff;box-shadow:var(--shadow-drawer)}.confirm-dialog h2{margin:0}.confirm-dialog p{color:var(--color-text-muted)}.dialog-kicker{margin:0 0 var(--space-2);color:var(--color-danger)!important;font-size:.75rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase}.dialog-actions{display:flex;justify-content:flex-end;gap:var(--space-2);margin-top:var(--space-5)}
@media(max-width:640px){.detail-grid{grid-template-columns:1fr}.detail-grid>div,.detail-grid>div:nth-child(odd){grid-column:1;border-right:0}.detail-actions,.dialog-actions{flex-direction:column}}
</style>
