<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import AdminLayout from '@/layouts/AdminLayout.vue'
import PageHeader from '@/components/shared/PageHeader.vue'
import { getIntentTree, resetIntentTree, saveIntentTree } from '@/api/intentConfig'
import type { IntentNode } from '@/types/intent'
import { useAccessibleDialog } from '@/composables/useAccessibleDialog'
import { onBeforeRouteLeave } from 'vue-router'

const treeJson = ref('')
const savedTreeJson = ref('')
const customized = ref(false)
const loading = ref(false)
const saving = ref(false)
const resetting = ref(false)
const loadError = ref('')
const actionError = ref('')
const validationError = ref('')
const feedback = ref('')
const {
  isOpen: resetDialogOpen,
  overlayRef: resetOverlayRef,
  dialogRef: resetDialogRef,
  openDialog: openResetDialog,
  closeDialog: closeResetDialog,
} = useAccessibleDialog(() => !resetting.value)
let loadSequence = 0
let saveSequence = 0
let resetSequence = 0
let viewActive = false

const dirty = computed(() => treeJson.value !== savedTreeJson.value)
const saveDisabled = computed(() => loading.value || saving.value || resetting.value || !dirty.value)
const lineCount = computed(() => treeJson.value ? treeJson.value.split(/\r?\n/).length : 0)

onMounted(() => {
  viewActive = true
  window.addEventListener('beforeunload', handleBeforeUnload)
  void fetchTree()
})
onBeforeUnmount(() => {
  viewActive = false
  loadSequence += 1
  saveSequence += 1
  resetSequence += 1
  window.removeEventListener('beforeunload', handleBeforeUnload)
})

onBeforeRouteLeave(() => {
  if (!dirty.value) return true
  return window.confirm('当前意图树有未保存修改，确定离开吗？')
})

function validateNode(node: unknown, location: string, keys: Set<string>): asserts node is IntentNode {
  if (!node || typeof node !== 'object' || Array.isArray(node)) throw new Error(`${location} 必须是对象`)
  const record = node as Record<string, unknown>
  if (typeof record.key !== 'string' || !record.key.trim()) throw new Error(`${location} 缺少有效的 key`)
  if (typeof record.title !== 'string' || !record.title.trim()) throw new Error(`${location} 缺少有效的 title`)
  if (keys.has(record.key)) throw new Error(`${location} 的 key “${record.key}” 重复`)
  keys.add(record.key)
  for (const field of ['type', 'source', 'description', 'collection'] as const) {
    if (record[field] !== undefined && typeof record[field] !== 'string') throw new Error(`${location}.${field} 必须是字符串`)
  }
  if (record.parentKey !== undefined && record.parentKey !== null && typeof record.parentKey !== 'string') {
    throw new Error(`${location}.parentKey 必须是字符串或 null`)
  }
  if (record.enabled !== undefined && typeof record.enabled !== 'boolean') throw new Error(`${location}.enabled 必须是布尔值`)
  if (record.sortOrder !== undefined && (typeof record.sortOrder !== 'number' || !Number.isFinite(record.sortOrder))) {
    throw new Error(`${location}.sortOrder 必须是有效数字`)
  }
  if (record.examples !== undefined && (!Array.isArray(record.examples) || record.examples.some(item => typeof item !== 'string'))) {
    throw new Error(`${location}.examples 必须是字符串数组`)
  }
  if (record.children !== undefined) {
    if (!Array.isArray(record.children)) throw new Error(`${location}.children 必须是数组`)
    record.children.forEach((child, index) => validateNode(child, `${location}.children[${index}]`, keys))
  }
}

function parseAndValidate(source: string) {
  let parsed: unknown
  try {
    parsed = JSON.parse(source)
  } catch {
    throw new Error('JSON 格式无效，请检查括号、引号和逗号。')
  }
  if (!Array.isArray(parsed)) throw new Error('意图树 JSON 顶层必须是数组。')
  const keys = new Set<string>()
  parsed.forEach((node, index) => validateNode(node, `节点[${index}]`, keys))
  return parsed as IntentNode[]
}

function handleBeforeUnload(event: BeforeUnloadEvent) {
  if (!dirty.value) return
  event.preventDefault()
  event.returnValue = ''
}

