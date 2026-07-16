<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AdminLayout from '@/layouts/AdminLayout.vue'
import PageHeader from '@/components/shared/PageHeader.vue'
import { adminDeleteApp, adminListApps, deployApp, downloadApp } from '@/api/app'
import type { AppVO } from '@/types/app'
import { useAccessibleDialog } from '@/composables/useAccessibleDialog'
import { useAuthStore } from '@/stores/auth'
import { buildAdminListQuery, isCanonicalAdminListQuery, parseAdminListQuery } from '@/utils/adminListQuery'
import { formatDateTime, formatInteger } from '@/utils/formatters'
import { normalizePageResult } from '@/utils/pageResult'
import { sameEntityId } from '@/utils/entityId'
import type { EntityId } from '@/types/entity'

const apps = ref<AppVO[]>([])
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const searchName = ref('')
const currentPage = ref(1)
const pageSize = ref(10)
const total = ref(0)
const serverPages = ref(1)
const loading = ref(false)
const loadError = ref('')
const actionError = ref('')
const feedback = ref('')
const deploymentUrl = ref('')
const deletingApp = ref<AppVO | null>(null)
const deleting = ref(false)
const deployingIds = ref(new Set<EntityId>())
const appsTableTitle = ref<HTMLElement | null>(null)
const {
  isOpen: deleteDialogOpen,
  overlayRef: deleteOverlayRef,
  dialogRef: deleteDialogRef,
  openDialog: openDeleteDialog,
  closeDialog: closeDeleteDialog,
} = useAccessibleDialog(() => !deleting.value)
let requestSequence = 0
let operationEpoch = 0
const deploySequences = new Map<EntityId, number>()

const totalPages = computed(() => Math.max(1, serverPages.value || Math.ceil(total.value / pageSize.value)))

watch(
  () => route.query,
  (query) => {
    const state = parseAdminListQuery(query)
    currentPage.value = state.page
    pageSize.value = state.pageSize
    searchName.value = state.search
    const canonical = buildAdminListQuery(state)
    if (!isCanonicalAdminListQuery(query, canonical)) {
      void router.replace({ query: canonical })
      return
    }
    void fetchApps()
  },
  { deep: true, immediate: true },
)
onBeforeUnmount(() => {
  requestSequence += 1
  invalidateDeployments()
})

async function fetchApps() {
  invalidateDeployments()
  const sequence = ++requestSequence
  const requestedPage = currentPage.value
  loading.value = true
  loadError.value = ''
  try {
    const result = await adminListApps({
      pageNum: requestedPage,
      pageSize: pageSize.value,
      appName: searchName.value.trim() || undefined,
      sortField: 'createTime',
      sortOrder: 'descend',
    })
    if (sequence !== requestSequence) return
    const page = normalizePageResult(result, requestedPage, pageSize.value)
    const records = page.records
    const resultTotal = page.total
    const pages = page.pages
    total.value = resultTotal
    serverPages.value = pages
    if (records.length === 0 && resultTotal > 0 && requestedPage > pages) {
      void updateRoute({ page: pages })
      return
    }
    apps.value = records
    currentPage.value = Math.min(pages, page.current)
  } catch {
    if (sequence !== requestSequence) return
    apps.value = []
    total.value = 0
    serverPages.value = 1
    loadError.value = '应用列表加载失败，请检查网络后重试。'
  } finally {
    if (sequence === requestSequence) loading.value = false
  }
}

function searchApps() {
  void updateRoute({ page: 1, search: searchName.value.trim() })
}

function changePage(nextPage: number) {
  if (nextPage < 1 || nextPage > totalPages.value || nextPage === currentPage.value) return
  void updateRoute({ page: nextPage })
}

function changePageSize(event: Event) {
  void updateRoute({ page: 1, pageSize: Number((event.target as HTMLSelectElement).value) })
}

async function updateRoute(patch: Partial<{ page: number; pageSize: number; search: string }>) {
  const state = {
    page: patch.page ?? currentPage.value,
    pageSize: patch.pageSize ?? pageSize.value,
    search: patch.search ?? searchName.value.trim(),
  }
  const query = buildAdminListQuery(state)
  if (isCanonicalAdminListQuery(route.query, query)) await fetchApps()
  else await router.replace({ query })
}