async function fetchTree() {
  const sequence = ++loadSequence
  loading.value = true
  loadError.value = ''
  actionError.value = ''
  try {
    const result = await getIntentTree()
    if (!viewActive || sequence !== loadSequence) return
    const normalizedTreeJson = result.treeJson.trim() ? result.treeJson : '[]'
    parseAndValidate(normalizedTreeJson)
    treeJson.value = normalizedTreeJson
    savedTreeJson.value = normalizedTreeJson
    customized.value = result.customized && Boolean(result.treeJson.trim())
    validationError.value = ''
  } catch (error) {
    if (!viewActive || sequence !== loadSequence) return
    loadError.value = error instanceof Error && error.message.startsWith('JSON')
      ? '服务器返回的意图树无法解析，请稍后重试。'
      : '意图树加载失败，请检查网络后重试。'
  } finally {
    if (viewActive && sequence === loadSequence) loading.value = false
  }
}

function handleInput() {
  validationError.value = ''
  actionError.value = ''
  feedback.value = ''
}

async function handleSave() {
  if (saveDisabled.value) return
  validationError.value = ''
  actionError.value = ''
  feedback.value = ''
  const snapshot = treeJson.value
  try {
    parseAndValidate(snapshot)
  } catch (error) {
    validationError.value = error instanceof Error ? error.message : 'JSON 校验失败。'
    return
  }
  saving.value = true
  const sequence = ++saveSequence
  try {
    const saved = await saveIntentTree(snapshot)
    if (!viewActive || sequence !== saveSequence) return
    if (!saved) throw new Error('save rejected')
    savedTreeJson.value = snapshot
    customized.value = true
    feedback.value = treeJson.value === snapshot ? '意图树已保存。' : '已保存提交时的版本，当前还有未保存修改。'
  } catch {
    if (!viewActive || sequence !== saveSequence) return
    actionError.value = '保存失败，编辑内容已保留，请稍后重试。'
  } finally {
    if (viewActive && sequence === saveSequence) saving.value = false
  }
}

async function requestReset(event: Event) {
  if (resetting.value) return
  await openResetDialog(event.currentTarget)
}

async function confirmReset() {
  if (resetting.value) return
  resetting.value = true
  const sequence = ++resetSequence
  actionError.value = ''
  feedback.value = ''
  try {
    const reset = await resetIntentTree()
    if (!viewActive || sequence !== resetSequence) return
    if (!reset) throw new Error('reset rejected')
    resetting.value = false
    await closeResetDialog()
    if (!viewActive || sequence !== resetSequence) return
    await fetchTree()
    if (viewActive && sequence === resetSequence && !loadError.value) feedback.value = '已恢复默认意图树。'
  } catch {
    if (!viewActive || sequence !== resetSequence) return
    actionError.value = '重置失败，当前编辑内容未改变。'
    resetting.value = false
    await closeResetDialog()
  } finally {
    if (viewActive && sequence === resetSequence) resetting.value = false
  }
}
</script>

<template>
  <AdminLayout>
    <PageHeader title="意图树配置" description="以 JSON 维护意图层级。保存前会在本地校验结构。" eyebrow="Administration">
      <template #actions>
        <button type="button" class="secondary-button" data-action="request-reset" :disabled="loading || saving || resetting" @click="requestReset($event)">重置默认</button>
        <button type="button" class="primary-button" data-action="save-intent-tree" :disabled="saveDisabled" @click="handleSave">{{ saving ? '正在保存…' : '保存配置' }}</button>
      </template>
    </PageHeader>

    <div v-if="loading" class="admin-state admin-card" role="status">正在加载意图树…</div>
    <div v-else-if="loadError" class="admin-state admin-card" role="alert">
      <strong>加载失败</strong><span>{{ loadError }}</span>
      <button type="button" class="secondary-button" data-action="retry-intent-tree" @click="fetchTree">重新加载</button>
    </div>
    <template v-else>
      <div class="config-meta" aria-label="配置状态">
        <span :class="['status-badge', customized && 'status-badge--custom']">{{ customized ? '自定义配置' : '默认配置' }}</span>
        <span>{{ dirty ? '有未保存修改' : '所有修改已保存' }}</span>
        <span>{{ lineCount }} 行</span>
      </div>
      <p v-if="feedback" class="inline-feedback" role="status">{{ feedback }}</p>
      <p v-if="actionError" class="inline-alert" role="alert">{{ actionError }}</p>
      <section class="admin-card editor-card" aria-labelledby="intent-editor-title">
        <div class="editor-heading"><div><h2 id="intent-editor-title">配置 JSON</h2><p>每个节点至少需要非空的 <code>key</code> 和 <code>title</code>。</p></div></div>
        <label class="sr-only" for="intent-json">意图树 JSON</label>
        <textarea id="intent-json" v-model="treeJson" name="intent-tree-json" autocomplete="off" required aria-label="意图树 JSON" spellcheck="false" @input="handleInput" />
        <p v-if="validationError" class="validation-error" data-validation-error role="alert">{{ validationError }}</p>
      </section>
    </template>

    <div v-if="resetDialogOpen" ref="resetOverlayRef" class="dialog-backdrop" @mousedown.self="closeResetDialog">
      <section ref="resetDialogRef" class="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="reset-title" tabindex="-1">
        <p class="dialog-kicker">覆盖当前配置</p>
        <h2 id="reset-title">重置意图树？</h2>
        <p>当前自定义配置和未保存修改都将被默认配置替换。此操作需要重新从服务器加载。</p>
        <div class="dialog-actions">
          <button type="button" class="secondary-button" :disabled="resetting" @click="closeResetDialog">取消</button>
          <button type="button" class="danger-button" data-action="confirm-reset" data-dialog-initial-focus :disabled="resetting" @click="confirmReset">{{ resetting ? '正在重置…' : '确认重置' }}</button>
        </div>
      </section>
    </div>
  </AdminLayout>