async function requestDelete(app: AppVO, event: Event) {
  if (deployingIds.value.has(app.id)) return
  actionError.value = ''
  deletingApp.value = app
  await openDeleteDialog(event.currentTarget)
}

async function confirmDelete() {
  const app = deletingApp.value
  if (!app || deleting.value) return
  deleting.value = true
  invalidateDeployments()
  actionError.value = ''
  let deletedSuccessfully = false
  const shouldMoveToPreviousPage = apps.value.length === 1 && currentPage.value > 1
  try {
    const deleted = await adminDeleteApp({ id: app.id })
    if (!deleted) throw new Error('delete rejected')
    feedback.value = `已删除“${app.appName || `应用 #${app.id}`}”。`
    deletedSuccessfully = true
  } catch {
    actionError.value = '删除失败，应用仍然保留，请稍后重试。'
  } finally {
    deleting.value = false
    await closeDeleteDialog()
    deletingApp.value = null
  }
  if (deletedSuccessfully) {
    if (shouldMoveToPreviousPage) await updateRoute({ page: currentPage.value - 1 })
    else await fetchApps()
    await nextTick()
    if (document.activeElement === document.body) appsTableTitle.value?.focus()
  }
}

async function handleDeploy(app: AppVO) {
  if (!isOwner(app) || deployingIds.value.has(app.id)) return
  const epoch = operationEpoch
  const sequence = (deploySequences.get(app.id) ?? 0) + 1
  deploySequences.set(app.id, sequence)
  deployingIds.value = new Set(deployingIds.value).add(app.id)
  actionError.value = ''
  feedback.value = ''
  deploymentUrl.value = ''
  try {
    const url = await deployApp(app.id)
    if (epoch !== operationEpoch || sequence !== deploySequences.get(app.id)) return
    deploymentUrl.value = normalizeHttpUrl(url)
    feedback.value = `“${app.appName || `应用 #${app.id}`}”部署成功。`
  } catch {
    if (epoch !== operationEpoch || sequence !== deploySequences.get(app.id)) return
    actionError.value = '部署失败，请稍后重试。'
  } finally {
    if (sequence === deploySequences.get(app.id)) {
      const next = new Set(deployingIds.value)
      next.delete(app.id)
      deployingIds.value = next
    }
  }
}

function handleDownload(app: AppVO) {
  if (isOwner(app)) window.open(downloadApp(app.id), '_blank', 'noopener,noreferrer')
}

function isOwner(app: AppVO) {
  return sameEntityId(auth.userId, app.userId)
}

function invalidateDeployments() {
  operationEpoch += 1
}

function normalizeHttpUrl(value: unknown) {
  if (typeof value !== 'string') throw new Error('invalid deployment URL')
  const url = new URL(value)
  if (url.protocol !== 'http:' && url.protocol !== 'https:') throw new Error('invalid deployment URL')
  return url.toString()
}
</script>