</template>

<style scoped>
.admin-card{border:1px solid var(--color-border);border-radius:var(--radius-lg);background:var(--color-surface);box-shadow:var(--shadow-card)}.primary-button,.secondary-button,.danger-button{min-height:44px;border-radius:var(--radius-sm);padding:0 var(--space-4);font-weight:700}.primary-button{border:1px solid var(--color-primary);color:#fff;background:var(--color-primary)}.secondary-button{border:1px solid var(--color-border);background:#fff}.danger-button{border:1px solid var(--color-danger);color:#fff;background:var(--color-danger)}
.admin-state{display:flex;min-height:300px;align-items:center;justify-content:center;flex-direction:column;gap:var(--space-2);padding:var(--space-6);text-align:center}.admin-state span{color:var(--color-text-muted)}.config-meta{display:flex;flex-wrap:wrap;align-items:center;gap:var(--space-3);margin-bottom:var(--space-4);color:var(--color-text-muted);font-size:.875rem}.status-badge{border-radius:999px;padding:.25rem .65rem;color:#475569;background:#e2e8f0;font-weight:700}.status-badge--custom{color:var(--color-primary);background:var(--color-primary-soft)}
.inline-feedback,.inline-alert{margin:0 0 var(--space-4);border-radius:var(--radius-sm);padding:var(--space-3) var(--space-4)}.inline-feedback{color:#166534;background:#ecfdf3}.inline-alert,.validation-error{color:#991b1b;background:var(--color-danger-soft)}.editor-card{overflow:hidden}.editor-heading{padding:var(--space-5);border-bottom:1px solid var(--color-border)}.editor-heading h2,.editor-heading p{margin:0}.editor-heading p{margin-top:var(--space-1);color:var(--color-text-muted)}code{font-family:var(--font-mono)}textarea{display:block;width:100%;min-height:520px;resize:vertical;border:0;padding:var(--space-5);color:#dbeafe;background:#111827;font-family:var(--font-mono);font-size:.9rem;line-height:1.65;tab-size:2}textarea:focus-visible{outline:3px solid rgb(99 102 241 / 65%);outline-offset:-3px}.validation-error{margin:0;padding:var(--space-3) var(--space-5);font-weight:600}
.dialog-backdrop{position:fixed;z-index:1100;inset:0;display:grid;place-items:center;padding:var(--space-4);background:rgb(15 23 42 / 55%)}.confirm-dialog{width:min(100%,480px);max-height:calc(100dvh - 32px);overflow-y:auto;overscroll-behavior:contain;border-radius:var(--radius-lg);padding:var(--space-6);background:#fff;box-shadow:var(--shadow-drawer)}.confirm-dialog h2{margin:0}.confirm-dialog p{color:var(--color-text-muted)}.dialog-kicker{margin:0 0 var(--space-2);color:var(--color-danger)!important;font-size:.75rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase}.dialog-actions{display:flex;justify-content:flex-end;gap:var(--space-2);margin-top:var(--space-5)}
@media(max-width:640px){textarea{min-height:420px;padding:var(--space-4)}.dialog-actions>*{flex:1}}
</style>