<template>
  <AdminLayout>
    <PageHeader title="应用管理" description="检索、部署和维护平台中的生成项目。" eyebrow="Administration">
      <template #actions>
        <button type="button" class="secondary-button" :disabled="loading" @click="fetchApps">刷新</button>
      </template>
    </PageHeader>

    <section class="admin-card admin-toolbar" aria-label="应用筛选">
      <label class="field-label" for="app-search">应用名称</label>
      <div class="search-row">
        <input id="app-search" v-model="searchName" name="app-search" autocomplete="off" aria-label="搜索应用名称" type="search" placeholder="例如：运营看板…" @keyup.enter="searchApps">
        <button type="button" class="primary-button" data-action="search-apps" @click="searchApps">搜索</button>
      </div>
    </section>

    <p v-if="feedback" class="inline-feedback" role="status">{{ feedback }}</p>
    <p v-if="deploymentUrl" class="deployment-result">
      部署地址：<a :href="deploymentUrl" target="_blank" rel="noopener noreferrer">{{ deploymentUrl }}</a>
    </p>
    <p v-if="actionError" class="inline-alert" role="alert">{{ actionError }}</p>

    <section class="admin-card" aria-labelledby="apps-table-title">
      <div class="section-heading">
        <div>
          <h2 id="apps-table-title" ref="appsTableTitle" tabindex="-1">全部应用</h2>
          <p class="tabular-nums">共 {{ formatInteger(total) }} 个应用</p>
        </div>
      </div>

      <div v-if="loading" class="admin-state" role="status">正在加载应用…</div>
      <div v-else-if="loadError" class="admin-state admin-state--error" role="alert">
        <strong>加载失败</strong>
        <span>{{ loadError }}</span>
        <button type="button" class="secondary-button" data-action="retry-apps" @click="fetchApps">重新加载</button>
      </div>
      <div v-else-if="apps.length === 0" class="admin-state">
        <strong>没有找到应用</strong>
        <span>尝试更换搜索词。</span>
      </div>
      <template v-else-if="apps.length > 0">
        <div class="admin-table-scroll" tabindex="0" aria-label="应用表格，可横向滚动">
          <table>
            <thead><tr><th>名称</th><th>类型</th><th>创建者</th><th>部署状态</th><th>优先级</th><th>创建时间</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="app in apps" :key="app.id">
                <td><router-link class="table-link" :to="`/admin/apps/${app.id}`">{{ app.appName || `未命名应用 #${app.id}` }}</router-link></td>
                <td><span class="type-badge">{{ app.codeGenType || '未知' }}</span></td>
                <td>{{ app.userVO?.userName || `用户 #${app.userId}` }}</td>
                <td>{{ app.deployKey ? '已部署' : '未部署' }}</td>
                <td class="tabular-nums">{{ formatInteger(app.priority) }}</td>
                <td class="tabular-nums">{{ formatDateTime(app.createTime) }}</td>
                <td>
                  <div class="row-actions">
                    <button type="button" data-action="deploy-app" :disabled="!isOwner(app) || deployingIds.has(app.id)" :title="!isOwner(app) ? '仅应用所有者可操作' : undefined" @click="handleDeploy(app)">{{ deployingIds.has(app.id) ? '部署中…' : '部署' }}</button>
                    <button type="button" data-action="download-app" :disabled="!isOwner(app)" :title="!isOwner(app) ? '仅应用所有者可操作' : undefined" @click="handleDownload(app)">下载</button>
                    <button type="button" class="danger-link" data-action="request-delete-app" :disabled="deployingIds.has(app.id)" :title="deployingIds.has(app.id) ? '请等待部署请求完成' : undefined" @click="requestDelete(app, $event)">删除</button>
                  </div>
                  <small v-if="!isOwner(app)" class="owner-only">仅应用所有者可部署或下载；管理员可删除</small>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
        <div v-if="!loading && !loadError && total > 0" class="pagination" aria-label="应用分页">
          <label>每页 <select name="app-page-size" autocomplete="off" :value="pageSize" aria-label="每页应用数" @change="changePageSize"><option :value="10">10</option><option :value="20">20</option><option :value="50">50</option></select></label>
          <button type="button" :disabled="currentPage === 1" @click="changePage(currentPage - 1)">上一页</button>
          <span class="tabular-nums">第 {{ formatInteger(currentPage) }} / {{ formatInteger(totalPages) }} 页</span>
          <button type="button" :disabled="currentPage >= totalPages" @click="changePage(currentPage + 1)">下一页</button>
        </div>
    </section>

    <div v-if="deleteDialogOpen" ref="deleteOverlayRef" class="dialog-backdrop" @mousedown.self="closeDeleteDialog">
      <section ref="deleteDialogRef" role="dialog" aria-modal="true" aria-labelledby="delete-app-title" class="confirm-dialog" tabindex="-1">
        <p class="dialog-kicker">不可撤销操作</p>
        <h2 id="delete-app-title">删除应用？</h2>
        <p>将永久删除“{{ deletingApp?.appName || `应用 #${deletingApp?.id}` }}”，此操作无法撤销。</p>
        <div class="dialog-actions">
          <button type="button" class="secondary-button" :disabled="deleting" @click="closeDeleteDialog">取消</button>
          <button type="button" class="danger-button" data-action="confirm-delete-app" data-dialog-initial-focus :disabled="deleting" @click="confirmDelete">
            {{ deleting ? '正在删除…' : '确认删除' }}
          </button>
        </div>
      </section>
    </div>
  </AdminLayout>
</template>

<style scoped>
.admin-card{margin-bottom:var(--space-5);border:1px solid var(--color-border);border-radius:var(--radius-lg);background:var(--color-surface);box-shadow:var(--shadow-card)}
.admin-toolbar{padding:var(--space-5)}.field-label{display:block;margin-bottom:var(--space-2);font-weight:700}.search-row{display:flex;max-width:620px;gap:var(--space-2)}
input,select{min-height:44px;border:1px solid var(--color-border);border-radius:var(--radius-sm);padding:0 var(--space-3);color:var(--color-text);background:#fff}input{min-width:0;flex:1}
.primary-button,.secondary-button,.danger-button{min-height:44px;border-radius:var(--radius-sm);padding:0 var(--space-4);font-weight:700}.primary-button{border:1px solid var(--color-primary);color:#fff;background:var(--color-primary)}.secondary-button{border:1px solid var(--color-border);background:#fff}.danger-button{border:1px solid var(--color-danger);color:#fff;background:var(--color-danger)}
.inline-feedback,.inline-alert,.deployment-result{margin:0 0 var(--space-4);border-radius:var(--radius-sm);padding:var(--space-3) var(--space-4)}.inline-feedback{color:#166534;background:#ecfdf3}.inline-alert{color:#991b1b;background:var(--color-danger-soft)}.deployment-result{overflow-wrap:anywhere;background:var(--color-primary-soft)}.deployment-result a,.table-link{color:var(--color-primary);font-weight:700}
.section-heading{display:flex;justify-content:space-between;padding:var(--space-5);border-bottom:1px solid var(--color-border)}.section-heading h2,.section-heading p{margin:0}.section-heading p{margin-top:var(--space-1);color:var(--color-text-muted)}
.admin-state{display:flex;min-height:240px;align-items:center;justify-content:center;flex-direction:column;gap:var(--space-2);padding:var(--space-6);text-align:center}.admin-state span{color:var(--color-text-muted)}
.admin-table-scroll{max-width:100%;overflow-x:auto}table{width:100%;min-width:980px;border-collapse:collapse}th,td{padding:var(--space-3) var(--space-4);border-bottom:1px solid var(--color-border);text-align:left;vertical-align:middle}th{color:var(--color-text-muted);background:var(--color-surface-subtle);font-size:.8rem;letter-spacing:.04em;text-transform:uppercase}.type-badge{border-radius:999px;padding:.2rem .55rem;background:var(--color-primary-soft);font-family:var(--font-mono);font-size:.8rem}.tabular-nums{font-variant-numeric:tabular-nums}.row-actions{display:flex;gap:var(--space-1)}.row-actions button{min-height:44px;border:0;border-radius:var(--radius-sm);padding:0 var(--space-2);color:var(--color-primary);background:transparent;font-weight:700}.row-actions button:hover{background:var(--color-primary-soft)}.row-actions .danger-link{color:var(--color-danger)}
.owner-only{display:block;margin-top:var(--space-1);color:var(--color-text-muted)}
.pagination{display:flex;align-items:center;justify-content:flex-end;gap:var(--space-3);padding:var(--space-4)}.pagination button{min-height:44px;border:1px solid var(--color-border);border-radius:var(--radius-sm);padding:0 var(--space-3);background:#fff}
.dialog-backdrop{position:fixed;z-index:1100;inset:0;display:grid;place-items:center;padding:var(--space-4);background:rgb(15 23 42 / 55%)}.confirm-dialog{width:min(100%,460px);max-height:calc(100dvh - 32px);overflow-y:auto;overscroll-behavior:contain;border-radius:var(--radius-lg);padding:var(--space-6);background:#fff;box-shadow:var(--shadow-drawer)}.confirm-dialog h2{margin:0}.confirm-dialog p{color:var(--color-text-muted)}.dialog-kicker{margin:0 0 var(--space-2);color:var(--color-danger)!important;font-size:.75rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase}.dialog-actions{display:flex;justify-content:flex-end;gap:var(--space-2);margin-top:var(--space-5)}
@media(max-width:640px){.search-row{flex-direction:column}.pagination{align-items:stretch;flex-wrap:wrap;justify-content:flex-start}.dialog-actions>*{flex:1}}
</style>
